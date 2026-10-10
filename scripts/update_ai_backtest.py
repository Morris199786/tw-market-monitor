from sources import *
from statistics import median
from datetime import datetime
import json
import urllib.request
import urllib.parse
import time

BACKTEST_PATH = ROOT / 'data/ai_backtest.json'
MARKET_HISTORY_DIR = ROOT / 'data/history/market'


def normalize_date(value):
    s = str(value or '').strip()
    digits = ''.join(c for c in s if c.isdigit())
    if len(digits) == 8:
        try:
            return datetime.strptime(digits, '%Y%m%d').strftime('%Y-%m-%d')
        except ValueError:
            pass
    return s


def market_snapshots():
    by_date = {}
    for p in sorted(MARKET_HISTORY_DIR.glob('*.json')):
        d = load_json(p, {})
        date = normalize_date(d.get('date') or p.stem)
        stocks = d.get('stocks', {})
        if date and isinstance(stocks, dict) and stocks:
            by_date[date] = {'date': date, 'stocks': stocks}
    return [by_date[k] for k in sorted(by_date)]


def valid_price(v):
    try:
        x = float(str(v).replace(',', ''))
        return x if 0 < x < float('inf') else None
    except (TypeError, ValueError, OverflowError):
        return None


def pct_return(entry, exit_price):
    if not entry or not exit_price:
        return None
    return round((float(exit_price) / float(entry) - 1) * 100, 4)


def price_at(snapshots, idx, ticker):
    if idx < 0 or idx >= len(snapshots):
        return None
    stock = snapshots[idx]['stocks'].get(ticker, {})
    return valid_price(stock.get('price')) if isinstance(stock, dict) else None


def ma_at(snapshots, idx, ticker, window):
    values = []
    for j in range(idx, -1, -1):
        price = price_at(snapshots, j, ticker)
        if price is not None:
            values.append(price)
        if len(values) == window:
            return sum(values) / window
    return None


def latest_price_on_or_before(snapshots, idx, ticker):
    for j in range(idx, -1, -1):
        price = price_at(snapshots, j, ticker)
        if price is not None:
            return price, snapshots[j]['date']
    return None, None


def find_exit(snapshots, idx, ticker, window):
    for j in range(idx + 1, min(idx + 10, len(snapshots) - 1) + 1):
        close = price_at(snapshots, j, ticker)
        ma = ma_at(snapshots, j, ticker, window)
        if close is not None and ma is not None and close < ma:
            return j, close, ma
    return None, None, None


def find_percent_stop(snapshots, idx, ticker, entry, threshold_pct):
    if entry is None:
        return None, None
    trigger = entry * (1 - threshold_pct / 100)
    for j in range(idx + 1, min(idx + 10, len(snapshots) - 1) + 1):
        close = price_at(snapshots, j, ticker)
        if close is not None and close <= trigger:
            return j, close
    return None, None


def evaluate_record(rec, snapshots, date_index):
    selection_date = normalize_date(rec.get('selection_date'))
    ticker = str(rec.get('ticker') or '')
    idx = date_index.get(selection_date)
    if idx is None:
        for prefix in ('', 'baseline_', 'ma20_', 'stop5_', 'stop10_'):
            for days in (5, 10):
                rec[f'{prefix}return_{days}d'] = None
                rec[f'{prefix}status_{days}d'] = 'unavailable'
        return rec
    entry = valid_price(rec.get('entry_price'))
    exits = {window: find_exit(snapshots, idx, ticker, window) for window in (10, 20)}
    for window in (10, 20):
        exit_idx, exit_price, exit_ma = exits[window]
        tag = f'ma{window}'
        rec[f'{tag}_exit_date'] = snapshots[exit_idx]['date'] if exit_idx is not None else None
        rec[f'{tag}_exit_price'] = exit_price
        rec[f'{tag}_exit_value'] = round(exit_ma, 4) if exit_ma is not None else None
        rec[f'{tag}_exit_day'] = exit_idx - idx if exit_idx is not None else None
    stop_exits = {pct: find_percent_stop(snapshots, idx, ticker, entry, pct) for pct in (5, 10)}
    for pct, (stop_idx, stop_price) in stop_exits.items():
        rec[f'stop{pct}_exit_date'] = snapshots[stop_idx]['date'] if stop_idx is not None else None
        rec[f'stop{pct}_exit_price'] = stop_price
        rec[f'stop{pct}_exit_day'] = stop_idx - idx if stop_idx is not None else None
    for days in (5, 10):
        target_idx = idx + days
        matured = target_idx < len(snapshots)
        baseline_price, effective_date = (latest_price_on_or_before(snapshots, target_idx, ticker) if matured else (None, None))
        baseline_return = pct_return(entry, baseline_price) if matured else None
        rec[f'baseline_return_{days}d'] = baseline_return
        rec[f'baseline_status_{days}d'] = ('pending' if not matured else 'complete' if baseline_return is not None else 'unavailable')
        for window, prefix in ((10, ''), (20, 'ma20_')):
            exit_idx, exit_price, _ = exits[window]
            if not matured:
                rec[f'{prefix}return_{days}d'] = None
                rec[f'{prefix}status_{days}d'] = 'pending'
                rec[f'{prefix}end_date_{days}d'] = None
                continue
            early = exit_idx is not None and exit_idx <= target_idx
            result = pct_return(entry, exit_price if early else baseline_price)
            rec[f'{prefix}return_{days}d'] = result
            rec[f'{prefix}status_{days}d'] = 'complete' if result is not None else 'unavailable'
            rec[f'{prefix}end_date_{days}d'] = (snapshots[exit_idx]['date'] if early else effective_date or snapshots[target_idx]['date'])
        for pct in (5, 10):
            prefix = f'stop{pct}_'
            if not matured:
                rec[f'{prefix}return_{days}d'] = None
                rec[f'{prefix}status_{days}d'] = 'pending'
                rec[f'{prefix}end_date_{days}d'] = None
                continue
            stop_idx, stop_price = stop_exits[pct]
            early = stop_idx is not None and stop_idx <= target_idx
            result = pct_return(entry, stop_price if early else baseline_price)
            rec[f'{prefix}return_{days}d'] = result
            rec[f'{prefix}status_{days}d'] = 'complete' if result is not None else 'unavailable'
            rec[f'{prefix}end_date_{days}d'] = (snapshots[stop_idx]['date'] if early else effective_date or snapshots[target_idx]['date'])
    return rec


def stats_for(records, days, prefix=''):
    key = f'{prefix}return_{days}d'
    status_key = f'{prefix}status_{days}d'
    vals = [float(r[key]) for r in records if r.get(status_key) == 'complete' and r.get(key) is not None]
    if not vals:
        return {'avg_return': None, 'median_return': None, 'win_rate': None, 'samples': 0}
    return {'avg_return': round(sum(vals) / len(vals), 4), 'median_return': round(median(vals), 4), 'win_rate': round(sum(x > 0 for x in vals) / len(vals) * 100, 2), 'samples': len(vals)}


def summary_block(records, prefix=''):
    return {'5d': stats_for(records, 5, prefix), '10d': stats_for(records, 10, prefix)}


def build_summary(records, prefix=''):
    out = {'all': summary_block(records, prefix), 'twse': summary_block([r for r in records if r.get('market') == 'twse'], prefix), 'tpex': summary_block([r for r in records if r.get('market') == 'tpex'], prefix), 'rank_buckets': {}}
    for label, max_rank in (('top5', 5), ('top10', 10), ('top20', 20)):
        subset = [r for r in records if int(r.get('rank') or 999) <= max_rank]
        out['rank_buckets'][label] = summary_block(subset, prefix)
    return out


def current_records(ai, market_data):
    selection_date = normalize_date(market_data.get('date'))
    stocks = market_data.get('stocks', {})
    if not selection_date:
        raise RuntimeError('market_latest.json has no date')
    rows = []
    for mk in ('twse', 'tpex'):
        for rank, x in enumerate(ai.get(mk, []), start=1):
            ticker = str(x.get('ticker') or '')
            entry_price = valid_price(stocks.get(ticker, {}).get('price'))
            if not ticker or entry_price is None:
                continue
            rows.append({'selection_date': selection_date, 'market': mk, 'ticker': ticker, 'name': x.get('name') or ticker, 'rank': rank, 'score': x.get('score'), 'entry_price': entry_price, 'return_5d': None, 'return_10d': None, 'status_5d': 'pending', 'status_10d': 'pending', 'end_date_5d': None, 'end_date_10d': None})
    return selection_date, rows


# Index comparison uses exactly the same matured stock signal dates and weights.
# Index closing prices are official: TWSE market_monitor raw, TPEx indexSummary.
def fetch_tpex_close(date):
    url = 'https://www.tpex.org.tw/www/zh-tw/afterTrading/indexSummary?' + urllib.parse.urlencode({'date': date.replace('-', '/'), 'response': 'json'})
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0', 'Accept': 'application/json'})
    with urllib.request.urlopen(req, timeout=18) as response:
        payload = json.load(response)
    # The first table is price indices, not total-return indices.
    tables = payload.get('tables', [])
    for table in tables:
        rows = table.get('data') or []
        for row in rows:
            if isinstance(row, list) and row and str(row[0]).strip() == '櫃買指數':
                price = valid_price(row[1] if len(row) > 1 else None)
                if price:
                    return price
        # Don't read later total-return index tables.
        if rows:
            break
    return None


def index_closes(snapshots, old):
    dates = {x['date'] for x in snapshots}
    cached = old.get('benchmark_index_closes', {})
    result = {'twse': {}, 'tpex': {}}
    for market in result:
        for date, value in (cached.get(market, {}) or {}).items():
            if date in dates and valid_price(value):
                result[market][date] = valid_price(value)
    monitor = load_json(ROOT / 'data/market_monitor.json', {})
    for row in monitor.get('raw', []):
        date = normalize_date(row.get('date'))
        price = valid_price(row.get('index'))
        if date in dates and price:
            result['twse'][date] = price
    # Only fetch TPEx for dates that can be used in completed 5/10 day comparisons.
    required = set()
    for i in range(len(snapshots)):
        for days in (5, 10):
            if i + days < len(snapshots):
                required.add(snapshots[i]['date'])
                required.add(snapshots[i + days]['date'])
    missing = sorted(required - set(result['tpex']))
    for date in missing:
        try:
            price = fetch_tpex_close(date)
            if price:
                result['tpex'][date] = price
            else:
                print('TPEx benchmark missing:', date)
        except Exception as exc:
            print('TPEx benchmark fetch failed:', date, type(exc).__name__, str(exc)[:120])
        time.sleep(0.15)
    return result


def benchmark_summary(records, snapshots, date_index, closes):
    output = {}
    for days in (5, 10):
        eligible = [r for r in records if r.get(f'baseline_status_{days}d') == 'complete']
        row = {}
        for market in ('twse', 'tpex'):
            returns = []
            prices = closes[market]
            for rec in eligible:
                idx = date_index.get(normalize_date(rec.get('selection_date')))
                if idx is None or idx + days >= len(snapshots):
                    continue
                start = prices.get(snapshots[idx]['date'])
                end = prices.get(snapshots[idx + days]['date'])
                ret = pct_return(start, end)
                if ret is not None:
                    returns.append(ret)
            row[market] = {'avg_return': round(sum(returns) / len(returns), 4) if returns else None, 'samples': len(returns), 'expected_samples': len(eligible)}
        output[f'{days}d'] = row
    return output


def main():
    ai = load_json(ROOT / 'data/ai_picks.json', {})
    market_data = load_json(ROOT / 'data/market_latest.json', {})
    old = load_json(BACKTEST_PATH, {})
    records = list(old.get('records', []) or [])
    selection_date, today_rows = current_records(ai, market_data)
    records = [r for r in records if normalize_date(r.get('selection_date')) != selection_date]
    records.extend(today_rows)
    snapshots = market_snapshots()
    date_index = {x['date']: i for i, x in enumerate(snapshots)}
    records = [evaluate_record(r, snapshots, date_index) for r in records]
    records.sort(key=lambda r: (r.get('selection_date') or '', r.get('market') or '', int(r.get('rank') or 999)), reverse=True)
    dates = sorted({r.get('selection_date') for r in records if r.get('selection_date')})
    closes = index_closes(snapshots, old)
    out = {
        'updated_at': now_tpe().isoformat(timespec='minutes'),
        'method': {
            'entry': 'AI選股基準交易日收盤價',
            'return_5d': '推薦後第1日起收盤跌破MA10出場，否則第5個交易日收盤結算；第5日後才計入統計',
            'return_10d': '推薦後第1日起收盤跌破MA10出場，否則第10個交易日收盤結算；第10日後才計入統計',
            'ma20': '與MA10相同規則，改為收盤跌破20日均線出場，分別計算5日及10日績效',
            'stop5': '推薦次交易日起，首次收盤價低於或等於買進價95%時，以該日收盤價出場；否則持有至第5/10日',
            'stop10': '推薦次交易日起，首次收盤價低於或等於買進價90%時，以該日收盤價出場；否則持有至第5/10日',
            'stop_execution': '僅有每日收盤價，採收盤觸發、收盤成交模型；跳空可能使實際損失超過5%或10%，不假設必然成交於門檻價',
            'calendar_basis': '交易日，不是日曆日',
            'baseline': 'baseline_return_5d/10d 保留原固定持有策略作比較',
            'benchmark': '加權指數及OTC各以每筆已滿期推薦日收盤至第5/10個交易日收盤計算，再依相同選股訊號權重平均；指數缺值不補零',
            'notes': [
                '推薦日即使低於MA10或MA20也保留樣本，從次一交易日才開始檢查',
                '提前出場立即鎖定賣價，但必須等第5/10個交易日結束才納入對應績效統計',
                '固定持有、MA10、MA20、停損5%、停損10%在各期使用相同成熟樣本，方便公平比較',
                '收盤確認跌破並以同日收盤價成交屬理想化假設，實盤可能有執行落差',
                '停牌缺價不視為跌破，均線採最近10/20筆有效收盤價',
                '同一股票在不同選股日視為不同訊號樣本',
            ],
        },
        'start_date': dates[0] if dates else selection_date,
        'latest_selection_date': selection_date,
        'selection_days': len(dates),
        'record_count': len(records),
        'summary': build_summary(records),
        'ma10_summary': build_summary(records),
        'ma20_summary': build_summary(records, 'ma20_'),
        'baseline_summary': build_summary(records, 'baseline_'),
        'stop5_summary': build_summary(records, 'stop5_'),
        'stop10_summary': build_summary(records, 'stop10_'),
        'benchmark_summary': benchmark_summary(records, snapshots, date_index, closes),
        'benchmark_index_closes': closes,
        'records': records,
    }
    save_json(BACKTEST_PATH, out)
    print('ai backtest', 'selection_date', selection_date, 'records', len(records))
    for label, key in (('Fixed', 'baseline_summary'), ('MA10', 'summary'), ('MA20', 'ma20_summary'), ('Stop5%', 'stop5_summary'), ('Stop10%', 'stop10_summary')):
        print(label, '5d samples', out[key]['all']['5d']['samples'], '10d samples', out[key]['all']['10d']['samples'])
    print('benchmarks', out['benchmark_summary'])


if __name__ == '__main__':
    main()
