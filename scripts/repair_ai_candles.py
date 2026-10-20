"""Repair shared heatmap/AI daily K using independently verified real OHLCV.

Only data/daily_k is written. Official bars are accepted only when their close
agrees with the market snapshot; Yahoo is used for gaps, not to overwrite bars.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
import sys
import time

import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from sources import load_json, save_json, ordinary_ticker
from tech_universe import tech_tickers
from update_daily_k import DEST, read, valid_bar, parse_chart, save_candles, fetch_dated
from ai_setup_strategy import number


def close_matches(bar, price):
    price = number(price)
    return price is not None and abs(float(bar['close']) - price) <= max(.01, price * .0001)


def load_bars(ticker):
    obj = read(DEST / f'{ticker}.json', {})
    return obj, {b['time']: b for b in obj.get('bars', [])
                 if isinstance(b, dict) and b.get('time') and valid_bar(b)}


def check(bars, quotes):
    missing, mismatch = [], []
    for date, quote in quotes.items():
        if date not in bars:
            missing.append(date)
        elif not close_matches(bars[date], quote.get('price')):
            mismatch.append(date)
    return missing, mismatch


def yahoo_bars(ticker, market, now):
    symbol = ticker + ('.TW' if market == 'twse' else '.TWO')
    error = ''
    for host in ('query1.finance.yahoo.com', 'query2.finance.yahoo.com'):
        for attempt in range(2):
            try:
                with requests.get(f'https://{host}/v8/finance/chart/{symbol}',
                    params={'range':'2y','interval':'1d','events':'splits,div',
                            'includeAdjustedClose':'false'},
                    headers={'User-Agent':'Mozilla/5.0','Accept-Encoding':'identity'},
                    timeout=(10,40)) as response:
                    response.raise_for_status()
                    return parse_chart(response.json(), symbol, now), ''
            except (requests.RequestException, ValueError, KeyError, TypeError) as exc:
                error = f'{type(exc).__name__}: {exc}'[:160]
                if attempt == 0: time.sleep(1)
    return [], error


def official_bars(market, date, now):
    error = ''
    for attempt in range(3):
        try:
            return fetch_dated(market, date, now), ''
        except Exception as exc:
            error = f'{type(exc).__name__}: {exc}'[:160]
            if attempt < 2: time.sleep(2 ** attempt)
    return {}, error


def main():
    now = datetime.now(ZoneInfo('Asia/Taipei'))
    master = load_json(ROOT/'data/master.json', {}).get('stocks', {})
    day = load_json(ROOT/'data/market_latest.json', {}).get('date')
    snapshots = []
    for path in sorted((ROOT/'data/history/market').glob('*.json')):
        if day and path.stem <= day:
            stocks = load_json(path, {}).get('stocks', {})
            if stocks: snapshots.append((path.stem, stocks))
    if len(snapshots) < 10 or snapshots[-1][0] != day:
        raise RuntimeError('AI shared K repair requires current market snapshots')
    window = snapshots[-40:]
    universe = tech_tickers(master)
    candidates = {t:m for t,m in master.items() if t in universe
                  and ordinary_ticker(t) and m.get('market') in ('twse','tpex')
                  and t in window[-1][1]}
    pending = {}
    for ticker, meta in candidates.items():
        obj, bars = load_bars(ticker)
        quotes = {d:s[ticker] for d,s in window if ticker in s}
        missing, mismatch = check(bars, quotes)
        if missing or mismatch:
            pending[ticker] = (meta, obj, bars, quotes, missing, mismatch)
    print(f'AI shared daily K: {len(candidates)} candidates, {len(pending)} need repair', flush=True)

    yahoo = {}
    with ThreadPoolExecutor(max_workers=5) as pool:
        jobs = {pool.submit(yahoo_bars, t, x[0]['market'], now):t for t,x in pending.items()}
        for future in as_completed(jobs):
            ticker = jobs[future]
            try: yahoo[ticker] = future.result()
            except Exception as exc: yahoo[ticker] = ([], str(exc)[:160])

    # Query official data only for dates still inconsistent after checking Yahoo.
    # The official source is downloaded once per market/date and reused by stocks.
    required = defaultdict(set)
    for ticker, (meta, _, bars, quotes, missing, mismatch) in pending.items():
        ybars = {b['time']:b for b in yahoo[ticker][0] if valid_bar(b)}
        for date in missing + mismatch:
            if date in ybars and close_matches(ybars[date], quotes[date].get('price')):
                continue
            required[meta['market']].add(date)
    official = {}
    errors = {}
    with ThreadPoolExecutor(max_workers=2) as pool:
        jobs = {pool.submit(official_bars, market, date, now):(market,date)
                for market, dates in required.items() for date in sorted(dates)}
        for future in as_completed(jobs):
            market,date = jobs[future]
            rows,error = future.result()
            official[(market,date)] = rows
            if error: errors[f'{market}:{date}'] = error

    stats = {'twse':Counter(), 'tpex':Counter()}
    unresolved = {}
    for ticker, (meta, obj, old, quotes, missing, mismatch) in pending.items():
        market = meta['market']
        merged = dict(old)
        yrows,error = yahoo[ticker]
        ybars = {b['time']:b for b in yrows if valid_bar(b)}
        for date in missing + mismatch:
            quote_price = quotes[date].get('price')
            official_bar = official.get((market,date), {}).get(ticker)
            yahoo_bar = ybars.get(date)
            # Official OHLCV is preferred; never overwrite with an unverified
            # price basis, even if Yahoo disagrees with the official snapshot.
            if official_bar and valid_bar(official_bar) and close_matches(official_bar,quote_price):
                merged[date] = official_bar
            elif yahoo_bar and close_matches(yahoo_bar,quote_price):
                merged[date] = yahoo_bar
        new_missing,new_mismatch = check(merged,quotes)
        if merged != old:
            save_candles(ticker,meta,now,[merged[d] for d in sorted(merged) if d<=day],
                [d for d in obj.get('missing_dates',[]) if d not in merged],
                [d for d in obj.get('invalid_dates',[]) if d not in merged])
            stats[market]['changed'] += 1
        if not new_missing and not new_mismatch:
            stats[market]['fully_repaired'] += 1
        stats[market]['missing'] += bool(new_missing)
        stats[market]['mismatch'] += bool(new_mismatch)
        if new_missing or new_mismatch:
            unresolved[ticker] = {'market':market,'missing':new_missing,
                'price_mismatch':new_mismatch,'yahoo_error':error}
    report = {'date':day,'candidates':len(candidates),'pending':len(pending),
        'markets':{m:dict(v) for m,v in stats.items()},
        'official_source_errors':errors,'unresolved':unresolved}
    save_json(ROOT/'data/ai_candle_repair_diagnostics.json',report)
    for market in ('twse','tpex'):
        print(f'AI shared K {market}: {dict(stats[market])}',flush=True)
    print(f'AI shared K unresolved={len(unresolved)} official_errors={len(errors)}',flush=True)

if __name__ == '__main__':
    main()
