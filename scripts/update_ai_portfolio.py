"""Full-market, recency-aware, market-regime weighted forward paper account. No pushes."""
import argparse,hashlib,json,math,statistics
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from ai_portfolio_engine import DEFAULTS,VERSION,TZ,number,stamp,initial,migrate,frozen_decision,session
from ai_allocation import average,market_regime,fundamentals,allocate,decay,age_days,ensure_floor
ROOT=Path(__file__).resolve().parents[1]

def read(path,default=None):return json.loads(path.read_text(encoding='utf-8')) if path.exists() else ({} if default is None else default)
def write(path,value):
    path.parent.mkdir(parents=True,exist_ok=True);tmp=path.with_suffix(path.suffix+'.tmp')
    tmp.write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n');tmp.replace(path)
def percentile(values):
    ranks=defaultdict(list);items=sorted(values.items(),key=lambda x:x[1]);n=len(items)
    for i,(t,v) in enumerate(items):ranks[v].append(i)
    return {t:100*sum(ranks[v])/len(ranks[v])/max(1,n-1) if n>1 else 50 for t,v in items}
def directional(values):return {t:50+v/2 if values[t]>0 else v/2 if values[t]<0 else 50 for t,v in percentile(values).items()}

def snapshots(data):
    out={}
    for folder in ('history/market','ai_market_snapshots','ai_universe_days'):
        for p in sorted((data/folder).glob('*.json')):
            o=read(p)
            if o.get('date') and (folder!='ai_universe_days' or o.get('complete')):out.setdefault(o['date'],{}).update(o.get('stocks',{}))
    d=read(data/'market_latest.json')
    if d.get('date'):
        # Preserve official OHLC when merging the existing close-only source.
        out.setdefault(d['date'],{})
        for t,q in d.get('stocks',{}).items():out[d['date']][t]={**q,**out[d['date']].get(t,{})}
    return out

def bars_for(data,ticker,frames=None):
    bars={}
    for folder in ('ai_backtest_k','ai_setup_k','daily_k','ai_etf_bars'):
        x=read(data/folder/(ticker+'.json'))
        if str(x.get('ticker',''))!=ticker:continue
        for b in x.get('bars',[]):
            if all((number(b.get(k)) or 0)>0 for k in ('open','high','low','close')):bars[b['time']]=dict(b)
    for day,stocks in (frames or snapshots(data)).items():
        q=stocks.get(ticker)
        if q and all((number(q.get(k)) or 0)>0 for k in ('open','high','low','close')):bars[day]=dict(q,time=day)
    prev=None
    for d in sorted(bars):
        b=bars[d]
        if prev and not .55<b['open']/prev<1.45:b['corporate_action']=True
        prev=b['close']
    return bars

def proposal(data,cfg,now,protected=()):
    universe=read(data/'ai_universe.json');day=universe.get('date','');attempt=dict(date=day,available_at=now.isoformat(timespec='seconds'),valid=False,targets=[],candidates=[],errors=[],coverage={})
    if not day or day>now.date().isoformat() or now<stamp(day+'T13:30:00+08:00') or (now.date()-datetime.fromisoformat(day).date()).days>4:
        attempt['errors'].append('全市場行情尚未完成／過舊，請先執行 collect_ai_universe.py');return attempt
    if not universe.get('complete'):attempt['errors'].append('全市場上市／上櫃官方行情不完整')
    monitor=read(data/'market_monitor.json');calendar=sorted({r['date'] for r in monitor.get('raw',[]) if r.get('date','9999')<=day})
    dates=calendar[-21:]
    if len(dates)<21 or dates[-1]!=day:attempt['errors'].append('大盤交易日曆不足21日');return attempt
    stocks=universe.get('stocks',{});frames=snapshots(data);mom5={};mom20={};vol={};avgvol={};history={}
    manifest=read(data/'etf-flow-v2/manifest.json');base=data/'etf-flow-v2'/manifest.get('path','missing');meta=read(base/'meta.json')
    fund_history={}
    for t,q in stocks.items():
        if q.get('asset_type')=='etf':fund_history[t]=read(base/'etfs'/(t+'.json'))
        saved=bars_for(data,t,frames);prices={d:number(b.get('close')) for d,b in saved.items()}
        if t in fund_history:
            prices.update({p[0]:number(p[1]) for p in fund_history[t].get('prices',[]) if p[0]<day})
        volumes={d:number(b.get('volume')) for d,b in saved.items()}
        for d in dates:
            z=frames.get(d,{}).get(t,{})
            if z:prices[d]=number(z.get('close',z.get('price')));volumes[d]=number(z.get('volume'))
        prices[day]=number(q.get('price',q.get('close')));volumes[day]=number(q.get('volume'))
        if any(not prices.get(d) or prices[d]<=0 for d in dates):continue
        cs=[prices[d] for d in dates]
        if any(not .55<cs[i]/cs[i-1]<1.45 for i in range(1,21)):continue
        if day not in saved or abs(saved[day]['close']-cs[-1])>max(.011,cs[-1]*.0001):continue
        mom5[t]=100*(cs[-1]/cs[-6]-1);mom20[t]=100*(cs[-1]/cs[-21]-1)
        changes=[100*(cs[i]/cs[i-1]-1) for i in range(1,21)]
        vol[t]=statistics.pstdev(changes);avgvol[t]=average([volumes.get(d) for d in dates[-5:]],0);history[t]=saved
    registered=universe.get('register_count',0);usable_stocks=sum(stocks[t].get('asset_type')=='stock' for t in history)
    attempt['coverage'].update(register=registered,quoted_stocks=universe.get('stock_quote_count',0),usable_stocks=usable_stocks,
        usable_etfs=sum(stocks[t].get('asset_type')=='etf' for t in history),quote_etfs=universe.get('etf_count',0),price={'usable':len(history),'universe':len(stocks)})
    if registered<1500 or usable_stocks<registered*.70:attempt['errors'].append('全市場普通股21日行情覆蓋不足70%，保留前次決策')
    if missing:=sorted(set(protected)-set(history)):attempt['errors'].append('已持有／前次目標行情不足：'+','.join(missing))
    breadth=average([1 if x>0 else 0 for t,x in mom20.items() if stocks[t]['asset_type']=='stock'],0)
    regime=market_regime(monitor,day,breadth);attempt['regime']=regime
    if not regime['valid']:attempt['errors'].extend(regime['reasons'])
    # Institutional daily data: same-date full archive preferred; ranked absence stays neutral.
    institutional=read(data/'institutional.json');flows={};archive=read(data/'history/institutional'/(day+'.json'))
    if archive:
        for m in ('twse','tpex'):
            for t,v in archive.get(m,{}).items():
                ns=[number(v.get(k)) for k in ('foreign','trust','dealer')]
                if all(n is not None for n in ns):flows[t]=sum(ns)
    else:
        for m in ('twse','tpex'):
            group=institutional.get('periods',{}).get('1d',{}).get(m,{}).get('total',{})
            for side,sign in [('buy',1),('sell',-1)]:
                for x in group.get(side,[]):
                    n=number(x.get('shares'))
                    if n is not None:flows[str(x['ticker'])]=sign*abs(n)
    if institutional.get('date')!=day:attempt['errors'].append('法人資料不是同日')
    flowrank=directional({t:v*stocks[t]['price'] for t,v in flows.items() if t in stocks})
    funds=[f for f in meta.get('funds',[]) if f.get('region')=='TW' and f.get('listing','9999')<=day];fresh=0;etf_flow={};etf_details=defaultdict(list)
    for fund in funds:
        f=fund_history.get(fund['code']) or read(base/'etfs'/(fund['code']+'.json'))
        if f.get('fund',{}).get('latest')!=day:continue
        fresh+=1
        for e in f.get('events',[]):
            t=str(e.get('code'));n=number(e.get('delta'))
            if e.get('date')==day and t in stocks and n is not None:
                etf_flow[t]=etf_flow.get(t,0)+n*stocks[t]['price'];etf_details[t].append(dict(fund=fund['code'],shares_delta=n,date=day))
    if not funds or fresh/len(funds)<.7:attempt['errors'].append('同日台股ETF持股資料不足70%')
    attempt['coverage']['etf']={'fresh':fresh,'total':len(funds)};etfrank=directional(etf_flow)
    holder=read(data/'holders.json');hdate=holder.get('date','');holders={}
    try:hage=(now.date()-datetime.strptime(hdate,'%Y%m%d').date()).days
    except ValueError:hage=999
    if hage<=14 and holder.get('complete'):
        for m in ('twse','tpex'):
            for x in holder.get(m,{}).get('400',[]):
                if number(x.get('delta')) is not None:holders[str(x['ticker'])]=number(x['delta'])
    if not holders:attempt['errors'].append('大戶資料未齊或超過14日')
    holder_sessions=age_days(datetime.strptime(hdate,'%Y%m%d').date().isoformat(),now,calendar) if holders else 0
    holdrank={t:50+(v-50)*decay(holder_sessions,10) for t,v in directional(holders).items()}
    earnings=read(data/'quarterly_earnings.json');opm=read(data/'quarterly_opm.json').get('metrics',{});official=read(data/'ai_fundamentals.json').get('stocks',{})
    reports=read(data/'reports.json');financial={};research=defaultdict(list)
    if not earnings.get('reports') or not reports.get('items'):attempt['errors'].append('既有財報或研究資料庫讀取失敗')
    for f in earnings.get('reports',[]):
        published=f.get('publish_date');t=str(f.get('ticker'))
        if not published:continue
        try:when=stamp(published+'T'+(f.get('publish_time') or '23:59:59')+'+08:00')
        except ValueError:continue
        if when>now:continue
        if t not in financial or (f.get('period',''),published)>(financial[t].get('period',''),financial[t].get('publish_date','')):financial[t]=f
    for r in reports.get('items',[]):research[str(r.get('ticker'))].append(r)
    ranking5=percentile(mom5);ranking20=percentile(mom20);turnrank=percentile({t:q.get('turnover',0) for t,q in stocks.items()})
    ranked=[];stock_scores={}
    for t in history:
        q=stocks[t]
        if q['asset_type']=='etf':continue
        f=fundamentals(t,financial.get(t),official.get(t),opm,research[t],now,calendar)
        chip=.35*flowrank.get(t,50)+.35*etfrank.get(t,50)+.2*holdrank.get(t,50)+.1*turnrank.get(t,50)
        momentum=.6*ranking5[t]+.4*ranking20[t];score=.4*chip+.4*f['score']+.2*momentum
        evidence=f['evidence'];risks=f['risks']
        if t in flows:evidence.append(f'法人同日已知淨額 {flows[t]/1000:+,.1f} 張')
        else:risks.append('法人排行未涵蓋，不能當成零買超')
        if t in etf_flow:evidence.append(f'ETF同日持股淨變動估值 {etf_flow[t]/10000:+,.0f} 萬元')
        if t in holders:evidence.append(f'400張以上週變化 {holders[t]:+.2f} 百分點（{hdate}）')
        evidence.append(f'5日 {mom5[t]:+.2f}%／20日 {mom20[t]:+.2f}%；實際加權指數5日 {regime.get("return5",0):+.2f}%')
        if mom5[t]>25:score-=10;risks.append('近5日漲逾25%，扣10分避免過度追價')
        discovery=not f['verified']
        liquid=q.get('turnover',0)>=10000000 and avgvol[t]>=100000
        confirmed=(f['verified'] and f['score']>=50 and chip>=55 and momentum>=45)
        exploring=(discovery and chip>=70 and momentum>=75 and (t in flows or t in etf_flow))
        eligible=liquid and score>=cfg['minimum_score'] and (confirmed or exploring)
        x=dict(ticker=t,name=q['name'],market=q['market'],asset_type='stock',sector='產業 '+str(q.get('industry','unknown')),
            score=round(score,2),pillars=dict(chip=round(chip,2),fundamental=round(f['score'],2),momentum=round(momentum,2)),eligible=eligible,
            discovery=discovery,confidence='基本面已驗證' if f['verified'] else '待基本面確認的小部位',freshness=f['freshness'],
            evidence=evidence,risks=risks,etf_details=etf_details[t],volatility=vol[t],avg_volume=avgvol[t],price=q['price'])
        ranked.append(x);stock_scores[t]=x
    for t in history:
        q=stocks[t]
        if q['asset_type']!='etf':continue
        holdings=q.get('holdings',[]);known=[]
        total_weight=sum(float(h[3]) for h in holdings if len(h)>3 and number(h[3]) is not None)
        for h in holdings:
            if len(h)>3 and str(h[0]) in stock_scores and number(h[3]) is not None:known.append((stock_scores[str(h[0])]['pillars']['fundamental'],float(h[3])))
        coverage=sum(w for s,w in known)/total_weight if total_weight else 0
        underlying=sum(s*w for s,w in known)/sum(w for s,w in known) if known and coverage>=.60 else 50
        momentum=.6*ranking5[t]+.4*ranking20[t];chip=50+max(-25,min(25,(regime.get('score',0)-2)*8))
        score=.4*chip+.3*underlying+.3*momentum
        ranked.append(dict(ticker=t,name=q['name'],market=q['market'],asset_type='etf',sector='分散ETF',score=round(score,2),
            pillars=dict(chip=chip,fundamental=round(underlying,2),momentum=round(momentum,2)),eligible=q.get('turnover',0)>=10000000 and avgvol[t]>=100000 and score>=60 and mom20[t]>0 and momentum>=50,
            core_eligible=t in ('0050','006208') and q.get('turnover',0)>=10000000 and avgvol[t]>=100000,discovery=False,confidence='ETF配置',volatility=vol[t],avg_volume=avgvol[t],price=q['price'],freshness={},
            evidence=[f'台股原型股票ETF；5日 {mom5[t]:+.2f}%／20日 {mom20[t]:+.2f}%',f'持股基本面可辨識權重 {coverage:.1%}，不足60%時中性評分'],
            risks=['ETF不套用公司EPS／OPM；持股與個股可能重疊，單檔25%、ETF合計50%上限'],etf_details=[]))
    ranked.sort(key=lambda x:(-x['score'],x['ticker']));targets=allocate(ranked,regime['target_exposure'],cfg)
    core=[dict(x,confidence='最低部位大盤ETF') for x in ranked if x.get('core_eligible')]
    targets,floor_met=ensure_floor(targets,core,cfg)
    if not floor_met:attempt['errors'].append('無法以合格標的及可驗證大盤ETF達到最低40%目標，保留前次決策')
    exposure=sum(t['weight'] for t in targets)
    attempt.update(valid=not attempt['errors'],targets=targets,candidates=ranked[:50],regime=regime,target_exposure=exposure,target_cash=1-exposure,
        model='既有AI研究＋官方全市場財務資料＋透明規則配置；分數不是機率',sources={'market_date':day,'institutional_date':institutional.get('date'),
        'holder_date':hdate,'market_monitor_date':regime.get('date'),'etf_version':manifest.get('version'),'official_financial_count':len(official)},
        temporal_policy={'event_half_life_sessions':5,'research_thesis_half_life_sessions':30,'financial_max_age_calendar_days':150})
    attempt['input_hash']=hashlib.sha256(json.dumps(attempt,ensure_ascii=False,sort_keys=True).encode()).hexdigest()
    return attempt

def run(root,now,preview=False):
    data=root/'data';cfg={**DEFAULTS,**read(root/'config/ai_portfolio.json')}
    if cfg['initial_cash']<=0 or cfg['max_positions']<1 or not 0<cfg['max_stock_weight']<=1 or not 0<cfg['max_etf_weight']<=1:raise ValueError('Invalid configuration')
    path=data/'ai_portfolio.json';old=read(path) if path.exists() else None
    state,archive=migrate(old,cfg,now.isoformat(timespec='seconds')) if old else (initial(cfg,now.isoformat(timespec='seconds')),None)
    frames=snapshots(data);needed=set(state['positions'])|{t['ticker'] for d in state['decisions'] for t in d['targets']}
    candles={t:bars_for(data,t,frames) for t in needed}
    for day in sorted(frames):
        if day>now.date().isoformat() or now<stamp(day+'T13:30:00+08:00'):continue
        session(state,day,{t:b.get(day) for t,b in candles.items()},{t:q.get('close',q.get('price')) for t,q in frames[day].items()})
    protected=set(state['positions'])|{t['ticker'] for t in (state['decisions'][-1]['targets'] if state['decisions'] else [])}
    attempt=proposal(data,cfg,now,protected);frozen_decision(state,attempt)
    state.update(updated_at=now.isoformat(timespec='seconds'),status='ready' if attempt['valid'] else 'data_pending',
        limitations=['整數股可含零股；以普通交易開盤價加滑價作模擬代理，非真實零股9:10撮合價。',
        '含費稅的價格損益口徑，尚未自動匯入股利、配股與減資；疑似公司行動保留標記待確認。',
        '每次成交上限為決策時已知5日均量的1%，未成交部分等待後續可驗證交易日。',
        '大盤曝險和時效半衰期是未經最佳化的模型設定，不保證績效；ETF與個股仍可能存在穿透持股重疊。',
        '完整上市上櫃名冊都掃描；不足21日行情、新上市、資料不齊標的會揭露覆蓋並暫不交易。'])
    output=root/'preview' if preview else data
    if archive is not None:
        archive_path=output/'ai_portfolio_archives'/('v1_'+archive['started_at'].replace(':','-')+'.json')
        if not archive_path.exists():write(archive_path,archive)
    write(output/'ai_portfolio.json',state)
    print(json.dumps(dict(preview=preview,status=state['status'],capital=cfg['initial_cash'],targets=len(state['decisions'][-1]['targets']) if state['decisions'] else 0,
        errors=attempt['errors'],coverage=attempt['coverage'],regime=attempt.get('regime'),cash_target=attempt.get('target_cash')),ensure_ascii=False))
    return state

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,default=ROOT);p.add_argument('--preview',action='store_true');a=p.parse_args();run(a.root,datetime.now(TZ),a.preview)
