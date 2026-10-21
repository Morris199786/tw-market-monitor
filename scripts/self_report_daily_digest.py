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
from self_report_v17_settle_actuals import all_items

def metric(item, prefix):
    value = item.get(prefix+'_eps')
    period = item.get(prefix+'_period') or '期間未解析'
    yoy = item.get(prefix+'_eps_yoy_text')
    if not yoy and item.get(prefix+'_eps_yoy') is not None:
        yoy = f"{float(item[prefix+'_eps_yoy']):+.2f}%"
    eps = '未解析／未揭露' if value is None else f'{float(value):g} 元'
    return f'{period}：{eps}；年增減 {yoy or "未揭露"}'

def render(history, forecast, day):
    # Prefer latest announcement, with parsed record winning over its diagnostics copy.
    companies = {}
    for row in sorted(all_items(history), key=lambda r: (
            r.get('publish_time') or '', r.get('monthly_eps') is not None,
            r.get('quarter_eps') is not None)):
        ticker = str(row.get('ticker') or '')
        if row.get('publish_date') == day and ticker:
            companies[ticker] = row
    lines = [f'今日盤後自結整理（{day}）', '彙整今日公告；資料截至 '+history['updated_at']]
    for i, (ticker, row) in enumerate(sorted(companies.items()), 1):
        lines += [f'{i}. {ticker} {row.get("name", "")}',
                  '   單月 EPS '+metric(row, 'monthly'),
                  '   最近公告單季 EPS '+metric(row, 'quarter')]
    if not companies:
        lines += ['截至抓取時間，網站尚無本日自結公告。']
    lines += ['', f'下一交易日盤後可能公布自結（{forecast["prediction_date"]}）']
    for i, row in enumerate(forecast['picks'], 1):
        lines += [f'{i}. {row["ticker"]} {row.get("name", "")}（'+
                  ('上市' if row['market']=='twse' else '上櫃')+'）']
    if not forecast['picks']:
        lines += ['無符合條件公司']
    settled = forecast.get('forward_settlements', {}).get(day)
    lines += ['', '今日預測核對（僅注意交易觸發自結）']
    if not settled:
        lines += ['待核對／沒有事前保存的今日預測，不用明日名單回填。']
    else:
        def pct(v):
            return '—' if v is None else f'{v:.2%}'
        for market, label in [('twse', '上市'), ('tpex', '上櫃')]:
            m = settled['metrics'][market]
            lines += [f'{label}：命中 {m["hits"]}/{m["predictions"]}；實際 {m["actual"]} 家；命中率 {pct(m["precision"])}；召回率 {pct(m["recall"])}']
        if settled.get('provisional'):
            lines += ['本日為暫結，後續抓取會補入晚到／更正公告。']
    return '\n'.join(lines)

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
    text = render(load('data/self_reports_history.json'), load('data/self_report_forecast.json'), a.date)
    Path('self_report_live').mkdir(exist_ok=True)
    Path('self_report_live/telegram_digest.txt').write_text(text, encoding='utf-8')
    if a.send:
        send(text, 'data/self_report_digest_sent.json')
    else:
        print(text)

if __name__ == '__main__':
    main()
