import os
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = [
    'https://www.googleapis.com/auth/gmail.readonly',
    'https://www.googleapis.com/auth/drive'
]

def main():
    creds_file = 'credentials.json'
    token_file = 'token.json'
    
    if not os.path.exists(creds_file):
        print(f"Error: {creds_file} not found in the current directory.")
        print("Please place the OAuth 2.0 Client ID JSON file here and name it 'credentials.json'.")
        return

    print("Starting OAuth 2.0 authorization flow...")
    flow = InstalledAppFlow.from_client_secrets_file(creds_file, SCOPES)
    creds = flow.run_local_server(port=0)
    
    with open(token_file, 'w') as token:
        token.write(creds.to_json())
        
    print(f"Success! Authorization complete. Credentials saved to {token_file}.")
    print("You can now run your FastAPI server.")

if __name__ == '__main__':
    main()
