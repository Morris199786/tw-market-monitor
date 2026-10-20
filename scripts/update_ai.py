"""Daily accumulation/setup selector; existing site schema, no paid API calls."""
from sources import ROOT, load_json, save_json, now_tpe, ordinary_ticker
from tech_universe import tech_tickers
from ai_setup_strategy import STRATEGY, NAME, WEIGHTS, MIN_SCORE, features, score, number, self_eps_signal
from update_daily_k import valid_bar, fetch_official
import argparse
from collections import Counter


def load_candles(ticker):
    merged={}
    # Prefer the chart's official-corrected candles over the research backfill.
    for folder in ('ai_backtest_k','ai_setup_k','daily_k'):
        data=load_json(ROOT/f'data/{folder}/{ticker}.json',{})
        if str(data.get('ticker'))!=str(ticker): continue
        for b in data.get('bars',[]):
            if valid_bar(b): merged[b['time']]=b
    return merged


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--offline',action='store_true');args=ap.parse_args()
    master=load_json(ROOT/'data/master.json',{}).get('stocks',{})
    latest=load_json(ROOT/'data/market_latest.json',{});day=latest.get('date')
    snapshots=[]
    for p in sorted((ROOT/'data/history/market').glob('*.json')):
        if p.stem<=day:
            d=load_json(p,{}).get('stocks',{})
            if d: snapshots.append((p.stem,d))
    if len(snapshots)<10 or snapshots[-1][0]!=day:
        raise RuntimeError('AI requires 10 complete market dates ending '+str(day))
    dates=[d for d,_ in snapshots[-40:]]
    institutions={}
    for d in dates[-10:]:
        x=load_json(ROOT/f'data/history/institutional/{d}.json',{})
        if not x: raise RuntimeError('Missing institutional date '+d)
        institutions[d]={**x.get('twse',{}),**x.get('tpex',{})}
    universe=tech_tickers(master)
    candidates={t:m for t,m in master.items() if t in universe and ordinary_ticker(t)
                and m.get('market') in ('twse','tpex') and t in snapshots[-1][1]}
    candles={t:load_candles(t) for t in candidates}
    needs=any(day not in v for v in candles.values())
    official,errors=fetch_official(now_tpe()) if needs and not args.offline else ({},{})
    disclosures=load_json(ROOT/'data/self_reports_history.json',{}).get('items',[])
    pools={'twse':[],'tpex':[]};excluded={};valid_counts=Counter()
    for t,m in candidates.items():
        bydate=candles[t]
        fresh=official.get(m['market'],{}).get(t)
        if fresh and fresh['time']==day and valid_bar(fresh): bydate[day]=fresh
        # Cache only validated data; never overwrite another feature's candle files.
        if day in bydate:
            save_json(ROOT/f'data/ai_setup_k/{t}.json',{'ticker':t,'bars':[bydate[d] for d in sorted(bydate) if d<=day][-260:]})
        if any(d not in bydate for d in dates): excluded[t]='日K缺漏或日期未同步';continue
        bars=[bydate[d] for d in sorted(bydate) if d<=day][-40:]
        if len(bars)<40: excluded[t]='日K不足40日';continue
        quotes=[s.get(t,{}) for _,s in snapshots[-10:]]
        # Check the entire feature window against official close snapshots.
        matching=True
        for d,s in snapshots[-40:]:
            b=bydate[d]
            price=number(s.get(t,{}).get('price'))
            if price is None or abs(b['close']-price)>max(.01,price*.0001): matching=False;break
        if not matching: excluded[t]='日K與市場收盤價不一致';continue
        valid_counts[m['market']]+=1
        flows=[institutions[d].get(t,{}) for d in dates[-10:]]
        f,why=features(bars,flows,quotes,number(m.get('shares_issued')))
        if why: excluded[t]=why;continue
        f.update(ticker=t,name=m.get('name',t),change_pct=snapshots[-1][1][t].get('change_pct'))
        f['self_eps']=self_eps_signal(t,disclosures,day,[d for d,_ in snapshots])
        pools[m['market']].append(f)
    # Fail rather than publish an apparently successful empty result from a data outage.
    for mk in pools:
        total=sum(m['market']==mk for m in candidates.values())
        if total and valid_counts[mk]<max(10,.5*total):
            save_json(ROOT/'data/ai_setup_diagnostics.json',{'date':day,'coverage':dict(valid_counts),'excluded':excluded,'source_errors':errors})
            raise RuntimeError(f'AI {mk} current OHLC coverage {valid_counts[mk]}/{total} below 50%; previous picks preserved. Run AI K Backfill if needed.')
    details=[
        '正式策略：籌碼改善＋整理型態；不以5日漲幅、10日漲幅、突破20日高點加分',
        '全台股科技普通股，上市上櫃分開評分；至少55分、每市場最多20檔，不足不湊數',
        '籌碼45分：近5日預估淨買超占最新市值15分、占成交額10分、5日買超天數每一天2分、近5日對前5日流入率改善10分；正值以合格同市場股票的百分位評分，同值同分',
        '預估淨買超金額＝每日三大法人淨買賣超股數×當日收盤價；市值＝最新收盤價×已發行股數；缺法人資料不補零',
        '量縮收斂：近5日平均高低差≤前10日80%、均量≤85%、低點不再降低，20MA五日降幅不超過1%；12至20分',
        '量縮回測：20MA五日降幅不超過0.5%、當日低點接近前一日20MA半個ATR內、收回均線且收盤位置≥60%、回檔量縮；14至20分',
        '二次測底：前30至16日與前10至3日各取低點，兩底差≤1個ATR、第二底量小於第一底、現收盤高於第二底最高且法人流入率改善；16分；型態只取一種最高分',
        'K線承接15分：收盤在區間上半部最多10分；支撐附近下影線占40%且收盤位置≥60%可得10分；收盤高於開盤與前收且收盤位置≥70%再加5分，總計最多15分',
        '均線止跌10分：10MA與20MA各看五日變化，-1%至+1%線性給0至5分，超過+1%不再增加；支撐距離10分，距支撐≤2%滿分，至10%遞減為0分',
        '不合格：5日淨買超非正、近3日無買超、尚無整理型態、收盤跌破前10日低點、距型態支撐超過10%、近5日均成交額不足2千萬、日K或法人資料不完整',
        '爆量：今日量比前20日均量≥2且收盤位置<40%扣5分；≥3且位置<25%並低於前收扣10分；放量跌破支撐扣15分，當日取最重一條；前4日至少2次放量弱收再扣5，最多20分',
        '爆量且收盤在上方80%、高於開盤與前收，免當日爆量扣分，但不豁免過熱；漲跌停無高低差的收盤位置以50%處理',
        '過熱：5日漲幅超過10%每多1百分點扣1分；20MA正乖離超過2個ATR每多1個ATR扣5分，兩項各上限15分、取較重者；ATR為14日真實波幅平均；爆量與過熱合計最多扣30分',
        '自結EPS額外分：最新單月EPS×3＞前季單季EPS×1.3加5分；≤前季扣5分；其間0分。前季非正或缺漏不計分。只用公告中明列、且緊接自結月份所在季度之前一季的單季EPS；不拿累計EPS替代，不用無公告時間的季報倒填；公告後20交易日內有效，同公司僅最新月份一筆',
        '自結只採選股當日18:00前可用公告，次交易日進場；單月乘三是獲利速度比較，不是季EPS預測',
        '選股是規則評分，不是上漲機率；績效改由本版實際留存訊號累積，次一交易日開盤進場，與舊放寬B分開'
    ]
    out={'updated_at':now_tpe().isoformat(timespec='minutes'),'date':day,'mode':'trade_day','complete':not errors,
         'universe':'全台股科技普通股','universe_count':{mk:sum(m['market']==mk for m in candidates.values()) for mk in pools},
         'logic':{'version':STRATEGY,'strategy':STRATEGY,'strategy_name':NAME,'details':details,'lookback_days':40,
                  'institutional_dates':dates[-10:],'top_n_each_market':20,'minimum_score':MIN_SCORE,
                  'markets_ranked_separately':True,'score_is_probability':False,
                  'factors':[{'key':k,'label':k,'weight':v/100,'weight_pct':v} for k,v in WEIGHTS.items()]},
         'coverage':dict(valid_counts),'excluded_counts':dict(Counter(excluded.values()))}
    for mk,rows in pools.items():
        ranked=score(rows)
        out[mk]=[]
        for r in ranked[:20]:
            contrib=r['contributions']
            out[mk].append({'ticker':r['ticker'],'name':r['name'],'score':round(r['score'],2),'change_pct':r['change_pct'],
                'tags':[r['tag'],f"5日買超{r['buy_days']}天",f"距支撐{r['risk_pct']:.1f}%"],
                'reason':f"{r['tag']}｜買超占市值{r['cap_flow']:.2f}%｜過熱扣{r['heat_penalty']:.1f}分｜自結EPS {r['self_eps']['points']:+d}分",
                'factor_scores':{k:round(100*max(0,v)/WEIGHTS[k],1) for k,v in contrib.items() if k in WEIGHTS},
                'contributions':{k:round(v,2) for k,v in contrib.items()},
                'raw':{k:v for k,v in r.items() if k not in ('contributions','tags','name')}})
    save_json(ROOT/'data/ai_setup_diagnostics.json',{'date':day,'excluded':excluded,'source_errors':errors,'coverage':dict(valid_counts)})
    old=load_json(ROOT/'data/ai_picks.json',{})
    if old and old.get('logic',{}).get('strategy')!=STRATEGY:
        archive=ROOT/'data/ai_archive/legacy_picks.json'
        if not archive.exists(): save_json(archive,old)
    save_json(ROOT/'data/ai_picks.json',out)
    save_json(ROOT/f'data/history/ai_setup/{day}.json',out)
    print(STRATEGY,day,'selected',len(out['twse']),len(out['tpex']),'coverage',dict(valid_counts))

if __name__=='__main__': main()
