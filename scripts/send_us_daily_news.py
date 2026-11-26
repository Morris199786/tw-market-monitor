import json, os, pathlib, subprocess, urllib.request, sys

def read(ref):
    if not ref or set(ref)=={'0'}: return {'reports':[]}
    return json.loads(subprocess.check_output(['git','show',ref+':data/us_daily_news.json'],text=True))

def key(r): return (r['date'],r['session'])
def validate(d):
    assert isinstance(d['reports'],list)
    keys=set()
    for r in d['reports']:
        assert r['session'] in ('pre','post') and len(r['date'])==10 and isinstance(r['events'],list)
        assert key(r) not in keys; keys.add(key(r))
        for e in r['events']:
            assert isinstance(e['tickers'],list) and e['title'] and e['analysis']
            assert e['sources'] and all(s['url'].startswith('https://') for s in e['sources'])
    return d

def main():
    current=validate(json.loads(pathlib.Path('data/us_daily_news.json').read_text()))
    before=read(os.environ.get('NEWS_BEFORE',''))
    old={key(r) for r in before['reports']}
    new=[r for r in current['reports'] if key(r) not in old]
    if not new: print('No new report'); return
    if len(new)!=1: raise ValueError('Expected one new session per commit')
    r=new[0]; label='盤前' if r['session']=='pre' else '盤後'
    lines=[f'🇺🇸 美股每日新聞｜{label}',r['date'],f"新增 {len(r['events'])} 則"]
    for e in r['events'][:12]: lines.append(f"{e['impact']}｜{', '.join(e['tickers'])}：{e['title']}")
    msg='\n'.join(lines)[:1700]+'\n完整研究及圖表：https://tw-market-monitor.pages.dev/?page=reports&usnews=1'
    if '--dry-run' in sys.argv: print(msg); return
    token=os.environ['TELEGRAM_BOT_TOKEN']; body=json.dumps({'chat_id':os.environ['TELEGRAM_CHAT_ID'],'text':msg}).encode()
    req=urllib.request.Request(f'https://api.telegram.org/bot{token}/sendMessage',data=body,headers={'Content-Type':'application/json'})
    with urllib.request.urlopen(req,timeout=30) as response:
        if not json.load(response).get('ok'): raise RuntimeError('Telegram rejected message')
if __name__=='__main__': main()
