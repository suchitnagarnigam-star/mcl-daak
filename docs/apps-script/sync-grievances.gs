/**
 * sync-grievances.gs
 * ===================
 * Reference copy only — pasted verbatim from the user's existing,
 * already-deployed Apps Script. This script is bound to the DAAK Records
 * spreadsheet (SpreadsheetApp.getActiveSpreadsheet() is DAAK Records
 * itself) and already runs in production.
 *
 * It is NOT modified, executed, or deployed by this feature. It is kept
 * here purely so the Gmail grievance classifier's design can be checked
 * against its actual behavior:
 *   - Scans every tab/sheet in DAAK Records.
 *   - Finds columns named "Serial Number" and "category" by header text
 *     (case-insensitive); skips any tab missing either.
 *   - Keeps rows whose category (lowercased) contains "grievance".
 *   - De-dupes by Serial Number (last write wins).
 *   - CLEARS rows 2+ in Grievances Data's first tab, then rewrites them
 *     from scratch every run.
 *
 * Because of the clear-and-rewrite behavior, nothing should ever write to
 * Grievances Data directly — any such row would be wiped on the next run
 * of this script unless it also exists in DAAK Records with a matching
 * Serial Number. This is why the Gmail grievance classifier only ever
 * writes to DAAK Records (via the existing backend -> Supabase -> Sheets
 * webhook path) and never touches Grievances Data itself.
 */

const TARGET_SPREADSHEET_ID =
  "12deP8F2FKA0WL9q5N_qUzhZeXutMdA54uGiRycYu19k";


function syncGrievances() {

  // Source = the DAAK-Records spreadsheet
  const sourceSpreadsheet =
    SpreadsheetApp.getActiveSpreadsheet();

  // Destination = separate Grievances Data spreadsheet
  const targetSpreadsheet =
    SpreadsheetApp.openById(TARGET_SPREADSHEET_ID);

  // Use the first tab in Grievances Data
  const targetSheet =
    targetSpreadsheet.getSheets()[0];


  // This will hold one row per Serial Number
  const grievanceMap = new Map();


  // Get every sheet/tab inside DAAK-Records
  const sourceSheets =
    sourceSpreadsheet.getSheets();


  sourceSheets.forEach(sheet => {

    const lastRow = sheet.getLastRow();
    const lastColumn = sheet.getLastColumn();

    // Ignore empty sheets
    if (lastRow < 2 || lastColumn < 1) {
      return;
    }


    // Read headers
    const headers =
      sheet
        .getRange(1, 1, 1, lastColumn)
        .getValues()[0];


    // Find the Serial Number column
    const serialColumn =
      findColumn(headers, "Serial Number");


    // Find the category column
    const categoryColumn =
      findColumn(headers, "category");


    // If this isn't a DAAK data sheet, skip it
    if (
      serialColumn === -1 ||
      categoryColumn === -1
    ) {
      return;
    }


    // Read all rows
    const data =
      sheet
        .getRange(2, 1, lastRow - 1, lastColumn)
        .getValues();


    data.forEach(row => {

      const serialNumber =
        String(row[serialColumn]).trim();

      const category =
        String(row[categoryColumn])
          .trim()
          .toLowerCase();


      // Ignore rows without Serial Number
      if (!serialNumber) {
        return;
      }


      // Only include categories containing "grievance"
      //
      // Examples that WILL be included:
      // Grievance
      // Public Grievance
      // PUBLIC GRIEVANCE
      //
      // Examples that WON'T:
      // General Correspondence
      // Legal & Court Cases
      // Inter-Department
      //
      if (!category.includes("grievance")) {
        return;
      }


      /*
       * Serial Number is our unique identifier.
       *
       * If the same Serial Number occurs more than once,
       * only one copy will be kept.
       */
      grievanceMap.set(serialNumber, row);

    });

  });


  // Convert our Map into rows
  const grievanceRows =
    Array.from(grievanceMap.values());


  // --------------------------------------------------
  // CLEAR OLD DATA
  // --------------------------------------------------

  const targetLastRow =
    targetSheet.getLastRow();

  const targetLastColumn =
    Math.max(targetSheet.getLastColumn(), 12);


  if (targetLastRow > 1) {

    targetSheet
      .getRange(
        2,
        1,
        targetLastRow - 1,
        targetLastColumn
      )
      .clearContent();

  }


  // --------------------------------------------------
  // WRITE CURRENT GRIEVANCE DATA
  // --------------------------------------------------

  if (grievanceRows.length > 0) {

    const numberOfColumns =
      grievanceRows[0].length;


    targetSheet
      .getRange(
        2,
        1,
        grievanceRows.length,
        numberOfColumns
      )
      .setValues(grievanceRows);

  }


  Logger.log(
    "Sync completed. Grievances found: " +
    grievanceRows.length
  );
}


/**
 * Finds a column by its header name.
 */
function findColumn(headers, columnName) {

  const target =
    columnName.trim().toLowerCase();


  for (let i = 0; i < headers.length; i++) {

    if (
      String(headers[i])
        .trim()
        .toLowerCase() === target
    ) {
      return i;
    }

  }


  return -1;
}
