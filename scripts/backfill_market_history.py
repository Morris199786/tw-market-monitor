"""Build one closed calendar year using the live monitor's calculation rules."""
import argparse
import datetime as dt
import json
import subprocess
import sys
import unicodedata
from pathlib import Path

import update_market_breadth as breadth
import update_market_monitor as monitor

MARKETS = ('twse', 'tpex', 'all')
CACHE = Path('.cache/tw-history')
OUTPUT = Path('history-result')


def label(value):
    return ''.join(unicodedata.normalize('NFKC', value).split())


def historical_funds(day):
    key = day.replace('-', '')
    report = monitor.fetch('fund/BFI82U', dayDate=key, type='day')
    if report.get('date') != key:
        raise ValueError(f'{day}: foreign flow date mismatch')
    fields = [label(field) for field in report['fields']]
    accepted = {'外資及陸資(不含外資自營商)', '外資及陸資', '外資'}
    match = [row for row in report['data'] if label(row[0]) in accepted]
    if len(match) != 1:
        raise ValueError(f"{day}: unexpected categories {[r[0] for r in report['data']]}")
    row, = match
    buy, sell, net = [monitor.number(row[fields.index(k)]) for k in ('買進金額', '賣出金額', '買賣差額')]
    if abs(buy - sell - net) > 0.1:
        raise ValueError(f'{day}: inconsistent foreign flow')
    return {'foreign': net / 1e8, 'foreign_basis': row[0]}


def cached(path, fetch):
    value = breadth.read(path)
    if value is None:
        value = fetch()
        breadth.save(path, value)
    return value


def calendar(year):
    start = dt.date(year - 1, 9, 1)
    months = [dt.date(year - 1, m, 1) for m in range(9, 13)]
    months.extend(dt.date(year, m, 1) for m in range(1, 13))
    prices = {}
    for month in months:
        tag = month.strftime('%Y%m')
        def load():
            report = monitor.fetch('afterTrading/FMTQIK', date=tag + '01')
            fields = report['fields']
            values = {monitor.date_iso(r[fields.index('日期')]): monitor.number(r[fields.index('發行量加權股價指數')]) for r in report['data']}
            if not values or any(not d.startswith(month.isoformat()[:7]) for d in values):
                raise ValueError(f'{tag}: wrong calendar')
            return values
        prices.update(cached(CACHE / 'index' / (tag + '.json'), load))
    if sum(d < f'{year}-01-01' for d in prices) < 60:
        raise ValueError(f'{start}: insufficient warm-up')
    return prices


def margin(day):
    key = day.replace('-', '')
    report = monitor.fetch('marginTrading/MI_MARGN', date=key, selectType='MS')
    if report.get('date') != key:
        raise ValueError(f'{day}: margin date mismatch')
    for table in report.get('tables', []) + [report]:
        fields = [label(f) for f in table.get('fields', [])]
        if '項目' not in fields:
            continue
        for row in table.get('data', []):
            item = label(row[fields.index('項目')])
            if item in ('融資金額(仟元)', '融資金額(千元)'):
                return {k: monitor.number(row[fields.index(f)]) * 1000
                        for k, f in [('margin', '今日餘額'), ('margin_previous', '前日餘額')]}
    raise ValueError(f'{day}: missing margin amount in thousands of dollars')


def build(year):
    prices = calendar(year)
    expected = sorted(d for d in prices if int(d[:4]) == year)
    temp = CACHE / f'breadth-{year}.json'
    subprocess.run([sys.executable, breadth.__file__, '--year', str(year),
                    '--as-of', f'{year}-12-31', '--budget-seconds', '8500',
                    '--cache-dir', str(CACHE / 'quotes'), '--output', str(temp)], check=True)
    data = breadth.read(temp)
    if not data or not data['complete'] or any(data['missing_dates'].values()):
        raise ValueError('行情或暖機期缺漏，保留快取供重跑')
    for err in data.get('errors', []):
        # No ex-rights events is a valid response for a quiet month.
        if not (err.startswith('actions ') and '沒有符合條件的資料' in err):
            raise ValueError(err)
    for market in MARKETS:
        rows = data['series'][market]
        if [r['date'] for r in rows] != expected:
            raise ValueError(f'{market}: calendar mismatch')
        for r in rows:
            if not r.get('complete') or any(r.get(k) is None for k in ('ad', 'pct20', 'pct60')):
                raise ValueError(f"{market} {r['date']}: incomplete breadth")
            if market == 'twse':
                r['index'] = prices[r['date']]
            if market == 'all':
                r['index_twse'] = prices[r['date']]
            if market == 'tpex' and r.get('index') is None:
                raise ValueError(f"{r['date']}: missing OTC index")
    raw = []
    for day in sorted(prices):
        f = cached(CACHE / 'foreign' / (day + '.json'), lambda: historical_funds(day))
        m = cached(CACHE / 'margin' / (day + '.json'), lambda: margin(day))
        if raw:
            raw[-1]['margin'] = m['margin_previous']
        raw.append(dict(date=day, index=prices[day], **m, **f))
    monitor.START_YEAR = year
    funds = monitor.calculate(raw)
    if [r['date'] for r in funds] != expected or any(r.get('intersection') is None for r in funds):
        raise ValueError(f'{year}: missing funding signals')
    breadth.save(OUTPUT / f'{year}.json', {'rows': funds, 'series': data['series']})
    print(f'{year}: verified {len(expected)} sessions', flush=True)


def assemble():
    funds = []
    series = {market: [] for market in MARKETS}
    for year in range(2008, 2024):
        data = json.loads((OUTPUT / f'{year}.json').read_text())
        funds.extend(data['rows'])
        for market in MARKETS:
            series[market].extend(data['series'][market])
    breadth.save(Path('data/history/monitor-funds-2008-2023.json'), funds)
    breadth.save(Path('data/history/monitor-breadth-2008-2023.json'), series)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('year', choices=[str(y) for y in range(2008, 2024)] + ['assemble'])
    args = parser.parse_args()
    if args.year == 'assemble':
        assemble()
    else:
        build(int(args.year))
