"""One-time Telegram text replay of the 39 earnings announced on 2026-11-10.

This is a bounded replay of the original sent ledger delta (15:16 to 16:36),
not a second earnings data crawl.  Never alter the original sent ledger.
"""
import argparse
import json
import os
from pathlib import Path

from report_digest import make_batches, utf16_len

ROOT = Path(__file__).resolve().parents[1]
EARNINGS = ROOT / 'data/quarterly_earnings.json'
ORIGINAL_SENT = ROOT / 'data/quarterly_earnings_sent.json'
REPLAY_LEDGER = ROOT / 'data/earnings_replay_20261110.json'
DATE = '2026-11-10'
TICKERS = '''1560 2049 2356 2367 2428 2493 3010 3017 3024 3025
3044 3085 3276 3305 3308 3357 3523 3597 4760 4931
4933 4958 5210 5278 5309 5355 5388 6194 6763 6825
6829 6953 7722 7734 8038 8047 8111 8150 8410'''.split()
assert len(TICKERS) == len(set(TICKERS)) == 39


def metric(value, unit=''):
    if value is None:
        return '單季資料待補'
    return f'{float(value):.2f}{unit}'


def entry(row):
    return (f"📊 {row['name']} {row['ticker']}｜財報公布\n"
            f"本季 {row['period']}\n"
            f"毛利率：{metric(row.get('gross_margin'), '%')}\n"
            f"EPS：{metric(row.get('eps'), ' 元')}\n\n"
            f"上一季 {row['prev_period']}\n"
            f"毛利率：{metric(row.get('prev_gross_margin'), '%')}\n"
            f"EPS：{metric(row.get('prev_eps'), ' 元')}"+
            ('\n來源：當日新聞備援（非官方公告事件）' if row.get('source') == 'news_backup' else '')+
            ('\nEPS 含累計差額推算值' if 'cumulative_difference' in
             (row.get('eps_basis'),row.get('prev_eps_basis')) else ''))


def atomic_json(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + '.tmp')
    temp.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    temp.replace(path)


def build():
    data = json.loads(EARNINGS.read_text(encoding='utf-8'))
    already = json.loads(ORIGINAL_SENT.read_text(encoding='utf-8'))
    sent = set(already.get('ids', []))
    rows = {}
    for row in data.get('reports', []):
        ticker = str(row.get('ticker', ''))
        if row.get('publish_date') == DATE and row.get('period') == '2026-Q3' and ticker in TICKERS:
            if ticker in rows:
                raise RuntimeError(f'multiple source reports for {ticker}')
            rows[ticker] = row
    missing = sorted(set(TICKERS) - rows.keys())
    missing_sent = [t for t in TICKERS if f'report|{t}|2026-Q3|{DATE}' not in sent]
    if missing or missing_sent:
        raise RuntimeError(f'REPLAY_ABORT_MISSING: reports={missing}, original_sent={missing_sent}')
    return [entry(rows[t]) for t in TICKERS]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    entries = build()
    # Keep explicit 10/10/10/9 groups; extremely long individual entries are
    # rejected rather than allowing 5+ messages and accidentally reordering.
    groups = [entries[i:i+10] for i in range(0, len(entries), 10)]
    assert [len(x) for x in groups] == [10,10,10,9]
    title = '📊 財報公布｜2026-11-10｜39 筆（補發）'
    messages = []
    for idx, group in enumerate(groups, 1):
        message = f'{title}｜第 {idx}/4 則\n\n' + '\n\n'.join(group)
        if utf16_len(message) > 3900:
            raise RuntimeError('REPLAY_ABORT_MESSAGE_TOO_LONG: group '+str(idx))
        messages.append(message)
    state = {'date':DATE,'tickers':TICKERS,'sent_batches':[]}
    if REPLAY_LEDGER.exists():
        state = json.loads(REPLAY_LEDGER.read_text(encoding='utf-8'))
        if state.get('date') != DATE or state.get('tickers') != TICKERS:
            raise RuntimeError('REPLAY_LEDGER_MISMATCH')
    done = set(state.get('sent_batches', []))
    print('REPLAY_39_VERIFIED',len(entries),'groups',[len(x) for x in groups], 'already_sent',sorted(done))
    if args.dry_run:
        print('REPLAY_DRY_RUN_NO_TELEGRAM')
        return
    token = os.getenv('TELEGRAM_BOT_TOKEN','').strip()
    chat = os.getenv('TELEGRAM_CHAT_ID','').strip()
    if not token or not chat:
        raise RuntimeError('TELEGRAM_SECRETS_MISSING')
    import requests
    url = 'https://morris199786.github.io/tw-market-monitor/?page=selfReports'
    for i, msg in enumerate(messages, 1):
        if i in done:
            print('REPLAY_ALREADY_SENT',i)
            continue
        payload = {'chat_id':chat,'text':msg,'disable_web_page_preview':True,
                   'reply_markup':json.dumps({'inline_keyboard':[[{'text':'查看完整內容','url':url}]]},ensure_ascii=False)}
        res = requests.post(f'https://api.telegram.org/bot{token}/sendMessage',data=payload,timeout=30)
        res.raise_for_status()
        obj=res.json()
        if not obj.get('ok'):
            raise RuntimeError('TELEGRAM_REJECTED_GROUP_'+str(i))
        done.add(i)
        state['sent_batches'] = sorted(done)
        state.setdefault('telegram_messages',{})[str(i)] = obj.get('result',{}).get('message_id')
        atomic_json(REPLAY_LEDGER,state)
        print('REPLAY_SENT',i,'/',len(groups),'entries',len(groups[i-1]))
    print('REPLAY_COMPLETE',len(done),'of',len(groups))


if __name__ == '__main__':
    main()
