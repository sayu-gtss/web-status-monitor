import os
from datetime import datetime
from urllib.parse import urlparse
import gspread
from google.oauth2.service_account import Credentials
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

HEADERS = ["Timestamp", "Website URL", "Status Code", "Status Description", "Response Time (ms)", "Speed Rating", "Notification Sent"]

class SheetLogger:
    def __init__(self):
        self.creds_file = os.getenv("GOOGLE_CREDS_FILE", "storage/credentials.json")
        self.sheet_id = os.getenv("GOOGLE_SHEET_ID")
        self.client = None
        self.spreadsheet = None
        # Cache of domain -> worksheet object so we don't look up every time
        self._worksheet_cache = {}
        
        # Initialize Google Sheets
        self.init_google_sheets()
        
    def init_google_sheets(self):
        """Initializes connection to Google Sheets using service account credentials."""
        if not self.sheet_id:
            print("[Logger] GOOGLE_SHEET_ID not configured in .env. Google Sheets logging is disabled.")
            self.spreadsheet = None
            return False
            
        if not os.path.exists(self.creds_file):
            print(f"[Logger] Google credentials file '{self.creds_file}' not found. Google Sheets logging is disabled.")
            self.spreadsheet = None
            return False

        try:
            scopes = [
                'https://www.googleapis.com/auth/spreadsheets',
                'https://www.googleapis.com/auth/drive'
            ]
            credentials = Credentials.from_service_account_file(self.creds_file, scopes=scopes)
            self.client = gspread.authorize(credentials)
            self.spreadsheet = self.client.open_by_key(self.sheet_id)
            self._worksheet_cache = {}
            
            print("[Logger] Connected to Google Sheets successfully.")
            return True
        except Exception as e:
            print(f"[Logger] Failed to connect to Google Sheets: {e}. Heartbeat check cannot be logged online.")
            self.spreadsheet = None
            return False

    def _extract_domain(self, url):
        """Extracts the path/subdomain from a URL for use as a sheet tab name."""
        try:
            parsed = urlparse(url)
            # Use the path (e.g. '/live' -> 'live')
            path = parsed.path.strip('/')
            if not path:
                path = parsed.hostname or url
            return path
        except Exception:
            return "unknown"

    def _get_or_create_worksheet(self, domain):
        """Gets an existing worksheet tab for the domain, or creates a new one with headers."""
        # Check cache first
        if domain in self._worksheet_cache:
            return self._worksheet_cache[domain]
        
        # Search existing worksheets
        try:
            worksheet = self.spreadsheet.worksheet(domain)
            self._worksheet_cache[domain] = worksheet
            return worksheet
        except gspread.exceptions.WorksheetNotFound:
            pass
        
        # Create new worksheet tab for this domain
        try:
            worksheet = self.spreadsheet.add_worksheet(title=domain, rows=1000, cols=len(HEADERS))
            worksheet.append_row(HEADERS)
            self._worksheet_cache[domain] = worksheet
            print(f"[Logger] Created new sheet tab '{domain}' with headers.")
            return worksheet
        except Exception as e:
            print(f"[Logger] Error creating worksheet tab for '{domain}': {e}")
            return None

    def log(self, website_url, status_code, status_desc, response_time_ms, speed_rating, notification_sent):
        """
        Logs a heartbeat check to a domain-specific sheet tab.
        Each unique domain gets its own tab in the spreadsheet.
        """
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        # Format response time nicely, if available
        resp_time_str = f"{response_time_ms:.1f}" if response_time_ms is not None else "N/A"
        
        row = [timestamp, website_url, str(status_code), status_desc, resp_time_str, speed_rating, "Yes" if notification_sent else "No"]
        
        logged_to_sheets = False
        
        if self.spreadsheet:
            domain = self._extract_domain(website_url)
            
            try:
                worksheet = self._get_or_create_worksheet(domain)
                if worksheet:
                    worksheet.append_row(row)
                    logged_to_sheets = True
                    print(f"[Logger] Logged check to Google Sheets [{domain}]: {website_url} (Status: {status_code})")
            except Exception as e:
                print(f"[Logger] Error appending to Google Sheets: {e}. Attempting connection re-init...")
                # Try re-initializing Sheets once
                try:
                    if self.init_google_sheets():
                        worksheet = self._get_or_create_worksheet(domain)
                        if worksheet:
                            worksheet.append_row(row)
                            logged_to_sheets = True
                            print(f"[Logger] Logged check to Google Sheets [{domain}] (after re-init): {website_url} (Status: {status_code})")
                except Exception as re_init_err:
                    print(f"[Logger] Re-init connection failed: {re_init_err}.")
        
        if not logged_to_sheets:
            print(f"[Logger] WARNING: Heartbeat check for {website_url} (Status: {status_code}) could NOT be logged to Google Sheets.")
                
        return logged_to_sheets
