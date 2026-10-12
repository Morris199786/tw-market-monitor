"""Website AI performance: historical and future BAL_MA_SLOPE_RANK_HEAT25_30 only.
Uses the SAME daily ranked picks as the 36-strategy shadow engine and retains the
website's existing output keys and five exit policies.
"""
from sources import *
from statistics import median
from datetime import datetime
from pathlib import Path
import json
import subprocess
import sys
import urllib.request
import urllib.parse
import time

STRATEGY = 'BAL_MA_SLOPE_RANK_HEAT25_30'
BACKTEST_PATH = ROOT / 'data/ai_backtest.json'
SHADOW_JSON = ROOT / 'data/ai_shadow_test.json'
SHADOW_CSV = ROOT / 'data/ai_shadow_test.csv'
START = '2026-09-24'


def normalize_date(value):
    s = str(value or '').strip()
    digits = ''.join(c for c in s if c.isdigit())
    if len(digits) == 8:
        try: return datetime.strptime(digits, '%Y%m%d').strftime('%Y-%m-%d')
        except ValueError: pass
    return s


def price(v):
    try:
        n = float(str(v).replace(',', ''))
        return n if 0 < n < float('inf') else None
    except (TypeError, ValueError, OverflowError): return None


def ret(a, b):
    return round((b / a - 1) * 100, 4) if a and b else None


def market_snapshots():
    by_date = {}
    for path in sorted((ROOT / 'data/history/market').glob('*.json')):
        d = load_json(path, {})
        date = normalize_date(d.get('date') or path.stem)
        if date and isinstance(d.get('stocks'), dict) and d['stocks']:
            by_date[date] = {'date': date, 'stocks': d['stocks']}
    return [by_date[d] for d in sorted(by_date)]


def close_at(snapshots, i, ticker):
    if i < 0 or i >= len(snapshots): return None
    return price(snapshots[i]['stocks'].get(ticker, {}).get('price'))


def last_close(snapshots, i, ticker):
    for j in range(i, -1, -1):
        v = close_at(snapshots, j, ticker)
        if v is not None: return v, snapshots[j]['date']
    return None, None


def moving_average(snapshots, i, ticker, window):
    values = []
    for j in range(i, -1, -1):
        v = close_at(snapshots, j, ticker)
        if v is not None: values.append(v)
        if len(values) == window: return sum(values) / window
    return None


def evaluate(rec, snapshots, indices):
    idx = indices.get(rec['selection_date'])
    entry = price(rec['entry_price'])
    ticker = rec['ticker']
    for days in (5, 10):
        matured = idx is not None and idx + days < len(snapshots)
        target, end_date = last_close(snapshots, idx + days, ticker) if matured else (None, None)
        for prefix in ('baseline_', '', 'ma20_', 'stop5_', 'stop10_'):
            status = 'pending' if not matured else 'unavailable'
            result = None
            exit_date = None
            if matured:
                exit_price = target
                exit_date = end_date
                if prefix != 'baseline_':
                    for j in range(idx + 1, idx + days + 1):
                        c = close_at(snapshots, j, ticker)
                        if c is None: continue
                        triggered = False
                        if prefix in ('', 'ma20_'):
                            ma = moving_average(snapshots, j, ticker, 10 if prefix == '' else 20)
                            triggered = ma is not None and c < ma
                        elif prefix == 'stop5_': triggered = entry is not None and c <= entry * .95
                        elif prefix == 'stop10_': triggered = entry is not None and c <= entry * .90
                        if triggered:
                            exit_price, exit_date = c, snapshots[j]['date']
                            break
                result = ret(entry, exit_price)
                status = 'complete' if result is not None else 'unavailable'
            rec[f'{prefix}return_{days}d'] = result
            rec[f'{prefix}status_{days}d'] = status
            rec[f'{prefix}end_date_{days}d'] = exit_date
    return rec


def stats(rows, days, prefix):
    values = [r.get(f'{prefix}return_{days}d') for r in rows
              if r.get(f'{prefix}status_{days}d') == 'complete']
    values = [float(v) for v in values if v is not None]
    return {'avg_return': round(sum(values) / len(values), 4) if values else None,
            'median_return': round(median(values), 4) if values else None,
            'win_rate': round(100 * sum(v > 0 for v in values) / len(values), 2) if values else None,
            'samples': len(values)}


def summary(rows, prefix):
    def block(subset): return {f'{d}d': stats(subset, d, prefix) for d in (5, 10)}
    return {'all': block(rows),
            'twse': block([r for r in rows if r['market'] == 'twse']),
            'tpex': block([r for r in rows if r['market'] == 'tpex']),
            'rank_buckets': {f'top{n}': block([r for r in rows if r['rank'] <= n]) for n in (5, 10, 20)}}


def fetch_tpex_close(date):
    url = 'https://www.tpex.org.tw/www/zh-tw/afterTrading/indexSummary?' + urllib.parse.urlencode({'date': date.replace('-', '/'), 'response': 'json'})
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0', 'Accept': 'application/json'})
    with urllib.request.urlopen(req, timeout=18) as response: payload = json.load(response)
    for table in payload.get('tables', []):
        rows = table.get('data') or []
        for row in rows:
            if isinstance(row, list) and row and str(row[0]).strip() == '櫃買指數':
                return price(row[1] if len(row) > 1 else None)
        if rows: break
    return None


def benchmark_closes(snapshots, old, records):
    valid_dates = {x['date'] for x in snapshots}
    cache = old.get('benchmark_index_closes', {})
    result = {m: {d: price(v) for d, v in (cache.get(m, {}) or {}).items()
                  if d in valid_dates and price(v)} for m in ('twse', 'tpex')}
    monitor = load_json(ROOT / 'data/market_monitor.json', {})
    for row in monitor.get('raw', []):
        d = normalize_date(row.get('date'))
        v = price(row.get('index'))
        if d in valid_dates and v: result['twse'][d] = v
    indices = {x['date']: i for i, x in enumerate(snapshots)}
    needed = set()
    for r in records:
        idx = indices.get(r['selection_date'])
        if idx is None: continue
        for days in (5, 10):
            if idx + days < len(snapshots):
                needed.update((snapshots[idx]['date'], snapshots[idx + days]['date']))
    for date in sorted(needed - set(result['tpex'])):
        try:
            v = fetch_tpex_close(date)
            if v: result['tpex'][date] = v
        except Exception as exc:
            print('TPEx index unavailable', date, str(exc)[:120])
        time.sleep(.15)
    return result


def benchmark_summary(records, snapshots, closes):
    indices = {x['date']: i for i, x in enumerate(snapshots)}
    result = {}
    for days in (5, 10):
        eligible = [r for r in records if r.get(f'baseline_status_{days}d') == 'complete']
        result[f'{days}d'] = {}
        for market in ('twse', 'tpex'):
            vals = []
            for r in eligible:
                idx = indices.get(r['selection_date'])
                if idx is None or idx + days >= len(snapshots): continue
                v = ret(closes[market].get(snapshots[idx]['date']), closes[market].get(snapshots[idx + days]['date']))
                if v is not None: vals.append(v)
            result[f'{days}d'][market] = {'avg_return': round(sum(vals) / len(vals), 4) if vals else None,
                                           'samples': len(vals), 'expected_samples': len(eligible)}
    return result


def shadow_picks():
    # Rebuild all historical selections with the EXACT experimental scoring engine.
    # This intentionally does not use the old strategy's stored picks.
    shadow = ROOT / 'ai_shadow_backtest.py'
    if not shadow.exists(): raise RuntimeError('Missing ai_shadow_backtest.py')
    subprocess.run([sys.executable, str(shadow)], cwd=str(ROOT), check=True)
    data = load_json(SHADOW_JSON, {})
    daily = data.get('daily_picks', {})
    if not daily: raise RuntimeError('Shadow strategy produced no historical selections')
    rows = []
    for date, markets in sorted(daily.items()):
        if date < START: continue
        for market in ('twse', 'tpex'):
            picks = markets.get(market, {}).get(STRATEGY, [])
            if not picks: continue
            for x in picks:
                entry = price(x.get('entry_price'))
                if entry is None: continue
                rows.append({'selection_date': date, 'market': market,
                             'ticker': str(x['ticker']), 'name': x.get('name') or str(x['ticker']),
                             'rank': int(x['rank']), 'score': x.get('score'), 'entry_price': entry,
                             'strategy': STRATEGY})
    if not rows: raise RuntimeError('No historical B picks found')
    return rows, data


def main():
    old = load_json(BACKTEST_PATH, {})
    snapshots = market_snapshots()
    if not snapshots: raise RuntimeError('Missing historical market snapshots')
    rows, shadow = shadow_picks()
    indices = {x['date']: i for i, x in enumerate(snapshots)}
    records = [evaluate(r, snapshots, indices) for r in rows]
    records.sort(key=lambda r: (r['selection_date'], r['market'], -r['rank']), reverse=True)
    dates = sorted({r['selection_date'] for r in records})
    if dates[-1] != snapshots[-1]['date']:
        raise RuntimeError(f'Shadow latest selection {dates[-1]} != market latest {snapshots[-1]["date"]}; refusing stale backtest')
    closes = benchmark_closes(snapshots, old, records)
    result = {
        'updated_at': now_tpe().isoformat(timespec='minutes'),
        'strategy': STRATEGY, 'strategy_name': '放寬B',
        'method': {
            'strategy': '所有歷史選股均以放寬B重新選股，不混用舊策略推薦紀錄',
            'entry': 'AI選股基準交易日收盤價',
            'return_5d': '推薦後第1日起收盤跌破MA10出場，否則第5個交易日收盤結算；第5日後才計入統計',
            'return_10d': '推薦後第1日起收盤跌破MA10出場，否則第10個交易日收盤結算；第10日後才計入統計',
            'ma20': '收盤跌破20日均線出場，分別計算5日及10日績效',
            'stop5': '首次收盤價低於或等於買進價95%時以當日收盤價出場，否則持有至期滿',
            'stop10': '首次收盤價低於或等於買進價90%時以當日收盤價出場，否則持有至期滿',
            'stop_execution': '收盤觸發、收盤成交模型；跳空可能使實際損失超過門檻',
            'calendar_basis': '交易日，不是日曆日',
            'baseline': 'baseline_return_5d/10d 為固定持有',
            'benchmark': '指數與同批已滿期選股訊號加權比較',
            'notes': ['歷史選股由放寬B重新計算，非實際當日留存訊號，使用目前股票池定義，有存活者偏差',
                      '推薦當日收盤價買進，同日法人資料可能尚未可用，未計成本與滑價',
                      '同股票不同推薦日期視為不同樣本，報酬區間可能重疊',
                      '只有滿5/10個交易日的樣本才計入績效'],
        },
        'start_date': dates[0], 'latest_selection_date': dates[-1],
        'selection_days': len(dates), 'record_count': len(records),
        'summary': summary(records, ''), 'ma10_summary': summary(records, ''),
        'ma20_summary': summary(records, 'ma20_'),
        'baseline_summary': summary(records, 'baseline_'),
        'stop5_summary': summary(records, 'stop5_'),
        'stop10_summary': summary(records, 'stop10_'),
        'benchmark_summary': benchmark_summary(records, snapshots, closes),
        'benchmark_index_closes': closes, 'records': records,
    }
    save_json(BACKTEST_PATH, result)
    # Shadow artifacts belong to its separate workflow; do not commit 36-strategy
    # output through the website's daily close action.
    for p in (SHADOW_JSON, SHADOW_CSV):
        if p.exists(): p.unlink()
    print('AI B backtest:', len(dates), 'dates,', len(records), 'picks')
    for key in ('baseline_summary', 'ma10_summary', 'ma20_summary', 'stop5_summary', 'stop10_summary'):
        print(key, result[key]['all'])


if __name__ == '__main__': main()
