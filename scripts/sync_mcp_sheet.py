"""Private MCP-only complete Sheet snapshot. No AI, public data writes or notifications."""
import hashlib
import json
import os
import re
from datetime import datetime
from zoneinfo import ZoneInfo
import requests
from update_business_reports import private_store

SHEET_ID = '1ujXlmxd7h5lap-Np6saR9i9Dp1V8Q5orgO9Ko1ccISM'
TAB = 'LINE產業研究資料庫'

def column_name(n):
    out = ''
    while n:
        n, r = divmod(n - 1, 26)
        out = chr(65+r) + out
    return out

def build(values):
    if len(values)<2 or not any(any(str(v).strip() for v in row) for row in values[1:]):
        raise ValueError('Empty source; refusing to replace snapshot')
    headers = values[0]
    items=[]
    for number, cells in enumerate(values[1:],2):
        if not any(str(v).strip() for v in cells): continue
        row=list(cells)+['']*max(0,23-len(cells))
        digest=hashlib.sha256(json.dumps(cells,ensure_ascii=False).encode()).hexdigest()
        labels=[str(headers[i]) if i<len(headers) and headers[i] else column_name(i+1) for i in range(len(cells))]
        body='\n\n'.join(f'[{column_name(i+1)}｜{labels[i]}]\n{v}' for i,v in enumerate(cells) if str(v).strip())
        day=str(row[0]).replace('/','-')
        if re.fullmatch(r'\d{4}-\d{1,2}-\d{1,2}',day):
            y,m,d=day.split('-');day=f'{int(y):04}-{int(m):02}-{int(d):02}'
        items.append(dict(id='sheet-'+digest[:24],date=day,original_type=str(row[1]),broker=str(row[2]),company=str(row[4]),ticker=str(row[5]).replace('.TW','').replace('.TWO',''),title=str(row[4] or row[3] or row[7] or row[1])[:180],full_text=body,source_fingerprint=digest,source_url=f'https://docs.google.com/spreadsheets/d/{SHEET_ID}/edit#gid=2075037698&range=A{number}',sheet_row=number,unverified='小作文' in str(row[1]),raw_cells=cells))
    return items

def main():
    token=os.environ['ACCESS_TOKEN']
    session=requests.Session(); session.headers['Authorization']='Bearer '+token
    base=f'https://sheets.googleapis.com/v4/spreadsheets/{SHEET_ID}'
    response=session.get(base,params={'fields':'sheets.properties'},timeout=60);response.raise_for_status()
    prop=next(x['properties'] for x in response.json()['sheets'] if x['properties']['title']==TAB)
    grid=prop['gridProperties']; area=f"'{TAB}'!A1:{column_name(grid['columnCount'])}{grid['rowCount']}"
    response=session.get(base+'/values/'+requests.utils.quote(area,safe=''),params={'valueRenderOption':'FORMATTED_VALUE'},timeout=120);response.raise_for_status()
    items=build(response.json().get('values',[]))
    manifests=[];chunk=[];size=0
    def flush():
        nonlocal chunk,size
        if not chunk:return
        text=json.dumps({'items':chunk},ensure_ascii=False)
        name=hashlib.sha256(text.encode()).hexdigest()+'.json'
        private_store('sheet-shards/'+name,text)
        manifests.extend([{**{k:v for k,v in r.items() if k not in ('full_text','raw_cells')},'file':'sheet-shards/'+name} for r in chunk])
        chunk=[];size=0
    for row in items:
        length=len(json.dumps(row,ensure_ascii=False))
        if length>1_900_000:raise ValueError('A source row exceeds private store limit; old snapshot retained')
        if size+length>700_000:flush()
        chunk.append(row);size+=length
    flush()
    index={'schema_version':1,'updated_at':datetime.now(ZoneInfo('Asia/Taipei')).isoformat(),'items':manifests}
    private_store('sheet-index.json',json.dumps(index,ensure_ascii=False))
    print(f'Private MCP Sheet snapshot published: {len(items)} rows; all B-column types, no AI or notifications')

if __name__=='__main__':main()
