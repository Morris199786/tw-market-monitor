from __future__ import annotations

import json
import os
import re
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import requests


ROOT = Path(__file__).resolve().parents[1]
TZ = ZoneInfo("Asia/Taipei")

INBOX_PATH = ROOT / "data/report_inbox.json"
REPORTS_PATH = ROOT / "data/reports.json"

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "").strip()
MODEL = os.environ.get("OPENAI_REPORT_MODEL", "gpt-5.6-luna").strip()

API_URL = "https://api.openai.com/v1/responses"


def now_tpe():
    return datetime.now(TZ).isoformat(timespec="minutes")


def load_json(path, default):
    p = Path(path)

    if not p.exists():
        return default

    try:
        return json.loads(
            p.read_text(encoding="utf-8")
        )
    except Exception:
        return default


def save_json(path, data):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)

    p.write_text(
        json.dumps(
            data,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def response_text(data):
    chunks = []

    for out in data.get("output", []):
        for c in out.get("content", []):
            if c.get("type") == "output_text":
                chunks.append(c.get("text", ""))

    return "\n".join(chunks).strip()


def parse_json_loose(text):
    s = (text or "").strip()

    if s.startswith("```"):
        s = re.sub(
            r"^```(?:json)?\s*",
            "",
            s,
            flags=re.I,
        )
        s = re.sub(
            r"\s*```$",
            "",
            s,
        )

    try:
        return json.loads(s)
    except Exception:
        pass

    m = re.search(
        r"\{.*\}",
        s,
        flags=re.S,
    )

    if not m:
        raise ValueError(
            "model output did not contain JSON"
        )

    return json.loads(
        m.group(0)
    )


def normalize_action(v):
    s = str(v or "").strip().lower()

    mapping = {
        "upgrade": "upgrade",
        "up": "upgrade",
        "上調": "upgrade",
        "downgrade": "downgrade",
        "down": "downgrade",
        "下調": "downgrade",
        "initiate": "initiate",
        "initiation": "initiate",
        "初評": "initiate",
        "maintain": "maintain",
        "維持": "maintain",
        "sector": "sector",
        "industry": "sector",
        "產業": "sector",
        "none": "none",
        "": "none",
    }

    return mapping.get(
        s,
        "none",
    )


def clean_list(v, limit=8):
    if not isinstance(v, list):
        return []

    out = []

    for x in v:
        s = str(x or "").strip()

        if not s:
            continue

        out.append(s)

        if len(out) >= limit:
            break

    return out


def normalize_report(obj, src):
    report_type = str(
        obj.get("report_type")
        or "sector"
    ).strip().lower()

    if report_type not in (
        "company",
        "sector",
        "theme",
    ):
        report_type = "sector"

    action = normalize_action(
        obj.get("action")
    )

    if report_type != "company" and action == "none":
        action = "sector"

    primary = obj.get("primary_stock")

    if not isinstance(primary, dict):
        primary = {}

    ticker = str(
        primary.get("ticker")
        or ""
    ).strip()

    name = str(
        primary.get("name")
        or ""
    ).strip()

    rating = str(
        obj.get("rating")
        or ""
    ).strip()

    target_old = obj.get(
        "target_price_old"
    )

    target_new = obj.get(
        "target_price_new"
    )

    beneficiaries = []

    for x in obj.get(
        "beneficiaries",
        [],
    ) if isinstance(
        obj.get("beneficiaries"),
        list
    ) else []:
        if not isinstance(x, dict):
            continue

        beneficiaries.append({
            "ticker": str(
                x.get("ticker")
                or ""
            ).strip(),
            "name": str(
                x.get("name")
                or ""
            ).strip(),
            "reason": str(
                x.get("reason")
                or ""
            ).strip(),
        })

        if len(beneficiaries) >= 12:
            break

    return {
        "id": src.get("drive_file_id"),
        "source_file_id": src.get("drive_file_id"),
        "source_name": src.get("name"),
        "source_url": src.get("drive_url"),
        "date": (
            str(
                obj.get("date")
                or src.get("report_date")
                or ""
            ).strip()
        ),
        "broker": str(
            obj.get("broker")
            or ""
        ).strip(),
        "report_type": report_type,
        "title": str(
            obj.get("title")
            or src.get("name")
            or ""
        ).strip(),
        "action": action,
        "ticker": ticker,
        "name": name,
        "rating": rating,
        "target_price_old": target_old,
        "target_price_new": target_new,
        "summary": clean_list(
            obj.get("summary"),
            5,
        ),
        "key_points": clean_list(
            obj.get("key_points"),
            8,
        ),
        "beneficiaries": beneficiaries,
        "risks": clean_list(
            obj.get("risks"),
            5,
        ),
        "forecast_changes": clean_list(
            obj.get("forecast_changes"),
            6,
        ),
        "detail": str(
            obj.get("detail")
            or ""
        ).strip(),
        "ai_model": MODEL,
        "ai_processed_at": now_tpe(),
    }


def analyze_report(src):
    text = str(
        src.get("text")
        or ""
    )

    # 足夠涵蓋一般券商報告，同時避免極端超長 PDF
    text = text[:160000]

    system = """你是台股券商研究報告整理器。
只可以根據使用者提供的報告文字整理，不得補充外部資料、不得自行推測未寫明的評等或目標價。

輸出必須是單一 JSON object，不要 markdown，不要任何 JSON 以外文字。

規則：
1. 使用繁體中文
2. report_type 只能是 company / sector / theme
3. company 才能有 primary_stock；產業或主題報告 primary_stock 請用空物件
4. action 只能是 upgrade / downgrade / initiate / maintain / sector / none
5. 如果報告沒有明確寫「上調/下調/初評/維持」評等，不得自行判斷，company 可填 none，產業報告填 sector
6. target_price_old / target_price_new 只有報告明確寫到時才填數字，否則 null
7. rating 只有報告明確寫到時才填，否則空字串
8. summary 3~5 條，每條一句，最重要投資重點
9. key_points 最多 8 條，保留產業供需、規格、漲價、產能、EPS/財測等具體數字
10. beneficiaries 只列報告明確提到的受惠/首選/推薦關注個股，不能自己增加
11. risks 只有報告提到或報告文字可直接支持的風險，不可自己想像
12. forecast_changes 只有明確上修/下修或財測調整才列
13. detail 用 250~600 字整理全文核心，不要寫成泛泛而談
14. broker、日期、標題盡量從報告本身辨識；辨識不到可留空
15. 股票代號若報告明確出現才填

固定 JSON 欄位：
{
  "broker": "",
  "date": "",
  "report_type": "company|sector|theme",
  "title": "",
  "action": "upgrade|downgrade|initiate|maintain|sector|none",
  "primary_stock": {"ticker": "", "name": ""},
  "rating": "",
  "target_price_old": null,
  "target_price_new": null,
  "summary": [],
  "key_points": [],
  "beneficiaries": [
    {"ticker": "", "name": "", "reason": ""}
  ],
  "risks": [],
  "forecast_changes": [],
  "detail": ""
}"""

    user = f"""檔名：
{src.get("name")}

Drive 日期：
{src.get("report_date")}

以下為 PDF 擷取文字：

{text}
"""

    payload = {
        "model": MODEL,
        "reasoning": {
            "effort": "low"
        },
        "input": [
            {
                "role": "system",
                "content": [
                    {
                        "type": "input_text",
                        "text": system,
                    }
                ],
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": user,
                    }
                ],
            },
        ],
    }

    r = requests.post(
        API_URL,
        headers={
            "Authorization": (
                f"Bearer {OPENAI_API_KEY}"
            ),
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=180,
    )

    if r.status_code >= 400:
        raise RuntimeError(
            f"OpenAI API {r.status_code}: "
            + r.text[:1200]
        )

    data = r.json()

    text_out = response_text(
        data
    )

    obj = parse_json_loose(
        text_out
    )

    return normalize_report(
        obj,
        src,
    )


def main():
    if not OPENAI_API_KEY:
        print(
            "OPENAI_API_KEY is missing; "
            "skip AI report processing."
        )
        return

    inbox = load_json(
        INBOX_PATH,
        {
            "updated_at": None,
            "items": [],
        },
    )

    reports = load_json(
        REPORTS_PATH,
        {
            "updated_at": None,
            "items": [],
        },
    )

    items = list(
        reports.get("items", [])
        or []
    )

    by_source = {
        x.get("source_file_id"): x
        for x in items
        if x.get("source_file_id")
    }

    processed = 0
    failed = 0

    for src in inbox.get(
        "items",
        [],
    ):
        if src.get("status") != "pending_ai":
            continue

        file_id = src.get("drive_file_id")

        if not file_id:
            continue

        if file_id in by_source:
            src["status"] = "done"
            continue

        print(
            "AI processing:",
            src.get("name"),
        )

        try:
            report = analyze_report(
                src
            )

            items.append(
                report
            )
            by_source[file_id] = report

            src["status"] = "done"
            src["ai_processed_at"] = now_tpe()
            src.pop(
                "ai_error",
                None,
            )

            processed += 1

            print(
                "  OK:",
                report.get("broker"),
                report.get("title"),
            )

        except Exception as e:
            failed += 1
            src["ai_error"] = str(e)[:1000]
            src["ai_last_attempt_at"] = now_tpe()

            print(
                "  ERROR:",
                repr(e),
            )

    items.sort(
        key=lambda x: (
            x.get("date") or "",
            x.get("ai_processed_at") or "",
        ),
        reverse=True,
    )

    reports["items"] = items
    reports["updated_at"] = now_tpe()
    reports["_help"] = (
        "由 Google Drive 券商報告自動整理。"
        "action: upgrade/downgrade/initiate/"
        "maintain/sector/none"
    )

    inbox["updated_at"] = now_tpe()

    save_json(
        REPORTS_PATH,
        reports,
    )

    save_json(
        INBOX_PATH,
        inbox,
    )

    print(
        f"AI processed={processed}, "
        f"failed={failed}, "
        f"reports={len(items)}"
    )


if __name__ == "__main__":
    main()
