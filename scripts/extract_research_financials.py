#!/usr/bin/env python3
"""Offline financial forecast extraction from LINE research shards. No network / OpenAI.
Run: python scripts/extract_research_financials.py
Writes data/research_financial_forecasts.json; never edits AI cache or source shards.
"""
import argparse
import json
import re
from pathlib import Path

METRICS = [
 ('gross_margin',r'毛利率|gross\s+margin|GPM'),
 ('operating_margin',r'營業利益率|營益率|營業利潤率|operating\s+margin|OPM'),
 ('net_margin',r'淨利率|net\s+(?:profit\s+)?margin'),
 ('pretax_margin',r'稅前(?:淨)?利率|pretax\s+margin'),
 ('revenue_yoy',r'(?:營收|revenue)\s*(?:年成長率|YoY\s*%|YoY|年增率)|年成長率\(%\)|^\s*YoY%'),
 ('revenue_qoq',r'(?:營收|revenue)\s*(?:QoQ|季增率)|^\s*QoQ%'),
 ('revenue',r'營業收入|營收|revenue|net\s+sales'),
 ('gross_profit',r'銷貨毛利|營業毛利|gross\s+profit'),
 ('operating_profit',r'營業利益|營業利潤|operating\s+(?:income|profit)|EBIT'),
 ('pretax_profit',r'稅前(?:淨)?利|pretax\s+(?:income|profit)'),
 ('net_income',r'稅後淨利|歸屬母公司淨利|net\s+income'),
 ('eps',r'(?<![A-Za-z])(?:non-GAAP\s+)?(?:diluted\s+)?EPS|每股(?:稅後)?盈餘'),
 ('roe',r'淨值報酬率|股東權益報酬率|ROE'),
 ('roa',r'資產報酬率|ROA'),
 ('operating_cash_flow',r'營業(?:活動)?現金流|operating\s+cash\s+flow'),
 ('free_cash_flow',r'自由現金流|free\s+cash\s+flow|\bFCF\b'),
 ('capex',r'資本支出|\bCAPEX\b'),
 ('dividend',r'每股現金股利|現金股利'),
 ('pe',r'本益比\s*\(x\)|P/E\s*\(x\)'),
 ('pb',r'本淨比\s*\(x\)|P/B\s*\(x\)'),
]
PERIOD = re.compile(r'(?<!\w)(?:FY\s*)?(20\d{2}|\d{2})\s*[-/ ]?\s*(?:Q\s*([1-4])|([1-4])\s*Q)?\s*([EFA])?(?![A-Za-z0-9])',re.I)
QUARTER_FIRST = re.compile(r'(?<![A-Za-z0-9])([1-4])\s*Q\s*(20\d{2}|\d{2})\s*([EFA])?(?![A-Za-z0-9])',re.I)
NUM = re.compile(r'(?<![\w.])[-+−]?\s*(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?\s*%?')
BAD = re.compile(r'(?i)\b(?:#N/A|N/A|NA|nan|none|null)\b|^[-—–]+$')
REVISION = re.compile(r'原估|新估|差異|前次估|上修|下修|調升|調降|共識|consensus|revision',re.I)


def metric_of(label):
    for name,pattern in METRICS:
        if re.search(pattern,label,re.I):return name
    return None


def periods(text):
    hits=[]
    for m in QUARTER_FIRST.finditer(text):
        y=int(m[2]);y=2000+y if y<100 else y
        hits.append((m.start(),m.end(),f'{y}-Q{m[1]}',m[3].upper() if m[3] else ''))
    for m in PERIOD.finditer(text):
        if any(m.start()<end and m.end()>start for start,end,_,_ in hits):continue
        y=int(m[1]);y=2000+y if y<100 else y
        if y<2020 or y>2040:continue
        q=m[2] or m[3]
        if len(m[1])==2 and not q and not m[4]:continue
        hits.append((m.start(),m.end(),f'{y}-Q{q}' if q else str(y),m[4].upper() if m[4] else ''))
    return sorted(hits)


def numeric(token):
    t=token.strip().replace('−','-').replace(' ','').replace(',','')
    if BAD.search(t):return None
    try:return float(t.rstrip('%'))
    except ValueError:return None


def add(out, period, metric, value, unit, source, evidence, status='',segment='company',priority=0):
    if value is None or not (-1e12<value<1e12):return
    if metric.endswith('margin') or metric in ('roe','roa','revenue_yoy','revenue_qoq'):
        if not (-100<=value<=1000):return
        unit='%'
    k=(period,metric,segment)
    item={'period':period,'metric':metric,'value':value,'unit':unit,'status':status,
          'segment':segment,'evidence':evidence[:280],'source_field':source,'confidence':'high' if priority>=2 else 'medium'}
    old=out.get(k)
    if old is None or priority>old['_priority']:
        item['_priority']=priority;out[k]=item
    elif priority==old['_priority'] and (old['value']!=value or old['unit']!=unit):
        old['confidence']='conflict';old.setdefault('alternatives',[]).append({'value':value,'unit':unit,'evidence':evidence[:160]})


def parse_table(text,source,out):
    lines=[re.sub(r'[ \t]+',' ',x).strip() for x in text.splitlines()]
    for i,line in enumerate(lines):
        pp=periods(line)
        if len(pp)<2 or len(pp)>12:continue
        # Header must be mostly period labels; excludes natural prose with years.
        rest=line
        for a,b,_,_ in reversed(pp):rest=rest[:a]+' '+rest[b:]
        if len(rest.strip())>55:continue
        # Never accept an 'old estimate / new estimate / difference' table by position.
        context=' '.join(lines[max(0,i-2):i+2])
        if REVISION.search(context):continue
        cols=[(p,s) for _,_,p,s in pp]
        for row in lines[i+1:i+25]:
            if not row:continue
            if periods(row) and len(periods(row))>=2:break
            if REVISION.search(row) or re.search(r'資料來源|免責聲明|圖表\s*\d',row):break
            mt=metric_of(row)
            if not mt:continue
            # Require row to begin with a financial metric, not prose mentioning it.
            first=re.search(r'\d',row)
            if first and first.start()>65:continue
            label=re.split(r'(?<![A-Za-z])[-+−]?\d',row,1)[0]
            if len(label)>48:continue
            vals=[m.group() for m in NUM.finditer(row[len(label):])]
            if len(vals)!=len(cols):continue
            unit='%' if ('%' in label or mt.endswith('margin') or mt in ('roe','roa')) else ('元' if mt in ('eps','dividend') else (re.search(r'(?:百萬元|千元|億元|美元|US\$mn|NT\$mn)',line) or re.search(r'(?:百萬元|千元|億元|美元|US\$mn|NT\$mn)', ' '.join(lines[max(0,i-3):i+1]))).group() if (re.search(r'(?:百萬元|千元|億元|美元|US\$mn|NT\$mn)',line) or re.search(r'(?:百萬元|千元|億元|美元|US\$mn|NT\$mn)', ' '.join(lines[max(0,i-3):i+1]))) else '')
            for (period,status),v in zip(cols,vals):
                add(out,period,mt,numeric(v),unit,source,row,status,priority=3)


def parse_inline(text,source,out):
    for line in re.split(r'[\n。；;]',text):
        if len(line)>350 or len(line)<8:continue
        pp=periods(line)
        if not pp:continue
        # Focus on one explicit period, one metric, one value; do not guess ambiguous parallel arrays.
        for metric,pat in METRICS:
            for m in re.finditer(pat,line,re.I):
                nearby=[p for p in pp if abs(p[0]-m.start())<75]
                if not nearby:continue
                p=min(nearby,key=lambda z:abs(z[0]-m.start()))
                if len({z[2] for z in nearby})>1:continue
                # Find number directly after metric, but stop at the next period or a different metric.
                after=line[m.end():m.end()+38]
                after=re.sub(r'^(?:\s*(?:預估|估計|預計|約|達|為|至|NT\$|US\$|:|：|\(|\)))*','',after)
                nm=NUM.match(after)
                if not nm:continue
                # Growth/revision percentages must not become absolute EPS or revenue.
                if metric not in ('revenue_yoy','revenue_qoq') and re.search(r'上修|下修|調升|調降|成長率|增幅',line):continue
                if metric in ('eps','revenue','net_income','operating_profit') and '%' in nm.group():continue
                value=numeric(nm.group())
                unit='%' if '%' in nm.group() else ('元' if metric=='eps' else '')
                if metric.endswith('margin') and '%' not in nm.group():continue
                add(out,p[2],metric,value,unit,source,line,p[3],priority=1)


# Parallel period/value lists in broker memos (e.g. 2026/27 EPS 55/99).
PAIRED=re.compile(r'(?:20\d{2}|\d{2})\s*(?:年|E|F)?\s*[/／、和及]\s*(?:20\d{2}|\d{2})\s*(?:年|E|F)?')
VALUE_PAIR=re.compile(r'([-−]?\d+(?:\.\d+)?)\s*(?:元)?\s*[/／、]\s*([-−]?\d+(?:\.\d+)?)\s*(?:元)?')
def parse_pairs(text,source,out):
    for line in re.split(r'[\n。；;]',text):
        if len(line)>350:continue
        pm=PAIRED.search(line)
        if not pm:continue
        years=re.findall(r'20\d{2}|(?<!\d)\d{2}(?!\d)',pm.group())
        if len(years)!=2:continue
        ys=[int(x) if len(x)==4 else 2000+int(x) for x in years]
        if not all(2020<=y<=2040 for y in ys):continue
        # Avoid mapping multi-company text or multiple metrics in the same clause.
        for metric,pat in METRICS:
            matches=list(re.finditer(pat,line,re.I))
            if len(matches)!=1:continue
            m=matches[0]
            if m.start()<pm.start() or m.start()-pm.end()>70:continue
            vm=VALUE_PAIR.search(line[m.end():m.end()+75])
            if not vm:continue
            if metric in ('eps','revenue','net_income','operating_profit') and '%' in line[m.end():m.end()+75][:vm.end()]:continue
            if re.search(r'上修|下修|調升|調降|共識|consensus',line[m.end():m.end()+75],re.I):continue
            vals=[numeric(vm.group(1)),numeric(vm.group(2))]
            for year,val in zip(ys,vals):
                add(out,str(year),metric,val,'元' if metric=='eps' else '',source,line,priority=2)

def parse_period_first_eps(text,source,out):
    # "2026E EPS 55.01(+95%)、2027E 99.35(+81%)" — second period inherits EPS.
    pat=re.compile(r'(20\d{2})\s*[EF]\s*EPS\s*([-−]?\d+(?:\.\d+)?)(?:\s*\([^)]*\))?\s*[、,;/／]\s*(20\d{2})\s*[EF]\s*([-−]?\d+(?:\.\d+)?)',re.I)
    for m in pat.finditer(text):
        for year,val in [(m.group(1),m.group(2)),(m.group(3),m.group(4))]:
            add(out,year,'eps',numeric(val),'元',source,m.group(),priority=2)

def parse_repeated_year_eps(text,source,out):
    # 2026F EPS -4.04元、2027F -3.25元
    pat=re.compile(r'(20\d{2})\s*[EF]\s*(?:稅後\s*)?EPS\s*([-−]?\d+(?:\.\d+)?)\s*元?\s*[、,;/／]\s*(20\d{2})\s*[EF]\s*([-−]?\d+(?:\.\d+)?)',re.I)
    for m in pat.finditer(text):
        for year,val in ((m.group(1),m.group(2)),(m.group(3),m.group(4))):
            add(out,year,'eps',numeric(val),'元',source,m.group(),priority=2)

def extract(row):
    if row.get('source_kind')!='line' or row.get('market')=='US':return []
    if ';' in str(row.get('ticker','')) or '多檔聚合' in str(row.get('company','')):return []
    out={}
    for field in ('full_text','full_text_2','full_text_3','eps','revenue','guidance','numbers','story'):
        value=row.get(field)
        if not isinstance(value,str) or not value.strip():continue
        parse_table(value,field,out)
        parse_inline(value,field,out)
        parse_pairs(value,field,out)
        parse_period_first_eps(value,field,out)
        parse_repeated_year_eps(value,field,out)
    records=[]
    for v in out.values():
        v.pop('_priority',None)
        if v['confidence']!='conflict':records.append(v)
    return sorted(records,key=lambda x:(x['period'],x['metric']))


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--root',default=str(Path(__file__).resolve().parents[1]))
    ap.add_argument('--output',default='data/research_financial_forecasts.json')
    args=ap.parse_args();root=Path(args.root)
    folder=root/'data/research_shards'
    if not folder.is_dir():raise SystemExit('Missing data/research_shards; run LINE research sync first')
    manifest=json.loads((root/'data/research_manifest.json').read_text(encoding='utf8'))
    result={};stats={'scanned':0,'eligible':0,'with_financials':0,'facts':0,'conflicts_omitted':0}
    for sh in manifest['shards']:
        for row in json.loads((folder/sh['file']).read_text(encoding='utf8')).get('items',[]):
            stats['scanned']+=1
            if row.get('source_kind')!='line' or row.get('market')=='US':continue
            stats['eligible']+=1
            records=extract(row)
            if records:
                result[row['id']]={'company':row.get('company'),'date':row.get('date'),
                                    'broker':row.get('source'),'forecasts':records}
                stats['with_financials']+=1;stats['facts']+=len(records)
    path=root/args.output;path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps({'version':1,'stats':stats,'reports':result},ensure_ascii=False,separators=(',',':')),encoding='utf8')
    print(json.dumps(stats,ensure_ascii=False));print(path)

if __name__=='__main__':main()
