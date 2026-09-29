from __future__ import annotations

import argparse
import json
import os
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

ROOT = Path(__file__).resolve().parents[1]
TZ = ZoneInfo("Asia/Taipei")

BOT = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
CHAT = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
SITE = os.environ.get(
    "REPORT_SITE_URL",
    "https://morris199786.github.io/tw-market-monitor/",
).rstrip("/") + "/"

CONFIG = {
    "flows": ("籌碼日報", "data/institutional.json", "flows"),
    "volume": ("突然放量", "data/volume.json", "volume"),
    "turnover": ("成交排行", "data/turnover.json", "turnover"),
    "marginLending": ("融資／借券", "data/margin_lending.json", "marginLending"),
    "holders": ("大戶籌碼", "data/holders.json", "holders"),
}


def load_json(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return {}


def fmt_date(v):
    s = str(v or "").strip()
    if len(s) == 8 and s.isdigit():
        return f"{s[:4]}-{s[4:6]}-{s[6:8]}"
    return s


def fmt_time(v):
    if not v:
        return datetime.now(TZ).strftime("%Y-%m-%d %H:%M")

    s = str(v).strip()
    try:
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=TZ)
        return dt.astimezone(TZ).strftime("%Y-%m-%d %H:%M")
    except Exception:
        return s.replace("T", " ")[:16]


def send(key):
    if key not in CONFIG:
        raise RuntimeError(f"Unknown page: {key}")
    if not BOT or not CHAT:
        raise RuntimeError("Telegram secrets missing")

    title, file_name, page = CONFIG[key]
    data = load_json(ROOT / file_name)

    lines = [f"{title}｜更新完成"]
    if data.get("date"):
        lines.append(f"資料日期：{fmt_date(data.get('date'))}")
    lines.append(f"最後更新：{fmt_time(data.get('updated_at'))}")

    url = SITE + f"?page={page}"

    r = requests.post(
        f"https://api.telegram.org/bot{BOT}/sendMessage",
        data={
            "chat_id": CHAT,
            "text": "\n".join(lines),
            "disable_web_page_preview": True,
            "reply_markup": json.dumps(
                {"inline_keyboard": [[{"text": f"開啟{title}", "url": url}]]},
                ensure_ascii=False,
            ),
        },
        timeout=30,
    )
    r.raise_for_status()
    if not r.json().get("ok"):
        raise RuntimeError(f"Telegram rejected: {r.text[:500]}")
    print("Telegram sent:", title)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("page", choices=CONFIG.keys())
    send(parser.parse_args().page)
