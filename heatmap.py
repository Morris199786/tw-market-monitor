from sources import *
import time
from datetime import datetime

# 保留既有輸出結構；新增 index_quotes（盤中大盤／OTC）
INDEX_CHANNELS = {'twse': 'tse_t00.tw', 'tpex': 'otc_o00.tw'}

def NumberLike(v):
    try: return float(v)
    except (ValueError, TypeError): return 0.0

def latest_tdcc_totals():
    files = sorted((ROOT / 'data/history/holders').glob('*.json'), reverse=True)
    for p in files:
        stocks = load_json(p, {}).get('stocks', {})
        totals = {str(t): int(r.get('total') or 0) for t, r in stocks.items()}
        totals = {t: v for t, v in totals.items() if v > 0}
        if totals:
            print('heatmap share fallback:', p.name, len(totals))
            return totals
    return {}

def first_book_price(raw):
    for part in str(raw or '').split('_'):
        v = n(part)
        if v > 0: return v
    return 0.0

def get_mis_batch_with_retry(channels):
    last_error = None
    for attempt, wait in enumerate([0, 2, 5], 1):
        if wait: time.sleep(wait)
        try:
            data = get_json(MIS, params={'ex_ch': '|'.join(channels), 'json': '1', 'delay': '0'}, timeout=25)
            if not isinstance(data, dict): raise RuntimeError('MIS response is not dict')
            print('MIS batch success', f'attempt={attempt}', f'channels={len(channels)}')
            return data
        except Exception as e:
            last_error = e
            print('MIS batch failed', f'attempt={attempt}/3', repr(e))
    print('WARNING: MIS batch skipped after 3 attempts:', repr(last_error))
    return {'msgArray': []}

def fetch_heatmap_quotes(tickers, master):
    channels = []
    for t in tickers:
        market = str(master.get(t, {}).get('market', '')).lower()
        if market == 'twse': channels.append(f'tse_{t}.tw')
        elif market == 'tpex': channels.append(f'otc_{t}.tw')
        else: channels.extend([f'tse_{t}.tw', f'otc_{t}.tw'])
    out, quality = {}, {}
    for i in range(0, len(channels), 120):
        data = get_mis_batch_with_retry(channels[i:i+120])
        for r in data.get('msgArray', []):
            t = str(r.get('c', '')).strip()
            if not ordinary_ticker(t): continue
            prev_close, trade = n(r.get('y')), n(r.get('z'))
            bid, ask = first_book_price(r.get('b')), first_book_price(r.get('a'))
            if trade > 0: price, source, score = trade, 'mis_trade', 3
            elif bid > 0 or ask > 0:
                price = (bid + ask)/2 if bid > 0 and ask > 0 else (bid or ask)
                source, score = 'mis_book', 2
            else: continue
            if prev_close <= 0 or price <= 0 or score < quality.get(t, -1): continue
            out[t] = {'price': price, 'prev_close': prev_close,
                      'change_pct': (price / prev_close - 1) * 100,
                      'exchange': r.get('ex', ''), 'quote_source': source}
            quality[t] = score
        time.sleep(.2)
    return out

def previous_quotes():
    old = load_json(ROOT / 'data/heatmap.json', {})
    out = {}
    for sec in old.get('sectors', []):
        for x in sec.get('stocks', []):
            t = str(x.get('ticker') or '')
            if ordinary_ticker(t) and NumberLike(x.get('price')) > 0 and x.get('change_pct') is not None:
                out[t] = {'price': float(x['price']), 'change_pct': float(x['change_pct'])}
    return out

def fetch_index_quotes():
    """MIS 指數行情；拒絕缺價、缺昨收及不屬於今天的舊盤行情。"""
    data = get_mis_batch_with_retry(list(INDEX_CHANNELS.values()))
    today = now_tpe().strftime('%Y%m%d')
    out = {}
    for row in data.get('msgArray', []):
        ch = str(row.get('ch', '')).lower()
        market = next((k for k, v in INDEX_CHANNELS.items() if v.lower() == ch), None)
        if not market:
            # MIS 有時 ch 缺失，使用 c/ex 辨識
            c = str(row.get('c', '')).lower()
            ex = str(row.get('ex', '')).lower()
            if c == 't00' and ex == 'tse': market = 'twse'
            elif c == 'o00' and ex == 'otc': market = 'tpex'
        if not market: continue
        last, prev = NumberLike(row.get('z')), NumberLike(row.get('y'))
        if last <= 0 or prev <= 0: continue
        raw_date = str(row.get('d') or '').replace('-', '').replace('/', '')
        if raw_date and raw_date != today: continue
        out[market] = {
            'value': last, 'prev_close': prev,
            'change_pct': round((last / prev - 1) * 100, 4),
            'date': today, 'time': str(row.get('t') or ''),
            'source': 'twse_mis', 'live': True,
        }
    return out

def previous_index_quotes():
    old = load_json(ROOT / 'data/heatmap.json', {})
    old_date = str(old.get('updated_at', ''))[:10].replace('/', '').replace('-', '')
    today = now_tpe().strftime('%Y%m%d')
    if old_date != today: return {}
    out = {}
    for market, q in old.get('index_quotes', {}).items():
        if market not in INDEX_CHANNELS or not isinstance(q, dict): continue
        if str(q.get('date', '')).replace('-', '') != today: continue
        if NumberLike(q.get('value')) <= 0 or NumberLike(q.get('prev_close')) <= 0: continue
        out[market] = {**q, 'source': 'previous_heatmap', 'live': False}
    return out

def main():
    cfg = load_json(ROOT / 'data/sectors.json', {})
    master = load_json(ROOT / 'data/master.json', {}).get('stocks', {})
    if not master:
        master = fetch_master()
        save_json(ROOT / 'data/master.json', {'updated_at': now_tpe().isoformat(timespec='minutes'), 'stocks': master})
    tdcc_totals = latest_tdcc_totals()
    tickers = sorted({str(s['ticker']) for sec in cfg.get('sectors', []) for s in sec.get('stocks', [])})
    quotes = fetch_heatmap_quotes(tickers, master)
    old_quotes = previous_quotes()
    previous_fallback = 0
    for t in tickers:
        if t in quotes or t not in old_quotes: continue
        quotes[t] = {**old_quotes[t], 'exchange': master.get(t, {}).get('market', ''), 'quote_source': 'previous_heatmap'}
        previous_fallback += 1
    index_quotes = fetch_index_quotes()
    for market, q in previous_index_quotes().items():
        index_quotes.setdefault(market, q)
    sectors = []
    for sec in cfg.get('sectors', []):
        members, weighted, capsum, missing = [], 0.0, 0.0, []
        for s in sec.get('stocks', []):
            t = str(s['ticker'])
            q, m = quotes.get(t), master.get(t, {})
            name = s.get('name') or m.get('name') or t
            master_shares = int(m.get('shares_issued') or 0)
            shares = master_shares or int(tdcc_totals.get(t) or 0)
            if not q:
                missing.append(t)
                members.append({'ticker': t, 'name': name, 'price': None, 'change_pct': None,
                                'market_cap': None, 'weight': None, 'shares_source': None, 'quote_source': None})
                continue
            price, change = q.get('price'), q.get('change_pct')
            if shares <= 0 or NumberLike(price) <= 0 or change is None:
                missing.append(t)
                members.append({'ticker': t, 'name': name, 'price': price, 'change_pct': change,
                                'market_cap': None, 'weight': None, 'shares_source': None,
                                'quote_source': q.get('quote_source')})
                continue
            cap = float(price) * shares
            capsum += cap
            weighted += float(change) * cap
            members.append({'ticker': t, 'name': name, 'price': price, 'change_pct': round(float(change), 2),
                            'market_cap': cap, 'weight': None,
                            'shares_source': 'master' if master_shares > 0 else 'tdcc',
                            'quote_source': q.get('quote_source')})
        for x in members:
            if x['market_cap'] is not None and capsum: x['weight'] = x['market_cap'] / capsum
        sectors.append({'name': sec['name'], 'change_pct': round(weighted / capsum, 2) if capsum else None,
                        'complete': len(missing) == 0, 'missing': missing, 'stocks': members})
    save_json(ROOT / 'data/heatmap.json', {
        'updated_at': now_tpe().strftime('%Y/%m/%d %H:%M'),
        'method': 'market_cap_weighted',
        'source': 'TWSE MIS correct-market live quote + MIS retry + previous valid quote fallback + TWSE/TPEx master + TDCC share fallback',
        'index_quotes': index_quotes,
        'sectors': sectors,
    })
    print('heatmap', len(sectors), 'quotes', len(quotes), 'index_quotes', list(index_quotes),
          'previous_fallback', previous_fallback, 'missing', sum(len(x['missing']) for x in sectors))

if __name__ == '__main__': main()
