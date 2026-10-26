#!/usr/bin/env python3
"""Export audited LINE AI facts as a chart-friendly JSON dataset, without API calls.
Place at scripts/export_research_metrics.py; run after AI batch.
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SECTIONS = ('financials', 'guidance', 'operating_metrics', 'valuations')

def read(path, default):
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else default

def export(root=ROOT):
    manifest = read(root/'data/research_manifest.json', {})
    cache = read(root/'data/research_ai_cache.json', {})
    rows = []
    seen = set()
    for shard in manifest.get('shards', []):
        filename = shard.get('file', '')
        if Path(filename).name != filename:
            continue
        for item in read(root/'data/research_shards'/filename, {}).get('items', []):
            rid = item.get('id')
            if not rid or rid in seen or item.get('source_kind') != 'line':
                continue
            seen.add(rid)
            rec = cache.get(rid, {})
            if rec.get('status') not in ('success','needs_review'):
                continue
            result = rec.get('result') or {}
            for company in result.get('companies', []):
                if not isinstance(company, dict): continue
                for section in SECTIONS:
                    for fact in company.get(section) or []:
                        if not isinstance(fact, dict): continue
                        rows.append({
                            'research_id':rid, 'date':item.get('date'),
                            'document_type':item.get('original_type') or item.get('type'),
                            'document_source':item.get('source'),
                            'company':company.get('name') or item.get('company'),
                            'ticker':company.get('ticker') or item.get('ticker'),
                            'section':section, 'metric':fact.get('metric'),
                            'period':fact.get('period'), 'value':fact.get('value'),
                            'unit':fact.get('unit'), 'actual_or_estimate':fact.get('actual_or_estimate'),
                            'source_type':fact.get('source_type'),
                            'provider':fact.get('provider'),
                            'qualifier':fact.get('qualifier'),
                            'source_column':fact.get('source_column'),
                            'evidence':fact.get('evidence'),
                            'review_status':rec.get('status'),
                        })
    return {'schema':'research-metrics-v1','count':len(rows),'items':rows}

def main():
    output = ROOT/'data/research_metrics.json'
    data = export()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(data, ensure_ascii=False, separators=(',',':'))+'\n', encoding='utf-8')
    print(f'Exported {data["count"]} research metrics to {output}')

if __name__ == '__main__':main()
