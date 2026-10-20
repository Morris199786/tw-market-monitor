"""Forward performance of saved setup signals only. No paid APIs or reconstructed picks."""
from sources import ROOT, load_json, save_json, now_tpe
from ai_setup_strategy import STRATEGY, NAME
from update_ai import load_candles
from statistics import mean, median

BUY_COST=.001425+.001
SELL_COST=.001425+.003+.001
PREFIXES=('baseline_','','ma20_','stop5_','stop10_')

def evaluate(rec, dates, bars):
    idx=dates.index(rec['selection_date'])
    entry_day=dates[idx+1] if idx+1<len(dates) else None
    entry=bars.get(entry_day,{}).get('open')
    rec.update(entry_date=entry_day,entry_price=entry)
    for n in (5,10):
        mature=idx+n<len(dates)
        window=dates[idx+1:idx+n+1]
        valid=bool(entry and mature and all(d in bars for d in window))
        for prefix in PREFIXES:
            status='pending' if not mature else ('complete' if valid else 'unavailable')
            exit_price=exit_day=result=None
            if valid:
                exit_day=dates[idx+n];exit_price=bars[exit_day]['close']
                # A close-based exit signal can only execute at the next session's open.
                for j in range(idx+1,idx+n):
                    b=bars[dates[j]];trigger=False
                    if prefix in ('','ma20_'):
                        period=10 if prefix=='' else 20
                        history=dates[max(0,j-period+1):j+1]
                        if len(history)!=period or any(d not in bars for d in history):
                            status='unavailable';break
                        trigger=b['close']<mean(bars[d]['close'] for d in history)
                    elif prefix=='stop5_':trigger=b['close']<=entry*.95
                    elif prefix=='stop10_':trigger=b['close']<=entry*.90
                    if trigger:
                        exit_day=dates[j+1];exit_price=bars[exit_day]['open'];break
                if status=='complete':result=round((exit_price*(1-SELL_COST)/(entry*(1+BUY_COST))-1)*100,4)
            rec[f'{prefix}return_{n}d']=result
            rec[f'{prefix}status_{n}d']=status
            rec[f'{prefix}end_date_{n}d']=exit_day
    return rec

def stats(rows,n,prefix):
    vals=[r[f'{prefix}return_{n}d'] for r in rows if r.get(f'{prefix}status_{n}d')=='complete']
    return {'avg_return':mean(vals) if vals else None,'median_return':median(vals) if vals else None,
            'win_rate':100*sum(v>0 for v in vals)/len(vals) if vals else None,'samples':len(vals)}

def summary(rows,prefix):
    def block(rs):return {f'{n}d':stats(rs,n,prefix) for n in (5,10)}
    return {'all':block(rows),'twse':block([r for r in rows if r['market']=='twse']),
            'tpex':block([r for r in rows if r['market']=='tpex']),
            'rank_buckets':{f'top{n}':block([r for r in rows if r['rank']<=n]) for n in (5,10,20)}}

def main():
    history=[]
    for p in sorted((ROOT/'data/history/ai_setup').glob('*.json')):
        x=load_json(p,{})
        if x.get('logic',{}).get('strategy')==STRATEGY:history.append(x)
    dates=[p.stem for p in sorted((ROOT/'data/history/market').glob('*.json')) if load_json(p,{}).get('stocks')]
    if not dates:raise RuntimeError('Missing market history')
    records=[];cache={}
    for h in history:
        if h.get('date') not in dates:continue
        for market in ('twse','tpex'):
            for rank,r in enumerate(h.get(market,[]),1):
                t=r['ticker']
                if t not in cache:cache[t]=load_candles(t)
                rec={'selection_date':h['date'],'ticker':t,'name':r.get('name'),'market':market,
                     'rank':rank,'score':r['score'],'strategy':STRATEGY}
                records.append(evaluate(rec,dates,cache[t]))
    records.sort(key=lambda r:(r['selection_date'],r['market'],-r['rank']),reverse=True)
    path=ROOT/'data/ai_backtest.json';old=load_json(path,{})
    if old and old.get('strategy')!=STRATEGY:
        archive=ROOT/'data/ai_archive/legacy_backtest.json'
        if not archive.exists():save_json(archive,old)
    out={'updated_at':now_tpe().isoformat(timespec='minutes'),'strategy':STRATEGY,'strategy_name':NAME,
         'start_date':history[0]['date'] if history else None,'latest_selection_date':history[-1]['date'] if history else None,
         'selection_days':len(history),'record_count':len(records),'records':records,
         'rules':{'entry':'次交易日開盤','exit':'收盤觸發、次交易日開盤；期滿收盤',
                  'cost':'買賣各0.1425%手續費＋賣出0.3%稅＋買賣各0.1%滑價',
                  'notes':['僅使用新策略實際保存訊號，不與舊策略混算','未還原除權息，跨除權息樣本須另行核對']},
         'benchmark_summary':{f'{n}d':{m:{'avg_return':None,'samples':0} for m in ('twse','tpex')} for n in (5,10)}}
    for key,prefix in [('summary',''),('ma10_summary',''),('ma20_summary','ma20_'),('baseline_summary','baseline_'),('stop5_summary','stop5_'),('stop10_summary','stop10_')]:
        out[key]=summary(records,prefix)
    save_json(path,out)
    print(STRATEGY,'forward signals',len(records),'selection dates',len(history))

if __name__=='__main__':main()
