"""
ONE-TIME SETUP SCRIPT
=====================
Run this ONCE on your computer to get your OAuth2 refresh token.
After running, paste the output into .streamlit/secrets.toml

Steps before running:
  1. Go to https://console.cloud.google.com
  2. Create project (or use existing)
  3. Enable Google Drive API
  4. Go to: APIs & Services -> Credentials -> Create Credentials -> OAuth 2.0 Client ID
  5. Application type: Desktop App
  6. Download the JSON -> open it and copy client_id and client_secret below

Usage:
  python get_token.py
"""

import json
import os
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request

SCOPES = ["https://www.googleapis.com/auth/drive"]

# ─────────────────────────────────────────────────────────────
# This script will now read from 'new.json' if it exists.
# ─────────────────────────────────────────────────────────────
def load_secrets():
    if os.path.exists("new.json"):
        with open("new.json", "r") as f:
            data = json.load(f)
            if "installed" in data:
                return data["installed"]["client_id"], data["installed"]["client_secret"]
    return None, None

CLIENT_ID, CLIENT_SECRET = load_secrets()
# ─────────────────────────────────────────────────────────────

def main():
    if "PASTE" in CLIENT_ID or "PASTE" in CLIENT_SECRET:
        print("❌ Please open get_token.py and fill in CLIENT_ID and CLIENT_SECRET first!")
        return

    flow = InstalledAppFlow.from_client_config(
        {
            "installed": {
                "client_id": CLIENT_ID,
                "client_secret": CLIENT_SECRET,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": ["http://localhost"]
            }
        },
        scopes=SCOPES
    )

    print("\n>> Opening browser for Google login...")
    print("   -> Sign in with the Google account that OWNS the Drive folder")
    print("   -> Allow all permissions\n")

    creds = flow.run_local_server(
        port=0,
        access_type="offline",
        prompt="consent"          # force refresh token to be issued
    )

    print("\n" + "="*60)
    print("SUCCESS! Copy the section below into:")
    print("   .streamlit/secrets.toml")
    print("="*60)
    print()
    print("[oauth_credentials]")
    print(f'client_id     = "{creds.client_id}"')
    print(f'client_secret = "{creds.client_secret}"')
    print(f'refresh_token = "{creds.refresh_token}"')
    print()
    print("="*60)
    print("After pasting, restart the app and it will upload to YOUR Drive!")

if __name__ == "__main__":
    main()
