"""Deterministic financial, monthly-disclosure and research aggregation rules."""
import math,re
from datetime import date
from ai_portfolio_engine import number,stamp
from ai_content_research import selected,document,validate,content_score,meeting,dated

def clip(x,lo=0,hi=100):return max(lo,min(hi,x))
def decay(age,half):return 2**(-max(0,age)/half)
def weighted(items,default=50):
    usable=[(v,w) for v,w in items if v is not None]
    return sum(v*w for v,w in usable)/sum(w for v,w in usable) if usable else default

def mixed_flow_score(values,caps,directional):
    absolute=directional(values)
    relative=directional({t:v/caps[t] for t,v in values.items() if caps.get(t,0)>0})
    return {t:.5*absolute[t]+.5*relative.get(t,50) for t in values}

def quarter_signal(row,opm,ticker):
    vals={k:number(row.get(k)) for k in ('eps','gross_margin','operating_margin','prev_eps','prev_gross_margin','prev_operating_margin')}
    for prefix,period in [('',row.get('period')),('prev_',row.get('prev_period'))]:
        value=number(opm.get(ticker+'|'+str(period),{}).get('value'))
        if value is not None:vals[prefix+'operating_margin']=value
    changes={};evidence=[];risks=[]
    for k,label in [('eps','EPS'),('gross_margin','毛利率'),('operating_margin','OPM')]:
        a,b=vals[k],vals['prev_'+k]
        if a is not None:evidence.append(f'{row.get("period","")} 單季 {label}：{b if b is not None else "待補"} → {a}')
        if a is not None and b is not None:
            changes[k]=clip(50+50*(a-b)/max(abs(b),.25)) if k=='eps' else clip(50+8*(a-b))
    epschange=changes.get('eps');margin=[changes[k] for k in ('gross_margin','operating_margin') if k in changes]
    if epschange is not None and len(margin)==2:
        if epschange<50 and all(x>=50 for x in margin):
            changes['eps']=max(42,50+(epschange-50)*.25)
            risks.append('EPS季減但毛利率與OPM未惡化：降低EPS扣分；業外／稅率／股數等原因待確認，不直接認定業外')
        elif epschange>50 and all(x<50 for x in margin):
            changes['eps']=min(60,50+(epschange-50)*.35)
            risks.append('EPS季增但兩項本業利率下降：限制EPS加分，避免一次性獲利掩蓋本業轉弱')
    # EPS magnitude is no longer a positive/negative switch; QoQ dominates.
    eps=vals['eps'];eps_quality=None if eps is None else clip(50+12*math.copysign(math.log1p(abs(eps)),eps))
    quality=weighted([(eps_quality,.25),(None if vals['gross_margin'] is None else clip(50+vals['gross_margin']*1.5),.30),(None if vals['operating_margin'] is None else clip(50+vals['operating_margin']*1.5),.45)])
    trend=weighted([(changes.get('eps'),.30),(changes.get('gross_margin'),.30),(changes.get('operating_margin'),.40)])
    for k,label in [('eps','EPS'),('gross_margin','毛利率'),('operating_margin','OPM')]:
        a,b=vals[k],vals['prev_'+k]
        if a is not None and b is not None:
            text=f'{(a-b)/max(abs(b),.25)*100:+.2f}%（前期為零／接近零時採0.25元分母下限）' if k=='eps' else f'{a-b:+.2f}百分點'
            evidence.append(f'{label}季變化 {text}')
        if a is not None and a<0:risks.append(f'本季{label}為負，改善不等於已獲利')
    return vals,quality,trend,evidence,risks

def research_signal(rows,cache,now,calendar):
    choices=selected(rows,now);groups={'broker':[],'meeting':[]};details=[];missing=[];evidence=[];risks=[]
    for r in choices:
        key,doc=document(r,cache.get('model','gpt-5.6-luna'));entry=cache.get('items',{}).get(key,{})
        if entry.get('status')!='complete':missing.append(key);continue
        try:result=validate(entry['result'],doc)
        except (ValueError,KeyError,TypeError):missing.append(key);continue
        age=sum(dated(r)<d<=now.date().isoformat() for d in calendar)
        raw=content_score(result);fresh=decay(age,30);event=decay(age,5)
        score=50+(raw-50)*(.75*fresh+.25*event)
        kind='meeting' if meeting(r) else 'broker';groups[kind].append((score,fresh))
        details.append({'kind':kind,'source':doc['source'],'date':doc['date'],'score':round(score,2),'weight':round(fresh,4),'content_key':key,'dimensions':result['dimensions'],'summary':result['summary']})
        evidence.append(f'{"最新法說／訪談" if kind=="meeting" else "券商內容"}｜{doc["source"]} {doc["date"]}：{result["summary"]}')
        for name,d in result['dimensions'].items():
            label={'demand':'需求／訂單','profitability':'本業獲利','outlook':'展望／財測','catalyst':'具體催化','risk':'風險'}[name]
            if d['value']:evidence.append(f'內容依據 {label} {d["value"]:+d}／信心{d["confidence"]:.0%}：「{d["quote"]}」；{d["reason"]}')
        if result['one_off']!='none':risks.append('研究原文涉及一次性獲利：'+('有明確描述' if result['one_off']=='confirmed' else '仍待確認'))
    # Fixed category weights prevent broker count / duplicate management claims inflation.
    broker=weighted(groups['broker']);memo=weighted(groups['meeting'])
    score=.60*broker+.40*memo
    if not choices:risks.append('近90日沒有可對應研究內容，研究因子維持中性')
    if missing:risks.append(f'{len(missing)}份最新研究內容尚未完成AI判讀，不以評等或舊法說代替')
    positive=[x for x in details if x['score']>=55];negative=[x for x in details if x['score']<=45]
    if positive and negative:risks.append('最新研究來源存在多空分歧，逐來源保留判斷，不以多數票蓋過風險')
    return dict(score=score,count=len(details),selected=len(choices),missing=missing,details=details,evidence=evidence,risks=risks)

def monthly_bonus(t,items,quarters,now,calendar):
    usable=[]
    for r in items:
        if str(r.get('ticker'))!=t or number(r.get('monthly_eps')) is None:continue
        try:
            published=str(r['publish_date']);at=stamp(published+'T'+(r.get('publish_time') or '23:59:59')+'+08:00')
            period=str(r['monthly_period']);month=date.fromisoformat(period+'-01')
            lag=(now.year-month.year)*12+now.month-month.month
            if at>now or not 0<=(now-at).days<=45 or not 0<=lag<=2:continue
        except (ValueError,KeyError,TypeError):continue
        usable.append(r)
    if not usable:return dict(bonus=0,evidence=[],risks=[])
    r=max(enumerate(usable),key=lambda pair:(pair[1]['monthly_period'],pair[1]['publish_date'],pair[1].get('publish_time',''),pair[0]))[1]
    year,month=map(int,r['monthly_period'].split('-'));q=(month-1)//3+1
    baseline=f'{year-1}-Q4' if q==1 else f'{year}-Q{q-1}'
    prior=quarters.get((t,baseline),{});base=number(prior.get('eps'))
    # The announcement's quarter EPS is only used when the period matches exactly.
    if base is None and r.get('quarter_period')==baseline:base=number(r.get('quarter_eps'))
    if base is None or base<=0:
        return dict(bonus=0,evidence=[],risks=[f'單月自結{r["monthly_period"]}已讀取，但前一季{baseline} EPS非正或缺值，不用失真比例加分'])
    eps=number(r['monthly_eps']);ratio=eps/base;age=sum(r['publish_date']<d<=now.date().isoformat() for d in calendar)
    # Previous-quarter EPS x 120% / 3 = 40% of quarter EPS.
    # Strictly above the threshold; use a tolerance for floating point equality.
    excess=0 if ratio<=.40+1e-12 else ratio-.40
    bonus=round(clip(excess/.60,0,1)*4*decay(age,10),8)
    return dict(bonus=bonus,evidence=[f'自結加分 +{bonus:.2f}總分：{r["monthly_period"]} 單月EPS {eps:g} ÷ 前季{baseline} EPS {base:g}＝{ratio:.1%}；高於前季EPS×120%÷3（40%）才加分，不外推整季'],risks=['單月自結可能含業外，屬加分線索；無公布或不達門檻不扣分'])
