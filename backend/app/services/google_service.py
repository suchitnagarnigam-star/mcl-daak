import os
import io
import base64
import logging
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
from googleapiclient.errors import HttpError

from app.config import GOOGLE_SERVICE_ACCOUNT_FILE, GOOGLE_DRIVE_PARENT_FOLDER_ID

logger = logging.getLogger(__name__)

SCOPES = [
    'https://www.googleapis.com/auth/gmail.readonly',
    'https://www.googleapis.com/auth/drive'
]

def get_credentials():
    """Load and return Google credentials."""
    creds = None
    token_path = os.path.join(os.path.dirname(GOOGLE_SERVICE_ACCOUNT_FILE), 'token.json')
    
    if os.path.exists(token_path):
        creds = Credentials.from_authorized_user_file(token_path, SCOPES)
    
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except Exception as e:
                logger.error(f"Error refreshing Google credentials: {e}")
                creds = None
        
        if not creds:
            if not os.path.exists(GOOGLE_SERVICE_ACCOUNT_FILE):
                logger.warning(f"Google credentials file not found: {GOOGLE_SERVICE_ACCOUNT_FILE}")
                return None
            
            logger.error("token.json not found or invalid. Please run 'python generate_token.py' locally to authorize.")
            return None
            
    return creds


def fetch_gmail_attachments(message_id: str):
    """
    Fetch a Gmail message by its message_id (which is not necessarily the 'id' but might be RFC822 msg ID).
    Wait, the Gmail API messages.get requires the internal Gmail 'id'.
    If we have the internal id, we can fetch directly. If it's the Message-ID header, we need to search first.
    Assuming message_id passed from webhook is the internal Gmail 'id'.
    Returns a list of dictionaries with 'filename', 'mimeType', and 'data' (bytes).
    """
    creds = get_credentials()
    if not creds:
        return []

    try:
        service = build('gmail', 'v1', credentials=creds)
        # Search by RFC822 Message-ID first if needed, but assuming message_id is internal id
        try:
            # Attempt to get the message directly
            message = service.users().messages().get(userId='me', id=message_id).execute()
        except HttpError as e:
            if e.resp.status == 404:
                # Fallback to search if the ID was actually the RFC822 Message-ID
                results = service.users().messages().list(userId='me', q=f"rfc822msgid:{message_id}").execute()
                messages = results.get('messages', [])
                if not messages:
                    logger.error(f"Gmail message not found for ID: {message_id}")
                    return []
                message = service.users().messages().get(userId='me', id=messages[0]['id']).execute()
            else:
                raise e
        
        attachments = []
        parts = message.get('payload', {}).get('parts', [])
        
        # Simple recursive function to find all attachments in parts
        def find_attachments(parts_list):
            for part in parts_list:
                if part.get('filename') and part.get('body', {}).get('attachmentId'):
                    attachments.append({
                        'filename': part['filename'],
                        'mimeType': part['mimeType'],
                        'attachmentId': part['body']['attachmentId'],
                        'message_id': message['id']
                    })
                if part.get('parts'):
                    find_attachments(part['parts'])
                    
        find_attachments(parts)
        
        downloaded_attachments = []
        for att in attachments:
            attachment_obj = service.users().messages().attachments().get(
                userId='me', messageId=att['message_id'], id=att['attachmentId']
            ).execute()
            data = attachment_obj.get('data')
            if data:
                file_data = base64.urlsafe_b64decode(data.encode('UTF-8'))
                downloaded_attachments.append({
                    'filename': att['filename'],
                    'mimeType': att['mimeType'],
                    'data': file_data
                })
                
        return downloaded_attachments
        
    except Exception as e:
        logger.error(f"Error fetching Gmail attachments for {message_id}: {e}")
        return []

def create_drive_folder(folder_name: str) -> tuple[str, str]:
    """
    Create a Google Drive folder and return (folder_id, folder_link).
    """
    creds = get_credentials()
    if not creds:
        return None, None

    try:
        service = build('drive', 'v3', credentials=creds)
        file_metadata = {
            'name': folder_name,
            'mimeType': 'application/vnd.google-apps.folder'
        }
        if GOOGLE_DRIVE_PARENT_FOLDER_ID:
            file_metadata['parents'] = [GOOGLE_DRIVE_PARENT_FOLDER_ID]
            
        folder = service.files().create(
            body=file_metadata, 
            fields='id, webViewLink'
        ).execute()
        
        return folder.get('id'), folder.get('webViewLink')
        
    except Exception as e:
        logger.error(f"Error creating Drive folder {folder_name}: {e}")
        return None, None

def upload_to_drive(folder_id: str, attachments: list) -> bool:
    """
    Upload a list of attachments to a specific Google Drive folder.
    attachments: list of dicts with 'filename', 'mimeType', and 'data' (bytes).
    """
    if not folder_id or not attachments:
        return False
        
    creds = get_credentials()
    if not creds:
        return False
        
    try:
        service = build('drive', 'v3', credentials=creds)
        
        for att in attachments:
            file_metadata = {
                'name': att['filename'],
                'parents': [folder_id]
            }
            media = MediaIoBaseUpload(
                io.BytesIO(att['data']), 
                mimetype=att['mimeType'], 
                resumable=True
            )
            service.files().create(
                body=file_metadata, 
                media_body=media, 
                fields='id'
            ).execute()
            
        return True
    except Exception as e:
        logger.error(f"Error uploading to Drive folder {folder_id}: {e}")
        return False
