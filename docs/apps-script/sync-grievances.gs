/**
 * sync-grievances.gs
 * ===================
 * Reference copy of the script bound to the DAAK Records spreadsheet
 * (Extensions > Apps Script from DAAK Records). It is NOT deployed from
 * this repo and is NOT part of the Gmail classifier. Keep it in its own
 * project: pasting any other script over it removes syncGrievances().
 *
 * What it does (copied from the live version; logic unchanged):
 *   - Scans every tab of DAAK Records and finds the "Serial Number" and
 *     "category" columns by header text (case-insensitive).
 *   - Keeps rows whose category contains "grievance" (but not
 *     "non-grievance" / "non grievance" / "not a grievance").
 *   - Before touching Grievances Data it remembers each row's STATUS by
 *     Serial Number, rewrites the rows from DAAK Records, then writes each
 *     STATUS back next to the same Serial Number. STATUS typed by staff
 *     therefore survives a sync, even when rows move.
 *
 * Things to know when changing DAAK Records or Grievances Data:
 *   - Rows are copied by POSITION: source column N lands in target column N.
 *     The STATUS column in Grievances Data must therefore sit to the right
 *     of every copied DAAK Records column. If DAAK Records gets another
 *     column and STATUS is in the way, the copied data overwrites STATUS
 *     (the saved statuses are then written back into that column).
 *   - Only STATUS is preserved. Any other column staff type into on
 *     Grievances Data is cleared by each sync.
 *   - Source rows are keyed by "tab name || serial number", so the same
 *     serial number in two tabs produces two rows.
 */

const TARGET_SPREADSHEET_ID = "12deP8F2FKA0WL9q5N_qUzhZeXutMdA54uGiRycYu19k";

function syncGrievances() {

  // =========================================================
  // SOURCE = DAAK-Records spreadsheet
  // =========================================================
  const sourceSpreadsheet = SpreadsheetApp.getActiveSpreadsheet();

  // =========================================================
  // TARGET = Grievances Data spreadsheet
  // =========================================================
  const targetSpreadsheet = SpreadsheetApp.openById(TARGET_SPREADSHEET_ID);
  const targetSheet = targetSpreadsheet.getSheets()[0];

  // =========================================================
  // STEP 1: SAVE EXISTING STATUS
  //
  // SERIAL NUMBER -> STATUS
  // =========================================================
  const oldStatusMap = new Map();
  const oldLastRow = targetSheet.getLastRow();
  const oldLastColumn = targetSheet.getLastColumn();

  if (oldLastRow >= 2 && oldLastColumn >= 1) {
    const oldHeaders = targetSheet.getRange(1, 1, 1, oldLastColumn).getValues()[0];
    const oldSerialColumn = findColumn(oldHeaders, "Serial Number");
    const oldStatusColumn = findColumn(oldHeaders, "STATUS");

    if (oldSerialColumn !== -1 && oldStatusColumn !== -1) {
      const oldData = targetSheet.getRange(2, 1, oldLastRow - 1, oldLastColumn).getValues();

      oldData.forEach(row => {
        const serialNumber = normalizeSerialNumber(row[oldSerialColumn]);
        const status = row[oldStatusColumn];

        if (serialNumber !== "") {
          oldStatusMap.set(serialNumber, status);
        }
      });
    }
  }

  Logger.log("Existing STATUS records saved: " + oldStatusMap.size);

  // =========================================================
  // STEP 2: COLLECT ALL GRIEVANCE DATA
  // =========================================================
  const grievanceMap = new Map();
  const sourceSheets = sourceSpreadsheet.getSheets();

  let totalSourceRows = 0;
  let totalGrievanceRows = 0;
  let totalSkippedRows = 0;

  sourceSheets.forEach(sheet => {
    const sheetName = sheet.getName();
    const lastRow = sheet.getLastRow();
    const lastColumn = sheet.getLastColumn();

    // Ignore empty sheets
    if (lastRow < 2 || lastColumn < 1) {
      Logger.log("Skipping empty sheet: " + sheetName);
      return;
    }

    // =======================================================
    // READ HEADERS
    // =======================================================
    const headers = sheet.getRange(1, 1, 1, lastColumn).getValues()[0];

    // =======================================================
    // FIND REQUIRED COLUMNS
    // =======================================================
    const serialColumn = findColumn(headers, "Serial Number");
    const categoryColumn = findColumn(headers, "category");

    // If required columns do not exist, skip this sheet.
    if (serialColumn === -1 || categoryColumn === -1) {
      Logger.log("Skipping sheet '" + sheetName + "' because Serial Number or category column was not found.");
      return;
    }

    // =======================================================
    // READ DATA
    // =======================================================
    const data = sheet.getRange(2, 1, lastRow - 1, lastColumn).getValues();
    totalSourceRows += data.length;

    let sheetGrievanceCount = 0;

    // =======================================================
    // PROCESS EACH ROW
    // =======================================================
    data.forEach((row, index) => {

      // -----------------------------------------------------
      // SERIAL NUMBER
      // -----------------------------------------------------
      const serialNumber = normalizeSerialNumber(row[serialColumn]);

      // -----------------------------------------------------
      // CATEGORY
      // -----------------------------------------------------
      const category = normalizeCategory(row[categoryColumn]);

      // -----------------------------------------------------
      // IGNORE ROWS WITHOUT SERIAL NUMBER
      // -----------------------------------------------------
      if (serialNumber === "") {
        totalSkippedRows++;
        return;
      }

      // -----------------------------------------------------
      // ONLY GRIEVANCES
      // -----------------------------------------------------
      if (!isGrievanceCategory(category)) {
        totalSkippedRows++;
        return;
      }

      sheetGrievanceCount++;
      totalGrievanceRows++;

      // =====================================================
      // STORE RECORD
      // =====================================================
      const uniqueKey = sheetName + "||" + serialNumber;

      grievanceMap.set(uniqueKey, {
        serialNumber: serialNumber,
        row: row,
        sheetName: sheetName
      });
    });

    Logger.log("Sheet: " + sheetName + " | Source rows: " + data.length + " | Grievances: " + sheetGrievanceCount);
  });

  // =========================================================
  // STEP 3: CONVERT MAP TO ROWS
  // =========================================================
  const grievanceRecords = Array.from(grievanceMap.values());

  Logger.log("Total source rows: " + totalSourceRows);
  Logger.log("Total grievance records: " + grievanceRecords.length);
  Logger.log("Total skipped rows: " + totalSkippedRows);

  // =========================================================
  // STEP 4: CLEAR OLD DATA
  // =========================================================
  const targetLastRow = targetSheet.getLastRow();
  const targetLastColumn = Math.max(targetSheet.getLastColumn(), 1);

  if (targetLastRow > 1) {
    targetSheet.getRange(2, 1, targetLastRow - 1, targetLastColumn).clearContent();
  }

  // =========================================================
  // STEP 5: DETERMINE TARGET HEADERS & STATUS COLUMN
  // =========================================================
  let currentLastColumn = targetSheet.getLastColumn();
  if (currentLastColumn < 1) {
    currentLastColumn = 1;
  }

  let currentHeaders = targetSheet.getRange(1, 1, 1, currentLastColumn).getValues()[0];

  let statusColumn = findColumn(currentHeaders, "STATUS");
  if (statusColumn === -1) {
    statusColumn = currentLastColumn;
    targetSheet.getRange(1, statusColumn + 1).setValue("STATUS");
    currentLastColumn = statusColumn + 1;
    currentHeaders = targetSheet.getRange(1, 1, 1, currentLastColumn).getValues()[0];
  }

  // =========================================================
  // STEP 6: WRITE FRESH GRIEVANCE DATA
  // =========================================================
  if (grievanceRecords.length === 0) {
    Logger.log("No grievance records found.");
    Logger.log("Sync completed.");
    return;
  }

  // Find the maximum number of columns across ALL source sheets
  let maxSourceColumns = 0;
  grievanceRecords.forEach(record => {
    if (record.row.length > maxSourceColumns) {
      maxSourceColumns = record.row.length;
    }
  });

  // Ensure target sheet has enough columns
  const requiredColumns = Math.max(maxSourceColumns, statusColumn + 1);
  const existingMaxColumns = targetSheet.getMaxColumns();

  if (existingMaxColumns < requiredColumns) {
    targetSheet.insertColumnsAfter(existingMaxColumns, requiredColumns - existingMaxColumns);
  }

  // NORMALIZE ROWS: Pad all rows so they are exactly the same length
  const grievanceRows = grievanceRecords.map(record => {
    const rowCopy = record.row.slice();
    while (rowCopy.length < maxSourceColumns) {
      rowCopy.push("");
    }
    return rowCopy;
  });

  // Write all rows at once securely
  targetSheet
    .getRange(2, 1, grievanceRows.length, maxSourceColumns)
    .setValues(grievanceRows);

  // =========================================================
  // STEP 7: FIND SERIAL NUMBER COLUMN IN TARGET
  // =========================================================
  currentLastColumn = Math.max(targetSheet.getLastColumn(), requiredColumns);
  currentHeaders = targetSheet.getRange(1, 1, 1, currentLastColumn).getValues()[0];

  const currentSerialColumn = findColumn(currentHeaders, "Serial Number");
  if (currentSerialColumn === -1) {
    throw new Error("Serial Number column not found in target sheet.");
  }

  // =========================================================
  // STEP 8: RESTORE STATUS
  // =========================================================
  const statusValues = [];
  const newData = targetSheet.getRange(2, 1, grievanceRows.length, maxSourceColumns).getValues();

  newData.forEach(row => {
    const serialNumber = normalizeSerialNumber(row[currentSerialColumn]);

    if (serialNumber !== "" && oldStatusMap.has(serialNumber)) {
      statusValues.push([oldStatusMap.get(serialNumber)]);
    } else {
      statusValues.push([""]); // New grievance
    }
  });

  targetSheet
    .getRange(2, statusColumn + 1, statusValues.length, 1)
    .setValues(statusValues);

  // =========================================================
  // STEP 9: FINAL LOGGING
  // =========================================================
  let restoredStatusCount = 0;
  statusValues.forEach(value => {
    if (value[0] !== "" && value[0] !== null) {
      restoredStatusCount++;
    }
  });

  Logger.log("========================================");
  Logger.log("SYNC COMPLETED SUCCESSFULLY");
  Logger.log("Total source rows: " + totalSourceRows);
  Logger.log("Total grievance records: " + grievanceRecords.length);
  Logger.log("STATUS values restored: " + restoredStatusCount);
  Logger.log("New grievances: " + (grievanceRecords.length - restoredStatusCount));
  Logger.log("========================================");
}

/**
 * =========================================================
 * HELPER FUNCTIONS
 * =========================================================
 */
function findColumn(headers, columnName) {
  const target = normalizeHeader(columnName);
  for (let i = 0; i < headers.length; i++) {
    const header = normalizeHeader(headers[i]);
    if (header === target) {
      return i;
    }
  }
  return -1;
}

function normalizeHeader(value) {
  return String(value === null || value === undefined ? "" : value)
    .trim()
    .replace(/\s+/g, " ")
    .toLowerCase();
}

function normalizeSerialNumber(value) {
  if (value === null || value === undefined) {
    return "";
  }
  return String(value).trim();
}

function normalizeCategory(value) {
  if (value === null || value === undefined) {
    return "";
  }
  return String(value)
    .trim()
    .replace(/\s+/g, " ")
    .toLowerCase();
}

function isGrievanceCategory(category) {
  if (!category) return false;
  if (category.includes("non-grievance") || category.includes("non grievance") || category.includes("not a grievance")) {
    return false;
  }
  return category.includes("grievance");
}
