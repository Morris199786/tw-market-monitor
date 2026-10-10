from sources import *
from tech_universe import tech_tickers
import csv
import io
import re
from datetime import datetime, timedelta

MIN_AVG_TURNOVER_5D = 10_000_000
TURNOVER_LOOKBACK_DAYS = 5
ARCHIVE_LOOKBACK_DAYS = 35
MAX_HOLDER_INCREASE_PPT = 25.0
HISTORY_DAYS = 62


def field(r, names):
    return pick(r, names, None)


def normalized_date(value):
    s = re.sub(r'\D', '', str(value or '').strip())
    if len(s) != 8:
        return None
    try:
        day = datetime.strptime(s, '%Y%m%d').date()
    except ValueError:
        return None
    return s if day <= now_tpe().date() else None


def normalize_rows(rows):
    out = []
    for r in rows:
        t = str(field(r, ['證券代號', 'stockCode', 'SecurityCode']) or '').strip()
        if not ordinary_ticker(t):
            continue
        date = normalized_date(field(r, ['資料日期', 'date', 'DataDate']))
        level = iv(field(r, ['持股分級', 'level', 'HoldingLevel']))
        shares = iv(field(r, ['股數', 'shares', 'Shares']))
        pct = n(field(r, ['占集保庫存數比例%', '佔集保庫存數比例%', '占集保庫存數比例 (%)', 'percentage', 'Percentage']))
        if date and level:
            out.append((date, t, level, shares, pct))
    return out


def aggregate(rows):
    by = {}
    for date, t, level, shares, pct in rows:
        d = by.setdefault(t, {'date': date, 'total': 0, '400': 0, '1000': 0})
        if level == 17:
            d['total'] = shares
        if level in (13, 14, 15):
            d['400'] += shares
        if level == 15:
            d['1000'] += shares
    for t, d in by.items():
        total = d['total']
        d['400_ratio'] = d['400'] / total * 100 if total else 0
        d['1000_ratio'] = d['1000'] / total * 100 if total else 0
    return by


def fetch_archive_date(date):
    dt = datetime.strptime(date, '%Y%m%d').date()
    url = ('https://raw.githubusercontent.com/'
           'wirelessr/tdcc-opendata-archive/'
           f'main/snapshots/{dt.year}/{dt.isoformat()}.csv')
    try:
        response = S.get(url, timeout=30)
        if response.status_code != 200:
            return None
        rows = list(csv.DictReader(io.StringIO(response.text.lstrip('\ufeff'))))
        matched = [x for x in normalize_rows(rows) if x[0] == date]
        if matched:
            return {'date': date, 'rows': matched, 'stocks': aggregate(matched)}
    except Exception as exc:
        print('archive date fail', date, exc)
    return None


def fetch_latest_archive(reference_date=None):
    base = (datetime.strptime(reference_date, '%Y%m%d').date()
            if reference_date else now_tpe().date())
    for back in range(ARCHIVE_LOOKBACK_DAYS + 1):
        snap = fetch_archive_date((base - timedelta(days=back)).strftime('%Y%m%d'))
        if snap:
            return snap
    return None


def fetch_archive_before(date):
    dt = datetime.strptime(date, '%Y%m%d').date()
    for back in range(1, 36):
        snap = fetch_archive_date((dt - timedelta(days=back)).strftime('%Y%m%d'))
        if snap:
            return {'date': snap['date'], 'stocks': snap['stocks']}
    return None


def load_display_names():
    names = {}
    master = load_json(ROOT / 'data/master.json', {}).get('stocks', {})
    for ticker, row in master.items():
        name = str(row.get('name') or '').strip()
        name = name.replace('股份有限公司', '').replace('有限公司', '').strip()
        if name:
            names[str(ticker)] = name
    sectors = load_json(ROOT / 'data/sectors.json', {})
    for sec in sectors.get('sectors', []):
        for row in sec.get('stocks', []):
            ticker = str(row.get('ticker') or '').strip()
            name = str(row.get('name') or '').strip()
            if ticker and name:
                names[ticker] = name
    return names


def normalize_market_date(value):
    s = str(value or '').strip()
    return f'{s[:4]}-{s[4:6]}-{s[6:8]}' if len(s) == 8 and s.isdigit() else s


def market_history_snapshots():
    out = []
    for p in sorted((ROOT / 'data/history/market').glob('*.json')):
        d = load_json(p, {})
        stocks = d.get('stocks', {})
        date = normalize_market_date(d.get('date') or p.stem)
        if date and stocks:
            out.append({'date': date, 'stocks': stocks})
    return sorted(out, key=lambda x: x['date'])


def market_snapshot_on_or_before(target_date, snapshots):
    target = normalize_market_date(target_date)
    valid = [x for x in snapshots if x.get('date') and x['date'] <= target]
    return valid[-1] if valid else None


def latest_valid_price_on_or_before(ticker, target_date, snapshots):
    target = normalize_market_date(target_date)
    for snap in reversed(snapshots):
        if not snap.get('date') or snap['date'] > target:
            continue
        value = snap.get('stocks', {}).get(str(ticker), {}).get('price')
        try:
            price = float(value)
        except (TypeError, ValueError):
            continue
        if 0 < price < float('inf'):
            return price
    return None


def weekly_price_change_pct(ticker, start_date, end_date, snapshots):
    old = latest_valid_price_on_or_before(ticker, start_date, snapshots)
    cur = latest_valid_price_on_or_before(ticker, end_date, snapshots)
    if old is None or cur is None:
        return None
    return round((cur / old - 1) * 100, 4)


def average_turnover_on_or_before(ticker, end_date, snapshots, days=5):
    target = normalize_market_date(end_date)
    values = []
    for snap in reversed(snapshots):
        if not snap.get('date') or snap['date'] > target:
            continue
        row = snap.get('stocks', {}).get(str(ticker), {})
        try:
            turnover = float(row.get('turnover'))
        except (TypeError, ValueError):
            continue
        if turnover < 0:
            continue
        values.append(turnover)
        if len(values) >= days:
            break
    return sum(values) / days if len(values) >= days else None


def holder_history_snapshots(latest_date):
    """Keep source snapshots; backfill missing weekly observations within 62 days."""
    base = datetime.strptime(latest_date, '%Y%m%d').date()
    cutoff = (base - timedelta(days=HISTORY_DAYS)).strftime('%Y%m%d')
    directory = ROOT / 'data/history/holders'
    snapshots = {}
    for p in sorted(directory.glob('*.json')):
        data = load_json(p, {})
        day = normalized_date(data.get('date') or p.stem)
        if day and cutoff <= day <= latest_date and data.get('stocks'):
            snapshots[day] = data

    # One observation per calendar week. Probe Thu/Fri/Sat for holiday weeks.
    # Do not make requests for weeks that already have a local snapshot.
    cursor = base
    checked_weeks = set()
    while cursor >= base - timedelta(days=HISTORY_DAYS):
        monday = cursor - timedelta(days=cursor.weekday())
        key = monday.strftime('%Y%m%d')
        cursor = monday - timedelta(days=1)
        if key in checked_weeks:
            continue
        checked_weeks.add(key)
        if any(monday <= datetime.strptime(day, '%Y%m%d').date() < monday + timedelta(days=7)
               for day in snapshots):
            continue
        for weekday in (4, 3, 5, 2):
            day = monday + timedelta(days=weekday)
            if day > base or day < base - timedelta(days=HISTORY_DAYS):
                continue
            snap = fetch_archive_date(day.strftime('%Y%m%d'))
            if snap:
                value = {'date': snap['date'], 'stocks': snap['stocks']}
                save_json(directory / f"{snap['date']}.json", value)
                snapshots[snap['date']] = value
                break
    return [snapshots[day] for day in sorted(snapshots)]


def make_holder_history(snapshots, tickers):
    """Actual weekly ratios only; no interpolation or delta reconstruction."""
    result = {}
    for ticker in sorted(tickers):
        points = []
        for snap in snapshots:
            row = snap.get('stocks', {}).get(ticker)
            if not row or not row.get('total'):
                continue
            r400 = row.get('400_ratio')
            r1000 = row.get('1000_ratio')
            if r400 is None or r1000 is None:
                continue
            points.append({'date': snap['date'], '400': round(float(r400), 5),
                           '1000': round(float(r1000), 5)})
        if points:
            result[ticker] = points
    return result


def main():
    official_rows = normalize_rows(fetch_tdcc_distribution())
    official_date = max((x[0] for x in official_rows), default=None)
    archive = fetch_latest_archive()
    archive_date = archive.get('date') if archive else None
    print('TDCC official latest:', official_date or 'none')
    print('archive latest:', archive_date or 'none')

    if archive_date and (not official_date or archive_date > official_date):
        source, date, rows = 'archive', archive_date, archive['rows']
    elif official_date:
        source, date = 'official', official_date
        rows = [x for x in official_rows if x[0] == official_date]
    elif archive_date:
        source, date, rows = 'archive', archive_date, archive['rows']
    else:
        raise RuntimeError('TDCC official and archive both returned no usable rows')

    print('selected source:', source)
    print('selected date:', date)
    latest = aggregate(rows)
    if not latest:
        raise RuntimeError(f'Empty TDCC holdings snapshot: {date}')
    existing = load_json(ROOT / 'data/holders.json', {})
    existing_date = normalized_date(existing.get('date'))
    if existing_date and existing_date > date:
        print('Keeping newer existing holders.json:', existing_date, '> selected', date)
        return

    save_json(ROOT / f'data/history/holders/{date}.json', {'date': date, 'stocks': latest})
    snapshots = holder_history_snapshots(date)
    older = [x for x in snapshots if x['date'] < date]
    prev = older[-1] if older else None
    if not prev:
        prev = fetch_archive_before(date)
        if prev:
            save_json(ROOT / f"data/history/holders/{prev['date']}.json", prev)
            snapshots.insert(0, prev)
    print('previous date:', prev.get('date') if prev else 'none')

    master = load_json(ROOT / 'data/master.json', {}).get('stocks', {})
    tech = tech_tickers(master)
    if len(tech) < 100:
        raise RuntimeError(f'tech stock universe looks incomplete: {len(tech)}')
    display_names = load_display_names()
    market_hist = market_history_snapshots()
    price_start = (market_snapshot_on_or_before(prev.get('date'), market_hist) if prev else None)
    price_end = (market_snapshot_on_or_before(date, market_hist) if prev else None)
    out = {
        'date': date,
        'previous_date': prev.get('date') if prev else None,
        'price_change_start_date': price_start.get('date') if price_start else None,
        'price_change_end_date': price_end.get('date') if price_end else None,
        'complete': bool(prev),
        'source': source,
        'official_latest_date': official_date,
        'archive_latest_date': archive_date,
        'universe': '全台股科技普通股',
        'universe_count': len(tech),
        'liquidity_filter': {
            'lookback_trading_days': TURNOVER_LOOKBACK_DAYS,
            'min_avg_turnover': MIN_AVG_TURNOVER_5D,
            'min_avg_turnover_million': MIN_AVG_TURNOVER_5D / 1_000_000
        },
        'twse': {'400': [], '1000': []},
        'tpex': {'400': [], '1000': []}
    }
    if prev:
        pstocks = prev.get('stocks', {})
        liquidity_filtered = 0
        liquidity_data_missing = 0
        for t, d in latest.items():
            if t not in pstocks or t not in master or t not in tech:
                continue
            mk = master[t]['market']
            if mk not in ('twse', 'tpex'):
                continue
            avg_turnover_5d = average_turnover_on_or_before(t, date, market_hist, TURNOVER_LOOKBACK_DAYS)
            if avg_turnover_5d is None:
                liquidity_data_missing += 1
                continue
            if avg_turnover_5d < MIN_AVG_TURNOVER_5D:
                liquidity_filtered += 1
                continue
            week_change_pct = weekly_price_change_pct(t, prev.get('date'), date, market_hist)
            for kind in ('400', '1000'):
                cur = d[f'{kind}_ratio']
                old = pstocks[t].get(f'{kind}_ratio', 0)
                delta = cur - old
                if delta <= 0 or delta > MAX_HOLDER_INCREASE_PPT:
                    continue
                out[mk][kind].append({
                    'ticker': t,
                    'name': display_names.get(t) or master[t].get('name', ''),
                    'ratio': cur,
                    'delta': delta,
                    'week_change_pct': week_change_pct,
                    'avg_turnover_5d': round(avg_turnover_5d),
                    'score': 0
                })
        out['liquidity_filtered_count'] = liquidity_filtered
        out['liquidity_data_missing_count'] = liquidity_data_missing
        for mk in ('twse', 'tpex'):
            for kind in ('400', '1000'):
                arr = sorted(out[mk][kind], key=lambda x: x['delta'], reverse=True)[:30]
                for i, x in enumerate(arr):
                    x['score'] = round(100 * (len(arr) - i) / max(1, len(arr)), 1)
                out[mk][kind] = arr

    # Only serialize chart data for ranked stocks to keep holders.json compact.
    ranked_tickers = {str(x['ticker']) for mk in ('twse', 'tpex')
                      for kind in ('400', '1000') for x in out[mk][kind]}
    out['holder_history'] = make_holder_history(snapshots, ranked_tickers)
    out['holder_history_window_days'] = HISTORY_DAYS
    out['holder_history_dates'] = [x['date'] for x in snapshots]
    save_json(ROOT / 'data/holders.json', out)
    print('holders', date, 'source', source, 'previous', out['previous_date'],
          'weekly-price', out['price_change_start_date'], '->',
          out['price_change_end_date'], 'universe', len(tech),
          'liquidity-filtered', out.get('liquidity_filtered_count', 0),
          'liquidity-missing', out.get('liquidity_data_missing_count', 0),
          'twse400', len(out['twse']['400']), 'twse1000', len(out['twse']['1000']),
          'tpex400', len(out['tpex']['400']), 'tpex1000', len(out['tpex']['1000']),
          'history-weeks', len(snapshots), 'chart-stocks', len(out['holder_history']))


if __name__ == '__main__':
    main()
