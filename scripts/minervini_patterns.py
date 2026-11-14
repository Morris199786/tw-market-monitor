"""Explainable, point-in-time Minervini candidate detector (not a buy signal).
Book principles and engineering thresholds are exposed separately in output.
All calculations and annotations use the same validated OHLCV bars.
"""
import math
from statistics import mean

VERSION = 'minervini-v1'
RULES = {
    'book': ['趨勢樣板八項條件', 'VCP 波動逐步收縮與右側量縮', '平坦底部約4–7週、深度約10–15%'],
    'implementation': {
        'flat_sessions': [20, 25, 30, 35], 'flat_max_depth_pct': 15,
        'vcp_swing_reversal_pct': 3, 'vcp_contractions': [2, 4],
        'vcp_max_depth_pct': 35, 'vcp_next_depth_max_ratio': .85,
        'vcp_last_depth_max_pct': 10, 'dry_volume_5_vs_50_max': .75,
        'breakout_volume_vs_prior_50_min': 1.5, 'near_pivot_max_pct': 5,
        'rs_proxy': '252日報酬在當日具足夠有效歷史的上市櫃個股中之百分位；非IBD原版評等',
    },
}


def clean_bars(rows, as_of):
    out = {}
    for row in rows:
        try:
            date = row['time']
            if date > as_of: continue
            vals = [float(row[k]) for k in ('open', 'high', 'low', 'close', 'volume')]
            o, h, l, c, v = vals
            if not all(math.isfinite(x) for x in vals) or min(o,h,l,c)<=0 or v<0: continue
            if l > min(o,c)+1e-4 or h < max(o,c)-1e-4: continue
            if date in out: raise ValueError('duplicate candle date: '+date)
            out[date] = dict(time=date, **dict(zip(('open','high','low','close','volume'),vals)))
        except (KeyError, TypeError, OverflowError): continue
    return [out[d] for d in sorted(out)]


def trend(bars, rs):
    if len(bars)<253: return []
    c=[b['close'] for b in bars]; ma50=mean(c[-50:]);ma150=mean(c[-150:]);ma200=mean(c[-200:])
    past200=mean(c[-221:-21]);low=min(b['low'] for b in bars[-252:]);high=max(b['high'] for b in bars[-252:])
    specs=[('price_long','股價高於150日、200日均線',c[-1]>ma150 and c[-1]>ma200,round(c[-1],3),round(max(ma150,ma200),3)),
           ('ma_order','150日均線高於200日均線',ma150>ma200,round(ma150,3),round(ma200,3)),
           ('ma_slope','200日均線高於21個交易日前',ma200>past200,round(ma200,3),round(past200,3)),
           ('ma50_order','50日均線高於150日、200日均線',ma50>max(ma150,ma200),round(ma50,3),round(max(ma150,ma200),3)),
           ('price50','股價高於50日均線',c[-1]>ma50,round(c[-1],3),round(ma50,3)),
           ('above_low','比52週低點高至少30%',c[-1]/low>=1.3,round((c[-1]/low-1)*100,2),30),
           ('near_high','距52週高點不超過25%',c[-1]/high>=.75,round((1-c[-1]/high)*100,2),25),
           ('rs','台股相對強度代理排名至少70',rs is not None and rs>=70,rs,70)]
    return [dict(key=k,label=l,passed=bool(p),value=v,reference=r) for k,l,p,v,r in specs]


def pivots(bars, start, end, reversal=.03):
    """Directional-change swings. A peak/trough is confirmed only by later bars
    already available at `end`; an unfinished last leg is never fabricated.
    """
    if end-start<3:return []
    mode='peak';ext=start;out=[]
    for i in range(start+1,end):
        if mode=='peak':
            if bars[i]['high']>bars[ext]['high']:ext=i
            # Require separate sessions: daily OHLC cannot reveal intraday order.
            elif i>ext and bars[i]['low']<=bars[ext]['high']*(1-reversal):
                out.append(('H',ext,bars[ext]['high']));mode='trough';ext=i
        else:
            if bars[i]['low']<bars[ext]['low']:ext=i
            elif i>ext and bars[i]['high']>=bars[ext]['low']*(1+reversal):
                out.append(('L',ext,bars[ext]['low']));mode='peak';ext=i
    return out


def setup_at(bars, end):
    """End is exclusive. No breakout candles participate in base construction."""
    found=[]
    for length in (20,25,30,35):
        start=end-length
        if start<1:continue
        seg=bars[start:end]; high=max(b['high'] for b in seg); low=min(b['low'] for b in seg)
        depth=(1-low/high)*100
        # Need the resistance high to precede the final five sessions.
        high_i=max(range(start,end),key=lambda i:bars[i]['high'])
        if not 3<=depth<=15 or high_i>end-6:continue
        found.append(dict(pattern='flat',label='平坦底部',start=start,end=end-1,pivot=high,floor=low,
            depth_pct=round(depth,2),segments=[],zones=[dict(start=start,end=end-1,high=high,low=low,label='平坦整理區')],
            stop=low,stop_label='整理區低點（型態失效參考，非建議下單停損）'))
    for length in (40,60,80,100):
        start=end-length
        if start<1:continue
        pts=pivots(bars,start,end);pairs=[]
        for a,b in zip(pts,pts[1:]):
            if a[0]=='H' and b[0]=='L' and b[1]-a[1]>=2:
                pairs.append(dict(start=a[1],end=b[1],high=a[2],low=b[2],depth_pct=100*(1-b[2]/a[2])))
        for count in (4,3,2):
            if len(pairs)<count:continue
            seg=pairs[-count:];ds=[s['depth_pct'] for s in seg]
            if not (6<=ds[0]<=35 and ds[-1]<=10):continue
            if not all(b<=a*.85 for a,b in zip(ds,ds[1:])):continue
            if end-1-seg[-1]['end']>12:continue
            # Right-side recovery must reclaim most of the final contraction.
            pivot=seg[-1]['high'];close=bars[end-1]['close']
            if not pivot*.90<=close<=pivot*1.02:continue
            # Recoveries between contractions must reclaim >=50% of prior drop;
            # prevents a descending staircase being mislabelled constructive VCP.
            if not all(b['high']>=a['low']+(a['high']-a['low'])*.5 for a,b in zip(seg,seg[1:])):continue
            found.append(dict(pattern='vcp',label='VCP',start=seg[0]['start'],end=end-1,pivot=pivot,
                floor=min(s['low'] for s in seg),depth_pct=round(ds[0],2),segments=seg,zones=[],
                stop=seg[-1]['low'],stop_label='最後收縮低點（型態失效參考，非建議下單停損）'))
            break
    return found


def analyze(bars, rs):
    checks=trend(bars,rs)
    if len(checks)!=8 or not all(c['passed'] for c in checks):return []
    candidates={};n=len(bars)
    # Observe frozen setups ending today or within five sessions. Their original
    # pivot stays fixed; a failed recent breakout remains inspectable.
    for age in range(6):
        end=n-age
        if end<253:continue
        for s in setup_at(bars,end):
            baseline=mean(b['volume'] for b in bars[end-50:end])
            dry=mean(b['volume'] for b in bars[end-5:end])/baseline if baseline else None
            after=bars[end:];breakout=None;confirmed=False
            for i,b in enumerate(after,end):
                volbase=mean(x['volume'] for x in bars[i-50:i])
                if b['close']>s['pivot']:
                    breakout=i;confirmed=bool(volbase and b['volume']/volbase>=1.5);break
            price=bars[-1]['close'];distance=(price/s['pivot']-1)*100
            if price<s['stop'] or (breakout is not None and price<s['pivot']):status='failed'
            elif breakout is not None:status='breakout' if confirmed else 'unconfirmed'
            elif abs(distance)<=5 and dry is not None and dry<=.75:status='near'
            else:status='forming'
            # Do not emit stale setups that never broke and were superseded.
            if age and breakout is None:continue
            s.update(status=status,trend=checks,rs=rs,distance_pct=round(distance,2),dry_ratio=round(dry,3) if dry is not None else None,
                volume_ratio=round(bars[-1]['volume']/mean(b['volume'] for b in bars[-51:-1]),3) if mean(b['volume'] for b in bars[-51:-1]) else None,
                breakout_date=bars[breakout]['time'] if breakout is not None else None,
                breakout_volume_confirmed=confirmed,
                conditions=[dict(label='趨勢樣板（含台股RS代理）8/8',passed=True),
                    dict(label='型態幾何結構符合本版門檻',passed=True),
                    dict(label='整理末5日量／整理末50日均量 ≤0.75',passed=dry is not None and dry<=.75),
                    dict(label='突破收盤高於樞紐，且突破量≥前50日均量1.5倍',passed=confirmed),
                    dict(label='最新收盤未跌破型態失效位置',passed=price>=s['stop'])])
            # Prefer actual breakout/failed history to a newly fitted base today.
            priority={'breakout':6,'failed':5,'unconfirmed':4,'near':3,'forming':2}[status]
            prev=candidates.get(s['pattern'])
            if prev is None or priority>prev[0]:candidates[s['pattern']]=(priority,s)
    return [s for _,s in candidates.values()]


def rs_ranks(histories):
    returns={t:b[-1]['close']/b[-253]['close']-1 for t,b in histories.items() if len(b)>=253}
    ordered=sorted(returns.values());n=len(ordered)
    # Midrank ties, no artificial ticker-order advantage.
    import bisect
    return {t:round(100*(bisect.bisect_left(ordered,v)+bisect.bisect_right(ordered,v))/(2*n),2) for t,v in returns.items()} if n else {}


def limit_companies(items, maximum=10):
    """Keep existing ranking and qualifying rules; never pad the result.
    Multiple detected patterns for a selected company do not consume extra slots.
    """
    selected = set()
    for item in items:
        if len(selected) < maximum:
            selected.add(item['ticker'])
    return [item for item in items if item['ticker'] in selected]
