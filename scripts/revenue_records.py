"""Date-aware revenue records. Never infer all-time highs from a running maximum."""
from decimal import Decimal, InvalidOperation


def value(v):
    try:
        d = Decimal(str(v))
        return d if d.is_finite() and d >= 0 else None
    except (InvalidOperation, ValueError, TypeError):
        return None


def classify(row, history):
    t, month = row['ticker'], row['month']
    entry = history.get('stocks', {}).get(t, {})
    observations = entry.get('months', {})
    prior = {m: value(v) for m, v in observations.items() if m < month}
    prior = {m: v for m, v in prior.items() if v is not None}
    current = value(row.get('revenue_100m'))
    # Full-history certification must have a source and uninterrupted monthly coverage.
    start = entry.get('coverage_start', '')
    expected = []
    if start and start < month:
        y, m = map(int, start.split('-'))
        while f'{y:04d}-{m:02d}' < month:
            expected.append(f'{y:04d}-{m:02d}')
            y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    complete = bool(entry.get('full_history_verified') is True and entry.get('source')
                    and expected and all(m in prior for m in expected))
    checked = complete and current is not None
    previous_max = max(prior.values()) if prior else None
    high = bool(current > previous_max) if checked else None
    return {'record_high': high, 'record_high_checked': checked,
            'record_high_status': ('new_high' if high else 'not_high') if checked else 'insufficient_history',
            'previous_max_100m': float(previous_max) if previous_max is not None else None,
            'history_months': len(prior), 'history_start': min(prior) if prior else None,
            'history_source': entry.get('source'),
            'record_high_note': '已核對完整歷史' if checked else '歷史資料不足，待核對'}


def record(rows, history):
    history.setdefault('stocks', {})
    for row in rows:
        row.update(classify(row, history))
        if value(row.get('revenue_100m')) is not None:
            history['stocks'].setdefault(row['ticker'], {}).setdefault('months', {})[row['month']] = row['revenue_100m']
    history['schema_version'] = 2
    return history
