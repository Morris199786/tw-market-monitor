"""Repair AI candidate OHLCV gaps using real Yahoo daily bars (never fabricate prices)."""
from __future__ import annotations
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from sources import load_json, save_json, ordinary_ticker
from tech_universe import tech_tickers
from update_daily_k import valid_bar, parse_chart


def main():
    master = load_json(ROOT / 'data/master.json', {}).get('stocks', {})
    latest = load_json(ROOT / 'data/market_latest.json', {})
    day = latest.get('date')
    snapshots = []
    for p in sorted((ROOT / 'data/history/market').glob('*.json')):
        if p.stem <= (day or ''):
            data = load_json(p, {}).get('stocks', {})
            if data:
                snapshots.append((p.stem, data))
    if len(snapshots) < 40 or snapshots[-1][0] != day:
        print('AI candle repair skipped: current 40-day market history not ready')
        return
    dates = {d for d, _ in snapshots[-40:]}
    universe = tech_tickers(master)
    candidates = {t: m for t, m in master.items()
                  if t in universe and ordinary_ticker(t)
                  and m.get('market') in ('twse', 'tpex') and t in snapshots[-1][1]}
    pending = []
    for ticker, meta in candidates.items():
        merged = {}
        for folder in ('ai_backtest_k', 'ai_setup_k', 'daily_k'):
            obj = load_json(ROOT / f'data/{folder}/{ticker}.json', {})
            if str(obj.get('ticker')) != ticker:
                continue
            for bar in obj.get('bars', []):
                if valid_bar(bar):
                    merged[bar['time']] = bar
        if dates - merged.keys():
            pending.append((ticker, meta, merged))
    print(f'AI repair: {len(pending)}/{len(candidates)} candidates have missing OHLCV dates', flush=True)
    now = datetime.now(ZoneInfo('Asia/Taipei'))
    def fetch(item):
        ticker, meta, merged = item
        symbol = ticker + ('.TW' if meta['market'] == 'twse' else '.TWO')
        for host in ('query1.finance.yahoo.com', 'query2.finance.yahoo.com'):
            try:
                with requests.get(f'https://{host}/v8/finance/chart/{symbol}',
                                  params={'range': '6mo', 'interval': '1d', 'includeAdjustedClose': 'false'},
                                  headers={'User-Agent': 'Mozilla/5.0'}, timeout=(8, 22)) as response:
                    response.raise_for_status()
                    rows = parse_chart(response.json(), symbol, now)
                return ticker, merged, rows
            except (requests.RequestException, ValueError, KeyError, TypeError):
                pass
        return ticker, merged, []
    repaired = 0
    complete = 0
    failed = 0
    with ThreadPoolExecutor(max_workers=10) as pool:
        futures = [pool.submit(fetch, item) for item in pending]
        for future in as_completed(futures):
            ticker, merged, incoming = future.result()
            if not incoming:
                failed += 1
                continue
            # Only fill missing historical dates. Existing verified bars remain untouched.
            for bar in incoming:
                if bar['time'] <= day and bar['time'] not in merged and valid_bar(bar):
                    merged[bar['time']] = bar
                    repaired += 1
            if dates.issubset(merged):
                complete += 1
            save_json(ROOT / f'data/ai_setup_k/{ticker}.json',
                      {'ticker': ticker, 'bars': [merged[d] for d in sorted(merged) if d <= day][-260:]})
    print(f'AI repair finished: {repaired} actual candles recovered; '
          f'{complete} candidates now date-complete; {failed} downloads unavailable', flush=True)


if __name__ == '__main__':
    main()
