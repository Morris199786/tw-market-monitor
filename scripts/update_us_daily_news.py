import concurrent.futures as cf
import datetime as dt
import email.utils, hashlib, json, os, pathlib, re, sys, urllib.parse, urllib.request, xml.etree.ElementTree as ET
from zoneinfo import ZoneInfo
from report_provider import plan_request
ROOT=pathlib.Path(__file__).resolve().parents[1]; DATA=ROOT/'data/us_daily_news.json'; TW=ZoneInfo('Asia/Taipei')
def get(url):
    with urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0'}),timeout=25) as r: return r.read()
def feed(task):
    ticker,url=task
    try:
        items=[]
        for x in ET.fromstring(get(url)).findall('.//item'):
            try:
                date=email.utils.parsedate_to_datetime(x.findtext('pubDate')).astimezone(dt.timezone.utc)
                title=x.findtext('title') or ''; link=x.findtext('link') or ''
                if not title or not link.startswith('https://'): continue
                items.append(dict(id=hashlib.sha256(link.encode()).hexdigest()[:20],ticker=ticker,title=title,url=link,date=date.isoformat(),excerpt=re.sub('<[^>]+>',' ',x.findtext('description') or '')[:1600]))
            except (ValueError,TypeError,AttributeError): continue
        return items,True
    except Exception as e:
        print('Feed failed',ticker,type(e).__name__,file=sys.stderr); return [],False

def main():
    now=dt.datetime.now(TW); mode=os.getenv('NEWS_SESSION','auto'); mode=('post' if now.hour<15 else 'pre') if mode=='auto' else mode
    if mode not in ('pre','post'): raise ValueError('invalid session')
    state=json.loads(DATA.read_text()) if DATA.exists() else {'reports':[],'seen':[]}
    slot=f'{now.date()}-{mode}'
    if any(r['id']==slot for r in state['reports']): print('Already published'); return
    config=json.loads(get('https://raw.githubusercontent.com/Morris199786/us-stock-watch/main/config.json'))['groups']
    tickers={a[0]:a[2] for rows in config.values() for a in rows}; tasks=[(t,'https://feeds.finance.yahoo.com/rss/2.0/headline?s='+urllib.parse.quote(s)+'&region=US&lang=en-US') for t,s in tickers.items()]
    tasks += [(g,'https://news.google.com/rss/search?q='+urllib.parse.quote(g.split('／')[0]+' semiconductor OR AI when:2d')+'&hl=en-US&gl=US&ceid=US:en') for g in config]
    with cf.ThreadPoolExecutor(max_workers=10) as pool: results=list(pool.map(feed,tasks))
    if sum(ok for _,ok in results)<len(tasks)*.85: raise RuntimeError('Insufficient feed coverage; no publication')
    cutoff=dt.datetime.fromisoformat(state['last_success'])-dt.timedelta(hours=12) if state.get('last_success') else now-dt.timedelta(hours=48)
    seen=set(state['seen']); unique={}; titles=set()
    for items,_ in results:
        for x in items:
            title=re.sub(r'\W+','',x['title'].lower())
            if x['id'] in seen or title in titles or dt.datetime.fromisoformat(x['date'])<cutoff: continue
            unique[x['id']]=x; titles.add(title)
    candidates=sorted(unique.values(),key=lambda x:x['date'],reverse=True)
    # Process bounded batches, never silently mark unprocessed articles seen.
    events=[]; processed=[]
    prompt=(ROOT/'scripts/us_daily_news_prompt.md').read_text()
    for start in range(0,len(candidates),60):
        batch=candidates[start:start+60]; lookup={x['id']:x for x in batch}
        payload={'reasoning':{'effort':'medium'},'input':[{'role':'user','content':[{'type':'input_text','text':prompt+'\n追蹤清單:'+json.dumps(config,ensure_ascii=False)+'\n資料:'+json.dumps(batch,ensure_ascii=False)}]}]}
        result=plan_request(payload)
        if result.get('status')!='ok': raise RuntimeError('Codex unavailable; no API fallback; no publication')
        raw=result['text'].strip(); raw=re.sub(r'^```(?:json)?\s*|\s*```$','',raw); out=json.loads(raw)
        if not isinstance(out,list): raise ValueError('Expected array')
        for e in out:
            ids=e.get('source_ids',[])
            if not ids or any(i not in lookup for i in ids) or not e.get('title') or not e.get('analysis') or not e.get('tickers') or any(t not in tickers for t in e['tickers']): raise ValueError('Invalid event')
            e['sources']=[lookup[i] for i in ids]; events.append(e)
        processed.extend(lookup)
    # Merge identical event titles within this run.
    merged={}
    for e in events:
        k=re.sub(r'\W+','',e['title'].lower())
        if k in merged: merged[k]['sources']+=e['sources']
        else: merged[k]=e
    report={'id':slot,'date':str(now.date()),'session':mode,'updated_at':now.isoformat(),'events':list(merged.values()),'coverage':{'successful':sum(ok for _,ok in results),'total':len(tasks)},'candidate_count':len(candidates)}
    state['reports'].insert(0,report); state['seen']=sorted(seen|set(processed)); state['last_success']=now.isoformat(); tmp=DATA.with_suffix('.tmp'); tmp.write_text(json.dumps(state,ensure_ascii=False,indent=2)); tmp.replace(DATA)
    pathlib.Path('/tmp/us-news-published.json').write_text(json.dumps(report,ensure_ascii=False))
if __name__=='__main__': main()
