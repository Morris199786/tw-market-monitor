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

def fundamentals(t,row,official,opm,reports,now,calendar,content_cache=None):
    from ai_signal_model import quarter_signal,research_signal,weighted,clip
    row=row or {};evidence=[];risks=[];ages={}
    age=age_days(row.get('publish_date'),now,calendar)
    vals,quality,trend,ev,ri=quarter_signal(row,opm,t)
    financial_valid=age is not None and sum(vals[k] is not None for k in ('eps','gross_margin','operating_margin'))>=2 and (now.date()-stamp(row['publish_date']+'T00:00:00+08:00').date()).days<=150
    use_quarter=financial_valid
    if financial_valid:
        evidence+=ev;risks+=ri
        durable=.25*quality+.75*trend
        event=50+(trend-50)*decay(age,5)
        fin=.8*durable+.2*event
        ages.update(earnings_sessions=age,earnings_event_weight=round(decay(age,5),3))
        evidence.append('財務核心以季比較為主：持續性分數75%季變化／25%獲利狀態；EPS30%、毛利率30%、OPM40%交叉判讀')
    else:
        off=official or {};fresh=False
        try:
            year,quarter=off.get('period','').split('-Q');month=int(quarter)*3
            end=date(int(year),month,cal.monthrange(int(year),month)[1])
            fresh=stamp(off['observed_at'])<=now and (now-stamp(off['observed_at'])).days<=14 and 0<=(now.date()-end).days<=180
        except (KeyError,ValueError,TypeError):pass
        metrics=[]
        if fresh:
            for k,label in [('eps','EPS'),('gross_margin','GM'),('operating_margin','OPM')]:
                v=number(off.get(k))
                if v is not None:
                    metrics.append(clip(50+12*math.copysign(math.log1p(abs(v)),v)) if k=='eps' else clip(50+v*1.5))
                    evidence.append(f'官方 {off.get("period")} 累計 {label} {v:.2f}（非單季）')
        financial_valid=len(metrics)>=2
        fin=50+.30*(average(metrics)-50) # no fictitious QoQ from YTD numbers
        risks.append('缺少可驗證單季比較，累計數據僅作低權重獲利狀態，不能宣稱季成長')
    research=research_signal(reports,content_cache or {},now,calendar)
    evidence+=research['evidence'];risks+=research['risks']
    return dict(score=.60*fin+.40*research['score'],verified=financial_valid,evidence=evidence,risks=risks,freshness=ages,
        research_count=research['count'],research_missing=research['missing'],research_details=research['details'],
        financial_score=fin,research_score=research['score'],basis='single_quarter' if use_quarter else 'official_ytd_or_unknown')

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
