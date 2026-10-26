#!/usr/bin/env python3
"""Export research metrics, validate cached AI facts against original Excel A-W.
No paid API calls. Never modifies research_ai_cache.json or attempt ledger.
"""
import json
import hashlib
import re
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SECTIONS = ('financials', 'guidance', 'operating_metrics', 'valuations')
TICKER_RE = re.compile(r'^\d{4}(?:\.(?:TW|TWO))?$', re.I)
AGGREGATE_RE = re.compile(r'早報|晨報|日報|週報|彙總|匯總|總覽|多家公司|多檔|產業綜合|市場綜合|投資週刊|投資月刊', re.I)
COLUMN_KEYS = dict(zip('ABCDEFGHIJKLMNOPQRSUVW', ('date','original_type','source','industry','company','ticker','period','story','revenue','eps','inventory','utilization','guidance','trend','rating_target','numbers','dividend_current','dividend_next','dividend_policy','full_text','full_text_2','full_text_3')))


def read(path, default):
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else default


def single_company_identity(company, ticker):
    name, code = str(company or '').strip(), str(ticker or '').strip()
    return bool(TICKER_RE.fullmatch(code) and name and not AGGREGATE_RE.search(name)
                and not re.search(r'[;,；、/／]|(?:及|與).{1,10}(?:公司|股份)', name))


def is_meeting(row):
    typ = str(row.get('original_type') or row.get('type') or '').strip()
    return row.get('source_kind') == 'line' and re.sub(r'\s+', ' ', typ).casefold() in ('法說會', 'call memo')


def normalized(s):
    s = unicodedata.normalize('NFKC', str(s or '')).casefold()
    return re.sub(r'[\s,，。；;：:（）()％%＋+]', '', s)


def source_fields(row):
    result = {}
    for col, key in COLUMN_KEYS.items():
        value = row.get(key)
        if value is None and col == 'B':
            value = row.get('type')
        if value:
            result[col] = str(value)
    return result


def evidence_check(fact, row):
    """Return verified/corrected fact, or None if source cannot substantiate it.

    Do not accept paraphrases as verbatim evidence. This is intentional:
    unsupported or ambiguously classified facts are excluded, not invented.
    """
    evidence = str(fact.get('evidence') or '').strip()
    if not evidence or not str(fact.get('metric') or '').strip() or not str(fact.get('value') or '').strip():
        return None
    fields = source_fields(row)
    ev = normalized(evidence)
    matches = [col for col, value in fields.items() if ev in normalized(value)]
    if not matches:
        return None
    number = re.compile(r'(?<![\w.])-?\d+(?:,\d{3})*(?:\.\d+)?')
    ev_numbers = {n.replace(',', '') for n in number.findall(evidence)}
    value_numbers = {n.replace(',', '') for n in number.findall(str(fact.get('value')))}
    if value_numbers and not value_numbers.issubset(ev_numbers):
        return None
    # Upstream industry utilization must not become the reporting company's metric.
    if re.search(r'稼動率|利用率', str(fact.get('metric'))) and re.search(r'晶圓代工|晶圓廠|成熟製程', evidence):
        return None
    f = dict(fact)
    col = str(f.get('source_column') or '').strip().upper()
    if col not in matches:
        f['source_column'] = next((c for c in matches if c in 'IJKLMNOPQRSTUVW'), matches[0])
    period = str(f.get('period') or '').strip()
    if not period:
        return None
    # Cumulative periods must never be compared against standalone quarters.
    if re.search(r'前三季|前3季|1\s*[~～至-]\s*9\s*月', evidence):
        m = re.search(r'(20\d{2}|\d{2})', period)
        if not m:
            return None
        f['period'] = '9M' + m.group(1)[-2:]
    if re.search(r'上半年|前二季|前2季|1\s*[~～至-]\s*6\s*月', evidence):
        m = re.search(r'(20\d{2}|\d{2})', period)
        if not m:
            return None
        f['period'] = '1H' + m.group(1)[-2:]
    if re.search(r'超過|以上|至少|逾', evidence):
        f['qualifier'] = 'at_least'
    elif re.search(r'低於|不到|以下|未滿', evidence):
        f['qualifier'] = 'at_most'
    elif re.search(r'\d\s*[~～]\s*\d', evidence):
        f['qualifier'] = 'range'
    elif re.search(r'約|多元|多億|接近|略低|近\s*\d|左右', evidence):
        f['qualifier'] = 'approximate'
    # Do not change historical actuals just because the document came from a broker.
    # Forecast language attached to the *fact* is the necessary signal.
    source_type = str(f.get('source_type') or '').lower()
    forecast = bool(re.search(r'我們預估|我們預期|本行預估|預估|預期|預測|財測|目標價|上修|下修', evidence))
    if forecast and (source_type == 'broker' or str(f.get('actual_or_estimate') or '') == 'actual'):
        f['actual_or_estimate'] = 'estimate'
        f['source_type'] = 'broker'
    # The evidence can quote a current actual in a broker's forward-looking report.
    # If classification is not supported, keep it unknown rather than inventing it.
    if str(f.get('actual_or_estimate') or '') not in ('actual','estimate','guidance'):
        f['actual_or_estimate'] = 'unknown'
    return f


def reviewed_result(row, result, reviews):
    """Editorial corrections apply only to the exact source and cached result reviewed."""
    review = reviews.get(row['id']) or {}
    payload = {k: row.get(k) for k in ('company','ticker','date','full_text','full_text_2','full_text_3')}
    digest = lambda obj: hashlib.sha256(json.dumps(obj, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    if review.get('source_sha256') != digest(payload) or review.get('result_sha256') != digest(result):
        return None
    corrected = review.get('result') or {}
    for company in corrected.get('companies', []):
        for section in SECTIONS:
            for fact in company.get(section, []):
                col = fact.get('source_column')
                if not fact.get('evidence') or fact['evidence'] not in source_fields(row).get(col, ''):
                    raise ValueError('Reviewed evidence no longer matches source: ' + row['id'])
    return corrected


def export(root=ROOT):
    manifest_path = root / 'data/research_manifest.json'
    if not manifest_path.exists():
        raise RuntimeError('Missing research_manifest.json; refusing empty export')
    manifest = read(manifest_path, {})
    if not manifest.get('shards'):
        raise RuntimeError('Empty research manifest; refusing empty export')
    cache = read(root / 'data/research_ai_cache.json', {})
    reviews = read(root / 'data/research_reviewed_overrides.json', {})
    financial = read(root / 'data/research_financial_forecasts.json', {}).get('reports', {})
    items, seen = [], set()
    stats = {'meeting_rows': 0, 'offline_financial': 0, 'ai_facts': 0,
             'legacy_cache_without_new_schema': 0, 'excluded_ambiguous_offline': 0,
             'excluded_ambiguous_ai': 0, 'excluded_unverified_ai': 0}
    try:
        from sync_line_research import resolve_cache
    except ImportError:
        resolve_cache = None
    for shard in manifest['shards']:
        name = shard.get('file', '')
        if not name or Path(name).name != name:
            raise RuntimeError(f'Unsafe shard filename: {name!r}')
        path = root / 'data/research_shards' / name
        if not path.exists():
            raise RuntimeError(f'Missing shard: {path}')
        for row in read(path, {}).get('items', []):
            rid = row.get('id')
            if not rid or rid in seen or not is_meeting(row):
                continue
            seen.add(rid)
            stats['meeting_rows'] += 1
            base = {'research_id': rid, 'date': row.get('date'),
                    'document_type': row.get('original_type') or row.get('type'),
                    'document_source': row.get('source')}
            report = financial.get(rid, {})
            company = report.get('company') or row.get('company')
            ticker = row.get('ticker')
            forecasts = report.get('forecasts', [])
            if not single_company_identity(company, ticker):
                stats['excluded_ambiguous_offline'] += len(forecasts)
            else:
                for fact in forecasts:
                    if not isinstance(fact, dict) or fact.get('confidence') == 'conflict':
                        continue
                    status = str(fact.get('status') or '').upper()
                    classification = 'actual' if status == 'A' else 'estimate' if status in ('E','F') else 'unknown'
                    items.append({**base, 'company': company, 'ticker': ticker,
                                  'section': 'financials', 'metric': fact.get('metric'),
                                  'period': fact.get('period'), 'value': fact.get('value'),
                                  'unit': fact.get('unit'), 'actual_or_estimate': classification,
                                  'source_type': 'unknown', 'provider': report.get('broker') or row.get('source'),
                                  'qualifier': 'exact', 'source_column': fact.get('source_field'),
                                  'evidence': fact.get('evidence'), 'review_status': 'offline_unverified',
                                  'confidence': fact.get('confidence'), 'segment': fact.get('segment'),
                                  'extraction_method': 'python_existing'})
                    stats['offline_financial'] += 1
            rec = cache.get(rid) or {}
            if resolve_cache:
                rec = resolve_cache(row, cache) or rec
            if rec.get('status') not in ('success', 'needs_review'):
                continue
            result = rec.get('result') or {}
            reviewed = reviewed_result(row, result, reviews)
            if reviewed is not None:
                result = reviewed
            elif rec.get('status') == 'needs_review':
                # An unresolved AI audit is not a verified financial table.
                stats['excluded_unverified_ai'] += sum(len(c.get(s) or []) for c in result.get('companies', []) if isinstance(c, dict) for s in SECTIONS)
                continue
            if not isinstance(result.get('companies'), list):
                stats['legacy_cache_without_new_schema'] += 1
                continue
            for ai_company in result['companies']:
                if not isinstance(ai_company, dict):
                    continue
                name = ai_company.get('name') or row.get('company')
                code = ai_company.get('ticker') or row.get('ticker')
                if not single_company_identity(name, code) or (
                    not single_company_identity(row.get('company'), row.get('ticker'))
                    and not (ai_company.get('name') and ai_company.get('ticker'))):
                    stats['excluded_ambiguous_ai'] += sum(len(ai_company.get(s) or []) for s in SECTIONS)
                    continue
                for section in SECTIONS:
                    for fact in ai_company.get(section) or []:
                        if not isinstance(fact, dict):
                            stats['excluded_unverified_ai'] += 1
                            continue
                        checked = dict(fact) if reviewed is not None else evidence_check(fact, row)
                        if checked is None:
                            stats['excluded_unverified_ai'] += 1
                            continue
                        items.append({**base, 'company': name, 'ticker': code,
                                      'section': section, 'metric': checked.get('metric'),
                                      'period': checked.get('period'), 'value': checked.get('value'),
                                      'unit': checked.get('unit'),
                                      'actual_or_estimate': checked.get('actual_or_estimate'),
                                      'source_type': checked.get('source_type'),
                                      'provider': checked.get('provider'),
                                      'qualifier': checked.get('qualifier'),
                                      'source_column': checked.get('source_column'),
                                      'evidence': checked.get('evidence'),
                                      'review_status': 'editorially_verified' if reviewed is not None else 'source_verified',
                                      'extraction_method': 'openai_new_schema'})
                        stats['ai_facts'] += 1
    return {'schema': 'research-metrics-v1', 'count': len(items), 'stats': stats, 'items': items}



def export_ai_direct(root=ROOT):
    """Publish model output verbatim as data. No Python content or evidence gating."""
    manifest = read(root / 'data/research_manifest.json', {})
    cache = read(root / 'data/research_ai_cache.json', {})
    out = {}
    trial_suffix = '::gpt-5.6-luna-trial-v1'
    full_article_suffix = '::gpt-5.6-luna-full-article-v2'
    for shard in manifest.get('shards', []):
        path = root / 'data/research_shards' / shard.get('file', '')
        if not path.is_file():
            continue
        for row in read(path, {}).get('items', []):
            rid = row.get('id')
            if not rid or not is_meeting(row):
                continue
            # A paid 5.6 trial takes priority over older cached extraction.
            candidates = [cache.get(rid + full_article_suffix), cache.get(rid), cache.get(rid + trial_suffix)]
            for rec in candidates:
                if not isinstance(rec, dict) or rec.get('status') != 'success' or not isinstance(rec.get('result'), dict):
                    continue
                result = rec['result']
                # New model's free-form blocks, or existing model's native result.
                if isinstance(result.get('blocks'), list) or isinstance(result.get('companies'), list):
                    out[rid] = {'model':rec.get('model'), 'content':result}
                    break
    dest = root / 'data/research_ai_render.json'
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps({'schema':'research-ai-direct-v1','items':out},ensure_ascii=False,separators=(',',':'))+'\n',encoding='utf-8')
    print('AI_DIRECT_PUBLISHED',len(out))
    return out

def main():
    data = export()
    output = ROOT / 'data/research_metrics.json'
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(data, ensure_ascii=False, separators=(',', ':')) + '\n', encoding='utf-8')
    export_ai_direct(ROOT)
    print('Research metrics:', json.dumps(data['stats'], ensure_ascii=False))
    print(f'Exported {data["count"]} research metrics to {output}')


if __name__ == '__main__':
    main()
