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
 *   2. If the email has attachments, uploads them to one Google Drive
 *      folder for that email (reused on retry, never duplicated) and sends
 *      the folder link along. The backend puts that link in the Sheet's
 *      Filename column and on the Supabase record. If Drive fails, the
 *      email is left unlabeled and retried next run (nothing is recorded
 *      without its files). Emails with no attachments are unchanged.
 *      NOTE: using Drive needs a one-time permission approval — after
 *      pasting this version, run processInbox once by hand in the editor
 *      and approve, otherwise the installed trigger will fail to run.
 *   3. For each one, calls the backend's POST /classify-email/ endpoint.
 *      The backend does ALL the heavy lifting: Claude extraction/
 *      classification, the Supabase insert (with the same atomic serial
 *      number scheme as scanned documents), and the DAAK Records Sheets
 *      push. The existing, unmodified syncGrievances() then mirrors
 *      Grievance-category rows into Grievances Data on its own schedule —
 *      this script never writes to any Sheet.
 *   4. Applies a Gmail label reflecting the classification (Grievance /
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

  // Stop starting new threads after this long, so a run never hits Apps
  // Script's 6-minute limit mid-upload. Leftover threads wait for next run.
  RUN_TIME_BUDGET_MS: 5 * 60 * 1000,

  // ---- Email attachments (Google Drive) ----
  // Where attachment folders go. Leave DRIVE_PARENT_FOLDER_ID empty to let
  // the script create (once) a folder called DRIVE_ROOT_FOLDER_NAME in the
  // account's My Drive. Or paste the ID of a folder you created and shared
  // with the staff yourself — new folders inherit its sharing.
  DRIVE_PARENT_FOLDER_ID: '',
  DRIVE_ROOT_FOLDER_NAME: 'MCL Grievance Attachments',

  // true  = each email's folder is "anyone with the link can view" (works
  //         for every staff member; anyone who gets the link can open it).
  // false = leave sharing alone (use with a shared DRIVE_PARENT_FOLDER_ID).
  SHARE_ANYONE_WITH_LINK: true,

  // Pictures pasted INTO the email body (not attached) are "inline images".
  // Ones at least this many bytes are kept (real photos); smaller ones
  // (signature logos, icons, tracking pixels) are skipped.
  // Use -1 to skip all inline images (attachments only).
  INLINE_IMAGE_MIN_BYTES: 51200,

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
  // Only one run at a time: a manual run overlapping the 30-minute trigger
  // could otherwise create two Drive folders for the same email.
  var lock = LockService.getScriptLock();
  if (!lock.tryLock(30 * 1000)) {
    Logger.log('processInbox: another run is still in progress; skipping this one.');
    return;
  }
  try {
    runInbox_();
  } finally {
    lock.releaseLock();
  }
}

function runInbox_() {
  var started = Date.now();
  var env = activeEnv_();

  // Same gate in both environments: only messages carrying INPUT_LABEL are
  // ever considered, since this mailbox has other, unrelated mail in it too.
  var query = 'label:' + CONFIG.INPUT_LABEL +
    ' -label:' + CONFIG.LABEL_PROCESSED +
    ' after:' + CONFIG.PROCESS_AFTER;

  var threads = GmailApp.search(query, 0, CONFIG.BATCH_SIZE);

  Logger.log('processInbox: found ' + threads.length + ' candidate thread(s).');
  logDriveUsage_();

  for (var i = 0; i < threads.length; i++) {
    if (Date.now() - started > CONFIG.RUN_TIME_BUDGET_MS) {
      Logger.log('processInbox: time budget reached; the remaining threads will be handled next run.');
      break;
    }
    processThread_(threads[i], env);
  }
}

function processThread_(thread, env) {
  var messages = thread.getMessages();
  var message = messages[messages.length - 1]; // latest message in the thread

  // Attachments go to Drive BEFORE the backend is called, so a record is
  // never saved without its files. On failure nothing is recorded or
  // labeled; the next run retries and reuses the same Drive folder.
  var attachmentsLink = '';
  try {
    attachmentsLink = uploadAttachments_(message);
  } catch (err) {
    Logger.log('Attachment upload failed for thread "' + thread.getFirstMessageSubject() + '": ' + err);
    return;
  }

  var result;
  try {
    result = callBackend_(message, thread, env, attachmentsLink);
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

function callBackend_(message, thread, env, attachmentsLink) {
  var payload = {
    message_id: message.getId(),
    thread_id: thread.getId(),
    sender: message.getFrom(),
    subject: message.getSubject(),
    body: message.getPlainBody(),
    received_at: message.getDate().toISOString(),
  };
  // Only added when there are attachments, so emails without any send
  // exactly the same request as before.
  if (attachmentsLink) {
    payload.attachments_link = attachmentsLink;
  }

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
// Email attachments -> Google Drive
// =====================================================================

// Returns the Drive folder link for this email's attachments, or '' when
// there is nothing to upload (no folder is created in that case). Safe to
// run again for the same email: the folder and files are reused.
function uploadAttachments_(message) {
  var files = attachmentsToUpload_(message);
  if (files.length === 0) {
    return '';
  }

  var folder = getOrCreateEmailFolder_(getAttachmentsRoot_(), message.getId());

  for (var i = 0; i < files.length; i++) {
    // Numbered prefix: two attachments both called "image.jpg" stay
    // separate, and the same name on a retry means "already uploaded".
    var targetName = pad2_(i + 1) + '_' + (files[i].getName() || 'attachment');
    if (!folder.getFilesByName(targetName).hasNext()) {
      var blob = files[i].copyBlob();
      blob.setName(targetName);
      folder.createFile(blob);
    }
  }

  return folder.getUrl();
}

// Real attachments, plus (optionally) large pictures pasted into the body.
function attachmentsToUpload_(message) {
  var kept = message.getAttachments({ includeInlineImages: false, includeAttachments: true });

  if (CONFIG.INLINE_IMAGE_MIN_BYTES >= 0) {
    var inline = message.getAttachments({ includeInlineImages: true, includeAttachments: false });
    for (var i = 0; i < inline.length; i++) {
      if (inline[i].getSize() >= CONFIG.INLINE_IMAGE_MIN_BYTES) {
        kept.push(inline[i]);
      }
    }
  }

  return kept;
}

function getAttachmentsRoot_() {
  if (CONFIG.DRIVE_PARENT_FOLDER_ID) {
    return DriveApp.getFolderById(CONFIG.DRIVE_PARENT_FOLDER_ID);
  }

  var props = PropertiesService.getScriptProperties();
  var id = props.getProperty('ATTACHMENTS_ROOT_FOLDER_ID');
  if (id) {
    try {
      var existing = DriveApp.getFolderById(id);
      if (!existing.isTrashed()) {
        return existing;
      }
    } catch (err) {
      // The remembered folder was deleted; fall through and create a new one.
    }
  }

  var created = DriveApp.createFolder(CONFIG.DRIVE_ROOT_FOLDER_NAME);
  props.setProperty('ATTACHMENTS_ROOT_FOLDER_ID', created.getId());
  return created;
}

function getOrCreateEmailFolder_(root, messageId) {
  var existing = root.getFoldersByName(messageId);
  var folder = existing.hasNext() ? existing.next() : root.createFolder(messageId);
  if (CONFIG.SHARE_ANYONE_WITH_LINK) {
    folder.setSharing(DriveApp.Access.ANYONE_WITH_LINK, DriveApp.Permission.VIEW);
  }
  return folder;
}

function pad2_(n) {
  return (n < 10 ? '0' : '') + n;
}

// Informational only: Drive on a personal account is 15 GB shared with
// that account's Gmail/Photos, and videos can fill it. Never affects a run.
function logDriveUsage_() {
  try {
    var limit = DriveApp.getStorageLimit();
    var used = DriveApp.getStorageUsed();
    if (limit > 0) {
      Logger.log('Drive storage: ' + (used / 1073741824).toFixed(2) + ' GB used of ' +
        (limit / 1073741824).toFixed(2) + ' GB.');
    }
  } catch (err) {
    // ignore
  }
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
