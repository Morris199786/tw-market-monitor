#!/usr/bin/env python3
"""Incremental Excel research analysis. Durable claim before ONE broker API call.
No automatic retry, notification, or modification of original broker reports.
"""
import calendar
from collections import Counter
from datetime import date, datetime
import json
import os
from pathlib import Path
import subprocess
import sys
from zoneinfo import ZoneInfo

from sync_line_research import fetch_sheet, load_json, transform, ROOT, BROKER_FILE, write_json_atomic, load_all_brokers
from research_dedup import Matcher, content_key, stable_key, source_ids, excel_document_key

CACHE=ROOT/'data/research_ai_cache.json'
PLAN=ROOT/'data/research_ai_plan.json'

def window(today):
    year,month=today.year,today.month-1
    if month==0: year,month=year-1,12
    return date(year,month,min(today.day,calendar.monthrange(year,month)[1])),today

def validate_cache(cache):
    if not isinstance(cache,dict): raise ValueError('AI cache must be an object; API blocked')
    for key,entry in cache.items():
        if not isinstance(entry,dict) or not entry.get('status'):
            raise ValueError('Malformed AI ledger entry; API blocked')
    return cache

def previous(row,cache):
    if row['id'] in cache: return row['id']
    key,body,ids=stable_key(row),content_key(row),source_ids(row)
    doc=excel_document_key(row)
    hits=[]
    for cid,e in cache.items():
        if e.get('stable_key')==key or (body and e.get('content_key')==body) or (doc and e.get('document_key')==doc) or (
                len(ids)==1 and ids & set(e.get('source_ids',[]))): hits.append(cid)
    # Any prior attempt blocks charging, even when aliases are ambiguous.
    return sorted(hits)[0] if hits else None

# TW_ONLY_AI_GUARD_V1
# Fail closed for unknown stock markets: never spend API on a possible US report.
import re

def tw_only_reason(row):
    ticker=str(row.get('ticker') or '').strip().upper()
    market=str(row.get('market') or '').strip().upper()
    company=str(row.get('company') or '').strip()
    if market == 'US': return 'us_market'
    if re.search(r'\.(?:US|NYSE|NASDAQ)$', ticker): return 'us_exchange_suffix'
    if re.fullmatch(r'[A-Z]{1,5}', ticker): return 'us_equity_ticker'
    if ticker and not re.fullmatch(r'(?:[0-9]{4,6})(?:\.(?:TW|TWO))?', ticker):
        return 'unverified_foreign_ticker'
    # A company without a Taiwan ticker cannot be verified as a Taiwan stock.
    # Industry reports with no single-stock ticker are permitted only when the
    # subject is explicitly Taiwan-related and contains no US stock symbols.
    if not ticker:
        if row.get('original_type') == '個股報告': return 'missing_tw_ticker'
        if row.get('original_type') == '產業報告':
            if re.search(r'(?i)\b(?:NASDAQ|NYSE|US STOCK|U\.S\. EQUITY)\b',
                         ' '.join(str(row.get(k) or '')[:400] for k in ('company','industry','story'))):
                return 'us_industry_report'
            # No stock ticker: only allow reports with an explicit Taiwan indicator.
            context=' '.join(str(row.get(k) or '')[:400] for k in ('company','industry','story'))
            if not re.search(r'台灣|台股|臺灣|台廠|TWSE|TPEX|上市|上櫃|TPCA',context,re.I):
                return 'unverified_industry_market'
    return ''

def make_plan(rows,brokers,inbox,cache,today):
    start,end=window(today)
    matcher=Matcher(brokers,inbox)
    counts=Counter(stable_key(r) for r in rows)
    seen={}; seen_documents={}; result=[]
    for row in rows:
        day=date.fromisoformat(row['date'])
        if row.get('original_type') not in ('個股報告','產業報告') or not start<=day<=end: continue
        us_reason=tw_only_reason(row)
        if us_reason:
            result.append({'id':row['id'],'date':row['date'],'company':row.get('company',''),
                           'source':row.get('source',''),'status':'excluded_us',
                           'reason':us_reason})
            continue
        decision=matcher.decide(row)
        entry={'id':row['id'],'date':row['date'],'company':row.get('company',''),
               'source':row.get('source',''),**decision}
        if decision['status']=='new':
            old=previous(row,cache)
            body=content_key(row)
            if old: entry.update(status='cached',cache_id=old,previous_status=cache[old]['status'])
            elif body and body in seen: entry.update(status='excel_duplicate',cache_id=seen[body])
            elif (doc := excel_document_key(row)) and doc in seen_documents: entry.update(status='excel_duplicate',cache_id=seen_documents[doc])
            elif counts[stable_key(row)]>1:
                entry.update(status='needs_review',reason='ambiguous_excel_identity')
            elif not body: entry.update(status='needs_review',reason='insufficient_source_text')
            else:
                seen[body]=row['id']
                if (doc := excel_document_key(row)): seen_documents[doc]=row['id']
        result.append(entry)
    return {'start':start.isoformat(),'end':end.isoformat(),'items':result,
            'counts':dict(Counter(x['status'] for x in result))}

def checkpoint(cache):
    """If push fails, stop. A reserved remote entry survives a killed runner."""
    write_json_atomic(CACHE,cache)
    def git(*args,check=True):
        return subprocess.run(['git',*args],cwd=ROOT,check=check,capture_output=True,text=True)
    git('add','--','data/research_ai_cache.json')
    diff=git('diff','--cached','--quiet',check=False)
    if diff.returncode==0: return
    if diff.returncode!=1: raise RuntimeError('Cannot inspect checkpoint; API blocked')
    git('commit','-m','Checkpoint Excel research AI ledger')
    for attempt in range(3):
        if git('push','origin','HEAD:main',check=False).returncode==0: return
        # Unrelated market data writers may have pushed. Ledger conflicts fail
        # closed; never resolve them by overwriting the remote claim.
        if git('pull','--rebase','origin','main',check=False).returncode:
            git('rebase','--abort',check=False)
            raise RuntimeError('Checkpoint conflict; API blocked, inspect ledger')
    raise RuntimeError('Checkpoint push failed; API blocked')

def source_for(row):
    fields=('story','revenue','eps','inventory','utilization','guidance','trend','rating_target',
            'numbers','full_text','full_text_2','full_text_3')
    raw='\n\n'.join(f'{k}:\n{row[k]}' for k in fields if row.get(k))
    if len(raw.strip())<80: raise ValueError('Insufficient source text')
    return {'drive_file_id':row['id'],'name':f"{row.get('company','')} {row.get('source','')} {row['date']}",
            'drive_url':'','report_date':row['date'],
            'text':f"資料類型：{row['original_type']}\n報告日期：{row['date']}\n券商：{row.get('source','')}\n"+raw}

def request_ai(src):
    # Same model, prompt, identity audit and one-shot quarterly EPS as broker reports.
    import update_reports_ai as base
    import update_reports_ai_eps as eps
    base.COMPANIES=base.registry(refresh=False)
    old_post,old_normalize=base.requests.post,base.normalize_report
    try:
        base.requests.post=eps._post
        base.normalize_report=eps._normalize
        result=base.analyze_report(src)
    finally:
        base.requests.post,base.normalize_report=old_post,old_normalize
    if not result.get('title') or not result.get('summary') or not result.get('detail'):
        raise ValueError('Incomplete analysis; saved as unknown, no auto-retry')
    return result

def execute(rows,plan,cache,max_reports,save=checkpoint,analyze=request_ai):
    lookup={r['id']:r for r in rows}; used=0; consecutive_errors=0
    for item in plan['items']:
        row=lookup[item['id']]; rid=row['id']; status=item['status']
        if tw_only_reason(row):
            print(f'[TW_ONLY][SKIP] {rid} {row.get("company","")} reason={tw_only_reason(row)}',flush=True)
            continue
        if status in ('broker_duplicate','cached','excel_duplicate'):
            if rid not in cache:
                if status=='broker_duplicate': cache[rid]=dict(item)
                elif item['cache_id'] in cache: cache[rid]={'status':'alias','cache_id':item['cache_id']}
                else: continue
                cache[rid].update(stable_key=stable_key(row),content_key=content_key(row),source_ids=sorted(source_ids(row)))
                save(cache)
            continue
        if status!='new' or used>=max_reports or previous(row,cache): continue
        try: src=source_for(row)
        except ValueError:
            item.update(status='needs_review',reason='insufficient_source_text'); continue
        # All deterministic validation is before the durable reservation.
        from update_reports_ai import prepare_report_text
        try: prepare_report_text(src)
        except ValueError:
            item.update(status='needs_review',reason='source_too_large'); continue
        record={'status':'api_reserved','stable_key':stable_key(row),'content_key':content_key(row),
                'source_ids':sorted(source_ids(row)),'document_key':excel_document_key(row),'date':row['date'],
                'reserved_at':datetime.now(ZoneInfo('Asia/Taipei')).isoformat()}
        cache[rid]=record
        save(cache)  # Must succeed remotely BEFORE external request.
        used+=1
        try:
            result=analyze(src)
            cache[rid]={**record,'status':'success','result':result,'schema':'broker-v1',
                        'model':result.get('ai_model'),'finished_at':datetime.now(ZoneInfo('Asia/Taipei')).isoformat()}
        except Exception as exc:
            # Do not persist raw API exceptions (may contain request content).
            cache[rid]={**record,'status':'unknown','error_type':type(exc).__name__}
        save(cache)
        print(f"{used}/{max_reports} {rid} {cache[rid]['status']}",flush=True)
        if cache[rid]['status']=='unknown':
            consecutive_errors+=1
            # A validation error is quarantined, NEVER retried. Other errors
            # and two consecutive failures trigger a fail-closed circuit breaker.
            if cache[rid]['error_type']!='ValueError' or consecutive_errors>=2:
                print('Stopped: uncertain or repeated errors; no automatic retry',flush=True)
                break
            print('Quarantined validation error; continuing with next NEW report',flush=True)
        else:
            consecutive_errors=0
    return used

def main():
    today=date.fromisoformat(os.environ['RESEARCH_AI_TODAY']) if os.getenv('RESEARCH_AI_TODAY') else datetime.now(ZoneInfo('Asia/Taipei')).date()
    fixture=os.getenv('LINE_SYNC_FIXTURE')
    if fixture: values=json.loads(Path(fixture).read_text(encoding='utf-8'))
    else:
        token=os.getenv('ACCESS_TOKEN','')
        if not token: sys.exit('Missing ACCESS_TOKEN; no API calls')
        values=fetch_sheet(token)
    brokers=load_all_brokers()
    inbox=load_json(ROOT/'data/report_inbox.json').get('items',[])
    rows=transform(values,brokers,today)[0]['items']
    cache=validate_cache(load_json(CACHE))
    plan=make_plan(rows,brokers,inbox,cache,today)
    # Plan is saved for review even in check mode, but never changes ledger.
    print(json.dumps({k:v for k,v in plan.items() if k!='items'},ensure_ascii=False))
    if os.getenv('RESEARCH_AI_DRY_RUN','1')!='0':
        write_json_atomic(PLAN,plan)
        print('CHECK ONLY: zero API calls; ledger unchanged'); return
    if not os.getenv('OPENAI_API_KEY'): sys.exit('Missing OPENAI_API_KEY; stopped')
    cap=int(os.getenv('RESEARCH_AI_MAX_REPORTS','10'))
    if not 1<=cap<=200: sys.exit('Batch cap must be 1..200')
    execute(rows,plan,cache,cap)
    write_json_atomic(PLAN,make_plan(rows,brokers,inbox,cache,today))

if __name__=='__main__': main()
