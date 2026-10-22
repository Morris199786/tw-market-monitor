#!/usr/bin/env python3
"""Conservative multi-row quarterly EPS table parser; offline, no AI.
Only emits EPS when quarter, forecast status and broker column are evidenced.
"""
import re
from datetime import datetime

QUARTER=re.compile(r'(?<![A-Za-z0-9])(?:(?P<q1>[1-4])Q(?P<y1>20\d{2}|\d{2})|Q(?P<q2>[1-4])(?P<y2>20\d{2}|\d{2})|(?P<y3>20\d{2}|\d{2})Q(?P<q3>[1-4])|Q(?P<q4>[1-4])|(?P<q5>[1-4])Q)(?P<flag>\s*(?:\(\s*[AEFP]\s*\)|[AEFP]))?(?![A-Za-z0-9])',re.I)
YEAR=re.compile(r'(?<!\d)20(?:2[0-9])\s*[EF]?(?!\d)',re.I)
EPS=re.compile(r'(?<!\w)(?:net\s+)?EPS(?:\s*\([^)]{1,24}\))?(?!\w)|每股(?:稅後)?(?:盈餘|純益)',re.I)
VALUE=re.compile(r'(?<![\w.])\(?[-+]?\d{1,3}(?:,\d{3})*(?:\.\d+)?\)?(?![\w.%])')
FORECAST=re.compile(r'\b(?:forecast|estimates?|projection|UBSe|new|daiwa forecasts|GS estimates)\b|預估|預測',re.I)
ACTUAL=re.compile(r'\bactual\b|實際',re.I)
SKIP=re.compile(r'YoY|QoQ|growth|diff|change|稅前|pre.?tax|margin|EPS\s+revision',re.I)

def year_at(text, pos):
    matches=list(YEAR.finditer(text))
    before=[m for m in matches if m.start()<=pos]
    return int((before[-1] if before else matches[0]).group()[:4]) if matches else None

def date_quarter(report_date):
    try:
        d=datetime.fromisoformat(str(report_date).replace('/','-')[:10]);return d.year,(d.month-1)//3+1
    except (TypeError,ValueError):return None

def quarter_cols(line,year_line='',report_date=None):
    cols=[]
    for m in QUARTER.finditer(line):
        q=int(next(x for x in (m.group('q1'),m.group('q2'),m.group('q3'),m.group('q4'),m.group('q5')) if x))
        yy=next((x for x in (m.group('y1'),m.group('y2'),m.group('y3')) if x),None)
        y=int(yy) if yy else year_at(year_line,m.start())
        if y is None:continue
        if y<100:y+=2000
        flag=(m.group('flag') or '').replace('(','').replace(')','').strip().upper()
        status='actual' if flag=='A' else 'forecast' if flag in ('E','F','P') else 'unknown'
        if status=='unknown' and date_quarter(report_date):
            status='forecast' if (y,q)>date_quarter(report_date) else 'unknown'
        cols.append(dict(start=m.start(),period=f'{y}-Q{q}',status=status))
    return cols

def parse_layout(text,report_date=None):
    """Return (safe rows, review). No acceptance of unqualified historical quarters."""
    found=[];review=[]
    for page_no,page in enumerate(text.split('\f'),1):
        lines=page.splitlines()
        for i,line in enumerate(lines):
            if not EPS.search(line) or SKIP.search(line):continue
            label=EPS.search(line)
            nums=[(m.start(),float(m.group().replace(',','').replace('(','-').replace(')',''))) for m in VALUE.finditer(line,label.end())]
            if not nums:continue
            for j in range(max(0,i-18),i):
                header=lines[j]
                yearline=next((x for x in reversed(lines[max(0,j-3):j]) if len(list(YEAR.finditer(x)))>=1),'')
                cols=quarter_cols(header,yearline,report_date)
                if not cols:continue
                # EPS and header values align by character columns in pdftotext -layout.
                # When subcolumns exist (UBSe / consensus), use only broker's own.
                sub=lines[j+1:i]
                subheader=next((x for x in sub if re.search(r'\bUBSe\b|\bVA\b|\bConsensus\b',x,re.I)),None)
                for idx,c in enumerate(cols):
                    if c['status']!='forecast':continue
                    left=c['start']-3
                    right=(cols[idx+1]['start']-3) if idx+1<len(cols) else len(line)+10
                    candidates=[(pos,val) for pos,val in nums if left<=pos<right]
                    # Layout tools may shift columns a few characters. If there is
                    # one value per header, ordinal alignment is more reliable.
                    if len(nums)==len(cols):candidates=[nums[idx]]
                    if not candidates:continue
                    if len(candidates)>1:
                        # UBSe is the first of UBS/VA pairs, never accept consensus.
                        if subheader and re.search(r'\bUBSe\b',subheader,re.I):
                            candidates=candidates[:1]
                        else:
                            review.append({'reason':'MULTIPLE_SUBCOLUMNS','period':c['period'],'page':page_no});continue
                    pos,val=candidates[0]
                    if not -100<=val<=100:continue
                    found.append({'period':c['period'],'eps':val,'method':'pdf_structured_multilevel','page':page_no,'eps_kind':'basic' if 'basic' in line.lower() else 'generic','header':header.strip()[:220],'eps_row':line.strip()[:220]})
    grouped={}
    for row in found:grouped.setdefault(row['period'],set()).add(row['eps'])
    safe=[next(r for r in found if r['period']==p) for p,values in grouped.items() if len(values)==1]
    for p,values in grouped.items():
        if len(values)>1:review.append({'reason':'CONFLICTING_EPS_TABLES','period':p,'values':sorted(values)})
    return sorted(safe,key=lambda x:x['period']),review
