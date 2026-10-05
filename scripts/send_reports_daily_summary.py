from __future__ import annotations

import json
import os
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import requests


ROOT = Path(__file__).resolve().parents[1]
TZ = ZoneInfo("Asia/Taipei")

REPORTS_PATH = ROOT / "data/reports.json"
STATE_PATH = ROOT / "data/reports_daily_summary_sent.json"

TELEGRAM_BOT_TOKEN = os.environ.get(
    "TELEGRAM_BOT_TOKEN",
    "",
).strip()

TELEGRAM_CHAT_ID = os.environ.get(
    "TELEGRAM_CHAT_ID",
    "",
).strip()

SITE_URL = os.environ.get(
    "REPORT_SITE_URL",
    "https://morris199786.github.io/tw-market-monitor/",
).rstrip("/") + "/"

MAX_TEXT_LEN = 3600


def now_tpe():
    return datetime.now(TZ)


def load_json(path, default):
    p = Path(path)

    if not p.exists():
        return default

    try:
        return json.loads(
            p.read_text(
                encoding="utf-8",
            )
        )
    except Exception:
        return default


def save_json(path, data):
    p = Path(path)

    p.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    p.write_text(
        json.dumps(
            data,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def action_zh(action):
    return {
        "upgrade": "上調",
        "downgrade": "下調",
        "initiate": "初評",
        "maintain": "維持",
        "sector": "產業",
        "none": "",
    }.get(
        str(action or "").strip(),
        "",
    )


def fmt_num(v):
    if v is None:
        return ""

    try:
        x = float(v)
    except Exception:
        return str(v)

    if x.is_integer():
        return f"{int(x):,}"

    return (
        f"{x:,.2f}"
        .rstrip("0")
        .rstrip(".")
    )


def target_text(report):
    old = report.get(
        "target_price_old"
    )

    new = report.get(
        "target_price_new"
    )

    if (
        old is not None
        and new is not None
    ):
        if str(old) == str(new):
            return (
                "目標價 "
                + fmt_num(new)
            )

        return (
            "目標價 "
            + fmt_num(old)
            + " → "
            + fmt_num(new)
        )

    if new is not None:
        return (
            "目標價 "
            + fmt_num(new)
        )

    return "目標價未提供"


def rating_text(report):
    action = action_zh(
        report.get("action")
    )

    rating = str(
        report.get("rating")
        or ""
    ).strip()

    parts = []

    if action:
        parts.append(
            action
        )

    if rating:
        parts.append(
            rating
        )

    return " ".join(
        parts
    )


def short_reason(report):
    reason = str(
        report.get("push_reason")
        or ""
    ).strip()

    if not reason:
        summary = (
            report.get("summary")
            or []
        )

        if summary:
            reason = str(
                summary[0]
            ).strip()

    if len(reason) > 52:
        reason = (
            reason[:52]
            + "…"
        )

    return reason


def company_block(
    name,
    ticker,
    reports,
):
    lines = [
        f"📌 {name} {ticker}".strip()
    ]

    for r in reports:
        broker = str(
            r.get("broker")
            or "券商"
        ).strip()

        rating = rating_text(
            r
        )

        tp = target_text(
            r
        )

        head = f"• {broker}"

        if rating:
            head += (
                f"｜{rating}"
            )

        head += (
            f"｜{tp}"
        )

        lines.append(
            head
        )

        reason = short_reason(
            r
        )

        if reason:
            lines.append(
                f"  {reason}"
            )

    return "\n".join(
        lines
    )


def sector_block(report):
    broker = str(
        report.get("broker")
        or "券商"
    ).strip()

    title = str(
        report.get("title")
        or "產業報告"
    ).strip()

    reason = short_reason(
        report
    )

    lines = [
        f"📌 產業／主題｜{broker}",
        f"• {title}",
    ]

    if report.get("recommendation_headlines"):
        lines.extend("• " + line for line in report["recommendation_headlines"])
    elif reason:
        lines.append(
            f"  {reason}"
        )

    return "\n".join(
        lines
    )


def date_window(now):
    """
    週一～週五：只整理當天
    週六：不送
    週日：整合週六＋週日
    """
    weekday = now.weekday()
    today = now.date()

    if weekday == 5:
        return None

    if weekday == 6:
        start = (
            today
            - timedelta(days=1)
        )
        end = today

        return {
            "start": start,
            "end": end,
            "state_key": (
                f"weekend|{end.isoformat()}"
            ),
            "label": (
                f"{start.strftime('%Y/%m/%d')}–"
                f"{end.strftime('%m/%d')} 週末總整理"
            ),
        }

    return {
        "start": today,
        "end": today,
        "state_key": (
            f"daily|{today.isoformat()}"
        ),
        "label": (
            f"{today.strftime('%Y/%m/%d')} 當日總整理"
        ),
    }


def report_in_window(
    report,
    start,
    end,
):
    raw = str(
        report.get("group_date")
        or ""
    ).strip()

    try:
        d = datetime.strptime(
            raw,
            "%Y-%m-%d",
        ).date()
    except Exception:
        return False

    return (
        start
        <= d
        <= end
    )


def received_key(x):
    return str(
        x.get("received_at")
        or x.get("ai_processed_at")
        or ""
    )


def build_chunks(
    label,
    reports,
):
    if not reports:
        return [
            (
                f"券商報告｜{label}\n"
                "今日沒有報告"
            )
        ]

    companies = defaultdict(
        list
    )

    sectors = []

    for r in reports:
        ticker = str(
            r.get("ticker")
            or ""
        ).strip()

        report_type = str(
            r.get("report_type")
            or ""
        ).strip()

        if (
            report_type == "company"
            and ticker
        ):
            companies[
                ticker
            ].append(
                r
            )
        else:
            sectors.append(
                r
            )

    blocks = []

    ordered_companies = sorted(
        companies.items(),
        key=lambda kv: min(
            (
                received_key(x)
                for x in kv[1]
            ),
            default="",
        ),
    )

    for ticker, arr in ordered_companies:
        arr.sort(
            key=received_key
        )

        name = next(
            (
                str(
                    x.get("name")
                    or ""
                ).strip()
                for x in arr
                if x.get("name")
            ),
            "",
        )

        blocks.append(
            company_block(
                name,
                ticker,
                arr,
            )
        )

    sectors.sort(
        key=received_key
    )

    for r in sectors:
        blocks.append(
            sector_block(
                r
            )
        )

    header = (
        f"券商報告｜{label}\n"
        f"共 {len(reports)} 份報告｜"
        f"{len(companies)} 檔個股"
    )

    chunks = []
    current = header

    for block in blocks:
        candidate = (
            current
            + "\n\n"
            + block
        )

        if (
            len(candidate)
            > MAX_TEXT_LEN
            and current != header
        ):
            chunks.append(
                current
            )

            current = (
                f"券商報告｜{label}（續）\n\n"
                + block
            )
        else:
            current = candidate

    if current:
        chunks.append(
            current
        )

    return chunks


def send_telegram(text):
    if (
        not TELEGRAM_BOT_TOKEN
        or not TELEGRAM_CHAT_ID
    ):
        raise RuntimeError(
            "Telegram secrets missing"
        )

    url = (
        SITE_URL
        + "?page=reports"
    )

    r = requests.post(
        (
            "https://api.telegram.org/"
            f"bot{TELEGRAM_BOT_TOKEN}/"
            "sendMessage"
        ),
        data={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": text,
            "disable_web_page_preview": True,
            "reply_markup": json.dumps(
                {
                    "inline_keyboard": [
                        [
                            {
                                "text": "開啟券商報告",
                                "url": url,
                            }
                        ]
                    ]
                },
                ensure_ascii=False,
            ),
        },
        timeout=30,
    )

    r.raise_for_status()

    data = r.json()

    if not data.get(
        "ok"
    ):
        raise RuntimeError(
            "Telegram rejected message"
        )


def main():
    now = now_tpe()

    window = date_window(
        now
    )

    if window is None:
        print(
            "Saturday: skip daily summary. "
            "Saturday reports will be included on Sunday."
        )
        return

    reports_data = load_json(
        REPORTS_PATH,
        {
            "items": [],
        },
    )

    state = load_json(
        STATE_PATH,
        {
            "sent_keys": [],
        },
    )

    sent_keys = set(
        state.get(
            "sent_keys",
            [],
        )
    )

    state_key = window[
        "state_key"
    ]

    force_send = (
        os.environ.get(
            "FORCE_SEND",
            "",
        ).strip()
        == "1"
    )

    if (
        state_key in sent_keys
        and not force_send
    ):
        print(
            "Summary already sent:",
            state_key,
        )
        return

    selected_reports = [
        r
        for r in (
            reports_data.get(
                "items",
                [],
            )
            or []
        )
        if r.get("validation_status") != "needs_review" and report_in_window(
            r,
            window["start"],
            window["end"],
        )
    ]

    selected_reports.sort(
        key=received_key
    )

    chunks = build_chunks(
        window["label"],
        selected_reports,
    )

    for idx, text in enumerate(
        chunks,
        start=1,
    ):
        send_telegram(
            text
        )

        print(
            "Telegram summary sent",
            idx,
            "/",
            len(chunks),
        )

    sent_keys.add(
        state_key
    )

    state[
        "updated_at"
    ] = now.isoformat(
        timespec="minutes"
    )

    state[
        "sent_keys"
    ] = sorted(
        sent_keys
    )[-500:]

    state[
        "last_sent_key"
    ] = state_key

    state[
        "last_window_start"
    ] = window[
        "start"
    ].isoformat()

    state[
        "last_window_end"
    ] = window[
        "end"
    ].isoformat()

    state[
        "last_report_count"
    ] = len(
        selected_reports
    )

    save_json(
        STATE_PATH,
        state,
    )

    print(
        "Broker summary complete:",
        state_key,
        "reports=",
        len(selected_reports),
    )


if __name__ == "__main__":
    main()

