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
import hashlib
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
import requests
import pdfplumber

ROOT = Path(__file__).resolve().parents[1]
Q = re.compile(r"(?<![A-Za-z0-9])(?:(?P<a>[1-4])\s*Q\s*(?P<b>20\d{2}|\d{2})|(?P<c>20\d{2}|\d{2})\s*Q\s*(?P<d>[1-4])|Q\s*(?P<e>[1-4])\s*['’]?\s*(?P<f>20\d{2}|\d{2})|(?P<g>20\d{2})\s*[/\-]\s*(?P<h>[1-4])Q)\s*(?:\(\s*(?P<parenflag>[AEFP])\s*\)|(?P<flag>[AEFP]))?(?![A-Za-z0-9])", re.I)
YEAR = re.compile(r'(?<!\w)(?:20\d{2}|\d{2})(?:[AEFP])?(?!\w)', re.I)
EPS = re.compile(r'(?<![A-Za-z])(?:EPS|E\.P\.S\.)(?![A-Za-z])|每股(?:稅後)?(?:盈餘|純益|收益)', re.I)
NUM = re.compile(r'(?<![\w.])\(?[-+]?\d[\d,]*(?:\.\d+)?\)?(?![\w.%])')
SKIP = re.compile(r'growth|YoY|QoQ|成長率|成長幅度|增幅|變動率|修正率|上修幅度|下修幅度|CAGR|稀釋率', re.I)
FORECAST = re.compile(r'forecast|estimate|projection|預估|預測|預期|預計|預估值', re.I)


def period(m):
    y = int(m.group('b') or m.group('c') or m.group('f') or m.group('g'))
    if y < 100: y += 2000
    return f'{y}-Q{m.group("a") or m.group("d") or m.group("e") or m.group("h")}'


def parse_number(raw):
    s = raw.strip().replace(',', '')
    neg = s.startswith('(') and s.endswith(')')
    try: v = float(s.strip('()')) * (-1 if neg else 1)
    except ValueError: return None
    return round(v, 5) if -100 <= v <= 100 else None


def header_columns(line):
    """Find quarterly AND annual columns, preserving positions for alignment."""
    qmatches = list(Q.finditer(line))
    cols = [{'kind':'quarter', 'period':period(m), 'forecast':(m.group('flag') or m.group('parenflag') or '').upper() in ('E','F','P'),
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



def report_quarter_status(quarter, report_date, explicit=False):
    """A future quarter is forecast; an ended quarter without E/F is uncertain."""
    if explicit:
        return 'forecast'
    try:
        d = datetime.fromisoformat(str(report_date)[:10])
    except (ValueError, TypeError):
        return 'unconfirmed'
    y, q = map(int, re.match(r'(\d{4})-Q([1-4])', quarter).groups())
    return 'forecast' if (y, q) > (d.year, (d.month-1)//3+1) else 'unconfirmed'


def coordinate_extract(pdf_path, report_date):
    """Parse flat and multi-level PDF tables using word coordinates.

    A quarterly header can span several subcolumns (adjusted/prior/consensus).
    Missing cells and annual columns do not invalidate the whole EPS row.
    """
    found, review = [], []
    with pdfplumber.open(str(pdf_path)) as doc:
        for page_number, page in enumerate(doc.pages, 1):
            words = page.extract_words(x_tolerance=2, y_tolerance=3, keep_blank_chars=False)
            if not words:
                review.append({'reason':'IMAGE_OR_EMPTY_PAGE','page':page_number})
                continue
            lines = []
            for w in sorted(words,key=lambda z:(round(z['top']/3),z['x0'])):
                line = next((ln for ln in reversed(lines[-5:]) if abs(ln['y']-w['top'])<=3),None)
                if line is None:
                    line={'y':w['top'],'words':[]};lines.append(line)
                line['words'].append(w)
            for ln in lines:
                ln['words'].sort(key=lambda z:z['x0'])
                ln['text']=' '.join(w['text'] for w in ln['words'])
            headers=[]
            for hi,ln in enumerate(lines):
                for m in Q.finditer(ln['text']):
                    # Text offset is NOT a PDF x-coordinate. Map match back to words.
                    pieces=[(w['text'],w) for w in ln['words']]
                    pos=0; relevant=[]
                    for token,w in pieces:
                        a=pos;b=pos+len(token)
                        if a<m.end() and b>m.start():relevant.append(w)
                        pos=b+1
                    if not relevant:continue
                    headers.append({'period':period(m),'explicit':bool(m.group('flag') or m.group('parenflag')),
                        'x0':min(w['x0'] for w in relevant),'x1':max(w['x1'] for w in relevant),
                        'x':sum((w['x0']+w['x1'])/2 for w in relevant)/len(relevant),
                        'y':ln['y'],'line':hi,'header':ln['text'][:220]})
            if not headers:continue
            for i,row in enumerate(lines):
                if not EPS.search(row['text']):continue
                if SKIP.search(row['text']):continue
                label=[w for w in row['words'] if EPS.search(w['text'])]
                if not label:continue
                end=max(w['x1'] for w in label)
                values=[]
                for w in row['words']:
                    if w['x0']<=end+1:continue
                    raw=w['text'].strip()
                    if not re.fullmatch(r'\(?[-+]?\d[\d,]*(?:\.\d+)?\)?',raw):continue
                    val=parse_number(raw)
                    if val is not None:values.append({'x':(w['x0']+w['x1'])/2,'eps':val})
                if not values:continue
                nearby=[h for h in headers if 0<row['y']-h['y']<240]
                if not nearby:continue
                # Select closest coherent header row; headers of older tables should
                # not be allowed to claim EPS values from a newer table.
                nearest=max(h['y'] for h in nearby)
                heads=[h for h in nearby if abs(h['y']-nearest)<5]
                heads.sort(key=lambda h:h['x'])
                if not heads:continue
                # For single-level tables, the value aligns with the header center.
                # For multi-level tables, assign a whole horizontal span to each
                # quarter, then use the subheader labels to select adjusted values.
                subheaders=[ln for ln in lines if nearest+2<ln['y']<row['y']-2]
                matched=0
                for n,h in enumerate(heads):
                    left=(heads[n-1]['x']+h['x'])/2 if n else end
                    right=(h['x']+heads[n+1]['x'])/2 if n+1<len(heads) else page.width
                    candidates=[v for v in values if left<=v['x']<right]
                    if not candidates:continue
                    labels=[]
                    for sub in subheaders:
                        for w in sub['words']:
                            cx=(w['x0']+w['x1'])/2
                            if left<=cx<right and re.search(r'調整後|調整前|市場共識|consensus|revised|previous|new|old',w['text'],re.I):
                                labels.append((cx,w['text']))
                    if labels:
                        preferred=[x for x in labels if re.search(r'調整後|revised|new',x[1],re.I)]
                        if not preferred:
                            review.append({'reason':'AMBIGUOUS_FORECAST','page':page_number,'period':h['period'],'header':h['header']})
                            continue
                        chosen=min(candidates,key=lambda v:abs(v['x']-preferred[0][0]))
                        if len(candidates)>1:
                            ordered=sorted(candidates,key=lambda v:v['x'])
                            if abs(chosen['x']-preferred[0][0])>max(30,page.width*.055):
                                chosen=ordered[0]
                    else:
                        if len(candidates)>1:
                            review.append({'reason':'MULTIPLE_VALUES_NO_SUBHEADER','page':page_number,'period':h['period']})
                            continue
                        chosen=candidates[0]
                        if len(heads)>1 and abs(chosen['x']-h['x'])>max(38,page.width*.07):
                            review.append({'reason':'COLUMN_MISMATCH','page':page_number,'period':h['period']})
                            continue
                    status=report_quarter_status(h['period'],report_date,h['explicit'])
                    rec={'period':h['period'],'eps':chosen['eps'],'method':'pdf_coordinate_multilevel',
                        'classification':status,'page':page_number,'header':h['header'],
                        'eps_row':row['text'][:240]}
                    if status=='forecast':found.append(rec);matched+=1
                    else:review.append({'reason':'ACTUAL_OR_FORECAST_UNCONFIRMED',**rec})
                if not matched:
                    review.append({'reason':'NO_SAFE_QUARTER_ALIGNMENT','page':page_number,'eps_row':row['text'][:180]})
    return found,review


def reconcile_results(primary, coordinate, review):
    grouped=defaultdict(list)
    for r in primary+coordinate:grouped[r['period']].append(r)
    safe=[]
    for quarter,records in grouped.items():
        vals={r['eps'] for r in records}
        if len(vals)==1:
            safe.append(next((r for r in records if r['method']=='pdf_coordinate_table'),records[0]))
        else:
            review.append({'reason':'conflicting_methods_or_tables','period':quarter,'values':sorted(vals)})
    return sorted(safe,key=lambda r:r['period']),review



def diagnose_pdf(text, safe, review, report_date):
    """Evidence-based triage: zero extracted != no forecasts in the PDF."""
    pages=text.split('\f')
    accepted={r['period'] for r in safe}
    quarter_evidence=[]
    eps_table_evidence=[]
    inline_candidates=[]
    for page_no,page in enumerate(pages,1):
        lines=page.splitlines()
        for i,line in enumerate(lines):
            qm=list(Q.finditer(line))
            has_eps=bool(EPS.search(line))
            if qm and (len(qm)>=2 or has_eps):
                quarter_evidence.append({'page':page_no,'line':i+1,'text':line.strip()[:260],
                    'quarters':list(dict.fromkeys(period(m) for m in qm))})
            if has_eps and len(list(NUM.finditer(line)))>=3:
                eps_table_evidence.append({'page':page_no,'line':i+1,'text':line.strip()[:260]})
            # Only diagnostic: inline EPS estimates are not safe to publish without
            # deciding whether the number is a broker estimate or a consensus value.
            if qm and has_eps:
                for m in qm:
                    q=period(m)
                    if q in accepted:continue
                    inline_candidates.append({'page':page_no,'line':i+1,'quarter':q,
                        'text':line.strip()[:260]})
    reasons=Counter(r.get('reason','UNKNOWN') for r in review)
    if not safe:
        if quarter_evidence and eps_table_evidence:
            status='POSSIBLE_MISSED_QUARTER_EPS'
        elif quarter_evidence or eps_table_evidence:
            status='INSUFFICIENT_TABLE_ALIGNMENT'
        else:
            status='NO_QUARTER_EPS_EVIDENCE'
    elif any(x['quarter'] not in accepted for x in inline_candidates):
        status='PARTIAL_EXTRACTION_REVIEW'
    else:
        status='EXTRACTED_REVIEW_NOT_PROVEN_COMPLETE'
    return {'diagnostic_status':status,
            'quarter_header_evidence_count':len(quarter_evidence),
            'eps_numeric_row_evidence_count':len(eps_table_evidence),
            'inline_unmatched_quarter_count':len(inline_candidates),
            'quarter_header_evidence':quarter_evidence[:12],
            'eps_numeric_row_evidence':eps_table_evidence[:12],
            'unmatched_inline_evidence':inline_candidates[:12],
            'review_reason_counts':dict(reasons),
            'review_examples_priority':sorted(review,key=lambda x:(
                0 if x.get('reason') in ('conflicting_methods_or_tables','conflicting_eps_same_period','AMBIGUOUS_FORECAST','MULTIPLE_VALUES_NO_SUBHEADER','COLUMN_MISMATCH') else 1,
                x.get('page',999)))[:16]}


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
    selected=eligible if args.limit == 0 else eligible[:max(0,args.limit)]
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
                    entry['review_examples']=[{'reason':'IMAGE_TABLE_OR_NO_TEXT'}]
                else:
                    safe,review=extract_table(proc.stdout)
                    # Coordinate extraction also handles quarter headers without E/F.
                    coords,coord_review=coordinate_extract(pdf,report.get('date'))
                    review.extend(coord_review)
                    # Plain-text parser may label historical quarters as forecasts only
                    # when they explicitly carry E/F/P. Coordinate result is checked
                    # against the plain-text result before accepting.
                    safe,review=reconcile_results(safe,coords,review)
                    for row in safe:
                        output.append({**row,'ticker':str(report['ticker']),
                            'name':report.get('name') or '', 'broker':report['broker'],
                            'report_date':report.get('date'),'report_id':report.get('id'),
                            'source_url':report.get('source_url')})
                    entry.update(status='processed',extracted_characters=len(proc.stdout),
                        accepted_forecasts=len(safe),review_count=len(review),review_examples=review[:8],
                        **diagnose_pdf(proc.stdout,safe,review,report.get('date')))
                    entry['pdf_sha256']=hashlib.sha256(pdf.read_bytes()).hexdigest()
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
    reason_counts=Counter()
    for entry in audit: reason_counts.update(entry.get('review_reason_counts',{}))
    diagnostic_counts=Counter(entry.get('diagnostic_status','NOT_DIAGNOSED') for entry in audit)
    zero_reports=[{'ticker':r['ticker'],'broker':r['broker'],'report_id':r['report_id'],
                   'status':r.get('diagnostic_status',r['status']),
                   'quarter_header_evidence_count':r.get('quarter_header_evidence_count',0),
                   'eps_numeric_row_evidence_count':r.get('eps_numeric_row_evidence_count',0)}
                  for r in audit if r.get('accepted_forecasts',0)==0]
    args.audit.write_text(json.dumps({'mode':'read_only_pdf_test',
        'eligible_reports':len(eligible),'selected_reports':len(selected),
        'accepted_forecasts':len(output),'counts':dict(counts),
        'diagnostic_counts':dict(diagnostic_counts),'zero_forecast_reports':zero_reports,
        'review_reason_counts':dict(reason_counts),'reports':audit,
        'limitations':['Text PDFs only; scanned table images require a separate vision fallback.',
            'Zero extracted is not proof that no quarterly EPS exists.',
            'Ambiguous values are not published.','No AI, Telegram, or existing data changes.']},
        ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(f'Eligible={len(eligible)}, tested={len(selected)}, accepted={len(output)}')
    print('Diagnostic statuses:',dict(diagnostic_counts))
    print('Zero-extraction reports:',len(zero_reports))

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--source',type=Path,default=ROOT/'data/reports.json')
    parser.add_argument('--output',type=Path,default=ROOT/'data/broker_eps_pdf_test.json')
    parser.add_argument('--audit',type=Path,default=ROOT/'data/broker_eps_pdf_audit.json')
    parser.add_argument('--limit',type=int,default=0,help='0 = all eligible PDF reports')
    parser.add_argument('--tickers',default='')
    run(parser.parse_args())
