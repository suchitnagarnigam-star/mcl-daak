"""
One-time OAuth 2.0 token generation script.

Run this ONCE from the backend/ directory to generate token.json:

    cd backend
    python generate_token.py

A browser window will open asking you to log in with the Gmail account
configured in GMAIL_USER (.env). After granting access, token.json is
written to the current directory and the script exits.

The token contains a long-lived refresh token, so the server can
re-authenticate automatically without user intervention going forward.

Prerequisites
-------------
1. Download credentials.json from Google Cloud Console:
   - Go to https://console.cloud.google.com/
   - APIs & Services → Credentials → Create Credentials → OAuth 2.0 Client ID
   - Application type: Desktop App
   - Download as credentials.json and place it in backend/

2. Enable the Gmail API:
   - APIs & Services → Library → search "Gmail API" → Enable

3. Add your Gmail address as a Test User (while app is in testing mode):
   - APIs & Services → OAuth consent screen → Test users → Add users
"""

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

# Load .env so GMAIL_CREDENTIALS_FILE / GMAIL_TOKEN_FILE are available
load_dotenv()

GMAIL_CREDENTIALS_FILE = os.getenv("GMAIL_CREDENTIALS_FILE", "credentials.json")
GMAIL_TOKEN_FILE = os.getenv("GMAIL_TOKEN_FILE", "token.json")
GMAIL_SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]


def main():
    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
    except ImportError:
        print(
            "ERROR: Required packages not installed.\n"
            "Run: pip install google-api-python-client google-auth-oauthlib google-auth-httplib2"
        )
        sys.exit(1)

    creds_path = Path(GMAIL_CREDENTIALS_FILE)
    token_path = Path(GMAIL_TOKEN_FILE)

    if not creds_path.exists():
        print(
            f"ERROR: credentials.json not found at: {creds_path.resolve()}\n\n"
            "Steps to create it:\n"
            "  1. Go to https://console.cloud.google.com/\n"
            "  2. APIs & Services → Credentials → Create Credentials → OAuth 2.0 Client ID\n"
            "  3. Choose 'Desktop App' as the application type\n"
            "  4. Download the JSON and save it as credentials.json in the backend/ directory\n"
        )
        sys.exit(1)

    creds = None

    # Check for an existing token
    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), GMAIL_SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            print("Existing token expired. Refreshing...")
            creds.refresh(Request())
        else:
            print(
                "\n=== Gmail OAuth 2.0 Setup ===\n"
                "A browser window will open. Log in with your Gmail account\n"
                f"and grant read access. token.json will be saved to: {token_path.resolve()}\n"
            )
            flow = InstalledAppFlow.from_client_secrets_file(str(creds_path), GMAIL_SCOPES)
            # port=0 lets the OS pick a free port automatically
            creds = flow.run_local_server(port=0, prompt="consent", access_type="offline")

        # Save the credentials for next run
        token_path.write_text(creds.to_json())
        print(f"\n✅ token.json saved to: {token_path.resolve()}")
    else:
        print(f"✅ Existing token is still valid. No action needed. ({token_path.resolve()})")

    print("\nYou can now start the server normally. The token will auto-refresh when needed.")


if __name__ == "__main__":
    main()
