from __future__ import annotations

import json
import hashlib
import os
import re
import subprocess
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


REPORT_STATE_PATHS = (
    "data/report_inbox.json", "data/processed_reports.json",
    "data/reports.json", "data/report_company_registry.json",
    "data/tw_ratings.json", "data/tw_ratings_state.json",
)


def push_report_commits(max_attempts: int = 5) -> None:
    """Retry Git publication only; never replay AI/OCR/Telegram operations.

    Rebase unrelated market updates. If remote report state changed, stop before
    any external call: in-memory claims must not overwrite another writer.
    """
    def git(*args):
        return subprocess.run(
            ["git", *args], cwd=ROOT, check=True,
            capture_output=True, text=True, timeout=90,
        ).stdout.strip()

    for attempt in range(1, max_attempts + 1):
        git("fetch", "origin", "main")
        base = git("merge-base", "HEAD", "origin/main")
        changed = git("diff", "--name-only", base, "origin/main", "--",
                      *REPORT_STATE_PATHS)
        if changed:
            raise RuntimeError(
                "Remote report state changed; refusing to overwrite claims or "
                "perform external calls: " + changed.replace("\n", ", ")
            )
        try:
            git("rebase", "origin/main")
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
            subprocess.run(["git", "rebase", "--abort"], cwd=ROOT,
                           capture_output=True, timeout=90)
            raise
        try:
            git("push", "origin", "HEAD:main")
            print(f"Report state published (attempt {attempt}/{max_attempts})")
            return
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
            if attempt == max_attempts:
                raise RuntimeError(
                    "Report state could not be published; external call blocked"
                ) from exc
            print(f"Report push failed; syncing before retry {attempt + 1}")


def commit_claim_before_external_call(reason: str) -> None:
    """Persist one-shot claim to GitHub BEFORE spending credits or sending Telegram.

    Fail closed: if git push fails, do not perform the external operation.
    The workflow must use a single concurrency group and checkout main.
    """
    subprocess.run(["git", "config", "user.name", "github-actions[bot]"], cwd=ROOT, check=True)
    subprocess.run(["git", "config", "user.email", "41898282+github-actions[bot]@users.noreply.github.com"], cwd=ROOT, check=True)
    # Include ingestion/rating changes so the claim commit can be pushed cleanly.
    subprocess.run(["git", "add", "data/report_inbox.json", "data/processed_reports.json",
                    "data/reports.json", "data/report_company_registry.json",
                    "data/tw_ratings.json", "data/tw_ratings_state.json"], cwd=ROOT, check=True)
    diff = subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=ROOT)
    if diff.returncode == 0:
        raise RuntimeError("One-shot claim not changed; refusing external call")
    if diff.returncode != 1:
        raise RuntimeError("Could not verify staged claim")
    subprocess.run(["git", "commit", "-m", "Claim broker report once: " + reason[:90]], cwd=ROOT, check=True)
    push_report_commits()


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
        "push_reason": push_reason[:80],  # 保留原始解析內容；推播端另做20字與無效摘要檢查
        "summary": clean_list(obj.get("summary"), 5),
        "key_points": clean_list(obj.get("key_points"), 8),
        "beneficiaries": beneficiaries,
        "risks": clean_list(obj.get("risks"), 5),
        "forecast_changes": clean_list(obj.get("forecast_changes"), 6),
        "detail": str(obj.get("detail") or "").strip(),
        "ai_model": MODEL,
        "ai_processed_at": now_tpe(),
    }


def prepare_report_text(src):
    """Keep all words, rows and pages; compact layout gaps only when oversized."""
    text = str(src.get("text") or "")
    if len(text) > 240000:
        # A tab retains an explicit column separator without hundreds of spaces.
        text = re.sub(r"[ \t]{2,}", "\t", text)
    if len(text) > 240000:
        raise ValueError("Report exceeds safe input limit; no silent truncation")
    return text


def is_verified_kgi_preflight_failure(src):
    """One known local-only rejection, before requests.post; never retry API errors."""
    return (
        src.get("drive_file_id") == "1-TibDNTiixhAPfEZlCBZHWS9ZlSSy93P"
        and src.get("status") == "audit_error"
        and src.get("ai_error") == "Report exceeds safe input limit; no silent truncation"
        and src.get("ai_attempted_at") == "2026-10-16T07:25+08:00"
        and not src.get("kgi_first_api_claimed_at")
        and hashlib.sha256(str(src.get("text") or "").encode()).hexdigest()
        == "33cb87ff1a95c4c8d18f9a17d744fdfb84573f070e679f64e0a7676f195c0002"
    )


def analyze_report(src: dict) -> dict:
    text = prepare_report_text(src)

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
8. summary 3~5 條，每條一句，依重要性交代核心結論、主要依據、關鍵數字與公司影響；重要前提不得省略成確定事實
9. key_points 最多 8 條，保留產業供需、規格、漲價、產能、EPS/財測等具體數字
10. beneficiaries 只列報告明確提到的受惠/首選/推薦關注個股，不能自己增加；reason 寫明受益機制與報告所列成立條件，不得將潛在供應商寫成已取得訂單
11. risks 只有報告提到或報告文字可直接支持的風險，不可自己想像
12. forecast_changes 只有明確上修/下修或財測調整才列
13. detail 依報告實際主題分段，以具體主題作純文字小標，不套用空泛固定標題。一般報告約500~900字；多主題長篇產業報告可約900~1500字，依內容需要取捨，短報告更短。各段連結結論、原因、原文依據、公司影響與成立條件，不重複羅列summary/key_points的數字。只有解釋論點必須時才重述數字，不得為湊字數加入外部資訊
14. broker、日期、標題盡量從報告本身辨識；辨識不到可留空
15. 公司名稱與代號必須依下方已驗證公司對照表，禁止自行翻譯公司中文名稱；只有英文名稱但能唯一對應也可填代號，不得把 ISU Petasys 認成台灣公司
16. 產業報告若明確提供台灣個股評等或目標價，須在 summary 優先交代；未提供時不得強行填入。評等維持與目標價變動須分開描述，不可把目標價上調當成評等上調；n.a. 為 null，不是現價
17. push_reason 是手機推播用的一句話重點，最多20字（含標點），說明報告明確提出的評等／目標價調整主因，產業報告則寫最重要的產業變化。不得重複股票名稱、代號、評等、目標價；找不到真正原因請填空字串，不得編造。

18. 數字須附原文可辨識的年度或季度、幣別、單位與比較基準；百分比說明分母，區分百分比與百分點。營收差額與淨利影響不得混用，不能把情境差額當成已發生損失
19. 清楚區分已公布事實、報告作者預估、市場共識與假設情境；情境須說明前提與相對基準。不可把市場共識寫成作者財測，也不可把推算寫成確定訂單或獲利
20. 表格文字保留了空格、欄位與換頁。辨認公司、年度、情境欄頭後才引用數字，不要跨欄或跨公司拼接；若欄列對應不確定，省略該數值並在相關段落說明無法確認，不可猜測
21. 台灣公司使用已驗證的中文名稱，國外公司保留原文名稱。公司在不同情境可能受益或受壓，應分別說明；不能將條件式受益一概寫成推薦買進
22. 不額外搜尋或加入原文沒有的推論、計算、投資建議與追蹤指標。JSON 字串中的換行必須使用合法跳脫，禁止尾逗號、註解或未加雙引號的欄位名稱

23. 輸出前在同一次分析內檢查全文主題覆蓋：依目次、章節與結論確認主要需求驅動、競爭格局/市占變化、供應鏈轉移、財測調整及風險有無遺漏。只涵蓋原文實際存在的主題，不可只整理前幾頁；歷史報告彙整與免責聲明不得當成本期新觀點
24. beneficiaries 完整列出本期正文或投資建議明確點名的受惠/首選公司，不限前8家；按代號去重。summary/detail提到的明確受惠公司應與beneficiaries一致，不能漏掉名單尾端。單純營收表列示、同業比較或歷史推薦不算本期推薦；不同情境的受益理由要保留條件
25. 完成前檢查摘要、重點、完整解析的分工：summary講核心結論，key_points提供關鍵證據，detail解釋原因與各主題連結，beneficiaries逐家公司交代原因；避免同組數字在三處重複堆砌。上述檢查在本次回覆內完成，不要求額外API呼叫

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


def short_push_reason(report: dict) -> str:
    """從已保存的解析內容取一句真實重點，不額外呼叫 AI。"""
    candidates = [report.get("push_reason")]
    candidates.extend(report.get("summary") or [])
    candidates.extend(report.get("key_points") or [])
    name = str(report.get("name") or "").strip()
    ticker = str(report.get("ticker") or "").strip()
    for candidate in candidates:
        if not isinstance(candidate, str):
            continue
        reason = re.sub(r"\s+", "", candidate.strip())
        reason = re.sub(r"^(?:原因|重點|摘要|投資重點)[：:]", "", reason)
        if name:
            reason = reason.replace(name, "")
        if ticker:
            reason = reason.replace(ticker, "")
        reason = reason.strip("｜|：:，,。;；-— ")
        # 排除只有評等、目標價、股票名稱的假摘要。
        if not reason or re.search(r"(?:目標價|目標價格|目標股價|評等|買進|賣出|中立|維持Buy|NT\$)", reason, re.I):
            continue
        if re.fullmatch(r"[\d,.%％$NT元→↑↓+\- ]+", reason, re.I):
            continue
        # 不截斷造成語意不完整的句子；優先取20字內的完整短句。
        first = re.split(r"[。；;！!？?]", reason, maxsplit=1)[0].strip("，,、 ")
        if 4 <= len(first) <= 20:
            return first
        for fragment in re.split(r"[，,、]", first):
            fragment = fragment.strip()
            if 4 <= len(fragment) <= 20 and not re.search(r"(?:目標價|評等)", fragment):
                return fragment
    return ""


def build_push(report: dict):
    broker = report.get("broker") or "券商"
    action = action_zh(report.get("action") or "none")
    reason = short_push_reason(report)

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
            lines.append(f"重點：{reason}")
        message = "\n".join(lines)
    else:
        title = "券商報告"
        first = f"{broker}｜{report.get('title') or '產業報告'}"
        lines = [first]
        if report.get("recommendation_headlines"):
            lines.extend(report["recommendation_headlines"][:8])
        if reason:
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


def recover_saved_winway(src):
    """Local repair of one verified source; no OCR/AI call and no state reset."""
    if src.get("drive_file_id") != "1ylJQqGf6s3Be0GJsYAQN7v_kP9Tbb2yt":
        return None
    if src.get("status") != "audit_error":
        return None
    digest = hashlib.sha256(str(src.get("text") or "").encode()).hexdigest()
    if digest != "03e715be97e9266ef057525a27bf765d033696d85140cc6d62616951bee84178":
        print("WinWay local repair skipped: source text changed")
        return None
    obj = {
        "report_type": "company", "primary_stock": {"ticker": "6515", "name": "穎崴"},
        "broker": "", "date": src.get("report_date", ""),
        "title": "穎崴：留意產品轉換期，維持買進、目標價下調至8,250元",
        "action": "maintain", "rating": "Buy", "target_price_old": 9000,
        "target_price_new": 8250,
        "summary": [
            "維持買進，目標價由9,000元下調至8,250元，採2027至2028年預估EPS的32倍評價",
            "9月營收月減27%，第三季營收季增29%，低於報告所列35%至40%的預期",
            "第四季營收預估由季增個位數，下修為季減中至高個位數",
            "探針卡部分專案進入出貨週期後段，測試座成長尚不足以完全抵銷放緩",
            "仍預期2027、2028年營收各年增約70%，維持中長期正向看法"
        ],
        "key_points": ["2026年EPS預估由93.40元降至90.14元",
                       "2027年EPS預估由198.55元降至183.74元",
                       "2028年EPS預估由364.67元降至331.51元"],
        "forecast_changes": ["第四季營收展望由季增改為季減", "2026年EPS預估下修約4%"],
        "risks": ["主要AI XPU的記憶體與散熱問題可能影響客戶採購及追加訂單",
                  "新專案放量延遲可能對財測造成額外下行風險"],
        "detail": "報告指出，穎崴部分探針卡專案進入出貨週期後段，測試座業務力道不足以完全抵銷放緩，因此依實際出貨模式下修第四季營收展望。主要XPU客戶的測試座與探針卡可能面臨產品轉換空窗，新專案預計明年放量，其他ASIC及XPU專案則逐步爬坡。報告將近期困難視為時程影響，並未認為底層需求發生根本改變，因此維持買進，但下調EPS預估與目標價。截圖擷取文字未明確列出券商全名，故不自行填入。",
    }
    report = audit_report(normalize_report(obj, src), src, COMPANIES)
    report["ai_model"] = "local-source-repair-no-api"
    report["repaired_at"] = now_tpe()
    return report


def recover_saved_ase(src):
    """Repair the verified Fubon ASE report from saved text, without API retries."""
    if (src.get('drive_file_id') != '1TUBTgTSSqvOFlG24JTqHYkJfRzZrZNxS'
            or src.get('status') != 'audit_error'):
        return None
    digest = hashlib.sha256(str(src.get('text') or '').encode()).hexdigest()
    if digest != '7e4c0a4374fe73fdefeb97c6b6440750c3faa6c100c5ead017e64a9a014acf28':
        print('ASE local repair skipped: source text changed')
        return None
    obj = {
        'report_type': 'company', 'primary_stock': {'ticker':'3711','name':'日月光投控'},
        'broker':'富邦投顧', 'date':'2026-10-14',
        'title':'日月光投控：LEAP成長動能增強，CPO測試帶來上行機會',
        'action':'maintain', 'rating':'Buy', 'target_price_old':750, 'target_price_new':820,
        'summary':[
            '維持買進，目標價由750元上調至820元，以2027年預估EPS的22倍評價',
            '第三季營收2,442億元，季增27.8%、年增44.8%，高於富邦原估及市場共識4.6%',
            '2026、2027年EPS預估分別上調21.2%、25.2%，至21.96元及36.65元',
            '預估2027年LEAP營收達84.1億美元、年增103%，高於報告所列市場預期75億美元',
            'LEAP模型尚未納入潛在CPO測試機會，光引擎、光電最終測試與系統層級測試提供額外上行空間',
        ],
        'key_points':[
            '第三季ATM營收1,515億元，季增20.1%，受台積電oS委外及測試業務成長帶動',
            '第三季毛利率、營業利益率、EPS預估分別為22%、13%、6.71元',
            '第四季營收、EPS預估分別為2,607億元、7.56元',
            '2027年WoS產量預估由75萬片增至147萬片，平均售價維持3,500美元',
            '報告預期2027年先進封裝產能全年滿載',
            '2027年營業利益率預估由15.2%上調至16.3%',
        ],
        'forecast_changes':[
            '2026年營收預估上調2.2%至8,696億元；2027年上調0.7%至1兆965億元',
            '2026年EPS由18.13元上調至21.96元；2027年由29.26元上調至36.65元',
            '2026、2027年毛利率預估分別由20.9%、24.2%上調至21.6%、25.3%',
        ],
        'risks':['關稅及經濟不確定性為報告列示的主要風險'],
        'detail':'富邦投顧認為日月光投控第三季營收優於預期，後續獲利上修主要由ATM產品組合改善、毛利率提升與2027年LEAP產能增加帶動，因此維持買進並將目標價由750元上調至820元。報告預估2026及2027年EPS為21.96元與36.65元，分別高於市場共識16.8%及25.5%。LEAP營收預估由2026年的41.4億美元增加至2027年的84.1億美元，受台積電委外、FoCoS與AI測試成長支持。富邦預期先進封裝2027年全年滿載，且目前模型尚未計入潛在CPO測試需求，因此將其視為基礎財測以外的上行機會。第三季毛利率仍是近期的重要驗證項目，關稅與經濟不確定性為主要風險。',
    }
    report = audit_report(normalize_report(obj, src), src, COMPANIES)
    report['ai_model'] = 'local-source-repair-no-api'
    report['repaired_at'] = now_tpe()
    return report


def recover_saved_ccl(src):
    """Repair only this verified saved PDF; no AI/OCR request or claim reset."""
    if (src.get("drive_file_id") != "1MhlNmbXCSPx4V3lqs4r-UoKURv4B3xO9"
            or src.get("status") != "audit_error"):
        return None
    digest = hashlib.sha256(str(src.get("text") or "").encode()).hexdigest()
    if digest != "a6eca6c1b25aa8533d63599898a84f8b770a6230327eb480ee44b13f5dfe4ddc":
        print("CCL local repair skipped: source text changed")
        return None
    obj = {
        "report_type": "sector", "primary_stock": {},
        "broker": "ToAlpha", "date": "2026-10-15",
        "title": "高階 CCL 樹脂系統之爭：PTFE vs 碳氫樹脂（HC）",
        "action": "sector", "rating": "",
        "target_price_old": None, "target_price_new": None,
        "summary": [
            "ToAlpha認為PTFE與碳氫樹脂將分層並存：PTFE用於最高階互連板的關鍵訊號層，其他高速板材仍以碳氫系為主",
            "高階玻纖布、HVLP銅箔與鑽針的供給瓶頸，是報告認為較不依賴樹脂路線勝負的受益環節",
            "基本PTFE混壓情境下，台光電營收較碳氫系情境減少約29至64億元，推算淨利差額約占2027年市場共識淨利1%至2%",
            "若正交背板亦採PTFE混壓，台光電營收差額擴至約183至321億元，推算淨利差額約占2027年共識6%至10%",
            "報告認為CCL報價調整的影響大於基本PTFE情境；全文屬產業研究，未提供個股評等或目標價"
        ],
        "key_points": [
            "報告假設NVL576世代交換器板CCL價值約3至5億美元，屬情境推算而非確定訂單",
            "若台虹取得兩成第二供應份額，報告推算營收約13億元、約近12個月營收12%，仍取決於認證及材料路線",
            "CCL報價上調10%的對照情境，台光電淨利敏感度約為2027年共識淨利的11%至32%",
            "南亞同時具玻纖布、銅箔與CCL布局，兼有PTFE經驗及碳氫配方",
            "觀察2026年第四季至2027年第一季材料及供應商定案，以及PTFE混壓良率與高溫壓合產能",
            "展示或合作名單不代表確定量產訂單；市場共識數字亦非ToAlpha自行提出的財測"
        ],
        "beneficiaries": [
            {"ticker":"8358", "name":"金居", "reason":"報告列為HVLP銅箔供應鏈，各樹脂情境均可能受益"},
            {"ticker":"8021", "name":"尖點", "reason":"高縱深比與塗層鑽針需求，PTFE加工耗損可能提高用量"},
            {"ticker":"8039", "name":"台虹", "reason":"PTFE路線下的潛在第二供應商，營收貢獻取決於份額及量產"},
            {"ticker":"1303", "name":"南亞", "reason":"兼具上游材料與CCL布局，可參與PTFE及碳氫兩條路線"}
        ],
        "forecast_changes": [],
        "risks": [
            "PTFE滲透及背板混壓進展超出假設，可能擴大台系CCL高階份額壓力",
            "無布化可能減少玻纖布需求；CPO導入可能降低部分板材規格",
            "擴產快於需求可能造成價格循環反轉",
            "輝達產品時程、架構、供應商認證與量產良率均可能改變情境結果",
            "市場共識與市占、單價、板材價值等假設變動，均會改變估算比例"
        ],
        "detail": "這是ToAlpha於2026年10月15日發布的純產業研究，討論高階CCL補強材、銅箔及樹脂升級。報告預期碳氫系與PTFE分層並存，並以台系CCL廠角度區分樂觀、基本及悲觀情境。文中台光電營收差額與淨利敏感度，係依市場共識及自訂假設推算，不是實際損失或已確定財測下修。台虹等PTFE供應鏈的機會亦取決於認證、第二供應份額和量產。報告另指出台燿的ASIC滲透與擴產、聯茂的產品報價及高階產能、南亞跨材料布局各有不同驅動因素，不能以單一樹脂路線概括。長期需追蹤無布化、CPO、供需及價格循環。全文未提出個股評等、目標價或買賣建議。"
    }
    report = audit_report(normalize_report(obj, src), src, COMPANIES)
    report["ai_model"] = "local-source-repair-no-api"
    report["repaired_at"] = now_tpe()
    return report


def repair_saved_kgi_coverage(report, src):
    """Source-locked editorial repair; preserve AI/send claims and never call API."""
    if (src.get("drive_file_id") != "1-TibDNTiixhAPfEZlCBZHWS9ZlSSy93P"
            or report.get("source_file_id") != src.get("drive_file_id")
            or report.get("validation_status") != "verified"
            or report.get("coverage_repair_version") == "kgi-20261015-coverage-1"
            or hashlib.sha256(str(src.get("text") or "").encode()).hexdigest()
            != "33cb87ff1a95c4c8d18f9a17d744fdfb84573f070e679f64e0a7676f195c0002"):
        return False
    names = [("2383", "台光電", "報告列為AI伺服器受惠供應商，CCL規格升級與客戶、機種多元帶動營收，亦受惠ASIC需求擴張"),
             ("3037", "欣興", "報告列為AI伺服器受惠供應商，載板規格升級及ASIC伺服器擴張提供動能"),
             ("2345", "智邦", "報告在ASIC成長段落明確列為受惠業者，相關需求涵蓋交換器與OCS等供應鏈"),
             ("3665", "貿聯-KY", "報告在ASIC成長段落明確列為受惠業者，並指出客戶與機種多元支撐營收；相關需求涵蓋高速連接與電源等供應鏈")]
    members = report.setdefault("beneficiaries", [])
    existing = {str(x.get("ticker")) for x in members}
    for ticker, name, reason in names:
        if ticker not in existing:
            members.append({"ticker":ticker, "name":name, "reason":reason})
            existing.add(ticker)
    report["summary"] = [
        "凱基上調伺服器、下修PC與智慧型手機需求預估，電子硬體景氣呈現AI強、消費性產品弱的分化",
        "VR、Trainium 3與TPU v8等新平台進入放量，GPU與ASIC方案擴張推動組裝、液冷、電源與板材規格升級",
        "報告預期2027年ASIC晶片出貨強勁成長，Nvidia雖維持主要供應商地位，晶片市占可能降至50%以下；AMD市占仍低於10%",
        "T3供應鏈調整使部分零組件短期遞延，報告視為短期現象；客戶與機種較多元的廠商營收相對強勁",
        "本期投資建議點名緯穎、緯創、鴻海、奇鋐、富世達、健策、台達電、金像電、台光電與欣興；ASIC段落另列智邦、貿聯-KY為受惠業者"
    ]
    report["detail"] = """GPU／ASIC新平台與競爭格局
凱基的主軸不只是AI伺服器總量增加，而是新平台與晶片組合改變。報告預期VR、Trainium 3及TPU v8進入放量，第四季另有MI455與T3液冷方案帶動營收。AWS與Google受惠於平價、客製化推論需求，ASIC供貨擴張；Nvidia仍是主要晶片供應商，但2027年市占可能降至50%以下，AMD雖成長，2026至2027年市占仍低於10%。這些是凱基預估，不能當成已實現市占；晶片顆數、伺服器台數與機櫃數亦為不同口徑。

供應鏈規格升級與短期遞延
報告指出，需求擴張與規格升級帶動液冷、電源、AEC、CCL／PCB／載板，以及交換器與OCS等環節。投資建議點名的組裝廠為緯穎、緯創與鴻海，零組件供應商包括奇鋐、富世達、健策、台達電、金像電、台光電及欣興，ASIC段落另列智邦與貿聯-KY。這些公司並非全都供應相同產品，不能將整組供應鏈需求逐項套到每家公司。
T3供應鏈調整造成部分零組件九月營收不如預期，凱基視為短期現象，預期第四季恢復季增。相較之下，客戶及機種較多元的奇鋐、富世達、台光電、貿聯-KY與欣興等營收較強。台達電亦受T3調整及泰國淹水出貨阻礙影響，因此不能把產業需求強直接等同每家廠商當期出貨都強。

代理型AI帶動通用伺服器
原文另強調通用伺服器需求。代理型AI需要CPU進行自主工作的協調與調度，結合推論需求、CSP資本支出及CPU下單動能，凱基預期2027年通用伺服器成長仍強，並有望優於2026年。這條成長來源與GPU／ASIC加速器不同，但記憶體、CPU及其他零組件供應仍可能限制實際交付。

PC與手機：成本上升壓抑需求
消費性IT產品面臨相反的壓力。記憶體與CPU成本上升推高終端售價，凱基因此下修PC及智慧型手機出貨預估。筆電ODM雖有季底拉貨，仍未改變第三季出貨年減與季減的疲弱趨勢，第四季也預期缺乏旺季效應。iPhone新機拉貨墊高九至十月營收，但報告認為助益可能短暫，不能把新機備貨高峰當成終端需求全面復甦。

預估成立條件與風險
伺服器展望以CSP及neocloud持續投入AI基礎建設、新平台量產、組裝良率與生產效率改善為基礎。原文明列的風險是CSP資本支出放緩、零組件供應吃緊及AI出貨遞延。應區分需求與實際交付：即使需求存在，平台轉換或供應鏈調整仍會影響營收認列時點。各年度出貨預估與調整列於重點及財測欄，不代表已確認訂單。"""
    report["coverage_repair_version"] = "kgi-20261015-coverage-1"
    report["coverage_repaired_at"] = now_tpe()
    return True


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
        if old and repair_saved_kgi_coverage(old, src):
            reports["items"] = items
            save_json(REPORTS_PATH, reports)
            print("Locally improved KGI coverage; AI calls=0; send claims preserved")
        current_text_hash = hashlib.sha256(
            str(src.get("text") or "").encode()
        ).hexdigest()

        if not old:
            repaired = recover_saved_winway(src) or recover_saved_ase(src) or recover_saved_ccl(src)
            if repaired:
                items.append(repaired)
                by_source[file_id] = repaired
                src["status"] = "done"
                src["audit_version"] = VERSION
                src["local_repaired_at"] = now_tpe()
                for key in ("ai_error", "audit_failed_version", "audit_failed_text_hash", "audit_failed_at"):
                    src.pop(key, None)
                reports["items"] = items
                save_json(REPORTS_PATH, reports)
                save_json(INBOX_PATH, inbox)
                print("Locally repaired", file_id, "from saved text; AI calls=0")
                continue

        # Strict File ID one-shot: never retry completed, failed, or claimed reports.
        # Audit version changes must NOT trigger another API call.
        kgi_first_api = is_verified_kgi_preflight_failure(src)
        if old or (not kgi_first_api and (
                src.get("status") != "pending_ai" or src.get("ai_attempted_at"))):
            continue

        # 額度用完後，本輪不再碰後續報告
        if quota_exhausted:
            break

        # Local validation happens before the durable API claim; no input truncation.
        try:
            prepare_report_text(src)
        except ValueError as exc:
            src["status"] = "audit_error"
            src["ai_error"] = str(exc)
            save_json(INBOX_PATH, inbox)
            print("Local input check failed; API calls=0:", file_id)
            continue

        if kgi_first_api:
            src["preflight_rejected_at"] = src["ai_attempted_at"]
            src["kgi_first_api_claimed_at"] = now_tpe()

        # Commit the claim to GitHub before calling OpenAI.
        # A failed push aborts the workflow without spending any API credit.
        src["ai_attempted_at"] = now_tpe()
        src["status"] = "ai_processing"
        save_json(INBOX_PATH, inbox)
        commit_claim_before_external_call("AI " + file_id)

        try:
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

    from report_digest import send_digest
    pending_notifications = [
        report for report in items
        if report.get("validation_status") == "verified"
        and not report.get("telegram_sent_at")
        and not report.get("telegram_attempted_at")
        and report.get("source_file_id")
    ]
    if pending_notifications and TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:
        # Persist every member's claim before a single network operation.
        for report in pending_notifications:
            report["telegram_attempted_at"] = now_tpe()
        reports["items"] = items
        save_json(REPORTS_PATH, reports)
        commit_claim_before_external_call("Telegram report digest")
        entries = [build_push(report)[1] for report in pending_notifications]
        if send_digest(TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID,
                       f"券商報告彙整｜新增 {len(entries)} 份", entries,
                       SITE_URL + "?page=reports"):
            for report in pending_notifications:
                report["telegram_sent_at"] = now_tpe()
            telegram_pushed = 1
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
        "每個 Drive File ID 僅嘗試一次 AI 分析；"
        "Telegram 在發送前持久化一次性 claim，失敗不自動重送。"
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

