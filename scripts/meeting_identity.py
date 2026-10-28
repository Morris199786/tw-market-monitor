"""Company/day identity for LINE meetings; never calls a model or sends messages."""
import json
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


def event_index(root, cache, rows):
    """Migrate known historical IDs from durable notification records, no guessing dates."""
    previous_rows = read(root, 'data/research_meta.json', [])
    keys = {r['id']: event_key(r) for r in previous_rows + list(rows) if r.get('id')}
    aliases = {}
    for r in previous_rows + list(rows):
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
        base = rec.get('original_id') or rid.split('::')[0]
        key = rec.get('meeting_event_key') or keys.get(base)
        if not key:
            continue
        rec['meeting_event_key'] = key
        choices.setdefault(key, []).append((rid, rec))
    return {key: min(vals, key=lambda v: (v[1].get('status') != 'success', v[1].get('at', ''), v[0])) for key, vals in choices.items()}


def reuse_and_select(root, cache, rows):
    index = event_index(root, cache, rows)
    selected = {}
    others = []
    for row in rows:
        key = event_key(row)
        if not key:
            others.append(row)
            continue
        row['meeting_event_key'] = key
        old = index.get(key)
        if old:
            rid, record = old
            canonical = record.get('original_id') or rid.split('::')[0]
            row['id'] = canonical
            # A copy under the current display ID retains compatibility with render/export.
            if row['id'] != rid and record.get('status') == 'success':
                cache[row['id']] = dict(record, reused_from=rid, meeting_event_key=key)
            elif row['id'] not in cache:
                cache[row['id']] = dict(record, reused_from=rid, meeting_event_key=key)
        prior = selected.get(key)
        if prior is None or (old and row['id'] == old[0]):
            selected[key] = row
    return others + list(selected.values())
