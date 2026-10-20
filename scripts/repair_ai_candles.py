"""Share heatmap daily_k with AI; repair missing/mismatched real OHLCV.

Uses update_daily_k's Yahoo parsing, validation, official market OHLCV and
save_candles. Never creates a synthetic candle or writes ai_setup_k.
"""
from __future__ import annotations
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from zoneinfo import ZoneInfo
import sys
from pathlib import Path
import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from sources import load_json, save_json, ordinary_ticker
from tech_universe import tech_tickers
from update_daily_k import (DEST, read, valid_bar, parse_chart, merge_bars,
                            save_candles, fetch_official, fetch_dated)
from ai_setup_strategy import number


def load_shared(ticker):
    obj = read(DEST / (ticker + '.json'), {})
    return obj, {b['time']: b for b in obj.get('bars', []) if isinstance(b, dict)
                 and b.get('time') and valid_bar(b)}


def problems(bars, snapshots):
    missing, mismatched = [], []
    for day, stocks in snapshots:
        if day not in bars:
            missing.append(day)
        else:
            price = number(stocks.get('price'))
            if price is not None and abs(bars[day]['close'] - price) > max(.01, price * .0001):
                mismatched.append(day)
    return missing, mismatched


def yahoo_history(ticker, market, now):
    symbol = ticker + ('.TW' if market == 'twse' else '.TWO')
    last_error = 'no valid response'
    for host in ('query1.finance.yahoo.com', 'query2.finance.yahoo.com'):
        try:
            with requests.get('https://' + host + '/v8/finance/chart/' + symbol,
                              params={'range':'2y','interval':'1d','events':'splits,div',
                                      'includeAdjustedClose':'false'},
                              headers={'User-Agent':'Mozilla/5.0'}, timeout=(10,35)) as r:
                r.raise_for_status()
                return parse_chart(r.json(), symbol, now), ''
        except (requests.RequestException, ValueError, TypeError, KeyError) as exc:
            last_error = f'{type(exc).__name__}: {exc}'[:180]
    return [], last_error


def main():
    now = datetime.now(ZoneInfo('Asia/Taipei'))
    master = load_json(ROOT / 'data/master.json', {}).get('stocks', {})
    day = load_json(ROOT / 'data/market_latest.json', {}).get('date')
    history = []
    for path in sorted((ROOT / 'data/history/market').glob('*.json')):
        if day and path.stem <= day:
            stocks = load_json(path, {}).get('stocks', {})
            if stocks:
                history.append((path.stem, stocks))
    if len(history) < 10 or history[-1][0] != day:
        raise RuntimeError('AI candle repair: market snapshots not current')
    window = history[-40:]
    universe = tech_tickers(master)
    candidates = {t:m for t,m in master.items() if t in universe and ordinary_ticker(t)
                  and m.get('market') in ('twse','tpex') and t in history[-1][1]}
    pending = []
    for ticker, meta in candidates.items():
        _, bars = load_shared(ticker)
        checks = [(d, s[ticker]) for d,s in window if ticker in s]
        missing, mismatch = problems(bars, checks)
        if missing or mismatch:
            pending.append((ticker,meta,missing,mismatch))
    print(f'AI shared daily K: {len(candidates)} candidates; {len(pending)} require repair',flush=True)

    # Only download Yahoo for stocks needing repair. Shared chart and AI candles
    # are identical: all repairs are saved to data/daily_k.
    fetched = {}
    with ThreadPoolExecutor(max_workers=5) as pool:
        tasks = {pool.submit(yahoo_history,t,m['market'],now):t for t,m,_,_ in pending}
        for future in as_completed(tasks):
            ticker=tasks[future]
            fetched[ticker]=future.result()

    # Request verified historical official candles once per (market, date),
    # not once per stock. This corrects Yahoo price-basis discrepancies.
    dates_by_market = defaultdict(set)
    for ticker,meta,missing,mismatch in pending:
        for date in missing + mismatch:
            dates_by_market[meta['market']].add(date)
    official_history = {}
    official_errors = {}
    # Historical official endpoints are requested only for dates with issues.
    # Limit requests to the current 40-date window; never invent OHLCV.
    jobs = [(market,date) for market, dates in dates_by_market.items() for date in sorted(dates)]
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures={pool.submit(fetch_dated,m,d,now):(m,d) for m,d in jobs}
        for future in as_completed(futures):
            market,date=futures[future]
            try: official_history[(market,date)]=future.result()
            except Exception as exc: official_errors[f'{market}:{date}']=str(exc)[:140]

    summary = {'twse':Counter(), 'tpex':Counter()}
    details={}
    for ticker,meta,_,_ in pending:
        market=meta['market']; obj,old=load_shared(ticker)
        merged=dict(old)
        incoming,error=fetched[ticker]
        # Yahoo supplies missing bars only. Existing chart candles are not
        # overwritten by an unverified price adjustment.
        for bar in incoming:
            date=bar['time']
            if date <= day and date not in merged and valid_bar(bar):
                merged[date]=bar
        for date in dates_by_market[market]:
            bar=official_history.get((market,date),{}).get(ticker)
            if bar and valid_bar(bar) and bar['time']==date:
                merged[date]=bar
        checks=[(d,s[ticker]) for d,s in window if ticker in s]
        missing,mismatch=problems(merged,checks)
        summary[market]['repaired']+=int(merged!=old)
        summary[market]['missing']+=int(bool(missing))
        summary[market]['mismatch']+=int(bool(mismatch))
        if merged!=old:
            bars=[merged[d] for d in sorted(merged) if d<=day]
            save_candles(ticker,meta,now,bars,
                         [d for d in obj.get('missing_dates',[]) if d not in merged],
                         [d for d in obj.get('invalid_dates',[]) if d not in merged])
        if missing or mismatch or error:
            details[ticker]={'market':market,'missing':missing,'price_mismatch':mismatch,
                             'yahoo_error':error}
    report={'date':day,'candidates':len(candidates),'pending':len(pending),
            'markets':{k:dict(v) for k,v in summary.items()},
            'official_source_errors':official_errors,'unresolved':details}
    save_json(ROOT/'data/ai_candle_repair_diagnostics.json',report)
    for market in ('twse','tpex'):
        print(f'AI shared K {market}: {dict(summary[market])}',flush=True)
    print(f'AI shared K: unresolved={sum(bool(v["missing"] or v["price_mismatch"]) for v in details.values())}; official errors={len(official_errors)}',flush=True)

if __name__=='__main__':
    main()
