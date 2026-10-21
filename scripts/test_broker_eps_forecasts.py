#!/usr/bin/env python3
"""Read-only, zero-API-credit audit of quarterly broker EPS estimates in data/reports.json.

Run: python scripts/test_broker_eps_forecasts.py
Writes data/broker_eps_forecasts_test.json and data/broker_eps_forecasts_audit.json.
No modifications to existing JSON, no Telegram, no API calls.
"""
from __future__ import annotations
import argparse
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PERIOD = re.compile(r'(?<!\w)(?:(?P<q1>[1-4])\s*Q\s*(?P<y1>20\d{2}|\d{2})|(?P<y2>20\d{2}|\d{2})\s*Q\s*(?P<q2>[1-4])|(?P<y3>20\d{2})\s*年\s*第?\s*(?P<q3>[一二三四1-4])\s*季)\s*(?P<suffix>[EeFfPpAa])?(?!\w)', re.I)
EPS_LABEL = re.compile(r'(?<![a-z])(?:EPS|每股(?:盈餘|純益|稅後盈餘|稅後純益))(?![a-z])', re.I)
NUMBER = re.compile(r'(?<![\d,])(?P<num>\(?[+-]?\d{1,3}(?:,\d{3})*(?:\.\d+)?\)?|\(?[+-]?\d+(?:\.\d+)?\)?)(?![\d,])')
FORECAST = re.compile(r'預估|預測|預期|估計|估|forecast|estimate|project|expected|\bE\b|\bF\b', re.I)
ACTUAL = re.compile(r'實際|已公布|已公告|actual|reported|\bA\b', re.I)
QUARTER_CN = {'一':1,'二':2,'三':3,'四':4}

def flatten(v):
    if isinstance(v, str): return [v]
    if isinstance(v, list):
        out=[]
        for item in v: out.extend(flatten(item))
        return out
    if isinstance(v, dict):
        out=[]
        for k, item in v.items():
            if k in ('source_url','url','source_file_id','id'): continue
            out.extend(flatten(item))
        return out
    return []

def quarter(m):
    y = m.group('y1') or m.group('y2') or m.group('y3')
    q = m.group('q1') or m.group('q2') or m.group('q3')
    y = int(y)
    if y < 100: y += 2000
    q = QUARTER_CN.get(q, q)
    return f'{y}-Q{q}'

def candidate(text):
    """Only explicit nearby EPS/period/value triplets; ambiguous snippets are excluded."""
    text = re.sub(r'\s+', ' ', text).strip()
    if len(text)>1800: return [],'too_long'
    if re.search(r'全年|年度|年EPS|FY\d{2,4}|9M\d{2}|1H\d{2}|累計',text,re.I) and not re.search(r'單季|當季',text):
        return [],'annual_or_cumulative_context'
    ms=list(PERIOD.finditer(text)); es=list(EPS_LABEL.finditer(text))
    if not ms or not es: return [],'no_period_or_eps'
    found=[]
    for pm in ms:
        # Require exactly one period in a compact evidence window to avoid table-column shifts.
        for em in es:
            left=min(pm.start(),em.start()); right=max(pm.end(),em.end())
            if right-left>85: continue
            window=text[max(0,left-15):min(len(text),right+45)]
            if len(PERIOD.findall(window)) != 1: continue
            suffix=(pm.group('suffix') or '').upper()
            if suffix=='A' or (ACTUAL.search(window) and not FORECAST.search(window)):
                continue
            if suffix not in ('E','F','P') and not FORECAST.search(window): continue
            # Only values after the last of period / EPS label, not years in period.
            tail=text[right:min(len(text),right+35)]
            tail=re.sub(r'^[\s:：=為約達NT$＄元]*','',tail)
            match=NUMBER.match(tail)
            if not match: continue
            raw=match.group('num'); negative=raw.startswith('(') and raw.endswith(')')
            try: val=float(raw.strip('()').replace(',','')) * (-1 if negative else 1)
            except ValueError: continue
            if not -100 <= val <= 100: continue
            found.append({'period':quarter(pm),'eps':val,'evidence':window[:160],'method':'explicit_text'})
    uniq={(x['period'],x['eps']):x for x in found}
    if len(uniq)!=1: return [],'ambiguous_or_multiple_values' if uniq else 'no_unambiguous_value'
    return list(uniq.values()),'ok'

def run(source:Path, output:Path, audit:Path):
    data=json.loads(source.read_text(encoding='utf-8'))
    items=data.get('items',[]) if isinstance(data,dict) else data
    records=[]; counts=Counter(); samples=[]
    for report in items:
        ticker=str(report.get('ticker') or '').strip()
        broker=str(report.get('broker') or '').strip()
        report_date=str(report.get('date') or '')[:10]
        if not re.fullmatch(r'\d{4}',ticker) or not broker or not re.fullmatch(r'20\d{2}-\d{2}-\d{2}',report_date):
            counts['skipped_no_stock_broker_or_date']+=1; continue
        evidence=[]
        for field in ('summary','key_points','detail','forecast_changes'):
            for fragment in flatten(report.get(field)):
                for piece in re.split(r'[。；;\n]',fragment):
                    if len(piece)<8 or not EPS_LABEL.search(piece): continue
                    rows,reason=candidate(piece)
                    counts[reason]+=1
                    evidence.extend(rows)
        for item in evidence:
            records.append({'ticker':ticker,'name':report.get('name',''),'broker':broker,'period':item['period'],
                'eps':item['eps'],'report_date':report_date,'report_id':report.get('id',''),
                'source_url':report.get('source_url',''),'method':item['method'],'evidence':item['evidence']})
    # Conflicting values in same report/quarter are not safe to publish.
    groups={}
    for row in records: groups.setdefault((row['report_id'],row['ticker'],row['period']),[]).append(row)
    safe=[]
    for rows in groups.values():
        vals={x['eps'] for x in rows}
        if len(vals)==1: safe.append(rows[0])
        else: counts['conflicting_report_values']+=1
    safe.sort(key=lambda x:(x['ticker'],x['period'],x['broker'],x['report_date']))
    result={'generated_at':datetime.now(timezone.utc).isoformat(),'mode':'test_only_no_ai_no_push',
        'source':'data/reports.json (existing extracted summaries only)','forecasts':safe}
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    audit.write_text(json.dumps({'reports_scanned':len(items),'candidate_mentions':len(records),
        'accepted_forecasts':len(safe),'reasons':dict(counts),
        'limitations':['Text-only audit; PDF tables missing from stored summaries cannot be recovered.',
        'Requires manual evidence review before production use.',
        'Does not modify the existing report ingestion or self-report workflows.']},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(f'Reports: {len(items)} | Candidate mentions: {len(records)} | Accepted: {len(safe)}')
    print(f'Forecasts: {output}\nAudit: {audit}')

if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--source',type=Path,default=ROOT/'data/reports.json')
    p.add_argument('--output',type=Path,default=ROOT/'data/broker_eps_forecasts_test.json')
    p.add_argument('--audit',type=Path,default=ROOT/'data/broker_eps_forecasts_audit.json')
    args=p.parse_args(); run(args.source,args.output,args.audit)
