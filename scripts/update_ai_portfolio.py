"""Three-pillar selection plus an immutable, forward-only paper portfolio.
Run after existing daily close / chip / heatmap updates. No notifications are sent.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import math
from datetime import datetime, timedelta
from pathlib import Path
from ai_portfolio_engine import DEFAULTS, VERSION, TZ, number, stamp, initial, frozen_decision, session

ROOT=Path(__file__).resolve().parents[1]


def read(path, default=None):
    if not path.exists(): return {} if default is None else default
    # Corrupted existing state must never silently restart the account.
    return json.loads(path.read_text(encoding='utf-8'))


def write(path, value):
    path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_suffix(path.suffix+'.tmp')
    temp.write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    temp.replace(path)


def bars_for(data,ticker):
    out={}
    for folder in ('ai_backtest_k','ai_setup_k','daily_k'):
        obj=read(data/folder/(ticker+'.json'))
        if str(obj.get('ticker',''))!=ticker: continue
        for b in obj.get('bars',[]):
            if all(number(b.get(k)) is not None and number(b.get(k))>0 for k in ('open','high','low','close')):
                out[b['time']]=b
    previous=None
    for day in sorted(out):
        b=dict(out[day]);out[day]=b
        if previous and not .55 < b['open']/previous < 1.45:
            b['corporate_action']=True
        previous=b['close']
    return out


def percentile(values):
    ordered=sorted(values.items(),key=lambda x:x[1]);n=len(ordered)
    if n<2: return {k:50 for k in values}
    rank={}
    for i,(_,v) in enumerate(ordered):rank.setdefault(v,[]).append(i)
    return {k:100*sum(rank[v])/len(rank[v])/(n-1) for k,v in values.items()}


def improvement(cur,prev,scale):
    a,b=number(cur),number(prev)
    return None if a is None or b is None else max(0,min(100,50+50*(a-b)/max(abs(b),scale)))


def finite_average(values,default=50):
    clean=[v for v in values if v is not None]
    return sum(clean)/len(clean) if clean else default


def proposal(data, config, now, protected=()):
    latest=read(data/'market_latest.json');day=latest.get('date','')
    attempt=dict(date=day,available_at=now.isoformat(timespec='seconds'),valid=False,targets=[],candidates=[],errors=[],coverage={})
    if not day or day>now.date().isoformat() or now<stamp(day+'T13:30:00+08:00'):
        attempt['errors'].append('尚無已完成交易日收盤資料');return attempt
    if (now.date()-datetime.fromisoformat(day).date()).days>4:
        attempt['errors'].append('最新收盤超過四個日曆日，暫停新決策');return attempt
    master=read(data/'master.json').get('stocks',{});heat=read(data/'heatmap.json')
    groups={str(s['ticker']):g['name'] for g in heat.get('sectors',[]) for s in g.get('stocks',[])}
    stocks={t:q for t,q in latest.get('stocks',{}).items() if len(t)==4 and t.isdigit() and master.get(t,{}).get('market') in ('twse','tpex') and t in groups and (number(q.get('price')) or 0)>0}
    history={};mom5={};mom20={};volume={}
    for t,q in stocks.items():
        b=bars_for(data,t);past=[v for d,v in sorted(b.items()) if d<=day]
        if len(past)<21 or past[-1]['time']!=day:continue
        if abs(past[-1]['close']-q['price'])>max(.011,q['price']*.0001):continue
        # Reject adjustment discontinuities; unadjusted OHLC cannot safely imply momentum across splits.
        if any(not .55 < past[i]['close']/past[i-1]['close'] < 1.45 for i in range(len(past)-20,len(past))):continue
        history[t]=b;mom5[t]=100*(past[-1]['close']/past[-6]['close']-1)
        mom20[t]=100*(past[-1]['close']/past[-21]['close']-1)
        volume[t]=finite_average([number(x.get('volume')) for x in past[-5:]],0)
    attempt['coverage']['price']={'usable':len(history),'universe':len(stocks)}
    unavailable=sorted(set(protected)-set(history))
    if unavailable:attempt['errors'].append('持倉／前次目標日K資料不足，暫停換股：'+','.join(unavailable))
    if not stocks or len(history)<max(20,len(stocks)*.70):attempt['errors'].append('可驗證最新收盤及21根日K覆蓋不足70%')
    # Complete institutional archives are preferred; top-20 ranked rows are evidence only,
    # absence from a ranked table is unknown, never treated as zero institutional flow.
    inst=read(data/'institutional.json'); flows={};instdate=inst.get('date')
    archives=[]
    for p in sorted((data/'history/institutional').glob('*.json'))[-10:]:
        d=read(p)
        if d.get('date')==day:archives.append(d)
    if archives:
        d=archives[-1]
        for market in ('twse','tpex'):
            for t,v in d.get(market,{}).items():
                vals=[number(v.get(k)) for k in ('foreign','trust','dealer')]
                if all(x is not None for x in vals):flows[t]=sum(vals)
    elif instdate==day:
        for market,v in inst.get('periods',{}).get('1d',{}).items():
            if market not in ('twse','tpex'):continue
            # Ranked total net flow, if available, otherwise trust direction only.
            g=v.get('total') or v.get('trust') or {}
            for side,sign in [('buy',1),('sell',-1)]:
                for x in g.get(side,[]):
                    n=number(x.get('shares'))
                    if n is not None:flows[str(x['ticker'])]=sign*abs(n)
    if instdate!=day:attempt['errors'].append('籌碼日報非同一交易日')
    flowrank={t:(50+v/2 if flows[t]>0 else v/2 if flows[t]<0 else 50) for t,v in percentile({t:v*stocks[t]['price'] for t,v in flows.items() if t in stocks}).items()}
    # ETF events are share count changes, not claimed exchange purchases.
    manifest=read(data/'etf-flow-v2/manifest.json');base=data/'etf-flow-v2'/manifest.get('path','missing')
    meta=read(base/'meta.json');funds=[f for f in meta.get('funds',[]) if f.get('region')=='TW' and f.get('listing','9999')<=day]
    etf={};fresh=0;etf_evidence={}
    for fund in funds:
        f=read(base/'etfs'/(fund['code']+'.json'))
        if f.get('fund',{}).get('latest')!=day:continue
        fresh+=1
        for event in f.get('events',[]):
            if event.get('date')!=day:continue
            t=str(event.get('code'));delta=number(event.get('delta'))
            if t in stocks and delta is not None:
                etf[t]=etf.get(t,0)+delta*stocks[t]['price']
                etf_evidence.setdefault(t,[]).append({'fund':fund['code'],'shares_delta':delta,'date':day})
    attempt['coverage']['etf']={'fresh':fresh,'total':len(funds)}
    if not funds or fresh/len(funds)<.70:attempt['errors'].append('台股主動ETF同日覆蓋不足70%')
    etfrank={t:(50+v/2 if etf[t]>0 else v/2 if etf[t]<0 else 50) for t,v in percentile(etf).items()}
    holder=read(data/'holders.json');holderdate=holder.get('date','');holders={}
    try:holderage=(now.date()-datetime.strptime(holderdate,'%Y%m%d').date()).days
    except ValueError:holderage=999
    if holderage<=14 and holder.get('complete'):
        for m in ('twse','tpex'):
            for x in holder.get(m,{}).get('400',[]):
                n=number(x.get('delta'))
                if n is not None:holders[str(x['ticker'])]=n
    holdrank={t:(50+v/2 if holders[t]>0 else v/2 if holders[t]<0 else 50) for t,v in percentile(holders).items()}
    if not holders:attempt['errors'].append('大戶籌碼缺漏或超過14日')
    earnings=read(data/'quarterly_earnings.json');opm=read(data/'quarterly_opm.json').get('metrics',{});reports=read(data/'reports.json')
    if not earnings.get('reports') or not reports.get('items'):attempt['errors'].append('財報或產業資料庫無法讀取')
    financial={};research={}
    for x in earnings.get('reports',[]):
        t=str(x.get('ticker',''));published=x.get('publish_date','')
        if not published or published>now.date().isoformat():continue
        if stamp(published+'T'+(x.get('publish_time') or '23:59:59')+'+08:00')>now:continue
        if (now.date()-datetime.fromisoformat(published).date()).days>150:continue
        if t not in financial or (x.get('period',''),published)>(financial[t].get('period',''),financial[t].get('publish_date','')):financial[t]=x
    for x in reports.get('items',[]):
        received=x.get('received_at') or (x.get('group_date') or x.get('date',''))+'T23:59:59+08:00'
        try:when=stamp(received)
        except (TypeError,ValueError):continue
        if when>now or now-when>timedelta(days=30):continue
        t=str(x.get('ticker',''))
        if t not in research or when>research[t][0]:research[t]=(when,x)
    turnrank=percentile({t:number(q.get('turnover')) or 0 for t,q in stocks.items()})
    market5=finite_average(list(mom5.values()),0);sector5={g:finite_average([v for t,v in mom5.items() if groups[t]==g],0) for g in set(groups.values())}
    relrank=percentile({t:v-market5 for t,v in mom5.items()});trendrank=percentile(mom20)
    ranked=[]
    for t in history:
        q=stocks[t];f=financial.get(t,{});evidence=[];risks=[]
        current_opm=opm.get(t+'|'+f.get('period',''),{}).get('value',f.get('operating_margin'))
        prev_opm=opm.get(t+'|'+f.get('prev_period',''),{}).get('value',f.get('prev_operating_margin'))
        metrics=[improvement(f.get('eps'),f.get('prev_eps'),.1),improvement(f.get('gross_margin'),f.get('prev_gross_margin'),1),improvement(current_opm,prev_opm,1)]
        if t in protected and sum(v is not None for v in metrics)<2:
            attempt['errors'].append('持倉／前次目標可比財報不足：'+t)
        fundamental=finite_average(metrics)
        for label,value,prev in [('EPS',f.get('eps'),f.get('prev_eps')),('GM',f.get('gross_margin'),f.get('prev_gross_margin')),('OPM',current_opm,prev_opm)]:
            if number(value) is not None and number(prev) is not None:evidence.append(f'{label} {prev} → {value}（{f.get("period")}）')
            else:risks.append(label+'資料未齊，該項不判多空')
        r=research.get(t,(None,{}))[1];researchscore=50
        if r:
            rating=str(r.get('rating') or '').lower()
            researchscore=75 if any(v in rating for v in ('buy','outperform','overweight','買進','優於')) else 25 if any(v in rating for v in ('sell','underperform','underweight','賣出')) else 50
            if r.get('target_price_action')=='downgrade':researchscore=max(0,researchscore-20)
            evidence.append(f'{r.get("broker","")} {r.get("date","")}：{r.get("rating") or "未評等"}；目標價動作 {r.get("target_price_action") or "未提供"}')
            risks.extend(str(x) for x in (r.get('risks') or [])[:2])
        else:risks.append('近30日無個股研究，研究項給中性分')
        fundamental=.75*fundamental+.25*researchscore
        chip=.35*flowrank.get(t,50)+.35*etfrank.get(t,50)+.20*holdrank.get(t,50)+.10*turnrank.get(t,50)
        momentum=.6*relrank.get(t,50)+.4*trendrank.get(t,50)
        if t in flows:evidence.append(f'法人／投信排行已知淨張數 {flows[t]/1000:+,.1f} 張（{day}）')
        else:risks.append('未列入法人完整資料／排行，方向未知')
        if t in etf:evidence.append(f'主動ETF當日持股淨變動估值 {etf[t]/10000:+,.0f} 萬元')
        if t in holders:evidence.append(f'400張以上持股比週變化 {holders[t]:+.2f} 百分點（{holderdate}）')
        else:risks.append('大戶排行未涵蓋，方向未知')
        evidence.append(f'近5日 {mom5[t]:+.2f}%／近20日 {mom20[t]:+.2f}%；同族群5日均值 {sector5[groups[t]]:+.2f}%')
        score=.4*chip+.4*fundamental+.2*momentum
        if mom5[t]>25:score-=10;risks.append('近5日漲幅逾25%，追價扣10分')
        liquid=(number(q.get('turnover')) or 0)>=10000000 and volume[t]>=100000
        eligible=liquid and score>=config['minimum_score'] and chip>=55 and fundamental>=50 and momentum>=45 and sum(v is not None for v in metrics)>=2
        ranked.append(dict(ticker=t,name=q.get('name') or master[t]['name'],market=master[t]['market'],score=round(score,2),
            pillars={'chip':round(chip,2),'fundamental':round(fundamental,2),'momentum':round(momentum,2)},eligible=eligible,
            evidence=evidence,risks=risks,etf_details=etf_evidence.get(t,[]),research_url=r.get('source_url'),financial_url=f.get('source_url'),sector=groups[t]))
    ranked.sort(key=lambda x:(-x['score'],x['ticker']))
    attempt.update(valid=not attempt['errors'],targets=[x for x in ranked if x['eligible']][:config['max_positions']],candidates=ranked[:30],
        sources={'market_date':day,'institutional_date':instdate,'holder_date':holderdate,'earnings_updated':earnings.get('updated_at'),'research_updated':reports.get('updated_at'),'etf_version':manifest.get('version')},
        model='既有AI研究結構化結果＋固定三面向規則；分數不是上漲機率')
    attempt['input_hash']=hashlib.sha256(json.dumps(attempt,ensure_ascii=False,sort_keys=True).encode()).hexdigest()
    return attempt


def run(root,now,preview=False):
    data=root/'data';config={**DEFAULTS,**read(root/'config/ai_portfolio.json')}
    if not 0<config['entry_weight']<=1/config['max_positions'] or config['max_positions']<1:raise ValueError('Invalid position limits')
    statepath=data/'ai_portfolio.json';state=read(statepath) if statepath.exists() else initial(config,now.isoformat(timespec='seconds'))
    if state.get('strategy')!=VERSION:raise ValueError('Strategy version mismatch; explicitly migrate, never reset performance')
    if state['config']!=config:raise ValueError('Live account configuration is immutable; use a new account/version for changes')
    # Replay ONLY actual missing sessions using stored decisions; never create old recommendations.
    latest=read(data/'market_latest.json');day=latest.get('date','')
    snapshots={}
    for folder in ('history/market','ai_market_snapshots'):
        for p in (data/folder).glob('*.json'):
            d=read(p)
            if d.get('date'):snapshots[d['date']]=d
    if day:snapshots[day]=latest
    all_tickers=set(state['positions'])|{x['ticker'] for d in state['decisions'] for x in d['targets']}
    candles={t:bars_for(data,t) for t in all_tickers}
    for date in sorted(snapshots):
        if date>now.date().isoformat() or now<stamp(date+'T13:30:00+08:00'):continue
        d=snapshots[date];bars={t:b.get(date) for t,b in candles.items()}
        closes={t:q.get('price') for t,q in d.get('stocks',{}).items()}
        session(state,date,bars,closes)
    protected=set(state['positions'])|{x['ticker'] for x in (state['decisions'][-1]['targets'] if state['decisions'] else [])}
    decision=proposal(data,config,now,protected)
    frozen_decision(state,decision)
    state['updated_at']=now.isoformat(timespec='seconds')
    state['status']='ready' if decision['valid'] else 'data_pending'
    state['limitations']=['這是向前追蹤的規則模擬，未重建歷史AI建議。','整數股數以普通交易開盤價代理零股成交，非真實零股撮合價。','含假設手續費、賣出稅及滑價；未自動計入股利、配股、減資等公司行動，淨值為價格損益口徑。','缺價沿用前次標記並提示；單一價日不假設成交。','晚到排程按實際產生時間決策，不倒填隔日已發生的開盤交易。']
    output=root/'preview' if preview else data
    write(output/'ai_portfolio.json',state)
    if not preview and day:write(data/'ai_market_snapshots'/(day+'.json'),latest)
    print(json.dumps({'preview':preview,'status':state['status'],'date':day,'published_targets':len(state['decisions'][-1]['targets']) if state['decisions'] else 0,'proposed_targets':len(decision['targets']),'positions':len(state['positions']),'trades':len(state['trades']),'errors':decision['errors'],'coverage':decision['coverage']},ensure_ascii=False))
    return state


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,default=ROOT);p.add_argument('--preview',action='store_true');args=p.parse_args()
    run(args.root,datetime.now(TZ),args.preview)
