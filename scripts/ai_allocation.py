"""Explainable market regime, time decay and constrained conviction allocation."""
import math
import calendar as cal
from datetime import date
from ai_portfolio_engine import number,stamp

def decay(age,half_life):return 2**(-max(0,age)/half_life)
def age_days(date,now,calendar):
    date=str(date)[:10]
    if not date or date>now.date().isoformat():return None
    return sum(date<d<=now.date().isoformat() for d in calendar)
def comparison(a,b,floor):
    a,b=number(a),number(b)
    return None if a is None or b is None else max(0,min(100,50+50*(a-b)/max(abs(b),floor)))
def average(vals,default=50):
    vs=[v for v in vals if v is not None];return sum(vs)/len(vs) if vs else default

def market_regime(monitor,day,breadth):
    rows=sorted([r for r in monitor.get('rows',[]) if r.get('date','9999')<=day],key=lambda x:x['date'])
    valid=[r for r in rows if (number(r.get('index')) or 0)>0]
    if len(valid)<60 or valid[-1]['date']!=day:return dict(valid=False,label='大盤資料待補',target_exposure=0,reasons=['需要與選股同日的大盤監控及60日歷史'])
    closes=[r['index'] for r in valid];last=valid[-1];ma20=sum(closes[-20:])/20;ma60=sum(closes[-60:])/60
    ret5=100*(closes[-1]/closes[-6]-1);dd20=100*(closes[-1]/max(closes[-20:])-1)
    foreign=[number(r.get('foreign')) for r in valid[-5:]]
    if any(x is None for x in foreign):return dict(valid=False,label='大盤資料待補',target_exposure=0,reasons=['外資近5日資料不完整'])
    score=sum([closes[-1]>ma20,ma20>ma60,ret5>0,sum(foreign)>0,breadth>=.55])
    reds=sum(last.get(k)=='red' for k in ('foreign_light','margin_light'));score-=reds
    reasons=[f'指數 {closes[-1]:,.2f}；20日均線 {ma20:,.2f}；60日均線 {ma60:,.2f}',
        f'5日漲跌 {ret5:+.2f}%；距20日高點 {dd20:.2f}%',f'上漲廣度 {breadth:.1%}；外資5日合計 {sum(foreign):+.2f} 億',
        f'監控燈號：外資 {last.get("foreign_light")}／融資 {last.get("margin_light")}／交集 {last.get("intersection")}']
    if dd20<=-12 or last.get('intersection')=='red':label,exposure='高度防禦',.40
    elif closes[-1]<ma20 and closes[-1]<ma60:label,exposure='防禦',.55
    elif score>=4:label,exposure='積極',.90
    elif score>=2:label,exposure='均衡',.70
    else:label,exposure='防禦',.55
    return dict(valid=True,date=day,label=label,target_exposure=exposure,cash_floor=1-exposure,score=score,
        ma20=ma20,ma60=ma60,return5=ret5,drawdown20=dd20,breadth=breadth,reasons=reasons,
        note='透明固定規則，未經績效最佳化；個股不足時用可驗證的大盤ETF補足最低40%；無法驗證時保留前次決策，不假設成交')

def fundamentals(t,row,official,opm,reports,now,calendar):
    evidence=[];risks=[];ages={};report=row or {};age=age_days(report.get('publish_date'),now,calendar)
    comparable=[];quality=[]
    for key,label,scale in [('eps','EPS',.1),('gross_margin','GM',1),('operating_margin','OPM',1)]:
        cur=report.get(key);prev=report.get('prev_'+key)
        if key=='operating_margin':
            cur=opm.get(t+'|'+report.get('period',''),{}).get('value',cur)
            prev=opm.get(t+'|'+report.get('prev_period',''),{}).get('value',prev)
        v=number(cur);c=comparison(cur,prev,scale)
        if c is not None:comparable.append(c)
        if v is not None:
            quality.append((70 if v>0 else 30) if key=='eps' else max(0,min(100,50+v*1.5)))
            evidence.append(f'{report.get("period","")} 單季 {label}：{prev if prev is not None else "待補"} → {cur}')
            if v<0:risks.append(f'本季{label}為負，不能只憑改善就當作已獲利')
    financial_valid=age is not None and len(quality)>=2 and (now.date()-stamp(report['publish_date']+'T00:00:00+08:00').date()).days<=150
    use_quarter=financial_valid
    if financial_valid:
        durable=.55*average(quality)+.45*average(comparable)
        surprise=average(comparable);event=50+(surprise-50)*decay(age,5)
        fin=.8*durable+.2*event;ages['earnings_sessions']=age;ages['earnings_event_weight']=round(decay(age,5),3)
        evidence.append(f'財報距今 {age} 交易日；事件效力半衰期5日，營運品質延續至新財報（最長150日）')
    else:
        # Official market-wide financials are cumulative and labelled as such.
        off=official or {};observed=off.get('observed_at');fresh=False
        if observed:
            try:
                year,quarter=off.get('period','').split('-Q');month=int(quarter)*3
                end=date(int(year),month,cal.monthrange(int(year),month)[1])
                fresh=stamp(observed)<=now and (now-stamp(observed)).days<=14 and 0<=(now.date()-end).days<=180
            except (ValueError,TypeError):pass
        offq=[]
        if fresh:
            for key,label in [('eps','EPS'),('gross_margin','GM'),('operating_margin','OPM')]:
                v=number(off.get(key))
                if v is not None:
                    offq.append((70 if v>0 else 30) if key=='eps' else max(0,min(100,50+v*1.5)))
                    evidence.append(f'官方 {off.get("period")} 累計 {label} {v:.2f}（非單季）')
        financial_valid=len(offq)>=2
        fin=average(offq)
        if offq:risks.append('官方全市場資料為累計口徑，首次取得日期不當成財報公告事件日期')
        else:risks.append('基本面資料不足，不能宣稱營運已改善')
    # Latest report per broker wins, so fresh downgrades replace old bullish calls.
    brokers={}
    for r in reports:
        received=r.get('received_at') or (r.get('group_date') or r.get('date',''))+'T23:59:59+08:00'
        try:when=stamp(received)
        except (TypeError,ValueError):continue
        if when>now or (now-when).days>90:continue
        broker=r.get('broker') or 'unknown';previous=brokers.get(broker)
        if not previous or (when,str(r.get('id','')))> (previous[0],str(previous[1].get('id',''))):brokers[broker]=(when,r)
    values=[]
    for when,r in sorted(brokers.values(),key=lambda x:(x[0],str(x[1].get('broker','')),str(x[1].get('id',''))),reverse=True)[:3]:
        sessions=age_days(when.date().isoformat(),now,calendar);rating=str(r.get('rating') or '').lower()
        base=75 if any(x in rating for x in ('buy','overweight','outperform','買進','優於')) else 25 if any(x in rating for x in ('sell','underweight','underperform','賣出')) else 50
        if r.get('target_price_action')=='downgrade':base-=20
        if r.get('action')=='downgrade':base=min(base,35)
        durable=50+(base-50)*decay(sessions,30)
        event=50+(base-50)*decay(sessions,5)
        values.append(.75*durable+.25*event)
        evidence.append(f'{r.get("broker","")} {r.get("date","")} {r.get("rating") or "未評等"}，距收到 {sessions} 交易日；目標價動作 {r.get("target_price_action") or "未提供"}')
        points=r.get('key_points') or ([r.get('summary')] if r.get('summary') else [])
        if isinstance(points,str):points=[points]
        evidence.extend('研究重點（原摘要）：'+str(x)[:240] for x in points[:2])
        risks.extend(str(x) for x in (r.get('risks') or [])[:1])
    if not values:risks.append('近90日無個股研究，研究因子中性，不限制股票池')
    return dict(score=.8*fin+.2*average(values),verified=financial_valid,evidence=evidence,risks=risks,freshness=ages,
        research_count=len(values),basis='single_quarter' if use_quarter else 'official_ytd_or_unknown')

def allocate(candidates,exposure,cfg):
    selected=[dict(x) for x in candidates if x.get('eligible')][:cfg['max_positions']]
    weights={x['ticker']:0 for x in selected}
    # Conviction adjusted for historical volatility. No assumed expected returns.
    strength={x['ticker']:max(1,x['score']-50)**2/max(1,x.get('volatility',2)) for x in selected}
    for _ in range(80):
        remaining=exposure-sum(weights.values())
        if remaining<1e-8:break
        room={}
        for x in selected:
            t=x['ticker'];cap=cfg['max_etf_weight'] if x['asset_type']=='etf' else cfg['max_stock_weight']
            if x.get('discovery'):cap=min(cap,cfg['discovery_weight'])
            sector=x.get('sector','unknown');used=sum(weights[y['ticker']] for y in selected if y.get('sector','unknown')==sector)
            sector_room=cfg['max_sector_weight']-used if x['asset_type']=='stock' else .50-sum(weights[y['ticker']] for y in selected if y['asset_type']=='etf')
            r=min(cap-weights[t],sector_room)
            if r>1e-9:room[t]=r
        if not room:break
        total=sum(strength[t] for t in room);progress=0
        for x in selected:
            t=x['ticker']
            if t not in room:continue
            sector=x.get('sector','unknown')
            sector_room=(cfg['max_sector_weight']-sum(weights[y['ticker']] for y in selected if y.get('sector','unknown')==sector)) if x['asset_type']=='stock' else (.50-sum(weights[y['ticker']] for y in selected if y['asset_type']=='etf'))
            addition=max(0,min(room[t],sector_room,remaining*strength[t]/total))
            weights[t]+=addition;progress+=addition
        if progress<1e-10:break
    out=[]
    for x in selected:
        w=math.floor(weights[x['ticker']]*1e6)/1e6
        if w<=0:continue
        x['weight']=w;x['allocation_reason']='資料尚待基本面確認，限制5%內' if x.get('discovery') else '依綜合分數、波動及單檔／產業上限配置'
        out.append(x)
    return out


def ensure_floor(targets,core,cfg):
    """Minimum is an explicit user allocation constraint, not an invented fill."""
    out=[dict(x) for x in targets];floor=cfg['min_exposure']
    def room(x):
        cap=cfg['max_etf_weight'] if x['asset_type']=='etf' else cfg['max_stock_weight']
        if x.get('discovery'):cap=min(cap,cfg['discovery_weight'])
        group_room=.50-sum(y['weight'] for y in out if y['asset_type']=='etf') if x['asset_type']=='etf' else cfg['max_sector_weight']-sum(y['weight'] for y in out if y['asset_type']=='stock' and y['sector']==x['sector'])
        return max(0,min(cap-x['weight'],group_room))
    if sum(x['weight'] for x in out)>=floor:return out,True
    # Rounding and minor cap shortfalls: first use already qualified names.
    for x in out:
        gap=floor-sum(y['weight'] for y in out)
        if gap<=1e-8:return out,True
        add=min(room(x),gap);x['weight']+=add
    for candidate in core:
        if sum(x['weight'] for x in out)>=floor-1e-8:break
        x=next((x for x in out if x['ticker']==candidate['ticker']),None)
        if x is None:
            if len(out)>=cfg['max_positions']:
                removable=[y for y in out if y['asset_type']=='stock']
                if not removable:continue
                out.remove(min(removable,key=lambda y:y['score']))
            x=dict(candidate,weight=0);out.append(x)
        gap=floor-sum(y['weight'] for y in out);x['weight']+=min(room(x),max(0,gap))
        x['allocation_reason']='依使用者最低40%投資部位規則，以已驗證的大盤ETF補足；不代表短線看多'
    out=[x for x in out if x['weight']>0]
    for x in out:x['weight']=round(x['weight'],8)
    return out,sum(x['weight'] for x in out)>=floor-1e-7
