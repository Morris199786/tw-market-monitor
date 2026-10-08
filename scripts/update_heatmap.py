from sources import *
import time
from datetime import datetime

INDEX_CHANNELS = {'twse': 'tse_t00.tw', 'tpex': 'otc_o00.tw'}


def NumberLike(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def latest_tdcc_totals():
    for p in sorted((ROOT / 'data/history/holders').glob('*.json'), reverse=True):
        stocks = load_json(p, {}).get('stocks', {})
        totals = {str(t): int(row.get('total') or 0) for t, row in stocks.items()}
        totals = {t: value for t, value in totals.items() if value > 0}
        if totals:
            print('heatmap share fallback:', p.name, len(totals))
            return totals
    return {}


def first_book_price(raw):
    for part in str(raw or '').split('_'):
        value = n(part)
        if value > 0:
            return value
    return 0.0


def get_mis_batch_with_retry(channels):
    last_error = None
    for attempt, wait in enumerate((0, 2, 5), 1):
        if wait:
            time.sleep(wait)
        try:
            data = get_json(MIS, params={
                'ex_ch': '|'.join(channels), 'json': '1', 'delay': '0'
            }, timeout=25)
            if not isinstance(data, dict):
                raise RuntimeError('MIS response is not dict')
            print('MIS batch success', f'attempt={attempt}', f'channels={len(channels)}')
            return data
        except Exception as exc:
            last_error = exc
            print('MIS batch failed', f'attempt={attempt}/3', repr(exc))
    print('WARNING: MIS batch skipped:', repr(last_error))
    return {'msgArray': []}


def fetch_heatmap_quotes(tickers, master):
    channels = []
    for ticker in tickers:
        market = str(master.get(ticker, {}).get('market', '')).lower()
        if market == 'twse':
            channels.append(f'tse_{ticker}.tw')
        elif market == 'tpex':
            channels.append(f'otc_{ticker}.tw')
        else:
            channels.extend((f'tse_{ticker}.tw', f'otc_{ticker}.tw'))
    out, quality = {}, {}
    for i in range(0, len(channels), 120):
        data = get_mis_batch_with_retry(channels[i:i + 120])
        for row in data.get('msgArray', []):
            ticker = str(row.get('c', '')).strip()
            if ticker not in tickers or not ordinary_ticker(ticker):
                continue
            previous, traded = n(row.get('y')), n(row.get('z'))
            bid, ask = first_book_price(row.get('b')), first_book_price(row.get('a'))
            if traded > 0:
                price, source, score = traded, 'mis_trade', 3
            elif bid > 0 or ask > 0:
                price = (bid + ask) / 2 if bid > 0 and ask > 0 else (bid or ask)
                source, score = 'mis_book', 2
            else:
                continue
            if previous <= 0 or price <= 0 or score < quality.get(ticker, -1):
                continue
            out[ticker] = {
                'price': price, 'prev_close': previous,
                'change_pct': (price / previous - 1) * 100,
                'exchange': row.get('ex', ''), 'quote_source': source
            }
            quality[ticker] = score
        time.sleep(0.2)
    return out


def previous_quotes():
    old = load_json(ROOT / 'data/heatmap.json', {})
    out = {}
    # Avoid presenting a prior trading day's stock prices as live.
    today = now_tpe().strftime('%Y%m%d')
    old_date = str(old.get('updated_at', ''))[:10].replace('/', '').replace('-', '')
    if old_date != today:
        return out
    for sector in old.get('sectors', []):
        for row in sector.get('stocks', []):
            ticker = str(row.get('ticker') or '')
            if ordinary_ticker(ticker) and NumberLike(row.get('price')) > 0 and row.get('change_pct') is not None:
                out[ticker] = {'price': float(row['price']), 'change_pct': float(row['change_pct'])}
    return out


def fetch_index_quotes():
    data = get_mis_batch_with_retry(list(INDEX_CHANNELS.values()))
    today = now_tpe().strftime('%Y%m%d')
    out = {}
    for row in data.get('msgArray', []):
        channel = str(row.get('ch') or '').lower()
        market = next((key for key, value in INDEX_CHANNELS.items() if channel == value.lower()), None)
        if not market:
            code, exchange = str(row.get('c') or '').lower(), str(row.get('ex') or '').lower()
            if code == 't00' and exchange == 'tse':
                market = 'twse'
            elif code == 'o00' and exchange == 'otc':
                market = 'tpex'
        if not market:
            continue
        price, previous = NumberLike(row.get('z')), NumberLike(row.get('y'))
        date = str(row.get('d') or '').replace('-', '').replace('/', '')
        if price <= 0 or previous <= 0 or date != today:
            continue
        out[market] = {
            'price': price, 'value': price, 'prev_close': previous,
            'change_pct': round((price / previous - 1) * 100, 4),
            'date': today, 'time': str(row.get('t') or ''),
            'source': 'twse_mis', 'live': True
        }
    return out


def previous_index_quotes():
    old = load_json(ROOT / 'data/heatmap.json', {})
    today = now_tpe().strftime('%Y%m%d')
    if str(old.get('updated_at', ''))[:10].replace('/', '').replace('-', '') != today:
        return {}
    prior = old.get('indices') or old.get('index_quotes') or {}
    out = {}
    for market, row in prior.items():
        if market not in INDEX_CHANNELS or not isinstance(row, dict):
            continue
        if str(row.get('date') or '').replace('-', '').replace('/', '') != today:
            continue
        price = NumberLike(row.get('price') or row.get('value'))
        previous = NumberLike(row.get('prev_close'))
        if price <= 0 or previous <= 0:
            continue
        out[market] = {
            **row, 'price': price, 'value': price, 'prev_close': previous,
            'change_pct': round((price / previous - 1) * 100, 4),
            'source': 'previous_heatmap', 'live': False
        }
    return out


def main():
    cfg = load_json(ROOT / 'data/sectors.json', {})
    master = load_json(ROOT / 'data/master.json', {}).get('stocks', {})
    if not master:
        master = fetch_master()
        save_json(ROOT / 'data/master.json', {
            'updated_at': now_tpe().isoformat(timespec='minutes'), 'stocks': master
        })
    tdcc_totals = latest_tdcc_totals()
    tickers = sorted({str(s['ticker']) for sector in cfg.get('sectors', []) for s in sector.get('stocks', [])})
    quotes = fetch_heatmap_quotes(tickers, master)
    old_quotes = previous_quotes()
    previous_fallback = 0
    for ticker in tickers:
        if ticker in quotes or ticker not in old_quotes:
            continue
        quotes[ticker] = {
            **old_quotes[ticker], 'exchange': master.get(ticker, {}).get('market', ''),
            'quote_source': 'previous_heatmap'
        }
        previous_fallback += 1

    indices = fetch_index_quotes()
    for market, quote in previous_index_quotes().items():
        indices.setdefault(market, quote)

    sectors = []
    for sector in cfg.get('sectors', []):
        members, weighted, capsum, missing = [], 0.0, 0.0, []
        for s in sector.get('stocks', []):
            ticker = str(s['ticker'])
            quote, info = quotes.get(ticker), master.get(ticker, {})
            name = s.get('name') or info.get('name') or ticker
            master_shares = int(info.get('shares_issued') or 0)
            shares = master_shares or int(tdcc_totals.get(ticker) or 0)
            if not quote:
                missing.append(ticker)
                members.append({
                    'ticker': ticker, 'name': name, 'price': None, 'change_pct': None,
                    'market_cap': None, 'weight': None, 'shares_source': None, 'quote_source': None
                })
                continue
            price, change = quote.get('price'), quote.get('change_pct')
            if shares <= 0 or NumberLike(price) <= 0 or change is None:
                missing.append(ticker)
                members.append({
                    'ticker': ticker, 'name': name, 'price': price, 'change_pct': change,
                    'market_cap': None, 'weight': None, 'shares_source': None,
                    'quote_source': quote.get('quote_source')
                })
                continue
            cap = float(price) * shares
            capsum += cap
            weighted += float(change) * cap
            members.append({
                'ticker': ticker, 'name': name, 'price': price,
                'change_pct': round(float(change), 2), 'market_cap': cap, 'weight': None,
                'shares_source': 'master' if master_shares > 0 else 'tdcc',
                'quote_source': quote.get('quote_source')
            })
        for member in members:
            if member['market_cap'] is not None and capsum:
                member['weight'] = member['market_cap'] / capsum
        sectors.append({
            'name': sector['name'],
            'change_pct': round(weighted / capsum, 2) if capsum else None,
            'complete': len(missing) == 0, 'missing': missing, 'stocks': members
        })

    save_json(ROOT / 'data/heatmap.json', {
        'updated_at': now_tpe().strftime('%Y/%m/%d %H:%M'),
        'method': 'market_cap_weighted',
        'source': 'TWSE MIS + retry + correct-market quotes + TDCC share fallback',
        'indices': indices,
        'index_quotes': indices,
        'sectors': sectors
    })
    print('heatmap', len(sectors), 'quotes', len(quotes), 'indices', list(indices),
          'previous_fallback', previous_fallback,
          'missing', sum(len(x['missing']) for x in sectors))


if __name__ == '__main__':
    main()
