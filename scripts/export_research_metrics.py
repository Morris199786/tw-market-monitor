#!/usr/bin/env python3
"""Export chart-ready LINE meeting metrics from existing offline financial extraction
and new-format AI cache. Does not call any API or change paid-attempt ledgers.
"""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SECTIONS = ('financials', 'guidance', 'operating_metrics', 'valuations')


def read(path, default):
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else default


def is_meeting(item):
    return (item.get('source_kind') == 'line' and
            re.sub(r'\s+', ' ', str(item.get('original_type') or item.get('type') or '').strip()).casefold()
            in ('法說會', 'call memo'))


def export(root=ROOT):
    manifest_path = root / 'data/research_manifest.json'
    if not manifest_path.exists():
        raise RuntimeError('Missing research_manifest.json; refusing to overwrite metrics with empty data')
    manifest = read(manifest_path, {})
    if not manifest.get('shards'):
        raise RuntimeError('Empty research manifest; refusing to overwrite metrics')
    cache = read(root / 'data/research_ai_cache.json', {})
    financial = read(root / 'data/research_financial_forecasts.json', {}).get('reports', {})
    # Keep original extraction and the new API facts separate; never infer
    # guidance/actual/estimate from a number with no explicit classification.
    items, seen_ids, stats = [], set(), {'meeting_rows': 0, 'offline_financial': 0, 'ai_facts': 0,
                                         'legacy_cache_without_new_schema': 0}
    for shard in manifest['shards']:
        name = shard.get('file', '')
        if not name or Path(name).name != name:
            raise RuntimeError(f'Unsafe shard filename: {name!r}')
        path = root / 'data/research_shards' / name
        if not path.exists():
            raise RuntimeError(f'Missing shard: {path}')
        for row in read(path, {}).get('items', []):
            rid = row.get('id')
            if not rid or rid in seen_ids or not is_meeting(row):
                continue
            seen_ids.add(rid)
            stats['meeting_rows'] += 1
            base = {'research_id': rid, 'date': row.get('date'),
                    'document_type': row.get('original_type') or row.get('type'),
                    'document_source': row.get('source')}
            report = financial.get(rid, {})
            for fact in report.get('forecasts', []):
                if not isinstance(fact, dict) or fact.get('confidence') == 'conflict':
                    continue
                # 'status' denotes A/E/F for some financial tables, but blank
                # is genuinely unknown. Do not mislabel historical figures as forecasts.
                status = str(fact.get('status') or '').upper()
                classification = ('actual' if status == 'A' else
                                  'estimate' if status in ('E', 'F') else 'unknown')
                items.append({**base, 'company': report.get('company') or row.get('company'),
                              'ticker': row.get('ticker'), 'section': 'financials',
                              'metric': fact.get('metric'), 'period': fact.get('period'),
                              'value': fact.get('value'), 'unit': fact.get('unit'),
                              'actual_or_estimate': classification,
                              'source_type': 'unknown', 'provider': report.get('broker') or row.get('source'),
                              'qualifier': 'exact', 'source_column': fact.get('source_field'),
                              'evidence': fact.get('evidence'), 'review_status': 'offline_unverified',
                              'confidence': fact.get('confidence'), 'segment': fact.get('segment'),
                              'extraction_method': 'python_existing'})
                stats['offline_financial'] += 1
            # Match cache by ID and (when available) the repository's stable alias resolver.
            rec = cache.get(rid) or {}
            try:
                from sync_line_research import resolve_cache
                rec = resolve_cache(row, cache) or rec
            except ImportError:
                pass
            if rec.get('status') not in ('success', 'needs_review'):
                continue
            result = rec.get('result') or {}
            if not isinstance(result.get('companies'), list):
                stats['legacy_cache_without_new_schema'] += 1
                continue
            for company in result['companies']:
                if not isinstance(company, dict):
                    continue
                for section in SECTIONS:
                    for fact in company.get(section) or []:
                        if not isinstance(fact, dict):
                            continue
                        items.append({**base, 'company': company.get('name') or row.get('company'),
                                      'ticker': company.get('ticker') or row.get('ticker'),
                                      'section': section, 'metric': fact.get('metric'),
                                      'period': fact.get('period'), 'value': fact.get('value'),
                                      'unit': fact.get('unit'),
                                      'actual_or_estimate': fact.get('actual_or_estimate'),
                                      'source_type': fact.get('source_type'),
                                      'provider': fact.get('provider'),
                                      'qualifier': fact.get('qualifier'),
                                      'source_column': fact.get('source_column'),
                                      'evidence': fact.get('evidence'),
                                      'review_status': rec.get('status'),
                                      'extraction_method': 'openai_new_schema'})
                        stats['ai_facts'] += 1
    return {'schema': 'research-metrics-v1', 'count': len(items), 'stats': stats, 'items': items}


def main():
    data = export()
    output = ROOT / 'data/research_metrics.json'
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(data, ensure_ascii=False, separators=(',', ':')) + '\n', encoding='utf-8')
    print('Research metrics:', json.dumps(data['stats'], ensure_ascii=False))
    print(f'Exported {data["count"]} research metrics to {output}')


if __name__ == '__main__':
    main()
