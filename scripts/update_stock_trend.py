"""Update only the 5/10/20-day trend; never write shared market/chip/AI files."""
from __future__ import annotations

import sys

from sources import ROOT, load_json, save_json, now_tpe
import update_stock_detail as detail
from stock_trend_history import completed_sessions, ensure_close_history


def build_trends(rows):
    dates = [row['date'] for row in rows]
    sectors = load_json(ROOT / 'data/sectors.json', {}).get('sectors', [])
    names, shares, _ = detail.display_names_and_shares()
    ticker_sectors = {}
    for sector in sectors:
        name = str(sector.get('name') or '').strip()
        for stock in sector.get('stocks', []):
            ticker = str(stock.get('ticker') or '').strip()
            if ticker and name:
                ticker_sectors.setdefault(ticker, []).append(name)
    stocks = {}
    for ticker in detail.all_tracked_tickers(sectors):
        prices = []
        for row in rows:
            price = row.get('stocks', {}).get(ticker, {}).get('price')
            prices.append(float(price) if price is not None and float(price) > 0 else None)
        periods = detail.build_period_block(prices)
        member_sectors = ticker_sectors.get(ticker, [])
        stocks[ticker] = {
            'name': names.get(ticker, ticker),
            'sectors': member_sectors,
            'primary_sector': member_sectors[0] if member_sectors else '',
            'returns': periods['5'],
            'returns_by_period': periods,
        }
    benchmark_prices = detail.fetch_taiex(dates)
    # A missing latest benchmark must not masquerade as a complete comparison.
    if any(day not in benchmark_prices for day in dates):
        raise RuntimeError('Incomplete official benchmark history for the trend window')
    benchmark_periods = detail.build_period_block([benchmark_prices[day] for day in dates])
    windows = {str(days): dates[-days:] for days in (5, 10, 20)}
    return {
        'schema': 1,
        'price_mode': 'completed_close',
        'updated_at': now_tpe().isoformat(timespec='minutes'),
        'as_of_date': dates[-1],
        'base_dates_by_period': {str(days): dates[-days - 1] for days in (5, 10, 20)},
        'dates_by_period': windows,
        'date_labels_by_period': {key: [day[5:].replace('-', '/') for day in days]
                                  for key, days in windows.items()},
        'benchmark': {'name': '上市加權指數', 'source': 'TWSE FMTQIK',
                      'returns': benchmark_periods['5'], 'returns_by_period': benchmark_periods},
        'sectors': detail.build_sector_series(sectors, rows, shares),
        'stocks': stocks,
    }


def main():
    expected, errors = None, []
    try:
        dates = completed_sessions(21)
        expected = dates[-1]
        rows = ensure_close_history(21, dates=dates)
        data = build_trends(rows)
        save_json(ROOT / 'data/stock_trend.json', data)
        print('Trend only:', data['as_of_date'], len(data['stocks']), 'stocks', flush=True)
    except Exception as exc:
        errors.append(str(exc))
        print('Trend update failed:', exc, flush=True)
    actual = load_json(ROOT / 'data/stock_trend.json', {}).get('as_of_date')
    if expected and actual != expected:
        errors.append(f'Trend end date {actual}, expected {expected}')
    save_json(ROOT / 'data/stock_trend_status.json', {
        'checked_at': now_tpe().isoformat(timespec='minutes'),
        'price_mode': 'completed_close',
        'expected_as_of_date': expected, 'as_of_date': actual,
        'ok': not errors, 'errors': errors,
    })
    return 1 if errors else 0


if __name__ == '__main__':
    sys.exit(main())
