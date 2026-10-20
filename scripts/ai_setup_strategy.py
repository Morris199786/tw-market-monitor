"""Deterministic accumulation/setup scoring. No LLM calls or future bars."""
from statistics import mean
import math

STRATEGY = 'ACCUMULATION_SETUP_EPS_V1'
NAME = '籌碼改善＋整理型態'
WEIGHTS = {'法人買超占市值':15, '法人買超占成交額':10, '買盤持續性':10,
           '買盤改善':10, '整理型態':20, 'K線承接':15, '均線止跌':10, '支撐距離':10}
MIN_SCORE = 55
MIN_TURNOVER = 20_000_000

def number(x):
    try:
        v = float(str(x).replace(',', ''))
        return v if math.isfinite(v) else None
    except (ValueError, TypeError): return None

def clamp(v, a=0., b=1.): return max(a, min(b, v))
def clv(b):
    return (b['close']-b['low'])/(b['high']-b['low']) if b['high']>b['low'] else .5

def volume_penalty(bars, support):
    """Worst current-day condition + prior weak distribution; capped, no stacking."""
    b, prev = bars[-1], bars[-2]
    avg = mean(x['volume'] for x in bars[-21:-1])
    vr = b['volume']/avg if avg>0 else 0
    pos = clv(b)
    p = 0
    if vr>=2 and pos<.4: p=5
    if vr>=3 and pos<.25 and b['close']<prev['close']: p=10
    if vr>=2 and b['close']<support: p=15
    # Strong closes are exempt from today's volume penalty, not from overheating.
    if pos>=.8 and b['close']>max(b['open'],prev['close']): p=0
    weak = 0
    for i in range(len(bars)-5, len(bars)-1):
        avg = mean(x['volume'] for x in bars[i-20:i])
        if avg>0 and bars[i]['volume']/avg>=2 and clv(bars[i])<.4 and bars[i]['close']<bars[i-1]['close']:
            weak += 1
    return min(20, p + (5 if weak>=2 else 0)), vr

def features(bars, flows, snapshots, shares):
    """Inputs aligned to market calendar; caller validates OHLC and exact dates."""
    if len(bars)<40 or len(flows)!=10 or len(snapshots)!=10: return None, '資料不足'
    if shares is None or shares<=0: return None, '缺公司股數'
    c=[b['close'] for b in bars]; b=bars[-1]
    if mean(number(x.get('turnover')) or 0 for x in snapshots[-5:])<MIN_TURNOVER:
        return None, '流動性不足'
    amounts=[]; turnovers=[]
    for inst, q in zip(flows, snapshots):
        values=[number(inst.get(k)) for k in ('foreign','trust','dealer')]
        price, turnover=number(q.get('price')),number(q.get('turnover'))
        if any(v is None for v in values) or price is None or price<=0 or turnover is None or turnover<=0:
            return None, '法人或成交資料缺漏'
        amounts.append(sum(values)*price); turnovers.append(turnover)
    net=sum(amounts[-5:]); flow=net/sum(turnovers[-5:])*100
    oldflow=sum(amounts[:5])/sum(turnovers[:5])*100
    ma20=mean(c[-20:]); old20=mean(c[-25:-5]); ma10=mean(c[-10:]); old10=mean(c[-15:-5])
    atr=mean(max(bars[i]['high']-bars[i]['low'],abs(bars[i]['high']-c[i-1]),abs(bars[i]['low']-c[i-1])) for i in range(len(bars)-14,len(bars)))
    if atr<=0: return None,'波動資料無效'
    # Do not reward a stock merely for falling or for having less net selling.
    if net<=0 or not any(x>0 for x in amounts[-3:]): return None,'近期無累積買盤'
    range_old=mean(x['high']-x['low'] for x in bars[-15:-5])
    range_new=mean(x['high']-x['low'] for x in bars[-5:])
    vol_old=mean(x['volume'] for x in bars[-15:-5]); vol_new=mean(x['volume'] for x in bars[-5:])
    recentlow=min(x['low'] for x in bars[-5:]); priorlow=min(x['low'] for x in bars[-15:-5])
    prior_support=min(x['low'] for x in bars[-11:-1])
    if c[-1]<prior_support: return None,'收盤跌破既有支撐'
    # Score ONE setup, never sum multiple descriptions of the same consolidation.
    setups=[]
    if range_old>0 and vol_old>0 and range_new<=.8*range_old and vol_new<=.85*vol_old and recentlow>=priorlow and ma20>=old20*.99:
        quality=clamp((1-range_new/range_old)/.5)
        setups.append((12+8*quality,'量縮收斂、低點墊高',prior_support))
    # Support MA is calculated before today's candle, not moved by today's close.
    support_ma=mean(c[-21:-1])
    if ma20>=old20*.995 and b['low']<=support_ma+.5*atr and c[-1]>=support_ma and clv(b)>=.6 and vol_new<=vol_old:
        setups.append((14+6*clamp((clv(b)-.6)/.4),'量縮回測後收回',min(prior_support,support_ma)))
    # Two troughs separated by >=5 sessions, second at least two sessions old.
    first=min(range(len(bars)-30,len(bars)-15),key=lambda i:bars[i]['low'])
    second=min(range(len(bars)-10,len(bars)-2),key=lambda i:bars[i]['low'])
    a,z=bars[first],bars[second]
    if second-first>=5 and abs(z['low']-a['low'])<=atr and z['volume']<a['volume'] and c[-1]>z['high'] and flow>oldflow:
        setups.append((16,'二次測底、賣壓減輕',min(a['low'],z['low'])))
    if not setups: return None,'尚無合格整理型態'
    pattern,tag,support=max(setups,key=lambda x:x[0])
    risk=(c[-1]-support)/c[-1]*100
    if risk<=0 or risk>10: return None,'距離型態支撐過遠'
    span=b['high']-b['low']; lower=min(b['open'],b['close'])-b['low']
    wick=lower/span if span>0 else 0
    confirmation=max(10*clamp((clv(b)-.5)/.5),
                     10 if wick>=.4 and clv(b)>=.6 and b['low']<=support+atr else 0)
    if c[-1]>b['open'] and c[-1]>c[-2] and clv(b)>=.7: confirmation=min(15,confirmation+5)
    slope=5*clamp((ma20/old20-1+.01)/.02)+5*clamp((ma10/old10-1+.01)/.02)
    proximity=10*clamp((10-risk)/8)
    r5=(c[-1]/c[-6]-1)*100
    volume,vr=volume_penalty(bars,support)
    heat=max(min(15,max(0,r5-10)),min(15,5*max(0,(c[-1]-ma20)/atr-2)))
    # Combined maximum 30, with volume penalty preserved first.
    heat=min(heat,30-volume)
    return {'cap_flow':net/(shares*c[-1])*100,'flow':flow,'accel':flow-oldflow,
            'buy_days':sum(x>0 for x in amounts[-5:]),'pattern':pattern,'tag':tag,
            'confirmation':confirmation,'slope':slope,'proximity':proximity,
            'volume_penalty':volume,'heat_penalty':heat,'support':support,'risk_pct':risk,
            'r5':r5,'atr':atr,'volume_ratio':vr,'close':c[-1]},None

def positive_ranks(rows,key):
    vals=sorted(r[key] for r in rows if r[key]>0)
    # Tied values receive the same midpoint rank; zero/negative never earns points.
    return {r['ticker']: (100*(sum(v<r[key] for v in vals)+.5*sum(v==r[key] for v in vals))/len(vals)
                          if vals and r[key]>0 else 0) for r in rows}

def score(rows):
    ranks={k:positive_ranks(rows,k) for k in ('cap_flow','flow','accel')}
    for r in rows:
        t=r['ticker']
        values=[.15*ranks['cap_flow'][t],.10*ranks['flow'][t],2*r['buy_days'],
                .10*ranks['accel'][t],r['pattern'],r['confirmation'],r['slope'],r['proximity']]
        r['contributions']=dict(zip(WEIGHTS,values))
        r['contributions'].update({'異常爆量':-r['volume_penalty'],'股價過熱':-r['heat_penalty']})
        r['contributions']['自結EPS']=r.get('self_eps',{}).get('points',0)
        r['score']=sum(r['contributions'].values())
    return sorted((r for r in rows if r['score']>=MIN_SCORE),key=lambda r:(-r['score'],r['ticker']))


def self_eps_signal(ticker, disclosures, asof, trading_dates):
    """Use the monthly/quarterly pair explicitly disclosed in the same notice.
    Missing formal-quarter timing in the historical database must not be guessed.
    Signal uses notices available by the daily 18:00 selection cutoff.
    """
    from decimal import Decimal
    from datetime import date
    import re
    candidates=[]
    for row in disclosures:
        day=str(row.get('publish_date') or '')[:10]
        if str(row.get('ticker'))!=ticker or not day or day>asof: continue
        if day==asof and str(row.get('publish_time') or '23:59:59')>'18:00:00': continue
        if not re.fullmatch(r'20\d{2}-\d{2}',str(row.get('monthly_period') or '')): continue
        try:
            date.fromisoformat(day)
            period_date=date.fromisoformat(row['monthly_period']+'-01')
            if period_date>date.fromisoformat(day): continue
        except ValueError: continue
        if number(row.get('monthly_eps')) is None: continue
        candidates.append(row)
    if not candidates: return {'points':0,'status':'無可用單月自結'}
    r=max(candidates,key=lambda x:(x['monthly_period'],x['publish_date'],x.get('publish_time') or ''))
    day=r['publish_date']; monthly=number(r.get('monthly_eps')); quarter=number(r.get('quarter_eps'))
    result={'points':0,'publish_date':day,'monthly_period':r['monthly_period'],
            'monthly_eps':monthly,'quarter_period':r.get('quarter_period'),
            'quarter_eps':quarter,'source_url':r.get('source_url')}
    age=sum(day<d<=asof for d in trading_dates)
    if age>=20: return dict(result,status='公告已超過20交易日')
    # Require an older quarterly period, not this month's quarter or a cumulative EPS.
    match=re.fullmatch(r'(20\d{2})-Q([1-4])',str(r.get('quarter_period') or ''))
    y,m=map(int,r['monthly_period'].split('-')); monthq=y*4+(m-1)//3+1
    if not match or int(match[1])*4+int(match[2])!=monthq-1:
        return dict(result,status='缺可確認的前季單季EPS')
    if quarter is None or quarter<=0: return dict(result,status='前季EPS非正或缺漏')
    a=Decimal(str(monthly))*3; b=Decimal(str(quarter))
    points=5 if a>b*Decimal('1.3') else (-5 if a<=b else 0)
    return dict(result,points=points,status='有效',monthly_times_three=float(a),
                ratio_pct=float(a/b*100),age_trading_days=age,
                basis='自結公告同列之前季單季EPS；未使用無公告時間的歷史季報倒填')
