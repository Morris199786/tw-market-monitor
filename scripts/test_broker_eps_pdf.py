#!/usr/bin/env python3
"""Read-only broker quarterly EPS PDF audit. No AI, Telegram, or repo writes.

Handles quarterly + annual columns in the same table, forecast headers such as
Q326E / 3Q26E / 2026Q3E, and EPS rows with extra annual numbers.
"""
from __future__ import annotations
import argparse
import json
import os
import re
import subprocess
import tempfile
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
import requests

ROOT = Path(__file__).resolve().parents[1]
Q = re.compile(r'(?<![\w])(?:(?P<a>[1-4])\s*Q\s*(?P<b>20\d{2}|\d{2})|(?P<c>20\d{2}|\d{2})\s*Q\s*(?P<d>[1-4])|Q\s*(?P<e>[1-4])\s*(?P<f>20\d{2}|\d{2}))\s*(?P<flag>[AEFP])?(?![A-Za-z0-9])', re.I)
YEAR = re.compile(r'(?<!\w)(?:20\d{2}|\d{2})(?:[AEFP])?(?!\w)', re.I)
EPS = re.compile(r'(?<![A-Za-z])(?:EPS|E\.P\.S\.)(?![A-Za-z])|每股(?:稅後)?(?:盈餘|純益|收益)', re.I)
NUM = re.compile(r'(?<![\w.])\(?[-+]?\d[\d,]*(?:\.\d+)?\)?(?![\w.%])')
SKIP = re.compile(r'growth|YoY|QoQ|%|成長|增幅|調整|變動|修正|上修|下修|CAGR|稀釋率', re.I)
FORECAST = re.compile(r'forecast|estimate|projection|預估|預測|預期|預計|預估值', re.I)


def period(m):
    y = int(m.group('b') or m.group('c') or m.group('f'))
    if y < 100: y += 2000
    return f'{y}-Q{m.group("a") or m.group("d") or m.group("e")}'


def parse_number(raw):
    s = raw.strip().replace(',', '')
    neg = s.startswith('(') and s.endswith(')')
    try: v = float(s.strip('()')) * (-1 if neg else 1)
    except ValueError: return None
    return round(v, 5) if -100 <= v <= 100 else None


def header_columns(line):
    """Find quarterly AND annual columns, preserving positions for alignment."""
    qmatches = list(Q.finditer(line))
    cols = [{'kind':'quarter', 'period':period(m), 'forecast':(m.group('flag') or '').upper() in ('E','F','P'),
             'start':m.start(), 'center':(m.start()+m.end())/2, 'end':m.end()} for m in qmatches]
    masked = list(line)
    for m in qmatches:
        for i in range(m.start(),m.end()): masked[i]=' '
    for m in YEAR.finditer(''.join(masked)):
        y = m.group()
        if len(y) >= 4 or y[-1].upper() in ('E','F','P'):
            cols.append({'kind':'annual','period':None,'forecast':False,
                         'start':m.start(),'center':(m.start()+m.end())/2,'end':m.end()})
    return sorted(cols,key=lambda c:c['start'])


def extract_table(text):
    accepted, review = [], []
    pages = text.split('\f')
    for page_no, page in enumerate(pages,1):
        lines = page.splitlines()
        for i,line in enumerate(lines):
            match = EPS.search(line)
            if not match or SKIP.search(line): continue
            # EPS row values begin after the label, never treat label/units as data.
            vals = [(m.start(),parse_number(m.group())) for m in NUM.finditer(line,match.end())]
            vals = [(pos,val) for pos,val in vals if val is not None]
            if not vals: continue
            candidates=[]
            for hi in range(max(0,i-32),i):
                h=lines[hi]
                cols=header_columns(h)
                qs=[c for c in cols if c['kind']=='quarter' and c['forecast']]
                if not qs: continue
                # Multiple unrelated numbers in text are rejected; table rows need
                # a complete 1:1 map of values to header columns.
                if len(cols)!=len(vals): continue
                # Relative index is robust to PDF text-width drift; also require
                # monotonic spatial correspondence to guard against shifted cells.
                alignment=[]
                for col,(x,v) in zip(cols,vals):
                    alignment.append(abs(x-col['start']))
                if max(alignment)>max(35, len(h)//12): continue
                for col,(_,value) in zip(cols,vals):
                    if col['kind']=='quarter' and col['forecast']:
                        candidates.append({'period':col['period'],'eps':value,
                            'method':'pdf_table_quarter_with_annual_alignment',
                            'page':page_no,'page_line':i+1,
                            'header':h.strip()[:240], 'eps_row':line.strip()[:240]})
            # Choose nearest matching header. Distant summary headers often refer
            # to a different table; reject conflicting values for a period.
            uniq={}
            for c in candidates: uniq.setdefault((c['period'],c['eps']),c)
            periods=defaultdict(set)
            for c in uniq.values(): periods[c['period']].add(c['eps'])
            if any(len(v)>1 for v in periods.values()):
                review.append({'reason':'ambiguous_headers','page':page_no,'line':i+1}); continue
            if uniq: accepted.extend(uniq.values())
            else: review.append({'reason':'no_safe_quarter_column_alignment','page':page_no,'line':i+1,'eps_row':line.strip()[:160]})
    by_period=defaultdict(list)
    for row in accepted: by_period[row['period']].append(row)
    safe=[]
    for p,rows in by_period.items():
        vals={r['eps'] for r in rows}
        if len(vals)==1: safe.append(rows[0])
        else: review.append({'reason':'conflicting_eps_same_period','period':p,'values':sorted(vals)})
    return sorted(safe,key=lambda r:r['period']),review


def download_pdf(fid,token,path):
    resp=requests.get(f'https://www.googleapis.com/drive/v3/files/{fid}',
        params={'alt':'media','supportsAllDrives':'true'},
        headers={'Authorization':f'Bearer {token}'},timeout=75)
    resp.raise_for_status()
    if not resp.content.startswith(b'%PDF'): raise ValueError('Drive response is not PDF')
    path.write_bytes(resp.content)


def run(args):
    reports=json.loads(args.source.read_text(encoding='utf-8'))['items']
    eligible=[r for r in reports if re.fullmatch(r'\d{4}',str(r.get('ticker') or ''))
        and (r.get('source_file_id') or r.get('id'))
        and str(r.get('source_name') or '').lower().endswith('.pdf') and r.get('broker')]
    eligible.sort(key=lambda r:(str(r.get('date') or ''),str(r.get('received_at') or '')),reverse=True)
    if args.tickers:
        tickers={t.strip() for t in args.tickers.split(',') if t.strip()}
        eligible=[r for r in eligible if str(r['ticker']) in tickers]
    selected=eligible[:min(args.limit,10)]
    token=os.getenv('ACCESS_TOKEN','').strip()
    if not token: raise SystemExit('ACCESS_TOKEN missing: run through test-broker-eps-pdf.yml')
    output,audit,counts=[],[],Counter()
    with tempfile.TemporaryDirectory() as temp:
        for report in selected:
            entry={'ticker':report['ticker'],'broker':report['broker'],
                'report_date':report.get('date'),'report_id':report.get('id'),
                'source_name':report.get('source_name')}
            try:
                pdf=Path(temp)/'source.pdf'
                download_pdf(report.get('source_file_id') or report['id'],token,pdf)
                proc=subprocess.run(['pdftotext','-layout','-enc','UTF-8',str(pdf),'-'],
                    capture_output=True,text=True,timeout=60)
                if proc.returncode: raise RuntimeError('pdftotext failed: '+proc.stderr[:180])
                if len(proc.stdout.strip())<100:
                    entry['status']='pdf_text_empty_or_scanned'
                else:
                    safe,review=extract_table(proc.stdout)
                    for row in safe:
                        output.append({**row,'ticker':str(report['ticker']),
                            'name':report.get('name') or '', 'broker':report['broker'],
                            'report_date':report.get('date'),'report_id':report.get('id'),
                            'source_url':report.get('source_url')})
                    entry.update(status='processed',extracted_characters=len(proc.stdout),
                        accepted_forecasts=len(safe),review_count=len(review),review_examples=review[:8])
                    counts['accepted']+=len(safe)
                    counts['needs_review']+=len(review)
            except Exception as exc:
                entry.update(status='error',error=str(exc)[:250])
            counts[entry['status']]+=1
            audit.append(entry)
            print(f"{entry['ticker']} {entry['broker']}: {entry['status']} EPS={entry.get('accepted_forecasts',0)}")
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps({'mode':'test_only_no_ai_no_push',
        'generated_at':datetime.now(timezone.utc).isoformat(),'forecasts':output},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    args.audit.write_text(json.dumps({'mode':'read_only_pdf_test',
        'eligible_reports':len(eligible),'selected_reports':len(selected),
        'accepted_forecasts':len(output),'counts':dict(counts),'reports':audit,
        'limitations':['Text PDFs only; scanned table images require a separate vision fallback.',
            'No quarterly forecast in report is a valid zero result.',
            'Ambiguous values are not published.','No AI, Telegram, or existing data changes.']},
        ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(f'Eligible={len(eligible)}, tested={len(selected)}, accepted={len(output)}')

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--source',type=Path,default=ROOT/'data/reports.json')
    parser.add_argument('--output',type=Path,default=ROOT/'data/broker_eps_pdf_test.json')
    parser.add_argument('--audit',type=Path,default=ROOT/'data/broker_eps_pdf_audit.json')
    parser.add_argument('--limit',type=int,default=10)
    parser.add_argument('--tickers',default='')
    run(parser.parse_args())
