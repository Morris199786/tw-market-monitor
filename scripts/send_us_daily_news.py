import json, os, pathlib, urllib.request
p=pathlib.Path('/tmp/us-news-published.json')
if p.exists():
    r=json.loads(p.read_text()); label='盤前' if r['session']=='pre' else '盤後'; lines=[f'🇺🇸 美股每日新聞｜{label}',r['date'],f"新增 {len(r['events'])} 則"]
    for e in r['events'][:12]: lines.append(f"{e['impact']}｜{', '.join(e['tickers'])}：{e['title']}")
    msg='\n'.join(lines)[:3400]+'\nhttps://tw-market-monitor.pages.dev/'
    token=os.environ['TELEGRAM_BOT_TOKEN']; body=json.dumps({'chat_id':os.environ['TELEGRAM_CHAT_ID'],'text':msg}).encode(); req=urllib.request.Request(f'https://api.telegram.org/bot{token}/sendMessage',data=body,headers={'Content-Type':'application/json'}); urllib.request.urlopen(req,timeout=30).close()
