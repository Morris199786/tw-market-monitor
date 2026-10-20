#!/usr/bin/env python3
"""00981A daily snapshot; source MoneyDJ publicly displayed holdings, not trading tape.
Fail closed if holdings table/date cannot be verified. No synthetic records.
"""
import datetime as dt
import json
import re
import sys
from pathlib import Path
from urllib.request import Request, urlopen
from html.parser import HTMLParser

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'data' / 'etf_00981a.json'
URL = 'https://www.moneydj.com/etf/x/basic/basic0007.xdjhtm?etfid=00981a.tw&topc='

class Tables(HTMLParser):
    def __init__(self):
        super().__init__(); self.tables=[]; self.current=None; self.row=None; self.cell=None
    def handle_starttag(self,tag,attrs):
        if tag=='table': self.current=[]
        if self.current is not None and tag=='tr': self.row=[]
        if self.row is not None and tag in ('td','th'): self.cell=[]
    def handle_data(self,data):
        if self.cell is not None: self.cell.append(data)
    def handle_endtag(self,tag):
        if tag in ('td','th') and self.cell is not None:
            self.row.append(' '.join(''.join(self.cell).split())); self.cell=None
        if tag=='tr' and self.row is not None:
            if self.row: self.current.append(self.row)
            self.row=None
        if tag=='table' and self.current is not None:
            self.tables.append(self.current); self.current=None

def main():
    req=Request(URL,headers={'User-Agent':'Mozilla/5.0 (compatible; ETFHoldingsMonitor/1.0)','Accept-Language':'zh-TW,zh;q=0.9'})
    with urlopen(req,timeout=30) as resp: raw=resp.read().decode('utf-8','replace')
    # Extract date specifically near the holding-detail heading, not industry allocation date.
    plain=re.sub(r'<[^>]+>',' ',raw)
    plain=re.sub(r'\s+',' ',plain)
    marker=plain.find('持股明細')
    if marker<0: raise RuntimeError('Missing holdings heading')
    m=re.search(r'資料日期\s*[：:]\s*(20\d{2})[/-](\d{1,2})[/-](\d{1,2})',plain[marker:marker+1200])
    if not m: raise RuntimeError('Missing dated holdings snapshot; refusing to update')
    date=f'{int(m[1]):04d}-{int(m[2]):02d}-{int(m[3]):02d}'
    p=Tables();p.feed(raw)
    holdings={}
    for table in p.tables:
        head=' '.join(' '.join(r) for r in table[:3])
        if not ('持有股數' in head and ('投資比例' in head or '比例' in head)): continue
        for row in table:
            joined=' '.join(row)
            match=re.search(r'([^\s()]+)\s*\((\d{4,6})\.(?:TW|TWO)\)',joined,re.I)
            if not match: continue
            code=match.group(2); name=match.group(1)
            nums=[]
            for v in row:
                x=v.replace(',','').replace('%','').strip()
                if re.fullmatch(r'-?\d+(?:\.\d+)?',x): nums.append(float(x))
            if len(nums)<2: continue
            # Column order: weight %, shares
            weight,shares=nums[-2:]
            if not 0<=weight<=100 or shares<0: continue
            holdings[code]={'name':name,'shares':int(round(shares)),'weight':weight}
    if len(holdings)<20: raise RuntimeError(f'Parsed only {len(holdings)} holdings; refusing to overwrite')
    data={'etf':'00981A','source':URL,'snapshots':{},'updated_at':''}
    if OUT.exists():
        old=json.loads(OUT.read_text(encoding='utf-8'))
        if old.get('etf')=='00981A': data['snapshots']=old.get('snapshots',{})
    if date in data['snapshots'] and data['snapshots'][date]==holdings:
        print(f'Unchanged: {date}, {len(holdings)} stocks');return
    data['snapshots'][date]=holdings
    data['snapshots']=dict(sorted(data['snapshots'].items()))
    data['updated_at']=dt.datetime.now(dt.timezone.utc).isoformat()
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(data,ensure_ascii=False,separators=(',',':')),encoding='utf-8')
    print(f'Updated {date}: {len(holdings)} stocks; snapshots={len(data["snapshots"])}')

if __name__=='__main__':
    try:main()
    except Exception as exc:
        print(f'ETF 00981A update failed: {exc}',file=sys.stderr);sys.exit(1)
