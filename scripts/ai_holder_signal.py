"""Weekly holder changes: publication-aware freshness and price confirmation."""
from datetime import datetime,timedelta
from ai_portfolio_engine import stamp
WEIGHTS=(1,.8,.55,.35,.2,.1,.05)

def publication(holder):
    """Never use a refreshed fetch timestamp as a new weekly publication."""
    observed=datetime.strptime(holder['date'],'%Y%m%d').date()
    scheduled=observed+timedelta(days=(5-observed.weekday())%7)
    if scheduled==observed and observed.weekday()!=5:scheduled+=timedelta(days=7)
    for key in ('published_at','available_at'):
        if holder.get(key):
            try:
                at=stamp(holder[key])
                if at.date()>=observed:return at,'source_timestamp'
            except (ValueError,TypeError):pass
    return stamp(scheduled.isoformat()+'T15:00:00+08:00'),'estimated_saturday_1500'

def confirmation(ticker,published,day,calendar,history,market,groups):
    # Exactly matching dates; never compress missing sessions or use pre-release moves.
    after=[d for d in calendar if published.date().isoformat()<=d<=day and stamp(d+'T13:30:00+08:00')>published]
    before=[d for d in calendar if stamp(d+'T13:30:00+08:00')<=published]
    if not before or not after:return dict(multiplier=1,status='等待公布後走勢',sessions=len(after))
    start=before[-1];dates=[start]+after;own=history.get(ticker,{})
    if any(not own.get(d,{}).get('close') or not market.get(d) for d in dates):
        return dict(multiplier=.5,status='公布後比較資料不足，正面加分暫減半',sessions=len(after))
    valid=[]
    for g in groups:
        if ticker not in g['members']:continue
        peers=g['members']-{ticker}
        known=[t for t in sorted(peers) if all(history.get(t,{}).get(d,{}).get('close') for d in dates)]
        if len(known)>=3 and len(known)/max(1,len(peers))>=.7:valid.append((g,known))
    if valid:
        depth=max(g['depth'] for g,ts in valid);valid=[(g,ts) for g,ts in valid if g['depth']==depth]
    relative=[];daily=[];prev=start
    for d in after:
        ownret=100*(own[d]['close']/own[start]['close']-1)
        bench=100*(market[d]/market[start]-1)
        if valid:
            peer=sum(sum(100*(history[t][d]['close']/history[t][start]['close']-1) for t in ts)/len(ts) for g,ts in valid)/len(valid)
            bench=.6*bench+.4*peer
        relative.append(ownret-bench)
        daily_own=100*(own[d]['close']/own[prev]['close']-1)
        daily_bench=100*(market[d]/market[prev]-1)
        if valid:
            daily_peer=sum(sum(100*(history[t][d]['close']/history[t][prev]['close']-1) for t in ts)/len(ts) for g,ts in valid)/len(valid)
            daily_bench=.6*daily_bench+.4*daily_peer
        daily.append(daily_own-daily_bench);prev=d
    excess=relative[-1];multiplier=1;status='尚無持續轉弱確認'
    # Two consecutive daily underperformances plus a cumulative threshold.
    if len(relative)>=2 and all(x<0 for x in daily[-2:]) and excess<=-3+1e-9:
        multiplier=.5;status='連續兩日落後且累計落後至少3百分點'
    first_lows=[own[d].get('low') for d in after[:2]]
    if len(after)>=3 and all(x is not None and x>0 for x in first_lows) and excess<=-5+1e-9 and own[day]['close']<min(first_lows):
        multiplier=0;status='落後至少5百分點且跌破前兩日低點，正面訊號失效'
    return dict(multiplier=multiplier,status=status,sessions=len(after),excess_pp=round(excess,4),
        benchmark='同期大盤60%＋族群40%' if valid else '同期加權指數',start=start,end=day,
        peers=[g['name'] for g,ts in valid])

def holder_signal(ticker,tier_scores,holder,now,day,calendar,history,market,groups):
    at,method=publication(holder)
    if at>now:return dict(score=50,published_at=at.isoformat(),publication_method=method,weight=0,
        status='尚未到公布時間，不使用未公布資料',sessions=0,confirmation_multiplier=1)
    elapsed=sum(at<stamp(d+'T13:30:00+08:00')<=now for d in calendar if d<=day)
    # Before the first post-publication close, full weight is valid for the next open.
    weight=WEIGHTS[max(0,elapsed-1)] if elapsed<=len(WEIGHTS) else 0
    check=confirmation(ticker,at,day,calendar,history,market,groups)
    adjusted=[50+(v-50)*weight*(check['multiplier'] if v>50 else 1) for v in tier_scores]
    return dict(score=sum(adjusted)/len(adjusted),published_at=at.isoformat(),publication_method=method,
        weight=weight,sessions=elapsed,confirmation_multiplier=check['multiplier'],status=check['status'],price_confirmation=check)
