from __future__ import annotations

import base64
import json
import mimetypes
import os
import re
import subprocess
import tempfile
from datetime import datetime
from io import BytesIO
from pathlib import Path
from zoneinfo import ZoneInfo

import requests


ROOT = Path(__file__).resolve().parents[1]
TZ = ZoneInfo("Asia/Taipei")

DRIVE_API = "https://www.googleapis.com/drive/v3"
ACCESS_TOKEN = os.environ["ACCESS_TOKEN"]
ROOT_FOLDER_ID = os.environ["DRIVE_FOLDER_ID"]

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "").strip()
OPENAI_MODEL = os.environ.get("OPENAI_REPORT_MODEL", "gpt-5.6-luna").strip()
OPENAI_API_URL = "https://api.openai.com/v1/responses"

INBOX_PATH = ROOT / "data/report_inbox.json"
STATE_PATH = ROOT / "data/processed_reports.json"

IMAGE_MIME_TYPES = {
    "image/jpeg",
    "image/png",
    "image/webp",
    "image/gif",
    "image/heic",
    "image/heif",
}
HEIC_MIME_TYPES = {"image/heic", "image/heif"}

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
        "files(id,name,mimeType,modifiedTime,size,"
        "webViewLink,md5Checksum)"
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


def download_file(file_id, out_path):
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


def response_text(data):
    chunks = []

    for out in data.get("output", []):
        for c in out.get("content", []):
            if c.get("type") == "output_text":
                chunks.append(c.get("text", ""))

    return "\n".join(chunks).strip()


def convert_heic_to_jpeg(image_path):
    try:
        import pillow_heif
        from PIL import Image
    except Exception as e:
        raise RuntimeError(
            "HEIC support package missing: " + repr(e)
        )

    pillow_heif.register_heif_opener()

    with Image.open(image_path) as img:
        img = img.convert("RGB")
        out = BytesIO()
        img.save(out, format="JPEG", quality=95)
        return out.getvalue(), "image/jpeg"


def image_bytes_and_mime(image_path, mime_type):
    if mime_type in HEIC_MIME_TYPES:
        return convert_heic_to_jpeg(image_path)

    raw = Path(image_path).read_bytes()

    safe_mime = (
        mime_type
        if mime_type in IMAGE_MIME_TYPES
        else None
    )

    if not safe_mime:
        guessed, _ = mimetypes.guess_type(str(image_path))
        safe_mime = guessed or "image/jpeg"

    return raw, safe_mime


def extract_image_text(image_path, mime_type, filename):
    if not OPENAI_API_KEY:
        raise RuntimeError(
            "OPENAI_API_KEY is missing for image report extraction"
        )

    raw, safe_mime = image_bytes_and_mime(
        image_path,
        mime_type,
    )

    encoded = base64.b64encode(raw).decode("ascii")
    data_url = f"data:{safe_mime};base64,{encoded}"

    prompt = f"""你是台股券商報告圖片文字擷取器。

檔名：{filename}

任務：
1. 完整讀取這張圖片中的可見文字
2. 保留券商名稱、公司名稱、股票代號、評等、目標價、日期
3. 表格中的營收、EPS、YoY、MoM、毛利率、目標價等數字要盡量保留
4. 不要自行分析、不補充外部資訊、不改寫內容
5. 如果是券商研究報告截圖，請依畫面閱讀順序輸出
6. 只輸出擷取到的文字，不要 markdown code fence
"""

    payload = {
        "model": OPENAI_MODEL,
        "reasoning": {
            "effort": "low"
        },
        "input": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": prompt,
                    },
                    {
                        "type": "input_image",
                        "image_url": data_url,
                        "detail": "high",
                    },
                ],
            }
        ],
    }

    r = requests.post(
        OPENAI_API_URL,
        headers={
            "Authorization": f"Bearer {OPENAI_API_KEY}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=180,
    )

    if r.status_code >= 400:
        raise RuntimeError(
            f"OpenAI image extraction {r.status_code}: "
            + r.text[:1200]
        )

    text = response_text(r.json())
    text = text.replace("\x00", "")
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{4,}", "\n\n\n", text)

    return text.strip()


def infer_report_date(item):
    parts = [
        p
        for p in str(
            item.get("_folder_path") or ""
        ).split("/")
        if p
    ]

    for p in reversed(parts):
        if re.fullmatch(r"20\d{6}", p):
            return f"{p[:4]}-{p[4:6]}-{p[6:8]}"

    mt = str(item.get("modifiedTime") or "")
    return mt[:10] if len(mt) >= 10 else None


def classify_source(item):
    mime = str(item.get("mimeType") or "").lower()

    if mime == "application/pdf":
        return "pdf"

    if mime in IMAGE_MIME_TYPES or mime.startswith("image/"):
        return "image"

    return None


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

    supported_files = [
        x
        for x in all_files
        if classify_source(x)
    ]

    pdf_count = sum(
        1
        for x in supported_files
        if classify_source(x) == "pdf"
    )

    image_count = sum(
        1
        for x in supported_files
        if classify_source(x) == "image"
    )

    print(
        f"Drive files={len(all_files)} "
        f"PDFs={pdf_count} "
        f"Images={image_count} "
        f"already_processed={len(processed)}"
    )

    added = 0

    for item in supported_files:
        file_id = item["id"]

        if file_id in processed:
            continue

        source_kind = classify_source(item)
        name = item.get("name") or file_id

        print(
            "Processing:",
            source_kind,
            name,
        )

        try:
            with tempfile.TemporaryDirectory() as td:
                suffix = Path(name).suffix

                if not suffix:
                    suffix = (
                        ".pdf"
                        if source_kind == "pdf"
                        else ".img"
                    )

                local_path = Path(td) / ("source" + suffix)

                download_file(
                    file_id,
                    local_path,
                )

                if source_kind == "pdf":
                    text = extract_pdf_text(
                        local_path
                    )
                else:
                    text = extract_image_text(
                        local_path,
                        item.get("mimeType", ""),
                        name,
                    )

            text_chars = len(text)

            status = (
                "pending_ai"
                if text_chars >= 40
                else "needs_ocr"
            )

            record = {
                "drive_file_id": file_id,
                "name": name,
                "mime_type": item.get("mimeType"),
                "source_kind": source_kind,
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
                source_kind,
                status,
                f"{text_chars} chars",
            )

        except Exception as e:
            print(
                "  ERROR",
                name,
                repr(e),
            )

            # 失敗不加入 processed，下次 cronjob 自動重試

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
        f"Added {added} new report file(s). "
        f"Inbox total={len(inbox.get('items', []))}"
    )


if __name__ == "__main__":
    main()
