"""Company/day identity for LINE meetings; never calls a model or sends messages."""
import json
from datetime import date
import re
import unicodedata


def name(value):
    text = unicodedata.normalize('NFKC', str(value or '')).strip()
    chinese = re.match(r'[\u4e00-\u9fff]+(?:-KY)?', text)
    return chinese.group().casefold() if chinese else re.sub(r'[^a-z0-9]', '', text.casefold())


def event_key(row):
    if row.get('source_kind') == 'broker':
        return ''
    if row.get('category') not in ('法說／訪談', '法說/訪談') and str(row.get('original_type') or row.get('type')).lower() not in ('call memo', '法說會'):
        return ''
    day = str(row.get('date') or '')[:10].replace('/', '-')
    if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', day):
        return ''
    # Exact company sets: a two-company meeting must not suppress an individual one.
    company = str(row.get('company') or '')
    parts = [name(x) for x in re.split(r'[/／、;；+＋]', company)]
    parts = sorted(set(x for x in parts if x))
    if not parts:
        return ''
    codes = sorted(set(re.findall(r'(?<![A-Za-z0-9])(?:\d{4,6}(?:\.(?:TW|TWO|JP|HK|KR))?|[A-Z]+\.US)(?![A-Za-z0-9])', str(row.get('ticker') or '').upper())))
    codes = [re.sub(r'\.(TW|TWO)$', '', x) for x in codes]
    identity = 'ticker:' + '|'.join(codes) if codes else 'name:' + '|'.join(parts)
    return 'meeting-day-v1:' + day + ':' + identity


def read(root, path, default):
    p = root / path
    return json.loads(p.read_text(encoding='utf-8')) if p.exists() else default


def _parts(key):
    match = re.fullmatch(r'meeting-day-v1:(\d{4}-\d{2}-\d{2}):(ticker|name):(.+)', key or '')
    if not match:
        return None
    try:
        return date.fromisoformat(match[1]), match[2], match[3]
    except ValueError:
        return None


def _same_event(a, b):
    x, y = _parts(a), _parts(b)
    return bool(x and y and x[1:] == y[1:] and abs((x[0] - y[0]).days) <= 2)


def event_index(root, cache, rows):
    """Index existing attempts; reuse a SUCCESS within two calendar days.

    Exact-day failed attempts retain their original retry lock. Different dates
    never inherit failed/uncertain attempts. No model calls are made here.
    """
    previous_rows = read(root, 'data/research_meta.json', [])
    all_rows = previous_rows + list(rows)
    keys = {str(r['id']): event_key(r) for r in all_rows if r.get('id')}
    aliases = {}
    for r in all_rows:
        nk = event_key(dict(r, ticker=''))
        if nk:
            aliases.setdefault(nk, set()).add(event_key(r))
    ledger = read(root, 'data/research_telegram_delivery.json', {}).get('deliveries', {})
    for rid, rec in ledger.items():
        match = re.fullmatch(r'(\d{4}-\d{2}-\d{2}) (.+) 法說/訪談', rec.get('text', ''))
        if match:
            nk = event_key({'date': match[1], 'company': match[2], 'category': '法說／訪談'})
            candidates = aliases.get(nk, set())
            keys[rid] = next(iter(candidates)) if len(candidates) == 1 else nk
    choices = {}
    for rid, rec in cache.items():
        if not isinstance(rec, dict) or rec.get('status') == 'alias':
            continue
        base = str(rec.get('original_id') or rid.split('::')[0])
        key = keys.get(base) or rec.get('meeting_event_key')
        if not _parts(key):
            continue
        rec['meeting_event_key'] = key
        choices.setdefault(key, []).append((rid, rec))
    exact = {key: min(vals, key=lambda v: (v[1].get('status') != 'success', v[1].get('at', ''), v[0]))
             for key, vals in choices.items()}
    # Alias only to an already successful, independently dated meeting.
    # Never let a failed attempt suppress a new report on another date.
    result = dict(exact)
    targets = set(keys.values()) | set(exact)
    successes = [(key, rid, rec) for key, vals in choices.items()
                 for rid, rec in vals if rec.get('status') == 'success']
    for target in targets:
        if not _parts(target):
            continue
        nearby = [(abs((_parts(target)[0] - _parts(key)[0]).days),
                   _parts(key)[0], rid, rec)
                  for key, rid, rec in successes if _same_event(target, key)]
        if nearby:
            # Prefer the earliest successfully parsed event on ties.
            _, _, rid, rec = min(nearby, key=lambda v: (v[0], v[1], v[2]))
            result[target] = rid, rec
    return result


def reuse_and_select(root, cache, rows):
    index = event_index(root, cache, rows)
    # Preserve the original successful row/date for website display.
    old_rows = read(root, 'data/research_meta.json', [])
    by_id = {str(r.get('id')): r for r in old_rows + list(rows) if r.get('id')}
    selected = {}
    others = []
    for row in rows:
        key = event_key(row)
        if not key:
            others.append(row)
            continue
        old = index.get(key)
        if old and old[1].get('status') == 'success':
            rid, record = old
            canonical = str(record.get('original_id') or rid.split('::')[0])
            original = by_id.get(canonical)
            if original and event_key(original) and _same_event(key, event_key(original)):
                row = dict(original)
            else:
                # Do not invent an original date or overwrite a different report.
                row = dict(row)
                row['id'] = canonical
            row['meeting_event_key'] = event_key(row)
            if canonical not in cache:
                cache[canonical] = dict(record, reused_from=rid, meeting_event_key=event_key(row))
            group = 'success:' + canonical
        else:
            row = dict(row)
            row['meeting_event_key'] = key
            group = 'day:' + key
        if group not in selected:
            selected[group] = row
    return others + list(selected.values())
