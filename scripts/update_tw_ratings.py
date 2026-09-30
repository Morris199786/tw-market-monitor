from __future__ import annotations

import base64
import json
import os
import re
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

OPENAI_API_KEY = os.environ["OPENAI_API_KEY"]
OPENAI_MODEL = os.environ.get("OPENAI_REPORT_MODEL", "gpt-5.6-luna").strip()
OPENAI_API_URL = "https://api.openai.com/v1/responses"

DATA_PATH = ROOT / "data/tw_ratings.json"
STATE_PATH = ROOT / "data/tw_ratings_state.json"
INBOX_PATH = ROOT / "data/report_inbox.json"

IMAGE_MIME_TYPES = {
    "image/jpeg",
    "image/png",
    "image/webp",
    "image/heic",
    "image/heif",
}
HEIC_MIME_TYPES = {"image/heic", "image/heif"}

S = requests.Session()
S.headers.update({
    "Authorization": f"Bearer {ACCESS_TOKEN}",
    "User-Agent": "tw-market-monitor rating image ingestor",
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
    fields = "nextPageToken,files(id,name,mimeType,modifiedTime,webViewLink)"
    out = []
    page_token = None

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

        r = S.get(f"{DRIVE_API}/files", params=params, timeout=60)
        r.raise_for_status()
        data = r.json()
        out.extend(data.get("files", []))
        page_token = data.get("nextPageToken")
        if not page_token:
            break

    return out


def walk_folder(folder_id, path_parts=None):
    path_parts = list(path_parts or [])
    out = []

    for item in drive_list(folder_id):
        mime = item.get("mimeType", "")
        name = item.get("name", "")

        if mime == "application/vnd.google-apps.folder":
            out.extend(walk_folder(item["id"], path_parts + [name]))
            continue

        item["_folder_path"] = "/".join(path_parts)
        out.append(item)

    return out


def download_bytes(file_id):
    r = S.get(
        f"{DRIVE_API}/files/{file_id}",
        params={"alt": "media", "supportsAllDrives": "true"},
        timeout=120,
    )
    r.raise_for_status()
    return r.content


def image_bytes_and_mime(raw, mime_type):
    if mime_type in HEIC_MIME_TYPES:
        import pillow_heif
        from PIL import Image

        pillow_heif.register_heif_opener()
        with Image.open(BytesIO(raw)) as img:
            img = img.convert("RGB")
            out = BytesIO()
            img.save(out, format="JPEG", quality=95)
            return out.getvalue(), "image/jpeg"

    return raw, mime_type if mime_type in IMAGE_MIME_TYPES else "image/jpeg"


def response_text(data):
    chunks = []
    for out in data.get("output", []):
        for content in out.get("content", []):
            if content.get("type") == "output_text":
                chunks.append(content.get("text", ""))
    return "\n".join(chunks).strip()


def parse_json_loose(text):
    s = str(text or "").strip()
    if s.startswith("```"):
        s = re.sub(r"^```(?:json)?\s*", "", s, flags=re.I)
        s = re.sub(r"\s*```$", "", s)

    try:
        return json.loads(s)
    except Exception:
        pass

    m = re.search(r"\{.*\}", s, flags=re.S)
    if not m:
        raise RuntimeError("model did not return JSON")
    return json.loads(m.group(0))


def analyze_image(raw, mime_type, filename):
    raw, safe_mime = image_bytes_and_mime(raw, mime_type)
    data_url = (
        f"data:{safe_mime};base64,"
        + base64.b64encode(raw).decode("ascii")
    )

    prompt = f"""你是台股券商評等表格圖片擷取器。

檔名：{filename}

先判斷這張圖是否為台股券商「目標價調整／評等調整」表格。
如果不是，輸出 is_rating_sheet=false、items=[]。

如果是：
1. 讀取圖片右上角或表頭的當日日期，sheet_date 用 YYYY-MM-DD
2. 只擷取「當日且黃色底」的資料列，白底舊日期全部忽略
3. 目標價調整區：New > Old 為 upgrade；New < Old 為 downgrade；New = Old 不輸出；kind=target_price
4. 評等調整區：Upgrade 為 upgrade；Downgrade 為 downgrade；kind=rating；同列 Old/New TP 也保留
5. 只輸出上下調，不輸出未變動列
6. broker、公司名稱、股票代號、Old TP、New TP 必須精確
7. rating 填圖上可見文字，例如 Neutral、Buy、Sell、Downgrade to Neutral
8. 不得補圖片以外資訊

只輸出 JSON：
{{
  "is_rating_sheet": true,
  "sheet_date": "YYYY-MM-DD",
  "items": [
    {{
      "date": "YYYY-MM-DD",
      "ticker": "2356",
      "name": "英業達",
      "broker": "Goldman Sachs",
      "kind": "target_price",
      "action": "upgrade",
      "rating": "Neutral",
      "target_price_old": 56,
      "target_price_new": 61
    }}
  ]
}}
"""

    payload = {
        "model": OPENAI_MODEL,
        "reasoning": {"effort": "medium"},
        "input": [{
            "role": "user",
            "content": [
                {"type": "input_text", "text": prompt},
                {"type": "input_image", "image_url": data_url, "detail": "high"},
            ],
        }],
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
        raise RuntimeError(f"OpenAI image parse {r.status_code}: {r.text[:1200]}")

    return parse_json_loose(response_text(r.json()))


def normalize_item(x, sheet_date, source):
    action = str(x.get("action") or "").strip().lower()
    if action not in ("upgrade", "downgrade"):
        return None

    kind = str(x.get("kind") or "target_price").strip().lower()
    if kind not in ("target_price", "rating"):
        kind = "target_price"

    ticker = re.sub(r"\D", "", str(x.get("ticker") or ""))
    if len(ticker) != 4:
        return None

    def price(v):
        if v is None:
            return None
        try:
            return float(v)
        except Exception:
            return None

    old_tp = price(x.get("target_price_old"))
    new_tp = price(x.get("target_price_new"))

    if old_tp is None or new_tp is None or old_tp == new_tp:
        return None

    return {
        "date": sheet_date,
        "ticker": ticker,
        "name": str(x.get("name") or "").strip(),
        "broker": str(x.get("broker") or "").strip(),
        "kind": kind,
        "action": action,
        "rating": str(x.get("rating") or "").strip(),
        "target_price_old": old_tp,
        "target_price_new": new_tp,
        "source_file_id": source.get("id"),
        "source_name": source.get("name"),
    }


def mark_inbox_rating(file_id):
    inbox = load_json(INBOX_PATH, {"items": []})
    changed = False

    for item in inbox.get("items", []):
        if item.get("drive_file_id") == file_id:
            item["status"] = "ratings_done"
            item["ratings_processed_at"] = now_tpe()
            changed = True

    if changed:
        inbox["updated_at"] = now_tpe()
        save_json(INBOX_PATH, inbox)


def main():
    state = load_json(STATE_PATH, {"processed_file_ids": []})
    processed = set(state.get("processed_file_ids", []))
    existing = load_json(DATA_PATH, {"date": "", "items": []})

    files = [
        x for x in walk_folder(ROOT_FOLDER_ID)
        if str(x.get("mimeType") or "").lower() in IMAGE_MIME_TYPES
        or str(x.get("mimeType") or "").lower().startswith("image/")
    ]
    files.sort(key=lambda x: x.get("modifiedTime") or "", reverse=True)

    newest_result = None

    for item in files:
        file_id = item["id"]
        if file_id in processed:
            continue

        print("rating image check:", item.get("name"))

        try:
            result = analyze_image(
                download_bytes(file_id),
                item.get("mimeType", ""),
                item.get("name", ""),
            )
            processed.add(file_id)

            if not result.get("is_rating_sheet"):
                continue

            sheet_date = str(result.get("sheet_date") or "").strip()
            if not re.fullmatch(r"20\d{2}-\d{2}-\d{2}", sheet_date):
                print("invalid sheet date", sheet_date)
                continue

            items = []
            for raw_item in result.get("items", []) or []:
                x = normalize_item(raw_item, sheet_date, item)
                if x:
                    items.append(x)

            candidate = {
                "updated_at": now_tpe(),
                "date": sheet_date,
                "source_file_id": file_id,
                "source_name": item.get("name"),
                "source_url": item.get("webViewLink"),
                "items": items,
            }

            if newest_result is None or sheet_date > newest_result.get("date", ""):
                newest_result = candidate

            # 避免同一張評等表又被當成一般券商報告處理/推播
            mark_inbox_rating(file_id)

        except Exception as exc:
            print("rating image failed:", item.get("name"), repr(exc))
            processed.discard(file_id)

    if newest_result:
        if newest_result["date"] >= str(existing.get("date") or ""):
            save_json(DATA_PATH, newest_result)
            print("saved rating date", newest_result["date"], "items", len(newest_result["items"]))
    elif not DATA_PATH.exists():
        save_json(DATA_PATH, {"updated_at": now_tpe(), "date": "", "items": []})

    state["updated_at"] = now_tpe()
    state["processed_file_ids"] = list(processed)[-3000:]
    save_json(STATE_PATH, state)


if __name__ == "__main__":
    main()
