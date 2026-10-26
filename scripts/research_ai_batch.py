#!/usr/bin/env python3
"""Manual, bounded research AI batch. Never retries an attempted source implicitly."""
import argparse, datetime, hashlib, json, os, pathlib, re, sys, urllib.request
ROOT=pathlib.Path(__file__).resolve().parents[1]
CACHE=ROOT/'data/research_ai_cache.json'
AUDIT=ROOT/'data/research_ai_batch_history.json'

def load(path,default):
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else default

def write(path,data):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

def content(row):
    return '\n\n'.join(str(row.get(k) or '') for k in ('full_text','full_text_2','full_text_3') if row.get(k))

def route(row):
    return row.get('api_route') or ('required' if row.get('category')=='早報' else 'none')

def parse(text,model):
    prompt=('你是台灣券商研究文件結構化解析器。只能引用原文，不可推測數字。'
            '請輸出 JSON 物件，欄位 title、summary(字串陣列)、companies(陣列)。'
            'companies 每項有 name,ticker,key_points(陣列),financials(陣列)。'
            'financials 每項含 metric,period,value,unit,actual_or_estimate,evidence。'
            '同篇多家公司嚴格分開；找不到公司歸屬或期間的數字不要填。'
            '沒有財務數字就回空陣列。摘要以繁體中文撰寫。')
    payload={'model':model,'temperature':0,'response_format':{'type':'json_object'},'messages':[{'role':'system','content':prompt},{'role':'user','content':text[:110000]}]}
    req=urllib.request.Request('https://api.openai.com/v1/chat/completions',data=json.dumps(payload).encode(),headers={'Authorization':'Bearer '+os.environ['OPENAI_API_KEY'],'Content-Type':'application/json'})
    with urllib.request.urlopen(req,timeout=180) as response: data=json.load(response)
    result=json.loads(data['choices'][0]['message']['content'])
    return result,data.get('usage',{})

def audit(result,original):
    issues=[]; count=0
    if not isinstance(result.get('companies'),list): issues.append('companies 格式不正確')
    for c in result.get('companies',[]):
        if not isinstance(c,dict): issues.append('公司格式不正確');continue
        for f in c.get('financials',[]):
            count+=1
            if not isinstance(f,dict):issues.append('財務資料格式不正確');continue
            ev=str(f.get('evidence') or '').strip()
            val=str(f.get('value') or '').strip()
            if not ev or ev not in original:issues.append(f"{c.get('name','?')} {f.get('metric','?')}: 原文證據未精確匹配")
            if not val or (val not in ev and val.replace(',','') not in ev.replace(',','')):issues.append(f"{c.get('name','?')} {f.get('metric','?')}: 數字與證據不一致")
            if not f.get('period'):issues.append(f"{c.get('name','?')} {f.get('metric','?')}: 缺期間")
            if f.get('actual_or_estimate') not in ('actual','estimate','unknown'):issues.append('預估／實際標記無效')
    return {'status':'needs_review' if issues else 'passed','financial_count':count,'issues':issues[:50]}

def main():
    p=argparse.ArgumentParser();p.add_argument('--limit',type=int,default=10);p.add_argument('--category',choices=['all','morning','meeting','industry'],default='all');p.add_argument('--mode',choices=['pending','failed'],default='pending');p.add_argument('--model',default=os.getenv('RESEARCH_AI_MODEL','gpt-4o-mini'));a=p.parse_args()
    if not 1<=a.limit<=100:sys.exit('limit must be 1..100')
    cache=load(CACHE,{}); history=load(AUDIT,[])
    manifest=load(ROOT/'data/research_manifest.json',{})
    if not manifest.get('shards'):sys.exit('research_manifest.json missing or empty; sync first')
    entries=[]; seen=set()
    for shard in manifest['shards']:
        file=ROOT/'data/research_shards'/shard['file']
        for row in load(file,{}).get('items',[]):
            if row.get('source_kind')!='line' or route(row)!='required':continue
            cat=row.get('category')
            if a.category=='morning' and cat!='早報':continue
            if a.category=='meeting' and cat!='法說／訪談':continue
            if a.category=='industry' and cat!='產業研究':continue
            raw=content(row)
            if not raw.strip():continue
            fingerprint=hashlib.sha256(raw.encode()).hexdigest()
            if fingerprint in seen:continue
            seen.add(fingerprint)
            old=cache.get(row['id'])
            if a.mode=='pending' and old is not None:continue
            if a.mode=='failed' and (not old or old.get('status') not in ('failed','needs_review')):continue
            entries.append((row,raw,fingerprint))
    entries.sort(key=lambda x:(x[0].get('date',''),x[0].get('id','')),reverse=True)
    selected=entries[:a.limit]
    print(f'BATCH selected={len(selected)} eligible={len(entries)} category={a.category} mode={a.mode}')
    if selected and not os.getenv('OPENAI_API_KEY'):sys.exit('OPENAI_API_KEY missing; no calls made')
    run={'at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'category':a.category,'mode':a.mode,'limit':a.limit,'model':a.model,'results':[]}
    for row,raw,fp in selected:
        rid=row['id']
        # Record attempted before request: even API errors must not auto-repeat.
        cache[rid]={'status':'attempted','fingerprint':fp,'category':row.get('category'),'model':a.model,'at':run['at']}
        write(CACHE,cache)
        try:
            result,usage=parse(raw,a.model)
            check=audit(result,raw)
            status='success' if check['status']=='passed' else 'needs_review'
            cache[rid].update({'status':status,'schema':'research-batch-v1','result':result,'audit':check,'usage':usage})
            run['results'].append({'id':rid,'status':status,'audit':check,'usage':usage})
        except Exception as exc:
            cache[rid].update({'status':'failed','error':str(exc)[:300]})
            run['results'].append({'id':rid,'status':'failed','error':str(exc)[:300]})
        write(CACHE,cache)
        print(f"{rid}: {cache[rid]['status']}")
    history.append(run);write(AUDIT,history)
    print(json.dumps({'processed':len(selected),'status_counts':{s:sum(r['status']==s for r in run['results']) for s in ('success','needs_review','failed')}},ensure_ascii=False))
if __name__=='__main__':main()
