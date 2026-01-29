#!/usr/bin/env python3
"""
One-time OAuth setup script for Google Calendar integration.

Run this ONCE on a machine with a browser (e.g., your Mac):
    python3 setup-google-auth.py

This will:
1. Open your browser for Google authentication
2. Create token.json with your OAuth refresh token
3. Copy token.json to your Pi (~/token.json)

Prerequisites:
1. Create a Google Cloud project
2. Enable Google Calendar API
3. Create OAuth 2.0 credentials (Desktop app type)
4. Download credentials.json to this directory
"""

import os
import sys

try:
    from google_auth_oauthlib.flow import InstalledAppFlow
except ImportError:
    print("Missing dependencies. Install with:")
    print("  pip3 install google-auth-oauthlib")
    sys.exit(1)

SCOPES = ["https://www.googleapis.com/auth/calendar.readonly"]
CREDENTIALS_FILE = "credentials.json"
TOKEN_FILE = "token.json"


def main():
    if not os.path.exists(CREDENTIALS_FILE):
        print(f"Error: {CREDENTIALS_FILE} not found!")
        print()
        print("To get credentials.json:")
        print("1. Go to https://console.cloud.google.com/")
        print("2. Create or select a project")
        print("3. Enable 'Google Calendar API'")
        print("4. Go to Credentials > Create Credentials > OAuth client ID")
        print("5. Select 'Desktop app' as application type")
        print("6. Download the JSON and save as credentials.json")
        sys.exit(1)

    print("Starting OAuth flow...")
    print("A browser window will open for Google authentication.")
    print()

    flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
    creds = flow.run_local_server(port=0)

    with open(TOKEN_FILE, "w") as f:
        f.write(creds.to_json())

    print()
    print(f"Success! Token saved to {TOKEN_FILE}")
    print()
    print("Next steps:")
    print(f"1. Copy {TOKEN_FILE} to your Pi:")
    print(f"   scp {TOKEN_FILE} pi@<your-pi-ip>:~/token.json")
    print("2. Set permissions: ssh pi@<your-pi-ip> 'chmod 600 ~/token.json'")
    print("3. Restart screen-server.py on the Pi")


if __name__ == "__main__":
    main()
