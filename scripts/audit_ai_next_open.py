#!/usr/bin/env python3
"""Independent realistic-entry audit; leaves website backtest and AI picks unchanged."""
import json,math,os
from pathlib import Path
from statistics import mean,median
ROOT=Path(__file__).resolve().parents[1]

def load(p):
    try:return json.loads(p.read_text(encoding='utf-8'))
    except (OSError,ValueError):return {}

def main():
    old=load(ROOT/'data/ai_backtest.json')
    records=old.get('records',[])
    if not records:raise RuntimeError('Missing official B backtest records')
    dates=sorted(p.stem for p in (ROOT/'data/history/market').glob('*.json'))
    idx={d:i for i,d in enumerate(dates)}
    bars={}
    for p in (ROOT/'data/ai_backtest_k').glob('*.json'):
        if p.stem=='manifest':continue
        bars[p.stem]={b['time']:b for b in load(p).get('bars',[]) if isinstance(b,dict) and b.get('time')}
    comm=float(os.getenv('AI_COMMISSION_BPS','14.25'))/10000
    tax=float(os.getenv('AI_SELL_TAX_BPS','30'))/10000
    slip=float(os.getenv('AI_SLIPPAGE_BPS','10'))/10000
    if not all(math.isfinite(x) and 0<=x<.1 for x in (comm,tax,slip)):raise ValueError('invalid costs')
    def candle(t,d):
        b=bars.get(t,{}).get(d)
        if not b:return None
        try:
            o,h,l,c,v=[float(b[k]) for k in ('open','high','low','close','volume')]
            if not all(math.isfinite(x) for x in (o,h,l,c,v)) or l<=0 or v<=0 or not l-1e-5<=min(o,c)<=max(o,c)<=h+1e-5:return None
            return o,h,l,c
        except (KeyError,ValueError,TypeError):return None
    def ma(t,i,n):
        closes=[]
        for j in range(i,-1,-1):
            b=candle(t,dates[j]);
            if b:closes.append(b[3])
            if len(closes)==n:return mean(closes)
        return None
    output=[]
    for rec in records:
        t=str(rec['ticker']);day=rec['selection_date'];i=idx.get(day)
        for horizon in (5,10):
            row={'ticker':t,'selection_date':day,'market':rec.get('market'),'rank':rec.get('rank'),'horizon':horizon,'status':'pending'}
            output.append(row)
            # First session after signal is entry session; fifth holding session is i+5.
            if i is None or i+horizon>=len(dates):continue
            entry=candle(t,dates[i+1]);row['entry_date']=dates[i+1]
            if not entry:row['status']='missing_entry_k';continue
            if entry[1]==entry[2]:row['status']='unverified_one_price_entry';continue
            ep=entry[0];exit_i=None;reason='holding_period'
            # A signal observed after close j is executed at OPEN j+1.
            for j in range(i+1,i+horizon):
                b=candle(t,dates[j]);avg=ma(t,j,10)
                if not b or avg is None:continue
                if b[3]<avg:
                    exit_i=j+1;reason='ma10_next_open';break
            if exit_i is None:
                exit_i=i+horizon;exit_mode='close'
            else:exit_mode='open'
            ex=candle(t,dates[exit_i]);row['exit_date']=dates[exit_i]
            if not ex:row['status']='missing_exit_k';continue
            xp=ex[0] if exit_mode=='open' else ex[3]
            row.update(status='complete',entry_price=ep,exit_price=xp,exit_reason=reason,gross_return=round(100*(xp/ep-1),4),net_return=round(100*(xp*(1-slip)*(1-comm-tax)/(ep*(1+slip)*(1+comm))-1),4))
    def stats(rows):
        mature=[r for r in rows if r['status']!='pending'];done=[r['net_return'] for r in mature if r['status']=='complete']
        return {'mature':len(mature),'samples':len(done),'coverage_pct':round(100*len(done)/len(mature),2) if mature else None,'avg_return':round(mean(done),4) if done else None,'median_return':round(median(done),4) if done else None,'win_rate':round(100*sum(v>0 for v in done)/len(done),2) if done else None}
    summary={m:{f'{h}d':stats([r for r in output if (m=='all' or r['market']==m) and r['horizon']==h]) for h in (5,10)} for m in ('twse','tpex','all')}
    result={'updated_from':old.get('updated_at'),'strategy':old.get('strategy'),'execution':'signal after close, next session open entry; MA10 close trigger next open; otherwise last holding session close','cost_bps':{'commission_each_side':comm*10000,'sell_tax':tax*10000,'slippage_each_side':slip*10000},'summary':summary,'records':output,'note':'Independent audit; not used by website; no survivorship-bias correction'}
    out=ROOT/'data/ai_next_open_audit.json';out.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(summary,ensure_ascii=False,indent=2))
    if summary['all']['5d']['coverage_pct'] is None or summary['all']['5d']['coverage_pct']<90:
        print('WARNING: insufficient OHLC coverage; results exploratory only')
if __name__=='__main__':main()
