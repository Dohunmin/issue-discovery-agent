import json
import base64
import tempfile
from datetime import datetime, timezone
import gspread
from google.oauth2.service_account import Credentials
from src.config import GOOGLE_SHEETS_CREDS, SPREADSHEET_NAME, WORKSHEET_NAME

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]


def write_to_sheets(topics: list[dict]) -> None:
    """선정된 이슈를 Google Sheets에 기록한다."""
    if not GOOGLE_SHEETS_CREDS:
        print("[Sheets] GOOGLE_SHEETS_CREDS가 설정되지 않아 건너뜀")
        return

    creds_json = _decode_creds()
    credentials = Credentials.from_service_account_info(creds_json, scopes=SCOPES)
    gc = gspread.authorize(credentials)

    sh = gc.open(SPREADSHEET_NAME)
    worksheet = sh.worksheet(WORKSHEET_NAME)

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    rows = []
    for topic in topics:
        rows.append([
            today,
            topic.get("rank", ""),
            topic.get("topic_id", ""),
            topic.get("canonical_title", ""),
            topic.get("why_now", ""),
            topic.get("issue_hook", ""),
        ])

    if rows:
        worksheet.append_rows(rows, value_input_option="USER_ENTERED")
        print(f"[Sheets] {len(rows)}개 행 추가 완료")


def _decode_creds() -> dict:
    """base64 인코딩된 서비스 계정 JSON을 디코딩한다."""
    try:
        decoded = base64.b64decode(GOOGLE_SHEETS_CREDS)
        return json.loads(decoded)
    except Exception:
        # base64가 아니면 직접 JSON 파싱 시도
        return json.loads(GOOGLE_SHEETS_CREDS)
