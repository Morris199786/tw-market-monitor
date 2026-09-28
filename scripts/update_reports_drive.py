from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import requests


ROOT = Path(__file__).resolve().parents[1]
TZ = ZoneInfo("Asia/Taipei")

DRIVE_API = "https://www.googleapis.com/drive/v3"
ACCESS_TOKEN = os.environ["ACCESS_TOKEN"]
ROOT_FOLDER_ID = os.environ["DRIVE_FOLDER_ID"]

INBOX_PATH = ROOT / "data/report_inbox.json"
STATE_PATH = ROOT / "data/processed_reports.json"

S = requests.Session()
S.headers.update({
    "Authorization": f"Bearer {ACCESS_TOKEN}",
    "User-Agent": "tw-market-monitor broker report ingestor",
})


def now_tpe():
    return datetime.now(TZ).isoformat(timespec="minutes")


def load_json(path, default):
    p = Path(path)
    if not p.exists():
        return default
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return default


def save_json(path, data):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def drive_list(folder_id):
    fields = (
        "nextPageToken,"
        "files("
        "id,name,mimeType,modifiedTime,size,"
        "webViewLink,md5Checksum"
        ")"
    )

    page_token = None
    out = []

    while True:
        params = {
            "q": f"'{folder_id}' in parents and trashed = false",
            "fields": fields,
            "orderBy": "modifiedTime desc",
            "pageSize": 1000,
            "supportsAllDrives": "true",
            "includeItemsFromAllDrives": "true",
        }

        if page_token:
            params["pageToken"] = page_token

        r = S.get(
            f"{DRIVE_API}/files",
            params=params,
            timeout=60,
        )
        r.raise_for_status()

        data = r.json()
        out.extend(data.get("files", []))

        page_token = data.get("nextPageToken")
        if not page_token:
            break

    return out


def walk_folder(folder_id, path_parts=None):
    path_parts = list(path_parts or [])
    rows = []

    for item in drive_list(folder_id):
        mime = item.get("mimeType", "")
        name = item.get("name", "")

        if mime == "application/vnd.google-apps.folder":
            rows.extend(
                walk_folder(
                    item["id"],
                    path_parts + [name],
                )
            )
            continue

        item["_folder_path"] = "/".join(path_parts)
        rows.append(item)

    return rows


def download_pdf(file_id, out_path):
    r = S.get(
        f"{DRIVE_API}/files/{file_id}",
        params={
            "alt": "media",
            "supportsAllDrives": "true",
        },
        timeout=120,
        stream=True,
    )
    r.raise_for_status()

    with open(out_path, "wb") as f:
        for chunk in r.iter_content(chunk_size=1024 * 1024):
            if chunk:
                f.write(chunk)


def extract_pdf_text(pdf_path):
    txt_path = str(pdf_path) + ".txt"

    cp = subprocess.run(
        [
            "pdftotext",
            "-layout",
            "-enc",
            "UTF-8",
            str(pdf_path),
            txt_path,
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=120,
    )

    if cp.returncode != 0:
        raise RuntimeError(
            "pdftotext failed: " + cp.stderr.strip()
        )

    p = Path(txt_path)
    if not p.exists():
        return ""

    text = p.read_text(
        encoding="utf-8",
        errors="replace",
    )

    text = text.replace("\x00", "")
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{4,}", "\n\n\n", text)

    return text.strip()


def infer_report_date(item):
    parts = [
        p
        for p in str(item.get("_folder_path") or "").split("/")
        if p
    ]

    for p in reversed(parts):
        if re.fullmatch(r"20\d{6}", p):
            return f"{p[:4]}-{p[4:6]}-{p[6:8]}"

    mt = str(item.get("modifiedTime") or "")
    return mt[:10] if len(mt) >= 10 else None


def main():
    inbox = load_json(
        INBOX_PATH,
        {
            "updated_at": None,
            "folder_id": ROOT_FOLDER_ID,
            "items": [],
        },
    )

    state = load_json(
        STATE_PATH,
        {
            "updated_at": None,
            "processed_file_ids": [],
        },
    )

    processed = set(
        state.get("processed_file_ids", [])
    )

    existing_ids = {
        x.get("drive_file_id")
        for x in inbox.get("items", [])
        if x.get("drive_file_id")
    }

    all_files = walk_folder(
        ROOT_FOLDER_ID,
        [],
    )

    pdfs = [
        x
        for x in all_files
        if x.get("mimeType") == "application/pdf"
    ]

    print(
        f"Drive files={len(all_files)} "
        f"PDFs={len(pdfs)} "
        f"already_processed={len(processed)}"
    )

    added = 0

    for item in pdfs:
        file_id = item["id"]

        if file_id in processed:
            continue

        name = item.get("name") or f"{file_id}.pdf"
        print("Processing:", name)

        try:
            with tempfile.TemporaryDirectory() as td:
                safe_name = re.sub(
                    r"[^A-Za-z0-9._-]+",
                    "_",
                    name,
                )

                pdf_path = Path(td) / safe_name

                download_pdf(
                    file_id,
                    pdf_path,
                )

                text = extract_pdf_text(
                    pdf_path
                )

            text_chars = len(text)

            status = (
                "pending_ai"
                if text_chars >= 100
                else "needs_ocr"
            )

            record = {
                "drive_file_id": file_id,
                "name": name,
                "mime_type": item.get("mimeType"),
                "modified_time": item.get("modifiedTime"),
                "size": (
                    int(item["size"])
                    if str(item.get("size", "")).isdigit()
                    else None
                ),
                "md5": item.get("md5Checksum"),
                "drive_url": (
                    item.get("webViewLink")
                    or f"https://drive.google.com/file/d/{file_id}/view"
                ),
                "folder_path": item.get("_folder_path") or "",
                "report_date": infer_report_date(item),
                "status": status,
                "text_chars": text_chars,
                "text": text,
                "ingested_at": now_tpe(),
            }

            if file_id in existing_ids:
                inbox["items"] = [
                    x
                    for x in inbox.get("items", [])
                    if x.get("drive_file_id") != file_id
                ]

            inbox.setdefault("items", []).append(record)

            processed.add(file_id)
            existing_ids.add(file_id)
            added += 1

            print(
                "  OK",
                status,
                f"{text_chars} chars",
            )

        except Exception as e:
            print(
                "  ERROR",
                name,
                repr(e),
            )
            # 失敗不加入 processed，下次排程自動重試

    inbox["items"] = sorted(
        inbox.get("items", []),
        key=lambda x: (
            x.get("report_date") or "",
            x.get("modified_time") or "",
            x.get("name") or "",
        ),
        reverse=True,
    )

    inbox["updated_at"] = now_tpe()
    inbox["folder_id"] = ROOT_FOLDER_ID

    state["updated_at"] = now_tpe()
    state["processed_file_ids"] = sorted(processed)

    save_json(
        INBOX_PATH,
        inbox,
    )

    save_json(
        STATE_PATH,
        state,
    )

    print(
        f"Added {added} new PDF(s). "
        f"Inbox total={len(inbox.get('items', []))}"
    )


if __name__ == "__main__":
    main()
