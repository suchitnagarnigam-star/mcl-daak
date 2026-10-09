import logging
logging.basicConfig(level=logging.INFO)

from app.services.google_service import fetch_gmail_attachments, create_drive_folder, upload_to_drive

msg_id = '1a0c79f6fe257586'
print(f"Fetching attachments for {msg_id}...")
att = fetch_gmail_attachments(msg_id)
print(f"Attachments found: {len(att)}")

if att:
    for a in att:
        print(f" - {a['filename']} ({a['mimeType']})")
    
    print("Creating folder...")
    fid, flink = create_drive_folder("DEBUG_FOLDER_MCL_TEST")
    print(f"Folder ID: {fid}, Link: {flink}")
    
    if fid:
        print("Uploading to Drive...")
        success = upload_to_drive(fid, att)
        print(f"Upload success: {success}")
