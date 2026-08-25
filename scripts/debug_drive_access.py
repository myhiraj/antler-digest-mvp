"""
One-off diagnostic for the digest_drive_writer 404 on files.create. Runs
three isolated Drive API calls against the real service account credentials
and reports exactly which one fails and why, instead of guessing further.

    python scripts/debug_drive_access.py
"""
import io
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

import json

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaIoBaseUpload

from app.config import settings

_SCOPES = ["https://www.googleapis.com/auth/drive"]


def _step(name):
    print(f"\n--- {name} ---")


def main() -> None:
    if not settings.google_service_account_json or not settings.google_drive_folder_id:
        print("GOOGLE_SERVICE_ACCOUNT_JSON or GOOGLE_DRIVE_FOLDER_ID not set. Aborting.")
        return

    creds_info = json.loads(settings.google_service_account_json)
    print(f"Service account: {creds_info.get('client_email')}")
    print(f"Target drive ID (GOOGLE_DRIVE_FOLDER_ID): {settings.google_drive_folder_id}")

    credentials = service_account.Credentials.from_service_account_info(creds_info, scopes=_SCOPES)
    service = build("drive", "v3", credentials=credentials, cache_discovery=False)

    _step("1. files.get on the drive ID (is it reachable as a Shared Drive?)")
    try:
        result = service.files().get(
            fileId=settings.google_drive_folder_id,
            supportsAllDrives=True,
            fields="id, name, mimeType, driveId",
        ).execute()
        print("OK:", result)
    except HttpError as e:
        print("FAILED:", e)

    _step("1b. drives.get on the drive ID (is it reachable as a Shared Drive's own root?)")
    try:
        result = service.drives().get(driveId=settings.google_drive_folder_id).execute()
        print("OK:", result)
    except HttpError as e:
        print("FAILED:", e)

    _step("2. files.list with driveId scoped to this drive (list up to 5 items at root)")
    try:
        result = service.files().list(
            q=f"'{settings.google_drive_folder_id}' in parents and trashed = false",
            fields="files(id, name)",
            pageSize=5,
            supportsAllDrives=True,
            includeItemsFromAllDrives=True,
            corpora="drive",
            driveId=settings.google_drive_folder_id,
        ).execute()
        print("OK:", result.get("files"))
    except HttpError as e:
        print("FAILED:", e)

    _step("3. files.create — tiny test text file at the drive root")
    try:
        media = MediaIoBaseUpload(io.BytesIO(b"debug_drive_access test file"), mimetype="text/plain")
        created = service.files().create(
            body={"name": "_debug_drive_access_test", "parents": [settings.google_drive_folder_id]},
            media_body=media,
            fields="id, name, parents",
            supportsAllDrives=True,
        ).execute()
        print("OK:", created)
        print("\nCreated a real test file — remember to delete '_debug_drive_access_test' from Drive when done.")
    except HttpError as e:
        print("FAILED:", e)
        print("\nFull error content:", e.content)


if __name__ == "__main__":
    main()
