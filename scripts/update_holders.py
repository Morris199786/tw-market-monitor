from sources import *
from tech_universe import tech_tickers
import csv
import io
import re
from datetime import datetime, timedelta

MIN_AVG_TURNOVER_5D = 10_000_000
TURNOVER_LOOKBACK_DAYS = 5
ARCHIVE_LOOKBACK_DAYS = 35


def field(r, names):
    return pick(r, names, None)


def normalized_date(value):
    """TDCC date -> YYYYMMDD; ignore invalid / future dates."""
    s = str(value or '').strip()
    digits = re.sub(r'\D', '', s)
    if len(digits) != 8:
        return None
    try:
        day = datetime.strptime(digits, '%Y%m%d').date()
    except ValueError:
        return None
    if day > now_tpe().date():
        return None
    return digits


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
        if not date or not level:
            continue
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
    """Check a real calendar date, not only Fridays (holiday weeks can close Thursday)."""
    dt = datetime.strptime(date, '%Y%m%d').date()
    url = ('https://raw.githubusercontent.com/'
           'wirelessr/tdcc-opendata-archive/'
           f'main/snapshots/{dt.year}/{dt.isoformat()}.csv')
    try:
        response = S.get(url, timeout=30)
        if response.status_code != 200:
            return None
        rows = list(csv.DictReader(io.StringIO(response.text.lstrip('\ufeff'))))
        nr = normalize_rows(rows)
        # Do not accept a file containing a different observation date.
        matched = [x for x in nr if x[0] == date]
        if not matched:
            return None
        return {'date': date, 'rows': matched, 'stocks': aggregate(matched)}
    except Exception as exc:
        print('archive date fail', date, exc)
        return None


def fetch_latest_archive(reference_date=None):
    """Find latest archive observation across calendar days (incl. holiday Thursdays)."""
    base = (datetime.strptime(reference_date, '%Y%m%d').date()
            if reference_date else now_tpe().date())
    for back in range(ARCHIVE_LOOKBACK_DAYS + 1):
        d = base - timedelta(days=back)
        # TDCC normally publishes weekly; try every day so holidays work too.
        snap = fetch_archive_date(d.strftime('%Y%m%d'))
        if snap:
            return snap
    return None


def fetch_archive_before(date):
    dt = datetime.strptime(date, '%Y%m%d').date()
    for back in range(1, 36):
        d = dt - timedelta(days=back)
        snap = fetch_archive_date(d.strftime('%Y%m%d'))
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
    if len(s) == 8 and s.isdigit():
        return f'{s[:4]}-{s[4:6]}-{s[6:8]}'
    return s


def market_history_snapshots():
    out = []
    files = sorted((ROOT / 'data/history/market').glob('*.json'))
    for p in files:
        d = load_json(p, {})
        stocks = d.get('stocks', {})
        date = normalize_market_date(d.get('date') or p.stem)
        if date and stocks:
            out.append({'date': date, 'stocks': stocks})
    return out


def market_snapshot_on_or_before(target_date, snapshots):
    target = normalize_market_date(target_date)
    valid = [x for x in snapshots if x.get('date') and x['date'] <= target]
    return valid[-1] if valid else None


def weekly_price_change_pct(ticker, start_snapshot, end_snapshot):
    if not start_snapshot or not end_snapshot:
        return None
    old = start_snapshot.get('stocks', {}).get(str(ticker), {}).get('price')
    cur = end_snapshot.get('stocks', {}).get(str(ticker), {}).get('price')
    try:
        old = float(old)
        cur = float(cur)
    except Exception:
        return None
    if old <= 0 or cur <= 0:
        return None
    return round((cur / old - 1) * 100, 4)


def average_turnover_on_or_before(ticker, end_date, snapshots, days=5):
    """Average turnover over last N available trading snapshots, requiring all N."""
    target = normalize_market_date(end_date)
    values = []
    for snap in reversed(snapshots):
        if not snap.get('date') or snap['date'] > target:
            continue
        row = snap.get('stocks', {}).get(str(ticker), {})
        turnover = row.get('turnover')
        try:
            turnover = float(turnover)
        except Exception:
            continue
        if turnover < 0:
            continue
        values.append(turnover)
        if len(values) >= days:
            break
    if len(values) < days:
        return None
    return sum(values) / days


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

    # Never overwrite newer output with an older snapshot if upstream regresses.
    existing = load_json(ROOT / 'data/holders.json', {})
    existing_date = normalized_date(existing.get('date'))
    if existing_date and existing_date > date:
        print('Keeping newer existing holders.json:', existing_date, '> selected', date)
        return

    save_json(ROOT / f'data/history/holders/{date}.json',
              {'date': date, 'stocks': latest})
    files = sorted((ROOT / 'data/history/holders').glob('*.json'))
    historical = []
    for p in files:
        d = load_json(p, {})
        dd = normalized_date(d.get('date') or p.stem)
        if dd and dd < date and d.get('stocks'):
            historical.append((dd, d))
    prev = max(historical, key=lambda x: x[0])[1] if historical else None
    if not prev:
        prev = fetch_archive_before(date)
        if prev:
            save_json(ROOT / f"data/history/holders/{prev['date']}.json", prev)
    print('previous date:', prev.get('date') if prev else 'none')

    master = load_json(ROOT / 'data/master.json', {}).get('stocks', {})
    tech = tech_tickers(master)
    if len(tech) < 100:
        raise RuntimeError(f'tech stock universe looks incomplete: {len(tech)}')
    display_names = load_display_names()
    market_hist = market_history_snapshots()
    price_start = (market_snapshot_on_or_before(prev.get('date'), market_hist)
                   if prev else None)
    price_end = (market_snapshot_on_or_before(date, market_hist)
                 if prev else None)
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
            avg_turnover_5d = average_turnover_on_or_before(
                t, date, market_hist, TURNOVER_LOOKBACK_DAYS)
            if avg_turnover_5d is None:
                liquidity_data_missing += 1
                continue
            if avg_turnover_5d < MIN_AVG_TURNOVER_5D:
                liquidity_filtered += 1
                continue
            week_change_pct = weekly_price_change_pct(t, price_start, price_end)
            for kind in ('400', '1000'):
                cur = d[f'{kind}_ratio']
                old = pstocks[t].get(f'{kind}_ratio', 0)
                delta = cur - old
                if delta <= 0:
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
    save_json(ROOT / 'data/holders.json', out)
    print('holders', date, 'source', source, 'previous', out['previous_date'],
          'weekly-price', out['price_change_start_date'], '->',
          out['price_change_end_date'], 'universe', len(tech),
          'liquidity-filtered', out.get('liquidity_filtered_count', 0),
          'liquidity-missing', out.get('liquidity_data_missing_count', 0),
          'twse400', len(out['twse']['400']),
          'twse1000', len(out['twse']['1000']),
          'tpex400', len(out['tpex']['400']),
          'tpex1000', len(out['tpex']['1000']))


if __name__ == '__main__':
    main()
