"""Full-market, recency-aware, market-regime weighted forward paper account. No pushes."""
import argparse,hashlib,json,math,statistics
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from ai_portfolio_engine import DEFAULTS,VERSION,TZ,number,stamp,initial,migrate,frozen_decision,session
from ai_allocation import average,market_regime,fundamentals,allocate,decay,age_days,ensure_floor
from ai_reference_data import CAPTURE,record,digest,reference_snapshot,merge_earnings,research_index,holder_values
from ai_content_research import load_sources
from ai_signal_model import monthly_bonus,mixed_flow_score
from ai_relative_momentum import sector_groups,benchmark_returns,momentum as relative_momentum
ROOT=Path(__file__).resolve().parents[1]

def read(path,default=None):
    value=json.loads(path.read_text(encoding='utf-8')) if path.exists() else ({} if default is None else default)
    record(path,value,path.exists())
    return value
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

def _proposal(data,cfg,now,protected=()):
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
    if registered<1500 or usable_stocks<registered*.70:attempt['errors'].append('全市場普通股21日行情覆蓋不足70%，本次不發布新名單')
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
    master=read(data/'master.json').get('stocks',{})
    caps={t:number(master.get(t,{}).get('shares_issued')) for t in stocks}
    caps={t:n*stocks[t]['price'] for t,n in caps.items() if n is not None and n>0}
    def mixed_flow(values):return mixed_flow_score(values,caps,directional)
    flow_amounts={t:v*stocks[t]['price'] for t,v in flows.items() if t in stocks}
    flowrank=mixed_flow(flow_amounts)
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
    attempt['coverage']['etf']={'fresh':fresh,'total':len(funds)};etfrank=mixed_flow(etf_flow)
    holder=read(data/'holders.json');hdate=holder.get('date','');holders={};hmode='unavailable'
    try:hage=(now.date()-datetime.strptime(hdate,'%Y%m%d').date()).days
    except ValueError:hage=999
    if 0<=hage<=14 and holder.get('complete'):
        current=read(data/'history/holders'/(hdate+'.json'))
        previous=read(data/'history/holders'/(str(holder.get('previous_date','missing'))+'.json'))
        holders,hmode=holder_values(holder,current,previous,number)
    holders={t:v for t,v in holders.items() if t in stocks and stocks[t].get('asset_type')=='stock'}
    if not holders:attempt['errors'].append('大戶資料未齊或超過14日')
    holder_sessions=age_days(datetime.strptime(hdate,'%Y%m%d').date().isoformat(),now,calendar) if holders else 0
    hgroups={g:directional({t:v[g]['delta'] for t,v in holders.items() if g in v}) for g in ('400','1000')}
    # Give both 400+ and 1000+ weekly changes half of the existing holder factor.
    # Missing tier stays neutral; never infer missing data as zero change.
    holdrank={t:average([50+(hgroups[g].get(t,50)-50)*decay(holder_sessions,10) for g in ('400','1000')]) for t in holders}
    attempt['coverage']['holders']={'mode':hmode,'date':hdate,'previous_date':holder.get('previous_date'),
        '400_companies':sum('400' in v for v in holders.values()),'1000_companies':sum('1000' in v for v in holders.values()),
        'weight_within_chips':.2,'tier_weights':{'400':.5,'1000':.5}}
    earnings=read(data/'quarterly_earnings.json');opm=read(data/'quarterly_opm.json').get('metrics',{});official=read(data/'ai_fundamentals.json').get('stocks',{})
    reports=read(data/'reports.json');financial={};research=load_sources(data,read,now)
    content_cache=read(data/'ai_research_content.json')
    self_items=read(data/'self_reports_history.json').get('items',[])+read(data/'self_reports.json').get('items',[])
    quarters={}
    raw_reports=read(data/'business_reports.json').get('items',[])
    recovered=read(data/'quarterly_earnings_recovered.json')
    earnings={**earnings,'reports':merge_earnings(earnings,recovered)}
    if not earnings.get('reports') or not reports.get('items'):attempt['errors'].append('既有財報或研究資料庫讀取失敗')
    for f in earnings.get('reports',[]):
        published=f.get('publish_date');t=str(f.get('ticker'))
        if not published:continue
        try:when=stamp(published+'T'+(f.get('publish_time') or '23:59:59')+'+08:00')
        except ValueError:continue
        if when>now:continue
        quarters[(t,f.get('period'))]=f
        if t not in financial or (f.get('period',''),published)>(financial[t].get('period',''),financial[t].get('publish_date','')):financial[t]=f
    for (t,period),f in quarters.items():
        match=__import__('re').fullmatch(r'(\d{4})-Q([1-4])',str(period))
        if not match:continue
        year,q=map(int,match.groups());previous=f'{year-1}-Q4' if q==1 else f'{year}-Q{q-1}'
        f.setdefault('prev_period',previous)
        for metric in ('eps','gross_margin','operating_margin'):
            if f.get('prev_'+metric) is None:f['prev_'+metric]=quarters.get((t,previous),{}).get(metric)
    groups=sector_groups(read(data/'sectors.json'))
    try:market_returns=benchmark_returns(monitor,dates)
    except ValueError as exc:
        attempt['errors'].append(str(exc));return attempt
    relative_returns={5:mom5,20:mom20}
    turnrank=percentile({t:q.get('turnover',0) for t,q in stocks.items()})
    ranked=[];stock_scores={};research_pending={}
    for t in history:
        q=stocks[t]
        if q['asset_type']=='etf':continue
        f=fundamentals(t,financial.get(t),official.get(t),opm,research[t],now,calendar,content_cache)
        if f['research_missing']:research_pending[t]=len(f['research_missing'])
        bonus=monthly_bonus(t,self_items,quarters,now,calendar)
        chip=.35*flowrank.get(t,50)+.35*etfrank.get(t,50)+.2*holdrank.get(t,50)+.1*turnrank.get(t,50)
        relative=relative_momentum(t,relative_returns,market_returns,groups)
        momentum=relative['score'];score=.4*chip+.4*f['score']+.2*momentum+bonus['bonus']
        evidence=f['evidence']+bonus['evidence']+relative['evidence'];risks=f['risks']+bonus['risks']
        if caps.get(t):
            if t in flow_amounts:evidence.append(f'法人淨額占收盤市值 {flow_amounts[t]/caps[t]*100:+.4f}%（金額／占市值各半）')
            if t in etf_flow:evidence.append(f'ETF淨持股變動占收盤市值 {etf_flow[t]/caps[t]*100:+.4f}%（金額／占市值各半）')
        else:risks.append('已發行股數缺值，占市值因子維持中性，不假設零市值')
        if t in flows:evidence.append(f'法人同日已知淨額 {flows[t]/1000:+,.1f} 張')
        else:risks.append('法人排行未涵蓋，不能當成零買超')
        if t in etf_flow:evidence.append(f'ETF同日持股淨變動估值 {etf_flow[t]/10000:+,.0f} 萬元')
        if t in holders:
            for g,label in [('400','400張以上'),('1000','千張以上')]:
                v=holders[t].get(g)
                if v:
                    ratio=f"，持股比 {v['ratio']:.2f}%" if v['ratio'] is not None else ''
                    evidence.append(f"{label}週變化 {v['delta']:+.2f} 百分點{ratio}（{hdate}）")
        evidence.append(f'5日 {mom5[t]:+.2f}%／20日 {mom20[t]:+.2f}%；實際加權指數5日 {regime.get("return5",0):+.2f}%')
        if mom5[t]>25:risks.append('近5日漲逾25%，提示追價／跳空風險；不固定扣分或降低部位')
        discovery=not f['verified']
        liquid=q.get('turnover',0)>=10000000 and avgvol[t]>=100000
        confirmed=(f['verified'] and f['score']>=50 and chip>=55 and momentum>=45)
        exploring=(discovery and chip>=70 and momentum>=75 and (t in flows or t in etf_flow))
        eligible=liquid and score>=cfg['minimum_score'] and (confirmed or exploring) and not f['research_missing']
        x=dict(ticker=t,name=q['name'],market=q['market'],asset_type='stock',sector='產業 '+str(q.get('industry','unknown')),
            score=round(score,2),pillars=dict(chip=round(chip,2),fundamental=round(f['score'],2),momentum=round(momentum,2)),eligible=eligible,
            research_details=f['research_details'],financial_score=round(f['financial_score'],2),research_score=round(f['research_score'],2),self_report_bonus=round(bonus['bonus'],3),model_version='relative-content-v5',relative_momentum=relative,research_pending=len(f['research_missing']),
            discovery=discovery,confidence='基本面已驗證' if f['verified'] else '待基本面確認的小部位',freshness=f['freshness'],
            evidence=evidence,risks=risks,etf_details=etf_details[t],volatility=vol[t],avg_volume=avgvol[t],price=q['price'])
        ranked.append(x);stock_scores[t]=x
    for t in history:
        q=stocks[t]
        if q['asset_type']!='etf':continue
        holdings=q.get('holdings',[]);known=[]
        total_weight=sum(float(h[3]) for h in holdings if len(h)>3 and number(h[3]) is not None)
        for h in holdings:
            if len(h)>3 and str(h[0]) in stock_scores and not stock_scores[str(h[0])].get('research_pending') and number(h[3]) is not None:known.append((stock_scores[str(h[0])]['pillars']['fundamental'],float(h[3])))
        coverage=sum(w for s,w in known)/total_weight if total_weight else 0
        underlying=sum(s*w for s,w in known)/sum(w for s,w in known) if known and coverage>=.60 else 50
        relative=relative_momentum(t,relative_returns,market_returns,[])
        momentum=relative['score'];chip=50+max(-25,min(25,(regime.get('score',0)-2)*8))
        score=.4*chip+.3*underlying+.3*momentum
        ranked.append(dict(ticker=t,name=q['name'],market=q['market'],asset_type='etf',sector='分散ETF',score=round(score,2),
            pillars=dict(chip=chip,fundamental=round(underlying,2),momentum=round(momentum,2)),eligible=q.get('turnover',0)>=10000000 and avgvol[t]>=100000 and score>=60 and mom20[t]>0 and momentum>=50,
            relative_momentum=relative,model_version='relative-content-v5',core_eligible=t in ('0050','006208') and q.get('turnover',0)>=10000000 and avgvol[t]>=100000,discovery=False,confidence='ETF配置',volatility=vol[t],avg_volume=avgvol[t],price=q['price'],freshness={},
            evidence=relative['evidence']+[f'台股原型股票ETF；5日 {mom5[t]:+.2f}%／20日 {mom20[t]:+.2f}%',f'持股基本面可辨識權重 {coverage:.1%}，不足60%時中性評分'],
            risks=['ETF不套用公司EPS／OPM；持股與個股可能重疊，單檔25%、ETF合計50%上限'],etf_details=[]))
    if research_pending:attempt.setdefault('warnings',[]).append(f'研究內容待核對{sum(research_pending.values())}份、{len(research_pending)}家公司：本次排除這些公司的直接交易，不阻擋其餘已驗證標的發布新名單')
    attempt['excluded_research']=[{'ticker':t,'name':stocks[t]['name'],'pending_documents':n} for t,n in sorted(research_pending.items())]
    attempt['coverage']['research_content']={'pending_companies':len(research_pending),'pending_documents':sum(research_pending.values()),'model':content_cache.get('model'),'version':content_cache.get('version')}
    ranked.sort(key=lambda x:(-x['score'],x['ticker']));targets=allocate(ranked,regime['target_exposure'],cfg)
    core=[dict(x,confidence='最低部位大盤ETF') for x in ranked if x.get('core_eligible')]
    targets,floor_met=ensure_floor(targets,core,cfg)
    if not floor_met:attempt['errors'].append('無法以合格標的及可驗證大盤ETF達到最低40%目標，本次不發布新名單')
    exposure=sum(t['weight'] for t in targets)
    attempt.update(valid=not attempt['errors'],targets=targets,candidates=ranked[:50],regime=regime,target_exposure=exposure,target_cash=1-exposure,
        model='relative-content-v5：同期大盤／族群相對動能＋不按波動率降權＋本業季比較＋自結加分＋金額及市值強度＋證據式AI內容判讀；分數不是機率',sources={'market_date':day,'institutional_date':institutional.get('date'),
        'holder_date':hdate,'market_monitor_date':regime.get('date'),'etf_version':manifest.get('version'),'official_financial_count':len(official),'earnings_updated_at':earnings.get('updated_at'),'opm_updated_at':read(data/'quarterly_opm.json').get('updated_at'),'research_updated_at':reports.get('updated_at'),'research_items':len(reports.get('items',[])),'research_raw_files':len(raw_reports),'holder_mode':hmode},
        temporal_policy={'event_half_life_sessions':5,'research_thesis_half_life_sessions':30,'financial_max_age_calendar_days':150})
    return attempt

def proposal(data,cfg,now,protected=()):
    captured={};token=CAPTURE.set(captured)
    try:attempt=_proposal(data,cfg,now,protected)
    finally:CAPTURE.reset(token)
    manifest=reference_snapshot(data,cfg,captured,now)
    attempt['reference_hash']=manifest['reference_hash']
    attempt['reference_files']=len(manifest['files'])
    attempt['evaluation_date']=manifest['evaluation_date']
    attempt['input_hash']=digest({'reference_hash':manifest['reference_hash'],'targets':attempt.get('targets',[]),
        'candidates':attempt.get('candidates',[]),'regime':attempt.get('regime'),'valid':attempt.get('valid'),'errors':attempt.get('errors',[])})
    attempt['_reference_manifest']=manifest
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
    attempt=proposal(data,cfg,now,protected);manifest=attempt.pop('_reference_manifest');frozen_decision(state,attempt)
    state.update(updated_at=now.isoformat(timespec='seconds'),status='ready' if attempt['valid'] else 'data_pending',
        limitations=['整數股可含零股；以普通交易開盤價加滑價作模擬代理，非真實零股9:10撮合價。',
        '含費稅的價格損益口徑，尚未自動匯入股利、配股與減資；疑似公司行動保留標記待確認。',
        '每次成交上限為決策時已知5日均量的1%，未成交部分等待後續可驗證交易日。',
        '波動率僅揭露，不直接扣分或降權；高波動不等於高預期報酬。大盤與半衰期尚未經績效最佳化；ETF與個股可能重疊。',
        '完整上市上櫃名冊都掃描；不足21日行情、新上市、資料不齊標的會揭露覆蓋並暫不交易。'])
    output=root/'preview' if preview else data
    if archive is not None:
        archive_path=output/'ai_portfolio_archives'/('v1_'+archive['started_at'].replace(':','-')+'.json')
        if not archive_path.exists():write(archive_path,archive)
    write(output/'ai_reference_manifest.json',manifest)
    write(output/'ai_portfolio.json',state)
    print(json.dumps(dict(preview=preview,status=state['status'],capital=cfg['initial_cash'],targets=len(state['decisions'][-1]['targets']) if state['decisions'] else 0,
        errors=attempt['errors'],coverage=attempt['coverage'],regime=attempt.get('regime'),cash_target=attempt.get('target_cash')),ensure_ascii=False))
    return state

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,default=ROOT);p.add_argument('--preview',action='store_true');a=p.parse_args();run(a.root,datetime.now(TZ),a.preview)
