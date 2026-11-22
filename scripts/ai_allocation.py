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

def _legacy_market_regime_for_compat(monitor,day,breadth):
    """Compatibility for older direct callers/tests; AI production always passes V12."""
    rows=sorted([r for r in monitor.get('rows',[]) if r.get('date','9999')<=day],key=lambda x:x['date'])
    valid=[r for r in rows if (number(r.get('index')) or 0)>0]
    if len(valid)<60 or valid[-1]['date']!=day:return dict(valid=False,label='大盤資料待補',target_exposure=0,reasons=['需要與選股同日的大盤監控及60日歷史'])
    closes=[r['index'] for r in valid];last=valid[-1];ma20=sum(closes[-20:])/20;ma60=sum(closes[-60:])/60
    ret5=100*(closes[-1]/closes[-6]-1);dd20=100*(closes[-1]/max(closes[-20:])-1)
    foreign=[number(r.get('foreign')) for r in valid[-5:]]
    if any(x is None for x in foreign):return dict(valid=False,label='大盤資料待補',target_exposure=0,reasons=['外資近5日資料不完整'])
    score=sum([closes[-1]>ma20,ma20>ma60,ret5>0,sum(foreign)>0,breadth>=.55])
    reds=sum(last.get(k)=='red' for k in ('foreign_light','margin_light'));score-=reds
    extreme=(dd20<=-20 or ret5<=-8) and closes[-1]<ma20 and closes[-1]<ma60 and 0<=breadth<=.20 and sum(foreign)<0
    if extreme:label,exposure='極度防禦',.20
    elif dd20<=-12 or last.get('intersection')=='red':label,exposure='高度防禦',.40
    elif closes[-1]<ma20 and closes[-1]<ma60:label,exposure='防禦',.55
    elif score>=4:label,exposure='積極',.90
    elif score>=2:label,exposure='均衡',.70
    else:label,exposure='防禦',.55
    return dict(valid=True,date=day,label=label,target_exposure=exposure,cash_floor=1-exposure,score=score,
        ma20=ma20,ma60=ma60,return5=ret5,drawdown20=dd20,breadth=breadth,reasons=[],
        note='Legacy compatibility only; not used in AI production execution')

def market_regime(monitor,day,breadth,v12=None):
    """Use the website's exact V12 result for AI production allocations.

    V12 is calculated by executing the site's own buildTwRisk JS, not by
    approximating its thresholds in Python. Only the risk-to-exposure mapping
    lives here, so future V12 changes remain shared by both views.
    """
    if v12 is None:
        return _legacy_market_regime_for_compat(monitor,day,breadth)
    rows=sorted([r for r in monitor.get('rows',[]) if r.get('date','9999')<=day],key=lambda x:x['date'])
    valid=[r for r in rows if (number(r.get('index')) or 0)>0]
    if len(valid)<60 or valid[-1]['date']!=day:
        return dict(valid=False,date=day,label='大盤資料待補',target_exposure=0,
                    reasons=['需要與選股同日的大盤監控及60日歷史'])
    if not isinstance(v12,dict) or not v12.get('valid') or v12.get('date')!=day or number(v12.get('score')) is None:
        return dict(valid=False,date=day,label='V12 風險待補',target_exposure=0,
                    reasons=['V12 綜合風險分數缺漏或與選股日期不一致，本次不發布新名單'])
    risk=float(v12['score'])
    level=v12.get('level')
    if type(level) is not int or level not in (0,1,2,3):
        return dict(valid=False,date=day,label='V12 風險待補',target_exposure=0,
                    reasons=['V12 燈號資料格式異常'])
    foreign=[number(r.get('foreign')) for r in valid[-5:]]
    if any(x is None for x in foreign):
        return dict(valid=False,date=day,label='大盤資料待補',target_exposure=0,
                    reasons=['外資近5日資料不完整'])
    closes=[r['index'] for r in valid]
    ma20=sum(closes[-20:])/20;ma60=sum(closes[-60:])/60
    ret5=100*(closes[-1]/closes[-6]-1)
    dd20=100*(closes[-1]/max(closes[-20:])-1)
    # Continuous cubic smoothstep: 0 risk -> 100%, risk >= 100 -> 0%.
    # There is no forced minimum allocation and no upper 90% ceiling.
    t=max(0.0,min(1.0,risk/100.0))
    exposure=round(max(0.0,min(1.0,1-(3*t*t-2*t*t*t))),6)
    labels=('綠燈','黃燈','橘燈','紅燈')
    levels=('積極','注意風險','防禦','高度防禦')
    label=levels[level]+' · '+labels[level]
    # Preserve the original 5-factor breadth score used by the ETF chip factor.
    # Do not replace regime['score'] with the V12 0-100 risk score.
    legacy_score=sum([closes[-1]>ma20,ma20>ma60,ret5>0,sum(foreign)>0,breadth>=.55])
    legacy_score-=sum(valid[-1].get(k)=='red' for k in ('foreign_light','margin_light'))
    reasons=[f'大盤綜合 V12：{risk:.1f} 分，{labels[level]}；建議持股 {exposure:.1%}、現金 {1-exposure:.1%}',
             f'指數 {closes[-1]:,.2f}；20日均線 {ma20:,.2f}；60日均線 {ma60:,.2f}',
             f'5日漲跌 {ret5:+.2f}%；距20日高點 {dd20:.2f}%；外資近5日 {sum(foreign):+.2f} 億',
             '持股曲線依 V12 原始分數連續換算，燈號變化不會造成固定級距跳躍']
    return dict(valid=True,date=day,label=label,target_exposure=exposure,cash_floor=1-exposure,
                score=legacy_score,risk_score=risk,risk_level=level,risk_light=labels[level],
                model='V12 JS 原始風險分數 + smoothstep 持股曲線 v2：0～100%',
                ma20=ma20,ma60=ma60,return5=ret5,drawdown20=dd20,breadth=breadth,
                reasons=reasons,note='持股水位0%～100%連續調整；V12 超過100分時建議0%（全現金），V12 為0分時建議100%。不設最低20%或最高90%限制；單檔與產業上限、2%調倉帶維持。此曲線尚未完成歷史績效最佳化；當日缺V12資料會暫停發布新名單。')

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
    # Conviction-only sizing. Volatility is diagnostic, not a mechanical penalty.
    strength={x['ticker']:max(1,x['score']-50)**2 for x in selected}
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
        x['weight']=w;x['allocation_reason']='資料尚待基本面確認，限制5%內' if x.get('discovery') else '依綜合分數及單檔／產業上限配置；不因高波動自動降權'
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
        x['allocation_reason']='依使用者最低20%投資部位規則，以已驗證的大盤ETF補足；不代表短線看多'
    out=[x for x in out if x['weight']>0]
    for x in out:x['weight']=round(x['weight'],8)
    return out,sum(x['weight'] for x in out)>=floor-1e-7

