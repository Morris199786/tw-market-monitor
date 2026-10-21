#!/usr/bin/env python3
"""Company-deduplicated daily digest; --send explicitly enables Telegram."""
import argparse
import datetime as dt
import hashlib
import json
import os
import urllib.request
from pathlib import Path
from zoneinfo import ZoneInfo
from self_report_forecast_export import load, save

def render(site, forecast, day):
    # Use exactly the website's display feed, never diagnostics or raw candidates.
    companies = {}
    for row in sorted(site.get('items', []), key=lambda r: r.get('publish_time') or ''):
        ticker = str(row.get('ticker') or '')
        if row.get('publish_date') == day and ticker and row.get('monthly_eps') is not None:
            companies[ticker] = row
    blocks = [f'今日盤後自結整理｜{day}']
    for ticker, row in sorted(companies.items()):
        monthly = f'{float(row["monthly_eps"]):g}'
        quarter = '未揭露' if row.get('quarter_eps') is None else f'{float(row["quarter_eps"]):g} 元'
        mp = row.get('monthly_period') or ''
        qp = row.get('quarter_period') or ''
        blocks.append(f'📌 {row.get("name", "")} {ticker}\n'
                      f'單月 EPS：{monthly} 元（{mp}）\n'
                      f'上一季 EPS：{quarter}'+(f'（{qp}）' if qp else ''))
    if not companies:
        blocks.append('網站目前尚無本日單月自結資訊。')
    lines = [f'下一交易日盤後可能公布自結｜{forecast["prediction_date"]}']
    for i, row in enumerate(forecast['picks'], 1):
        lines.append(f'{i}. {row.get("name", "")} {row["ticker"]}')
    if not forecast['picks']:
        lines.append('無符合條件公司')
    blocks.append('\n'.join(lines))
    return '\n\n'.join(blocks)


def chunks(text, size=1800):
    # Conservative length also accommodates UTF-16 surrogate pairs.
    return [text[i:i+size] for i in range(0, len(text), size)]

def send(text, state_path):
    token = os.environ.get('TELEGRAM_BOT_TOKEN', '').strip()
    chat = os.environ.get('TELEGRAM_CHAT_ID', '').strip()
    if not token or not chat:
        raise SystemExit('Missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID')
    state = load(state_path, {'sent': {}})
    # Ignore refresh timestamp for duplicate detection.
    stable = '\n'.join(s for s in text.splitlines() if not s.startswith('彙整今日公告；'))
    digest = hashlib.sha256((chat+'\n'+stable).encode()).hexdigest()
    for i, part in enumerate(chunks(text)):
        key = f'{digest}:{i}'
        if key in state['sent']:
            continue
        request = urllib.request.Request('https://api.telegram.org/bot'+token+'/sendMessage',
            data=json.dumps({'chat_id': chat, 'text': part}).encode(),
            headers={'Content-Type': 'application/json'})
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                result = json.load(response)
            if not result.get('ok'):
                raise RuntimeError('Telegram rejected digest')
        except Exception:
            # Never print token-bearing URLs; ambiguous sends are not auto-retried.
            raise SystemExit('Telegram delivery unconfirmed; inspect chat before retrying') from None
        state['sent'][key] = result['result']['message_id']
        save(state_path, state)

def main():
    p = argparse.ArgumentParser()
    p.add_argument('--date', default=dt.datetime.now(ZoneInfo('Asia/Taipei')).date().isoformat())
    p.add_argument('--send', action='store_true')
    a = p.parse_args()
    text = render(load('data/self_reports.json'), load('data/self_report_forecast.json'), a.date)
    Path('self_report_live').mkdir(exist_ok=True)
    Path('self_report_live/telegram_digest.txt').write_text(text, encoding='utf-8')
    if a.send:
        send(text, 'data/self_report_digest_sent.json')
    else:
        print(text)

if __name__ == '__main__':
    main()
