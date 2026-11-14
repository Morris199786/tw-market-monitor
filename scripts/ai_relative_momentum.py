"""Point-in-time, same-session market and heatmap-peer relative momentum."""
import math
VERSION='relative-momentum-v1'
def tickers(rows):
    return {str(x.get('ticker')) if isinstance(x,dict) else str(x) for x in rows if x}

def sector_groups(config):
    groups=[]
    for sector in config.get('sectors',[]):
        name=str(sector.get('name','未命名族群'));parent=tickers(sector.get('stocks',[]));subs=sector.get('subgroups',[])
        for sub in subs:
            members=tickers(sub.get('tickers',sub.get('stocks',[])))
            if members:groups.append({'name':name+'／'+str(sub.get('name','')),'members':members,'depth':1})
        if parent:groups.append({'name':name,'members':parent,'depth':0})
    return sorted(groups,key=lambda g:(-g['depth'],g['name']))

def benchmark_returns(monitor,dates):
    prices={r.get('date'):r.get('index') for r in monitor.get('raw',[]) if r.get('date') in dates}
    out={}
    for days in (5,20):
        start,end=dates[-days-1],dates[-1]
        a,b=prices.get(start),prices.get(end)
        if not isinstance(a,(int,float)) or not isinstance(b,(int,float)) or not math.isfinite(a) or not math.isfinite(b) or min(a,b)<=0:
            raise ValueError(f'加權指數缺同期{days}日端點：{start}／{end}')
        out[days]=100*(b/a-1)
    return out

def relative_score(excess,days):
    # 50 means matching the benchmark; both sign and magnitude matter.
    return 50+50*math.tanh(excess/(5 if days==5 else 10))

def momentum(ticker,returns,market,groups):
    horizons={};evidence=[]
    for days in (5,20):
        own=returns[days][ticker];market_return=market[days];excess=own-market_return
        usable=[]
        for group in groups:
            if ticker not in group['members']:continue
            peers=group['members']-{ticker};known=sorted(peers.intersection(returns[days]))
            if len(known)>=3 and len(known)/max(1,len(peers))>=.70:
                usable.append((group,sum(returns[days][x] for x in known)/len(known),len(known),len(peers)))
        if usable:
            depth=max(x[0]['depth'] for x in usable);usable=[x for x in usable if x[0]['depth']==depth]
            # Equal weight across explicit overlapping groups; never select the
            # easiest peer group after seeing performance.
            peer_return=sum(x[1] for x in usable)/len(usable)
            score=.60*relative_score(excess,days)+.40*relative_score(own-peer_return,days)
            peer_info=[{'name':g['name'],'return':r,'known':n,'total':total} for g,r,n,total in usable]
        else:peer_return=None;score=relative_score(excess,days);peer_info=[]
        horizons[days]={'stock_return':own,'market_return':market_return,'market_excess_pp':excess,'peer_return':peer_return,'peer_excess_pp':None if peer_return is None else own-peer_return,'groups':peer_info,'score':score}
        text=f'相對動能{days}日：個股{own:+.2f}%／加權指數{market_return:+.2f}%，超額{excess:+.2f}百分點'
        if peer_return is None:text+='；無足夠可核對族群，全部以同期大盤比較'
        else:text+=f'；同族群等權平均{peer_return:+.2f}%，超額{own-peer_return:+.2f}百分點（排除自身；'+ '、'.join(f'{x["name"]} {x["known"]}/{x["total"]}檔' for x in peer_info)+'）'
        evidence.append(text)
    return {'score':.60*horizons[5]['score']+.40*horizons[20]['score'],'horizons':{str(k):v for k,v in horizons.items()},'evidence':evidence,'benchmark':'台灣加權指數','version':VERSION}
