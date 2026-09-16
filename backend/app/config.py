from dotenv import load_dotenv
import os
try:
    from supabase import create_client, Client
except ImportError:
    create_client = None
    Client = None
try:
    import anthropic
except ImportError:
    anthropic = None
try:
    from google import genai
except ImportError:
    genai = None

# Load environment variables
load_dotenv()


GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
gemini_client = None
if genai and GEMINI_API_KEY:
    gemini_client = genai.Client(api_key=GEMINI_API_KEY)

# ==========================
# Anthropic Claude
# ==========================


ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
anthropic_client = None
if anthropic and ANTHROPIC_API_KEY:
    anthropic_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

# ==========================
# Supabase
# ==========================


SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
supabase_client=None
if create_client and SUPABASE_URL and SUPABASE_KEY:
    supabase_client = create_client(SUPABASE_URL, SUPABASE_KEY)

# ==========================
# Google Sheets & Drive
# ==========================

GOOGLE_SHEET_ID = os.getenv("GOOGLE_SHEET_ID")
GOOGLE_DRIVE_FOLDER_ID = os.getenv("GOOGLE_DRIVE_FOLDER_ID")

# ==========================
# Google Apps Script Sheets
# ==========================
SHEETS_WEBHOOK_URL = os.getenv("SHEETS_WEBHOOK_URL")
SHEETS_SECRET = os.getenv("SHEETS_SECRET")

# ==========================
# Gmail API (OAuth 2.0)
# ==========================
GMAIL_USER = os.getenv("GMAIL_USER")
GMAIL_CREDENTIALS_FILE = os.getenv("GMAIL_CREDENTIALS_FILE", "credentials.json")
GMAIL_TOKEN_FILE = os.getenv("GMAIL_TOKEN_FILE", "token.json")
# Poll interval in seconds (default 60 minutes)
EMAIL_POLL_INTERVAL = int(os.getenv("EMAIL_POLL_INTERVAL", "3600"))
# Overlap in minutes subtracted from last_successful_sync to avoid gaps
GMAIL_SYNC_OVERLAP_MINUTES = int(os.getenv("GMAIL_SYNC_OVERLAP_MINUTES", "5"))
