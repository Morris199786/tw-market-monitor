import argparse,collections,csv,datetime as dt,hashlib,importlib.util,json,os,sys
from pathlib import Path

def mod(name,path):
 s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);sys.modules[name]=m;s.loader.exec_module(m);return m
parser=argparse.ArgumentParser(description='Frozen historical replay: TWSE A and unchanged OTC; no network or production writes.')
parser.add_argument('--source-root',type=Path,required=True)
parser.add_argument('--notice-cache',type=Path,required=True)
parser.add_argument('--reference',type=Path,required=True)
parser.add_argument('--out',type=Path,default=Path('self_report_historical_backtest'))
args=parser.parse_args()
source=args.source_root
v=mod('self_report_predict',source/'scripts/self_report_predict.py')
rules=mod('historical_rule',source/'scripts/self_report_rule_backtest.py')
read=lambda p:list(csv.DictReader(open(p,encoding='utf-8-sig')))
events=read(source/'data/self_report_v17_archive/events.csv');
if min(e['date'] for e in events)!='2026-07-01' or max(e['date'] for e in events)!='2026-10-20':raise RuntimeError('Unexpected event archive coverage; recent-only reports must not be used')
master=json.load(open(source/'data/master.json'))['stocks'];cal=sorted({r['date'] for r in json.load(open(source/'data/market_monitor.json'))['raw'] if r.get('index') is not None and '2026-06-01'<=r['date']<='2026-10-20'})
notes=json.load(open(args.notice_cache/'twse_2026-07-01_2026-10-20.json'))['rows'];notes=[n for n in notes if rules.valid_notice(n)]
truth=collections.defaultdict(set);prior=collections.defaultdict(list)
for e in events:
 prior[e['ticker']].append(e)
 if e['kind']=='attention':truth[e['date'],e['market']].add(e['ticker'])
listed={}
for day in cal:
 if day<'2026-07-23':continue
 idx=cal.index(day);cut=cal[idx-1];windows={n:set(cal[idx-n:idx]) for n in (1,3,5)};group=collections.defaultdict(list)
 for n in notes:
  if n['date']<=cut and master.get(n['ticker'],{}).get('market')=='twse':group[n['ticker']].append(n['date'])
 pool=[]
 for ticker,hist in group.items():
  counts={f'n{n}':sum(d in ds for d in hist) for n,ds in windows.items()}
  if not counts['n1']:continue
  if any(e['date']<=cut and 0<=(dt.date.fromisoformat(day)-dt.date.fromisoformat(e['date'])).days<=30 for e in prior[ticker]):continue
  pool.append(dict(date=day,ticker=ticker,market='twse',label=int(ticker in truth[day,'twse']),**counts))
 listed[day]=sorted(pool,key=lambda r:(-r['n5'],-r['n3'],r['ticker']))[:10]
days=collections.defaultdict(list)
for r in read(source/'data/self_report_v17_archive/scores.csv'):
 for key in ('label','recent','gap','reason6','n1','n3','n5','n10','n20'):r[key]=int(r.get(key) or 0)
 r['reason6_flag']=int(r.get('reason6_flag') or (r['reason6']>0));r['days_since_report']=int(r['days_since_report']) if r['days_since_report'] else None
 r['market_pattern']=v.bucket(r);r['notice_intensity']='high' if r['n5']>=3 else 'mid' if r['n5']==2 else 'low'
 r['clause_data_available']=int('clause_last_known' in r and str(r.get('clause_last_known'))!='');r['rule_eligible']=v.eligible(r);r['label']=int(r['ticker'] in truth[r['date'],r['market']]);days[r['date']].append(r)
training=[];otc={}
for day,rows in sorted(days.items()):
 enough=len({r['date'] for r in training})>=5 and sum(r['label'] for r in training)>=15
 if enough:
  model=v.Model(training);scored=[]
  for r in rows:
   if r['market']=='tpex':
    p,n=model.predict(r);scored.append(dict(r,probability=p,cell_samples=n))
  otc[day]=v.choose(scored)
 training.extend(rows)
reference=read(args.reference);valid=sorted({r['date'] for r in reference})
for label,dates in [('same54',valid),('from723',sorted(d for d in listed if d in otc))]:
 print(label,len(dates),min(dates),max(dates))
 for market,ps in [('twse',listed),('tpex',otc)]:
  rr=[r for d in dates for r in ps[d]];actual=sum(len(truth[d,market]) for d in dates);print(market,v.metrics(rr,actual))
for market,ps,key in [('twse',listed,'rule_picks'),('tpex',otc,'v17_picks')]:
 dif=[]
 for r in reference:
  if r['market']!=market or (market=='tpex' and not r['group'].startswith('B')):continue
  actual={x['ticker'] for x in ps[r['date']]};exp=set(r[key].split())
  if actual!=exp:dif.append((r['date'],sorted(actual-exp),sorted(exp-actual)))
 print('DIFF',market,len(dif),dif[:15])
 if dif:raise RuntimeError('Historical daily picks differ; do not publish comparable metrics: '+str(dif[:10]))
out=args.out;out.mkdir(parents=True,exist_ok=True)
picks=[r for d in sorted(listed) if d in otc for r in listed[d]+otc[d]]
v.csvout(out/'backtest_picks.csv',picks)
daily=[]
for d in sorted(listed):
 if d not in otc:continue
 for market,ps in [('twse',listed),('tpex',otc)]:
  actual=truth[d,market];selected={r['ticker'] for r in ps[d]};daily.append(dict(date=d,market=market,valid_cooldown=market=='tpex' or d>='2026-07-31',picks=' '.join(sorted(selected)),hit_tickers=' '.join(sorted(selected&actual)),missed_tickers=' '.join(sorted(actual-selected)),**v.metrics(ps[d],len(actual))))
v.csvout(out/'backtest_daily.csv',daily)

windows={'original_54_days':valid,'from_july23_provisional':sorted(d for d in listed if d in otc),'from_july31':sorted(d for d in listed if d in otc and d>='2026-07-31')}
summary={'model':'TWSE A + original OTC, frozen source 860ef3a9a011faf9a821ad128524e21d50ce29cf',
         'network_requests':0,'daily_reference_match':True,'production_changed':False,
         'event_start':min(e['date'] for e in events),'event_end':max(e['date'] for e in events),
         'event_rows':len(events),'windows':{},
         'warnings':['July23-July30 TWSE cooldown lacks June23-June30 announcements; this window is provisional.',
                     'Original54 metrics reproduce the archive; this does not independently prove MOPS completeness.',
                     'No model tuning, no live predictions, no Telegram or OpenAI API calls.']}
for label,ds in windows.items():
 block={'start':min(ds),'end':max(ds),'days':len(ds)}
 for market,selected in [('twse',listed),('tpex',otc)]:
  block[market]=v.metrics([r for d in ds for r in selected[d]],sum(len(truth[d,market]) for d in ds))
 block['all']=v.metrics([r for d in ds for r in listed[d]+otc[d]],sum(len(truth[d,m]) for d in ds for m in ('twse','tpex')))
 summary['windows'][label]=block
v.write(out/'backtest_summary.json',summary)
v.csvout(out/'restored_event_audit.csv',events)
lines=['# 歷史資料恢復後離線回測','',
       '上市A與上櫃原模型固定不變；原54天推薦名單逐日比對完全一致。','',
       '| 區間 | 市場 | 預測 | 命中 | 實際 | 命中率 | 召回率 |',
       '|---|---|---:|---:|---:|---:|---:|']
for label,block in summary['windows'].items():
 for m,name in [('twse','上市 A'),('tpex','上櫃原模型'),('all','合計')]:
  x=block[m]
  pct=lambda n:'—' if n is None else f'{n:.2%}'
  lines.append(f'| {label} ({block["days"]}天) | {name} | {x["predictions"]} | {x["hits"]} | {x["actual"]} | {pct(x["precision"])} | {pct(x["recall"])} |')
lines+=['','original_54_days：8/3～10/20；from_july31：7/31～10/20。',
        'from_july23_provisional：7/23～10/20。7/23～7/30缺少6月公告作30日排除檢查，這段不是完整驗證結果。',
        '修復前誤讀近期self_reports_history.json；本次改讀封存events.csv與scores.csv。',
        '僅按指定預測日計算命中；命中率＝命中／推薦；召回率＝命中／實際注意交易自結。']
report='\n'.join(lines)+'\n'
(out/'REPORT.md').write_text(report,encoding='utf-8')
if os.environ.get('GITHUB_STEP_SUMMARY'):
 with open(os.environ['GITHUB_STEP_SUMMARY'],'a',encoding='utf-8') as f:f.write(report)
print(report)
