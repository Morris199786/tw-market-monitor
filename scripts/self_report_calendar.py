"""Verified exchange closures; never infer closure merely from no MOPS filings."""
import datetime as dt
import json
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]

def config():
    return json.loads((ROOT/'data/self_report_calendar.json').read_text())

def is_open(day):
    c=config(); date=dt.date.fromisoformat(day)
    if not c['valid_from'] <= day <= c['valid_through']:
        raise ValueError('Exchange calendar coverage missing: '+day)
    return date.weekday()<5 and day not in c['closed_dates']

def next_session(day):
    d=dt.date.fromisoformat(day)
    for _ in range(40):
        d+=dt.timedelta(days=1)
        if is_open(d.isoformat()): return d.isoformat()
    raise ValueError('No next session in verified calendar')

def windows(forecasts):
    """Freeze earliest forecast for each signal cutoff, retain originals for audit."""
    result={}
    for original_day, rec in sorted(forecasts.items()):
        asof=rec['asof']; target=next_session(asof)
        if original_day < target and is_open(original_day):
            raise ValueError('Unexpected forecast window: '+original_day)
        # Dates beyond target with the same stale cutoff remain in this one window.
        if target not in result:
            result[target]={**rec,'original_dates':[], 'window_start':asof}
        result[target]['original_dates'].append(original_day)
    return result
