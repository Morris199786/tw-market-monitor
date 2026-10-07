from __future__ import annotations

import json
import hashlib
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo
from urllib.parse import quote

import requests
from report_identity import registry, audit_report, VERSION, alias_hits, explicit_tickers

COMPANIES = {}

ROOT = Path(__file__).resolve().parents[1]
TZ = ZoneInfo("Asia/Taipei")

INBOX_PATH = ROOT / "data/report_inbox.json"
REPORTS_PATH = ROOT / "data/reports.json"

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "").strip()
MODEL = os.environ.get("OPENAI_REPORT_MODEL", "gpt-5.6-luna").strip()

PUSHOVER_APP_TOKEN = os.environ.get("PUSHOVER_APP_TOKEN", "").strip()
PUSHOVER_USER_KEY = os.environ.get("PUSHOVER_USER_KEY", "").strip()

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "").strip()

SITE_URL = os.environ.get(
    "REPORT_SITE_URL",
    "https://morris199786.github.io/tw-market-monitor/",
).rstrip("/") + "/"

API_URL = "https://api.openai.com/v1/responses"
PUSHOVER_URL = "https://api.pushover.net/1/messages.json"


def now_tpe() -> str:
    return datetime.now(TZ).isoformat(timespec="minutes")


def load_json(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def save_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def response_text(data: dict) -> str:
    chunks = []
    for out in data.get("output", []):
        for c in out.get("content", []):
            if c.get("type") == "output_text":
                chunks.append(c.get("text", ""))
    return "\n".join(chunks).strip()


def parse_json_loose(text: str) -> dict:
    s = (text or "").strip()
    if s.startswith("```"):
        s = re.sub(r"^```(?:json)?\s*", "", s, flags=re.I)
        s = re.sub(r"\s*```$", "", s)
    try:
        return json.loads(s)
    except Exception:
        pass
    m = re.search(r"\{.*\}", s, flags=re.S)
    if not m:
        raise ValueError("model output did not contain JSON")
    return json.loads(m.group(0))


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


def normalize_action(v):
    s = str(v or "").strip().lower()
    mapping = {
        "upgrade": "upgrade", "up": "upgrade", "上調": "upgrade",
        "downgrade": "downgrade", "down": "downgrade", "下調": "downgrade",
        "initiate": "initiate", "initiation": "initiate", "初評": "initiate",
        "maintain": "maintain", "維持": "maintain",
        "sector": "sector", "industry": "sector", "產業": "sector",
        "none": "none", "": "none",
    }
    return mapping.get(s, "none")


def parse_drive_time(raw: str | None):
    if not raw:
        return None
    s = str(raw).strip()
    try:
        if s.endswith("Z"):
            dt = datetime.fromisoformat(s[:-1] + "+00:00")
        else:
            dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(TZ)
    except Exception:
        return None


def received_info(src: dict):
    dt = parse_drive_time(src.get("modified_time"))
    if dt:
        return dt.isoformat(timespec="seconds"), dt.strftime("%Y-%m-%d")
    raw = src.get("ingested_at")
    try:
        dt = datetime.fromisoformat(str(raw))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=TZ)
        dt = dt.astimezone(TZ)
        return dt.isoformat(timespec="seconds"), dt.strftime("%Y-%m-%d")
    except Exception:
        pass
    now = datetime.now(TZ)
    return now.isoformat(timespec="seconds"), now.strftime("%Y-%m-%d")


def normalize_report(obj: dict, src: dict) -> dict:
    report_type = str(obj.get("report_type") or "sector").strip().lower()
    if report_type not in ("company", "sector", "theme"):
        report_type = "sector"
    action = normalize_action(obj.get("action"))
    if report_type != "company" and action == "none":
        action = "sector"
    primary = obj.get("primary_stock")
    if not isinstance(primary, dict):
        primary = {}
    ticker = str(primary.get("ticker") or "").strip()
    name = str(primary.get("name") or "").strip()
    beneficiaries = []
    raw_beneficiaries = obj.get("beneficiaries")
    if isinstance(raw_beneficiaries, list):
        for x in raw_beneficiaries:
            if not isinstance(x, dict):
                continue
            beneficiaries.append({
                "ticker": str(x.get("ticker") or "").strip(),
                "name": str(x.get("name") or "").strip(),
                "reason": str(x.get("reason") or "").strip(),
            })
            if len(beneficiaries) >= 20:
                break
    received_at, group_date = received_info(src)
    push_reason = str(obj.get("push_reason") or "").strip()
    if not push_reason:
        summary = clean_list(obj.get("summary"), 1)
        push_reason = summary[0] if summary else ""
    return {
        "id": src.get("drive_file_id"),
        "source_file_id": src.get("drive_file_id"),
        "source_name": src.get("name"),
        "source_url": src.get("drive_url"),
        "group_date": group_date,
        "received_at": received_at,
        "date": str(obj.get("date") or src.get("report_date") or "").strip(),
        "broker": str(obj.get("broker") or "").strip(),
        "report_type": report_type,
        "title": str(obj.get("title") or src.get("name") or "").strip(),
        "action": action,
        "ticker": ticker,
        "name": name,
        "rating": str(obj.get("rating") or "").strip(),
        "target_price_old": obj.get("target_price_old"),
        "target_price_new": obj.get("target_price_new"),
        "push_reason": push_reason[:80],
        "summary": clean_list(obj.get("summary"), 5),
        "key_points": clean_list(obj.get("key_points"), 8),
        "beneficiaries": beneficiaries,
        "risks": clean_list(obj.get("risks"), 5),
        "forecast_changes": clean_list(obj.get("forecast_changes"), 6),
        "detail": str(obj.get("detail") or "").strip(),
        "ai_model": MODEL,
        "ai_processed_at": now_tpe(),
    }


def analyze_report(src: dict) -> dict:
    text = str(src.get("text") or "")
    text = re.sub(r"[ \t]{2,}", " ", text)
    if len(text) > 240000:
        raise ValueError("Report exceeds safe input limit; no silent truncation")

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
15. 公司名稱與代號必須依下方已驗證公司對照表，禁止自行翻譯公司中文名稱；只有英文名稱但能唯一對應也可填代號，不得把 ISU Petasys 認成台灣公司
16. 產業報告仍須在 summary 第一條列出台灣個股的評等及目標價，不能只寫產業趨勢；目標價設定、目標價調升、評等調升必須區分；n.a. 為 null，不是現價
17. push_reason 是給手機推播看的極短原因，限 15~35 個中文字，直接說明評等/目標價改變的主因；若是產業報告則寫最重要的產業變化，不要寫「報告認為」

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
  "push_reason": "",
  "summary": [],
  "key_points": [],
  "beneficiaries": [{"ticker": "", "name": "", "reason": ""}],
  "risks": [],
  "forecast_changes": [],
  "detail": ""
}"""

    candidates = explicit_tickers(text) | alias_hits(text, COMPANIES)
    mapping = {t: COMPANIES[t] for t in sorted(candidates) if t in COMPANIES}
    system += "\n已驗證公司名稱對照（僅用於身分，不是財測來源）：" + json.dumps(
        mapping, ensure_ascii=False
    )

    user = f"""檔名：
{src.get("name")}

Drive 日期：
{src.get("report_date")}

以下為 PDF 擷取文字：

{text}
"""
    payload = {
        "model": MODEL,
        "reasoning": {"effort": "low"},
        "input": [
            {"role": "system", "content": [{"type": "input_text", "text": system}]},
            {"role": "user", "content": [{"type": "input_text", "text": user}]},
        ],
    }
    r = requests.post(
        API_URL,
        headers={
            "Authorization": f"Bearer {OPENAI_API_KEY}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=180,
    )
    if r.status_code >= 400:
        raise RuntimeError(f"OpenAI API {r.status_code}: " + r.text[:1200])
    obj = parse_json_loose(response_text(r.json()))
    return audit_report(normalize_report(obj, src), src, COMPANIES)


def action_zh(action: str) -> str:
    return {
        "upgrade": "上調", "downgrade": "下調", "initiate": "初評",
        "maintain": "維持", "sector": "產業報告", "none": "研究報告",
    }.get(action, "研究報告")


def target_price_line(report: dict) -> str:
    old = report.get("target_price_old")
    new = report.get("target_price_new")
    if old is not None and new is not None:
        return f"目標價：{old} → {new}"
    if new is not None:
        return f"目標價：{new}"
    return ""


def build_push(report: dict):
    broker = report.get("broker") or "券商"
    action = action_zh(report.get("action") or "none")
    reason = (
        report.get("push_reason")
        or (report.get("summary") or [""])[0]
        or ""
    ).strip()
    if len(reason) > 72:
        reason = reason[:72] + "…"

    if report.get("report_type") == "company":
        name = report.get("name") or ""
        ticker = report.get("ticker") or ""
        title = "券商報告"
        first = " ".join(x for x in [broker, action, name, ticker] if x)
        lines = [first]
        tp = target_price_line(report)
        if tp:
            lines.append(tp)
        if reason:
            lines.append(f"原因：{reason}")
        message = "\n".join(lines)
    else:
        title = "券商報告"
        first = f"{broker}｜{report.get('title') or '產業報告'}"
        lines = [first]
        if report.get("recommendation_headlines"):
            lines.extend(report["recommendation_headlines"][:8])
        elif reason:
            lines.append(f"重點：{reason}")
        message = "\n".join(lines)

    report_id = str(report.get("id") or "")
    url = SITE_URL + "?page=reports&report=" + quote(report_id, safe="")
    return title, message, url


def send_pushover(report: dict) -> bool:
    if not PUSHOVER_APP_TOKEN or not PUSHOVER_USER_KEY:
        print("Pushover secrets missing; skip push.")
        return False
    title, message, url = build_push(report)
    r = requests.post(
        PUSHOVER_URL,
        data={
            "token": PUSHOVER_APP_TOKEN,
            "user": PUSHOVER_USER_KEY,
            "title": title,
            "message": message,
            "url": url,
            "url_title": "開啟券商報告",
        },
        timeout=30,
    )
    if r.status_code >= 400:
        print("Pushover failed:", r.status_code, r.text[:500])
        return False
    data = r.json()
    ok = data.get("status") == 1
    if not ok:
        print("Pushover rejected:", data)
        return False
    print("Pushover sent:", report.get("title"))
    return True


def send_telegram(report: dict) -> bool:
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("Telegram secrets missing; skip telegram.")
        return False
    title, message, url = build_push(report)
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            data={
                "chat_id": TELEGRAM_CHAT_ID,
                "text": f"{title}\n{message}",
                "disable_web_page_preview": True,
                "reply_markup": json.dumps(
                    {"inline_keyboard": [[{"text": "開啟這篇報告", "url": url}]]},
                    ensure_ascii=False,
                ),
            },
            timeout=30,
        )
        r.raise_for_status()
        data = r.json()
        ok = bool(data.get("ok"))
        if ok:
            print("Telegram sent:", report.get("title"))
        return ok
    except Exception as e:
        print("Telegram failed:", repr(e))
        return False


def backfill_dates(items: list[dict], inbox_items: list[dict]) -> None:
    src_map = {
        x.get("drive_file_id"): x
        for x in inbox_items
        if x.get("drive_file_id")
    }
    for report in items:
        if report.get("group_date") and report.get("received_at"):
            continue
        src = src_map.get(report.get("source_file_id")) or {}
        received_at, group_date = received_info(src)
        if not report.get("received_at"):
            report["received_at"] = received_at
        if not report.get("group_date"):
            report["group_date"] = group_date


def is_quota_error(error_text: str) -> bool:
    s = (error_text or "").lower()
    return (
        "credit_balance_exhausted" in s
        or "insufficient_quota" in s
        or "you have no credits remaining" in s
    )


def main():
    global COMPANIES
    COMPANIES = registry(refresh=True)

    inbox = load_json(INBOX_PATH, {"updated_at": None, "items": []})
    reports = load_json(REPORTS_PATH, {"updated_at": None, "items": []})

    inbox_items = inbox.get("items", []) or []
    items = list(reports.get("items", []) or [])

    backfill_dates(items, inbox_items)

    by_source = {
        x.get("source_file_id"): x
        for x in items
        if x.get("source_file_id")
    }

    processed = 0
    failed = 0
    quota_exhausted = False

    for src in inbox_items:
        file_id = src.get("drive_file_id")
        if not file_id:
            continue

        old = by_source.get(file_id)
        current_text_hash = hashlib.sha256(
            str(src.get("text") or "").encode()
        ).hexdigest()

        # 已經以目前 audit version 驗證成功且來源未改變：永遠跳過
        if (
            old
            and old.get("audit_version") == VERSION
            and old.get("validation_status") == "verified"
            and old.get("source_text_hash") == current_text_hash
        ):
            continue

        # 同一份來源、同一 audit version 已經失敗過：
        # 不再由每 5 分鐘 workflow 自動重試，避免無限燒 API
        if (
            src.get("audit_failed_version") == VERSION
            and src.get("audit_failed_text_hash") == current_text_hash
        ):
            continue

        # 新報告只處理 pending_ai。
        # 舊版留下的 audit_error 若沒有 failure marker，允許最後重試一次；
        # 若再失敗，會寫入 marker，之後自動跳過。
        if (
            not old
            and src.get("status") not in ("pending_ai", "audit_error")
        ):
            continue

        # 額度用完後，本輪不再碰後續報告
        if quota_exhausted:
            break

        try:
            if old:
                report = audit_report(old, src, COMPANIES)
                old.clear()
                old.update(report)
                old.pop("audit_error", None)
                old.pop("audit_failed_at", None)
            else:
                if not OPENAI_API_KEY:
                    raise RuntimeError("OPENAI_API_KEY is missing")
                report = analyze_report(src)
                items.append(report)
                by_source[file_id] = report

            src["status"] = "done"
            src["audit_version"] = VERSION
            src.pop("ai_error", None)
            src.pop("audit_failed_version", None)
            src.pop("audit_failed_text_hash", None)
            src.pop("audit_failed_at", None)
            src["ai_processed_at"] = now_tpe()
            processed += 1

        except Exception as exc:
            failed += 1
            error_text = str(exc)[:1200]

            src["status"] = "audit_error"
            src["ai_error"] = error_text
            src["audit_failed_version"] = VERSION
            src["audit_failed_text_hash"] = current_text_hash
            src["audit_failed_at"] = now_tpe()

            if old:
                old["audit_error"] = error_text[:500]
                old["audit_failed_at"] = now_tpe()

            print(
                "Report audit failed:",
                src.get("name"),
                error_text[:300],
            )

            if is_quota_error(error_text):
                quota_exhausted = True
                print(
                    "OpenAI credit exhausted; stop AI processing for this run "
                    "to prevent repeated API calls."
                )

        # 每篇處理後立即 checkpoint
        reports["items"] = items
        save_json(REPORTS_PATH, reports)
        save_json(INBOX_PATH, inbox)

        if quota_exhausted:
            break

    # 第一次啟用 Telegram 時，不把既有舊報告全部補發
    if not reports.get("_telegram_initialized"):
        for report in items:
            if report.get("push_sent_at") and not report.get("telegram_sent_at"):
                report["telegram_sent_at"] = report.get("push_sent_at")
        reports["_telegram_initialized"] = True

    pushed = 0
    telegram_pushed = 0

    for report in items:
        if report.get("validation_status") != "verified":
            continue
        if not report.get("telegram_sent_at"):
            if send_telegram(report):
                report["telegram_sent_at"] = now_tpe()
                telegram_pushed += 1
                reports["items"] = items
                save_json(REPORTS_PATH, reports)

    items.sort(
        key=lambda x: (
            x.get("group_date") or "",
            x.get("received_at") or "",
            x.get("ai_processed_at") or "",
        ),
        reverse=True,
    )

    reports["items"] = items
    reports["updated_at"] = now_tpe()
    reports["_help"] = (
        "由 Google Drive 券商報告自動整理。"
        "group_date 使用 Drive 收到日期做網站分組；"
        "date 保留報告本身日期。"
        "公司身分與目標價經來源驗證，僅 Telegram 推播；"
        "同一 audit version 驗證失敗後不會由排程無限重試；"
        "來源文字或 audit version 改變後才會重新核對。"
    )

    inbox["updated_at"] = now_tpe()

    save_json(REPORTS_PATH, reports)
    save_json(INBOX_PATH, inbox)

    print(
        f"AI processed={processed}, "
        f"failed={failed}, "
        f"pushover={pushed}, "
        f"telegram={telegram_pushed}, "
        f"reports={len(items)}, "
        f"quota_exhausted={quota_exhausted}"
    )


if __name__ == "__main__":
    main()
