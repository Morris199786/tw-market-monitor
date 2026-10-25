#!/usr/bin/env python3
"""Manual one-month backfill. Uses OPENAI_API_KEY only when explicitly invoked.
Runs before sync_line_research.py; keeps an append-only status cache by Excel content ID.
"""
import json, os, sys, time, urllib.request, urllib.error
from datetime import date
from pathlib import Path
from zoneinfo import ZoneInfo
from datetime import datetime
from sync_line_research import (fetch_sheet, load_json, transform, is_same_broker_report,
                                BROKER_FILE, ROOT, write_json_atomic, parse_date)

CACHE=ROOT/'data/research_ai_cache.json'
START=date(2026,9,25)
END=date(2026,10,25)
MODEL=os.getenv('RESEARCH_AI_MODEL','gpt-4.1-mini')

def request_ai(row):
    raw='\n\n'.join(str(row.get(k) or '') for k in ('story','revenue','eps','inventory','utilization','guidance','trend','rating_target','numbers','full_text','full_text_2','full_text_3'))
    if len(raw.strip())<80: raise ValueError('原始內容不足，跳過 API')
    system=('你是台灣股票研究報告的整理助手。只根據提供的原文整理，繁體中文。'
            '禁止捏造數字、券商、季度、年份、評等或目標價。不同公司分段。'
            '保留全部重要研究論點；財務表格若無法可靠對齊，直接標示無法對齊，勿猜測。'
            '不要聯絡方式、免責聲明、著作權宣告。'
            '只回傳 JSON 物件：{"title":"...","summary":"...","sections":[{"heading":"...","body":"..."}],"financial_tables":[]}。')
    payload={'model':MODEL,'temperature':0,'response_format':{'type':'json_object'},'messages':[
        {'role':'system','content':system},
        {'role':'user','content':f"原始分類：{row['original_type']}；日期：{row['date']}；公司：{row.get('company','')}；券商：{row.get('source','')}\n原文：\n{raw[:60000]}"}]}
    req=urllib.request.Request('https://api.openai.com/v1/chat/completions',data=json.dumps(payload,ensure_ascii=False).encode(),headers={'Authorization':'Bearer '+os.environ['OPENAI_API_KEY'],'Content-Type':'application/json'})
    with urllib.request.urlopen(req,timeout=180) as res: reply=json.load(res)
    data=json.loads(reply['choices'][0]['message']['content'])
    if not isinstance(data,dict) or not isinstance(data.get('summary'),str) or not data['summary'].strip():
        raise ValueError('API 回傳格式不正確')
    return data

def main():
    token=os.getenv('ACCESS_TOKEN','')
    if not token: sys.exit('缺少 ACCESS_TOKEN；不執行')
    brokers=load_json(BROKER_FILE).get('items',[])
    values=fetch_sheet(token)
    today=datetime.now(ZoneInfo('Asia/Taipei')).date()
    data,_=transform(values,brokers,today)
    cache=load_json(CACHE)
    targets=[]
    for row in data['items']:
        day=parse_date(row['date'])
        if row['original_type'] not in ('個股報告','產業報告') or not day or not START<=day<=END: continue
        if any(is_same_broker_report(row,b) for b in brokers): continue
        if row['id'] in cache: continue  # success and failure never automatically retried
        targets.append(row)
    print(f'Eligible unprocessed reports: {len(targets)}')
    if os.getenv('RESEARCH_AI_DRY_RUN','1')!='0':
        print('DRY RUN: no OpenAI calls. Set RESEARCH_AI_DRY_RUN=0 manually to run.')
        return
    if not os.getenv('OPENAI_API_KEY'): sys.exit('OPENAI_API_KEY 未設定；停止')
    for i,row in enumerate(targets,1):
        try:
            result=request_ai(row)
            cache[row['id']]={'status':'success','result':result,'model':MODEL,'date':row['date']}
            status='success'
        except Exception as exc:
            cache[row['id']]={'status':'failed','reason':str(exc)[:400],'date':row['date']}
            status='failed'
        write_json_atomic(CACHE,cache)
        print(f'{i}/{len(targets)} {row["id"]} {status}',flush=True)
        time.sleep(.25)

if __name__=='__main__': main()
