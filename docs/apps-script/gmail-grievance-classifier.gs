/**
 * Gmail Grievance Classifier
 * ==========================
 * Standalone Google Apps Script — NOT part of the existing OCR Apps Script
 * deployment (the one bound to the DAAK Records spreadsheet that runs
 * syncGrievances()). This script never touches DAAK Records or Grievances
 * Data directly — it only talks to Gmail and to the backend.
 *
 * What it does, once configured and running:
 *   1. Searches for messages that carry CONFIG.INPUT_LABEL, received after
 *      CONFIG.PROCESS_AFTER, that don't yet have the "processed" label. The
 *      mailbox this runs against also receives unrelated mail, so ONLY
 *      labeled messages are ever touched — in prod, a Gmail filter applies
 *      INPUT_LABEL automatically to mail forwarded from the known office
 *      address; in test, you apply it by hand to deliberate test emails.
 *   2. For each one, calls the backend's POST /classify-email/ endpoint.
 *      The backend does ALL the heavy lifting: Claude extraction/
 *      classification, the Supabase insert (with the same atomic serial
 *      number scheme as scanned documents), and the DAAK Records Sheets
 *      push. The existing, unmodified syncGrievances() then mirrors
 *      Grievance-category rows into Grievances Data on its own schedule —
 *      this script never writes to any Sheet.
 *   3. Applies a Gmail label reflecting the classification (Grievance /
 *      Non-Grievance) and marks the thread "processed" — but ONLY once the
 *      backend confirms the record was fully persisted (HTTP 200). A
 *      failure leaves the thread unlabeled so the next run retries it;
 *      the backend's own message_id-based deduplication guarantees a
 *      retry can never create a duplicate record.
 */

// =====================================================================
// CONFIG — everything environment-specific lives here. Switching between
// a test Gmail account/backend and the real office inbox/backend later is
// a one-line change (CONFIG.ENV), not a code change.
//
// NOTE: which Gmail account this script reads from is determined by
// whoever authorizes it when it's first run in the Apps Script editor —
// that part cannot be toggled by config, only by re-authorizing the
// script under a different account.
// =====================================================================

var CONFIG = {
  // Set to 'test' while testing against a throwaway Gmail account/backend.
  // Flip to 'prod' once ready to point at the real office inbox/backend.
  ENV: 'test',

  ENVIRONMENTS: {
    test: {
      BACKEND_URL: 'https://mcl-ocr.onrender.com/classify-email/', // dev/test backend
    },
    prod: {
      BACKEND_URL: 'https://mcl-daak.onrender.com/classify-email/', // prod backend
    },
  },

  // Must match the backend's EMAIL_WEBHOOK_SECRET env var exactly.
  BACKEND_SECRET: 'PUT_SHARED_SECRET_HERE',

  LABEL_GRIEVANCE: 'Grievance',
  LABEL_OTHER: 'Non-Grievance',
  LABEL_PROCESSED: 'AutoClassified',

  // The mailbox this runs against receives OTHER mail too, not just the
  // forwarded office correspondence — so this script only ever touches
  // messages carrying INPUT_LABEL, in both environments:
  //   - In prod: a Gmail FILTER (set up once, outside this script) watches
  //     for mail from the known forwarding address and applies this label
  //     automatically. Nothing else in the inbox is ever touched, and no
  //     one has to manually label anything for day-to-day operation.
  //   - In test: you apply this label by hand to deliberate test emails.
  INPUT_LABEL: 'MCL-Grievance-Input',

  // Only messages received on/after this date are ever considered.
  // Format: 'YYYY/MM/DD'. Nothing before this date is touched, ever,
  // regardless of labels — change deliberately if a backfill is wanted.
  PROCESS_AFTER: '2026/09/16',

  // How many threads to process per run (keeps each run fast/cheap).
  BATCH_SIZE: 50,

  // Minutes between automatic runs once the trigger is installed via
  // installTrigger(). Manual runs (Run > processInbox) work regardless
  // of whether a trigger exists.
  TRIGGER_INTERVAL_MINUTES: 30,
};

function activeEnv_() {
  return CONFIG.ENVIRONMENTS[CONFIG.ENV];
}

// =====================================================================
// MAIN ENTRY POINT — safe to run manually from the editor at any time.
// =====================================================================

function processInbox() {
  var env = activeEnv_();

  // Same gate in both environments: only messages carrying INPUT_LABEL are
  // ever considered, since this mailbox has other, unrelated mail in it too.
  var query = 'label:' + CONFIG.INPUT_LABEL +
    ' -label:' + CONFIG.LABEL_PROCESSED +
    ' after:' + CONFIG.PROCESS_AFTER;

  var threads = GmailApp.search(query, 0, CONFIG.BATCH_SIZE);

  Logger.log('processInbox: found ' + threads.length + ' candidate thread(s).');

  for (var i = 0; i < threads.length; i++) {
    processThread_(threads[i], env);
  }
}

function processThread_(thread, env) {
  var messages = thread.getMessages();
  var message = messages[messages.length - 1]; // latest message in the thread

  var result;
  try {
    result = callBackend_(message, thread, env);
  } catch (err) {
    Logger.log('Backend call failed for thread "' + thread.getFirstMessageSubject() + '": ' + err);
    return; // no labels applied — retried on the next run, safely (backend dedupes by message_id)
  }

  var categoryLabelName = result.is_grievance ? CONFIG.LABEL_GRIEVANCE : CONFIG.LABEL_OTHER;
  thread.addLabel(getOrCreateLabel_(categoryLabelName));
  thread.addLabel(getOrCreateLabel_(CONFIG.LABEL_PROCESSED));
}

// =====================================================================
// Backend call — the backend owns classification, Supabase insert, and
// the DAAK Records Sheets push. This script only reports success/failure.
// =====================================================================

function callBackend_(message, thread, env) {
  var payload = {
    message_id: message.getId(),
    thread_id: thread.getId(),
    sender: message.getFrom(),
    subject: message.getSubject(),
    body: message.getPlainBody(),
    received_at: message.getDate().toISOString(),
  };

  var response = UrlFetchApp.fetch(env.BACKEND_URL, {
    method: 'post',
    contentType: 'application/json',
    headers: { 'X-Email-Webhook-Secret': CONFIG.BACKEND_SECRET },
    payload: JSON.stringify(payload),
    muteHttpExceptions: true,
  });

  var code = response.getResponseCode();
  if (code !== 200) {
    throw new Error('Backend returned ' + code + ': ' + response.getContentText());
  }

  return JSON.parse(response.getContentText());
}

// =====================================================================
// Label helper
// =====================================================================

function getOrCreateLabel_(name) {
  var label = GmailApp.getUserLabelByName(name);
  if (!label) {
    label = GmailApp.createLabel(name);
  }
  return label;
}

// =====================================================================
// One-time trigger setup — run manually ONCE from the editor after
// testing is done. Removes any existing processInbox trigger first so
// re-running this doesn't create duplicates.
// =====================================================================

function installTrigger() {
  var triggers = ScriptApp.getProjectTriggers();
  for (var i = 0; i < triggers.length; i++) {
    if (triggers[i].getHandlerFunction() === 'processInbox') {
      ScriptApp.deleteTrigger(triggers[i]);
    }
  }
  ScriptApp.newTrigger('processInbox')
    .timeBased()
    .everyMinutes(CONFIG.TRIGGER_INTERVAL_MINUTES)
    .create();
  Logger.log('Installed processInbox trigger every ' + CONFIG.TRIGGER_INTERVAL_MINUTES + ' minutes.');
}

function removeTrigger() {
  var triggers = ScriptApp.getProjectTriggers();
  for (var i = 0; i < triggers.length; i++) {
    if (triggers[i].getHandlerFunction() === 'processInbox') {
      ScriptApp.deleteTrigger(triggers[i]);
    }
  }
  Logger.log('Removed processInbox trigger(s), if any.');
}
