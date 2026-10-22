#!/usr/bin/env python3
"""Patch existing PDF parser in-place; no AI calls. Idempotent.

Run once after replacing this file in scripts/. Keeps the original parser and
adds support for grouped year headers (Daiwa ITEQ style).
"""
from pathlib import Path
p=Path(__file__).resolve().with_name('test_broker_eps_pdf.py')
s=p.read_text(encoding='utf-8')
if 'def grouped_year_quarter_extract(' in s:
    print('Grouped year-quarter EPS parser already installed')
    raise SystemExit(0)
anchor='\ndef reconcile_results(primary, coordinate, review):'
if anchor not in s or 'coords.extend(layout)' not in s:
    raise SystemExit('Parser layout differs from expected version; refusing unsafe patch')
code='''

def grouped_year_quarter_extract(text):
    """Recover explicit quarter estimates under year-grouped headers.

    Only uses E/F-marked quarterly columns; does not take annual, actual or
    consensus EPS. The EPS row must align with the quarter header columns.
    """
    found=[]
    qre=re.compile(r'(?<![A-Za-z0-9])([1-4])\\s*Q\\s*([EF])\\b',re.I)
    yre=re.compile(r'(?<!\\d)20\\d{2}(?:[EF])?(?!\\d)',re.I)
    label=re.compile(r'^\\s*(?:Net\\s+EPS|EPS|Diluted\\s+EPS|每股(?:稅後)?(?:盈餘|純益))\\s*(?:\\(\\s*(?:TWD|NT\\$|元)\\s*\\))?\\s+',re.I)
    for page_no,page in enumerate(text.split('\\f'),1):
        lines=page.splitlines()
        for i,row in enumerate(lines):
            m=label.match(row)
            if not m or SKIP.search(row):continue
            cells=[(v.start(),parse_number(v.group())) for v in NUM.finditer(row,m.end())]
            cells=[c for c in cells if c[1] is not None]
            if len(cells)<2:continue
            for hi in range(i-1,max(-1,i-10),-1):
                header=lines[hi]
                qs=list(qre.finditer(header))
                if len(qs)<2:continue
                # Grouped-year header is usually the immediately preceding line.
                year_candidates=[]
                for yi in range(max(0,hi-3),hi+1):
                    for y in yre.finditer(lines[yi]):
                        year_candidates.append((y.start(),int(y.group()[:4])))
                year_candidates.sort()
                if not year_candidates:continue
                # A row may also contain actual quarters before E/F quarters.
                allq=list(re.finditer(r'(?<![A-Za-z0-9])([1-4])\\s*Q(?:\\s*[AEF])?\\b',header,re.I))
                if len(allq)<len(qs) or len(cells)<len(allq):continue
                if any(abs(q.start()-cell[0])>28 for q,cell in zip(allq,cells)):continue
                for q,cell in zip(allq,cells):
                    if not qre.fullmatch(q.group().strip()):continue
                    yr=[year for pos,year in year_candidates if pos<=q.start()+5]
                    if not yr:continue
                    found.append({'period':f'{yr[-1]}-Q{q.group(1)}','eps':cell[1],
                        'method':'pdf_layout_block','classification':'forecast',
                        'page':page_no,'header':header.strip()[:240],
                        'eps_row':row.strip()[:240],'eps_kind':'generic'})
                break
    return found,[]
'''
s=s.replace(anchor,code+anchor)
s=s.replace('coords.extend(layout)\n', '''coords.extend(layout)
                    grouped,grouped_review=grouped_year_quarter_extract(proc.stdout)
                    coords.extend(grouped)
                    layout_review.extend(grouped_review)
''',1)
p.write_text(s,encoding='utf-8')
print('Patched',p)
