#!/usr/bin/env python3
"""Manual one-month backfill. Uses OPENAI_API_KEY only when explicitly invoked.
Runs before sync_line_research.py; keeps an append-only status cache by Excel content ID.
"""
import json, os, sys, time, urllib.request, urllib.error
from datetime import datetime
import re
from pathlib import Path
from zoneinfo import ZoneInfo
from datetime import date
import subprocess
import hashlib
from collections import Counter
from sync_line_research import (fetch_sheet, load_json, transform, is_same_broker_report,
                                BROKER_FILE, ROOT, write_json_atomic, parse_date)

CACHE=ROOT/'data/research_ai_cache.json'
START=date(2026,9,25)
END=date(2026,10,25)
MODEL=os.getenv('RESEARCH_AI_MODEL','gpt-4.1-mini')

def context_for(row, history):
    """Only dated, earlier records; distinguish same-broker revisions from other views."""
    day=parse_date(row['date'])
    code=re.search(r'(?<!\d)\d{4}(?!\d)',str(row.get('ticker') or ''))
    code=code.group() if code else ''
    company=str(row.get('company') or '').strip()
    same=[]; related=[]
    for old in history:
        if old['id']==row['id']: continue
        old_day=parse_date(old['date'])
        if not old_day or not day or old_day>=day: continue
        old_code=re.search(r'(?<!\d)\d{4}(?!\d)',str(old.get('ticker') or ''))
        old_code=old_code.group() if old_code else ''
        if not ((code and old_code==code) or (company and company==str(old.get('company') or '').strip())): continue
        brief={'date':old['date'],'source':old.get('source',''), 'company':old.get('company',''),
               'ticker':old.get('ticker',''), 'story':str(old.get('story') or '')[:1000],
               'eps':str(old.get('eps') or '')[:700], 'guidance':str(old.get('guidance') or '')[:700],
               'rating_target':str(old.get('rating_target') or '')[:500]}
        (same if str(old.get('source') or '').strip()==str(row.get('source') or '').strip() else related).append(brief)
    same.sort(key=lambda x:x['date'],reverse=True)
    related.sort(key=lambda x:x['date'],reverse=True)
    return {'same_broker_previous':same[:3], 'other_broker_history':related[:3]}

def request_ai(row, context):
    raw='\n\n'.join(str(row.get(k) or '') for k in ('story','revenue','eps','inventory','utilization','guidance','trend','rating_target','numbers','full_text','full_text_2','full_text_3'))
    if len(raw.strip())<80: raise ValueError('原始內容不足，跳過 API')
    system=("你是台股研究分析員。只根據提供的原文與歷史報告作證據導向整理，繁體中文。"
            "優先說明時間序列的變動、幅度、原因、是否有直接證據。"
            "只有同一券商、同一公司、同一預估期間且指標口徑相同，才可以稱上修或下修；"
            "不同券商只能說預估分歧，不得當作時間序列修正。"
            "產業上下游、客戶與競爭對手交互驗證，只能根據明確提供的資料，"
            "若無資料請填證據不足，不能杜撰供應鏈關係或客戶。"
            "數字要保留單位、期間、實際/預估與出處。原文沒有的理由不能推定為事實。"
            "不輸出聯絡方式、免責聲明。只輸出 JSON 物件，包含 title,summary,sections,financial_tables,"
            "changes (陣列，每項含 metric,period,previous,current,change,reason,evidence,source_dates),"
            "cross_validation (陣列，每項含 topic,status,evidence,contradictions,missing_evidence),"
            "uncertainties (陣列)。沒有證據的欄位用空陣列。")
    payload={'model':MODEL,'temperature':0,'response_format':{'type':'json_object'},'messages':[
        {'role':'system','content':system},
        {'role':'user','content':json.dumps({'report':{'original_type':row['original_type'],'date':row['date'],
            'company':row.get('company',''),'ticker':row.get('ticker',''),'broker':row.get('source',''),
            'raw':raw[:50000]},'historical_context':context},ensure_ascii=False)}]}
    req=urllib.request.Request('https://api.openai.com/v1/chat/completions',data=json.dumps(payload,ensure_ascii=False).encode(),headers={'Authorization':'Bearer '+os.environ['OPENAI_API_KEY'],'Content-Type':'application/json'})
    with urllib.request.urlopen(req,timeout=180) as res: reply=json.load(res)
    data=json.loads(reply['choices'][0]['message']['content'])
    if not isinstance(data,dict) or not isinstance(data.get('summary'),str) or not data['summary'].strip():
        raise ValueError('API 回傳格式不正確')
    return data

def stable_key(row):
    """Stable across edits to narrative; independent of Excel row order."""
    fields = ('date', 'original_type', 'source', 'company', 'ticker', 'period')
    return '|'.join(re.sub(r'\s+', '', str(row.get(k) or '')).casefold() for k in fields)


def checkpoint(cache):
    """Commit AND push the durable record before any API request."""
    write_json_atomic(CACHE, cache)
    if os.getenv('RESEARCH_AI_DRY_RUN', '1') != '0':
        return
    def git(*args):
        subprocess.run(['git', *args], cwd=ROOT, check=True, capture_output=True, text=True)
    git('add', '--', 'data/research_ai_cache.json')
    diff = subprocess.run(['git', 'diff', '--cached', '--quiet'], cwd=ROOT)
    if diff.returncode == 0:
        return
    if diff.returncode != 1:
        raise RuntimeError('git diff failed; API call blocked')
    git('commit', '-m', 'Checkpoint research AI report status')
    git('push', 'origin', 'HEAD:main')


def main():
    token=os.getenv('ACCESS_TOKEN','')
    if not token: sys.exit('缺少 ACCESS_TOKEN；不執行')
    brokers=load_json(BROKER_FILE).get('items',[])
    values=fetch_sheet(token)
    today=datetime.now(ZoneInfo('Asia/Taipei')).date()
    data,_=transform(values,brokers,today)
    cache=load_json(CACHE)
    if not isinstance(cache,dict): sys.exit('AI cache 格式錯誤')
    history=data['items']
    counts=Counter(stable_key(row) for row in history)
    # Existing content-hash IDs remain valid; add a stable-key index for future edits.
    index={}
    for cid, entry in cache.items():
        if not isinstance(entry,dict): continue
        key=entry.get('stable_key')
        if key: index.setdefault(key,[]).append(cid)
    targets=[]
    for row in history:
        day=parse_date(row['date'])
        if row['original_type'] not in ('個股報告','產業報告') or not day or not START<=day<=END: continue
        key=stable_key(row)
        if row['id'] in cache: continue
        # Do not auto-process ambiguous records with the same identifying fields.
        if counts[key]>1 or len(index.get(key,[]))>1:
            print(f'AMBIGUOUS: {row["id"]}; manual review, no API')
            continue
        if key in index:
            # Old content changed: alias to prior processing record, no new API.
            cache[row['id']]=dict(cache[index[key][0]],stable_key=key)
            continue
        matches=[b for b in brokers if is_same_broker_report(row,b)]
        if matches:
            cache[row['id']]={'status':'broker_duplicate','stable_key':key,
                              'broker_report_id':str(matches[0].get('id') or ''), 'date':row['date']}
            index[key]=[row['id']]
            continue
        targets.append((row,key))
    print(f'Eligible unprocessed reports: {len(targets)}')
    if os.getenv('RESEARCH_AI_DRY_RUN','1')!='0':
        print('DRY RUN: no OpenAI calls, no files written')
        return
    if not os.getenv('OPENAI_API_KEY'): sys.exit('OPENAI_API_KEY 未設定；停止')
    # Publish aliases and broker duplicate statuses first.
    checkpoint(cache)
    for i,(row,key) in enumerate(targets,1):
        # Reserve and PUSH before contacting the API. Unknown attempts are never retried.
        cache[row['id']]={'status':'api_reserved','stable_key':key,'date':row['date'],
                          'reserved_at':datetime.now(ZoneInfo('Asia/Taipei')).isoformat()}
        checkpoint(cache)
        try:
            result=request_ai(row,context_for(row,history))
            cache[row['id']]={'status':'success','stable_key':key,'result':result,
                              'model':MODEL,'date':row['date']}
            status='success'
        except Exception as exc:
            cache[row['id']]={'status':'unknown','stable_key':key,
                              'reason':str(exc)[:400],'date':row['date']}
            status='unknown'
        checkpoint(cache)
        print(f'{i}/{len(targets)} {row["id"]} {status}',flush=True)
        time.sleep(.25)

if __name__=='__main__': main()
