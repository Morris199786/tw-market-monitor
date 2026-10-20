#!/usr/bin/env python3
"""Self-report event study, NOT model optimization. Uses only as-of known events.
Run from repository root: python scripts/self_report_event_study.py
"""
import argparse
import collections
import csv
import datetime as dt
import json
import re
import time
from pathlib import Path
import requests

VERSION='2026-10-20-event-study-v3-market-cross-analysis'
S=requests.Session(); S.headers.update({'User-Agent':'Mozilla/5.0 (research; event-study)'})

def get(url):
    for k in range(3):
        try:
            r=S.get(url,timeout=45);r.raise_for_status();return r.json()
        except (requests.RequestException,ValueError):
            if k==2:raise
            time.sleep(k+1)

def parse_notice_date(value):
    # TWSE dates are commonly 115.10.19; TPEx dates commonly 115/10/19.
    m=re.search(r'(?<!\d)(\d{2,4})[./-](\d{1,2})[./-](\d{1,2})(?!\d)',str(value))
    if not m:return None
    year=int(m[1]);year=year+1911 if year<1911 else year
    try:return dt.date(year,int(m[2]),int(m[3])).isoformat()
    except ValueError:return None

def parse_clause(reason,clause):
    # Both 「第六款」 and 「﹝第六款﹞」 are accepted.
    return bool(re.search(r'第\s*'+clause+r'\s*款',reason or ''))

def attention(start,end):
    a=start.replace('-','');b=end.replace('-','')
    sources=[
        ('上市',[f'https://www.twse.com.tw/rwd/zh/announcement/notice?response=json&startDate={a}&endDate={b}']),
        ('上櫃',[f'https://www.tpex.org.tw/www/zh-tw/bulletin/attention?startDate={start.replace("-","/")}&endDate={end.replace("-","/")}&response=json',
                f'https://www.tpex.org.tw/web/bulletin/attention_information/attention_information.php?l=zh-tw&sd={start.replace("-","/")}&ed={end.replace("-","/")}&o=json']),
    ]
    result=[];diagnostics=[]
    for market,urls in sources:
        z=None;errors=[];used=None
        for url in urls:
            try:
                z=get(url);used=url;break
            except (requests.RequestException,ValueError) as exc:
                errors.append(f'{type(exc).__name__}: {str(exc)[:180]}')
        if z is None:
            diagnostics.append(dict(market=market,status='unavailable',source_rows=0,parsed_rows=0,errors=errors))
            print(f'WARNING: {market} official attention unavailable: {errors}',flush=True)
            continue
        tables=z.get('tables') or []
        rows=z.get('data') or (tables[0].get('data',[]) if tables else [])
        fields=z.get('fields') or (tables[0].get('fields',[]) if tables else [])
        # The published TWSE schema is 編號,證券代號,證券名稱,累計次數,注意交易資訊,日期,...
        # Resolve columns by field names when available, falling back to documented positions.
        def col(pattern,default):
            return next((i for i,f in enumerate(fields) if re.search(pattern,str(f))),default)
        ti=col('證券代號|股票代號',1);ni=col('證券名稱|股票名稱',2)
        ri=col('注意交易資訊|注意原因|注意交易原因',4);di=col('日期',5)
        parsed=0;nonstock=0;bad_date=0;seen=set()
        for row in rows:
            if not isinstance(row,(list,tuple)) or len(row)<=max(ti,ni,ri,di):continue
            ticker=str(row[ti]).strip()
            if not re.fullmatch(r'\d{4}',ticker):nonstock+=1;continue
            date=parse_notice_date(row[di])
            if not date:bad_date+=1;continue
            if not start<=date<=end:continue
            key=(date,ticker)
            if key in seen:continue
            seen.add(key);parsed+=1
            result.append(dict(date=date,ticker=ticker,name=str(row[ni]),market=market,reason=str(row[ri])))
        status='ok' if parsed else 'empty_or_unparsed'
        diagnostics.append(dict(market=market,status=status,source_rows=len(rows),parsed_rows=parsed,
                                skipped_nonstock=nonstock,unparsed_dates=bad_date,source=used,
                                fields=fields))
        if not parsed:print(f'WARNING: {market} source returned {len(rows)} rows but parsed none',flush=True)
    if not result:raise RuntimeError('No parsable attention records; refusing empty study')
    return result,diagnostics

def classify_report(x):
    subject=str(x.get('subject') or '')
    detail=str(x.get('detail') or '')[:4000]
    reason=str(x.get('match_reason') or '')
    if re.search(r'資金貸與|背書保證|取得或處分資產|衍生性商品|轉換公司債|可轉換公司|子公司資金',subject):
        return None
    if reason=='attention_trading' and re.search(r'注意交易|注意股|多次達公[布佈]注意',subject):
        return 'attention_trading'
    # Do not blindly trust direct_self_report: it can include unrelated disclosures.
    if reason=='direct_self_report' and re.search(r'自結|自編財務|自行結算|自編損益',subject):
        if re.search(r'營收|損益|財務|盈餘|獲利|財報|財務業務',subject):
            return 'direct_self_report'
        # Review ambiguous subjects separately instead of labeling them as negatives.
    return None

def read_reports(path):
    data=json.loads(Path(path).read_text(encoding='utf-8-sig'))
    raw=data.get('items',[])+data.get('parse_failed',[])
    events={};rejected=[]
    for x in raw:
        ticker=str(x.get('ticker') or '');date=str(x.get('publish_date') or '')
        if not re.fullmatch(r'\d{4}',ticker) or not re.fullmatch(r'20\d\d-\d\d-\d\d',date):continue
        kind=classify_report(x)
        if not kind:
            rejected.append(dict(date=date,ticker=ticker,name=x.get('name',''),match_reason=x.get('match_reason',''),subject=x.get('subject','')))
            continue
        month=x.get('monthly_period')
        if not re.fullmatch(r'20\d\d-(0[1-9]|1[0-2])',str(month or '')):month=None
        key=(date,ticker,kind)
        entry=dict(date=date,ticker=ticker,name=x.get('name',''),kind=kind,month=month,
                   monthly_eps=x.get('monthly_eps'),quarter_eps=x.get('quarter_eps'),subject=x.get('subject',''))
        if key not in events or (events[key]['monthly_eps'] is None and entry['monthly_eps'] is not None):events[key]=entry
    return sorted(events.values(),key=lambda x:(x['date'],x['ticker'])),rejected

def save(path,rows,fields):
    with open(path,'w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore');w.writeheader();w.writerows(rows)

def features(ticker,cutoff,calendar,by_ticker):
    days=[d for d in calendar if d<=cutoff]
    hist=[x for x in by_ticker[ticker] if x['date']<=cutoff]
    def last(n):
        allowed=set(days[-n:]);return [x for x in hist if x['date'] in allowed]
    d3=last(3);d5=last(5);d10=last(10);d20=last(20)
    kinds=lambda xs,k:sum(parse_clause(x['reason'],k) for x in xs)
    recent=hist[-1]['date']
    return dict(n1=len(last(1)),n3=len(d3),n5=len(d5),n10=len(d10),n20=len(d20),r1_10=kinds(d10,'一'),r4_10=kinds(d10,'四'),r6_10=kinds(d10,'六'),gap=(days.index(cutoff)-days.index(recent)) if cutoff in days and recent in days else (dt.date.fromisoformat(cutoff)-dt.date.fromisoformat(recent)).days,recent_reason=hist[-1]['reason'],market=hist[-1]['market'],name=hist[-1]['name'])

def main():
    p=argparse.ArgumentParser();p.add_argument('--attention-start',default='2026-09-01');p.add_argument('--start',default='2026-09-29');p.add_argument('--asof',default=dt.date.today().isoformat());p.add_argument('--history',default='data/self_reports_history.json');p.add_argument('--out',default='self_report_event_study');a=p.parse_args()
    out=Path(a.out);out.mkdir(parents=True,exist_ok=True)
    notices,source_info=attention(a.attention_start,a.asof);reports,rejected=read_reports(a.history)
    save(out/'excluded_announcements.csv',rejected,['date','ticker','name','match_reason','subject'])
    by_ticker=collections.defaultdict(list)
    for x in notices:by_ticker[x['ticker']].append(x)
    for xs in by_ticker.values():xs.sort(key=lambda x:x['date'])
    # Use the complete weekday calendar, not only dates with attention notices.
    # Otherwise cutoff can be absent on a quiet day and days.index(cutoff) crashes.
    cal_start=dt.date.fromisoformat(a.attention_start)
    cal_end=dt.date.fromisoformat(a.asof)
    calendar=[]
    cal_day=cal_start
    while cal_day<=cal_end:
        if cal_day.weekday()<5:calendar.append(cal_day.isoformat())
        cal_day+=dt.timedelta(days=1)
    by_report=collections.defaultdict(list)
    for x in reports:by_report[x['date']].append(x)
    # Full event calendar, not just dates with attention notices: prevents missing quiet report days.
    start=dt.date.fromisoformat(a.start);end=dt.date.fromisoformat(a.asof)
    days=[];day=start
    while day<=end:
        if day.weekday()<5:days.append(day.isoformat())
        day+=dt.timedelta(days=1)
    rows=[];event_audit=[]
    for i,day in enumerate(days):
        if i==0:continue
        cutoff=days[i-1]
        announced=by_report.get(day,[])
        target={x['ticker'] for x in announced if x['kind']=='attention_trading'}
        voluntary={x['ticker'] for x in announced if x['kind']=='direct_self_report'}
        unknown=sum(x['monthly_eps'] is None for x in announced)
        event_audit.append(dict(date=day,attention_self_report=len(target),voluntary_self_report=len(voluntary),missing_monthly_eps=unknown,all_announcements=len(announced)))
        # Risk set: tickers with attention in last 20 trading sessions, and not yet reported
        # the SAME month before cutoff. This exclusion is as-of and never uses future data.
        past_reports=[x for x in reports if x['date']<=cutoff]
        last20=set([d for d in calendar if d<=cutoff][-20:])
        candidates=[c for c,history in by_ticker.items() if any(x['date'] in last20 for x in history)]
        for ticker in candidates:
            f=features(ticker,cutoff,calendar,by_ticker)
            prior=[x for x in past_reports if x['ticker']==ticker]
            last_report=max((x['date'] for x in prior),default='')
            last_attention_report=max((x['date'] for x in prior if x['kind']=='attention_trading'),default='')
            since_report=(dt.date.fromisoformat(cutoff)-dt.date.fromisoformat(last_report)).days if last_report else None
            rows.append(dict(cutoff=cutoff,target_date=day,ticker=ticker,**f,days_since_report=since_report,prior_attention_report=int(bool(last_attention_report)),label_attention=int(ticker in target),label_voluntary=int(ticker in voluntary),label_any=int(ticker in target or ticker in voluntary)))
    if not rows:raise RuntimeError('No risk-set rows generated; check official feed parsing and dates')
    save(out/'event_audit.csv',event_audit,['date','attention_self_report','voluntary_self_report','missing_monthly_eps','all_announcements'])
    save(out/'risk_set.csv',rows,list(rows[0]))
    # Pre-declared descriptive conditions. No threshold sweep and no selecting a winner.
    conditions={
        '所有注意交易候選':lambda x:True,
        '前1交易日有注意交易':lambda x:x['n1']>=1,
        '前3交易日注意交易>=2次':lambda x:x['n3']>=2,
        '前5交易日注意交易>=3次':lambda x:x['n5']>=3,
        '前10交易日含第六款':lambda x:x['r6_10']>=1,
        '前10交易日含第四款':lambda x:x['r4_10']>=1,
        '前10交易日含第一款':lambda x:x['r1_10']>=1,
        '前3日>=2次且10日含第六款':lambda x:x['n3']>=2 and x['r6_10']>=1,
        '前5日>=3次且10日含第六款':lambda x:x['n5']>=3 and x['r6_10']>=1,
        '最近一次注意交易距今0日':lambda x:x['gap']==0,
        '最近一次注意交易距今1至2日':lambda x:1<=x['gap']<=2,
        '過去曾公布自結':lambda x:x['days_since_report'] is not None,
        '距前次自結0至5日':lambda x:x['days_since_report'] is not None and x['days_since_report']<=5,
    }
    summary=[]
    for market in ('全部','上市','上櫃'):
        group=[x for x in rows if market=='全部' or x['market']==market]
        for name,rule in conditions.items():
            subset=[x for x in group if rule(x)]
            n=len(subset);hits=sum(x['label_attention'] for x in subset);any_hits=sum(x['label_any'] for x in subset)
            summary.append(dict(market=market,condition=name,samples=n,next_day_attention_self_reports=hits,next_day_rate=round(hits/n,4) if n else None,next_day_any_reports=any_hits,any_report_rate=round(any_hits/n,4) if n else None))
    save(out/'conditional_rates.csv',summary,list(summary[0]))
    # Event-centric preceding features, for direct comparison with the non-event risk set.
    events=[]
    index={(x['target_date'],x['ticker']):x for x in rows}
    for x in reports:
        if not a.start<=x['date']<=a.asof:continue
        match=index.get((x['date'],x['ticker']))
        events.append(dict(**x,found_in_risk_set=bool(match),prior_n1=match['n1'] if match else None,prior_n3=match['n3'] if match else None,prior_n5=match['n5'] if match else None,prior_n10=match['n10'] if match else None,prior_r6=match['r6_10'] if match else None,prior_gap=match['gap'] if match else None))
    save(out/'actual_events.csv',events,['date','ticker','name','kind','month','monthly_eps','quarter_eps','found_in_risk_set','prior_n1','prior_n3','prior_n5','prior_n10','prior_r6','prior_gap','subject'])
    # Market-specific, mutually exclusive cross-sections: all features are known at cutoff.
    # Not a threshold sweep: fixed categorical bins to describe observed patterns.
    def count_bin(v):
        if v==0:return '0'
        if v==1:return '1'
        if v==2:return '2'
        if v==3:return '3'
        return '4+'
    def recent_bin(x):
        if x['n1']>=1:return '當日注意'
        if x['gap']<=2:return '距今1-2日'
        return '距今3日以上'
    def cooldown_bin(x):
        d=x['days_since_report']
        if d is None:return '從未公布'
        if d<=5:return '公布後0-5日'
        if d<=10:return '公布後6-10日'
        return '公布後11日以上'
    for x in rows:
        x['recent_group']=recent_bin(x)
        x['n3_group']=count_bin(x['n3'])
        x['n5_group']=count_bin(x['n5'])
        x['r6_group']='有第六款' if x['r6_10'] else '無第六款'
        x['cooldown_group']=cooldown_bin(x)
    save(out/'risk_set.csv',rows,list(rows[0]))
    cross=[]
    def summarize_cross(group_by,labels,market,group):
        buckets=collections.defaultdict(list)
        for x in group:
            buckets[tuple(x[k] for k in group_by)].append(x)
        for key,subset in sorted(buckets.items()):
            n=len(subset);hits=sum(x['label_attention'] for x in subset)
            days_count=len({x['target_date'] for x in subset})
            stocks_count=len({x['ticker'] for x in subset})
            # Wilson 95% interval, to avoid overinterpreting tiny subgroups.
            import math
            z=1.96; rate=hits/n
            denom=1+z*z/n
            mid=(rate+z*z/(2*n))/denom
            half=z*math.sqrt(rate*(1-rate)/n+z*z/(4*n*n))/denom
            cross.append(dict(market=market,analysis=labels,group='｜'.join(map(str,key)),samples=n,
                              distinct_stocks=stocks_count,distinct_days=days_count,
                              hits=hits,rate=round(rate,5),wilson_low=round(max(0,mid-half),5),
                              wilson_high=round(min(1,mid+half),5),
                              enough_samples=int(n>=30 and days_count>=5)))
    plans=[
        (['recent_group','n3_group'],'最近注意 × 前3日次數'),
        (['recent_group','n5_group'],'最近注意 × 前5日次數'),
        (['recent_group','r6_group'],'最近注意 × 第六款'),
        (['recent_group','cooldown_group'],'最近注意 × 自結冷卻期'),
        (['recent_group','n5_group','r6_group'],'最近注意 × 前5日次數 × 第六款'),
        (['recent_group','n5_group','cooldown_group'],'最近注意 × 前5日次數 × 冷卻期'),
    ]
    for market in ('上市','上櫃'):
        group=[x for x in rows if x['market']==market]
        for keys,label in plans:summarize_cross(keys,label,market,group)
    save(out/'market_cross_rates.csv',cross,list(cross[0]))

    # Daily stability of fixed, interpretable conditions; report zero-hit days too.
    daily_stability=[]
    fixed_rules={
        '當日注意':lambda x:x['n1']>=1,
        '當日注意且前3日>=2次':lambda x:x['n1']>=1 and x['n3']>=2,
        '當日注意且前5日>=3次':lambda x:x['n1']>=1 and x['n5']>=3,
        '當日注意且前5日>=4次':lambda x:x['n1']>=1 and x['n5']>=4,
        '當日注意且前5日>=3次且無5日內自結':lambda x:x['n1']>=1 and x['n5']>=3 and (x['days_since_report'] is None or x['days_since_report']>5),
    }
    for market in ('上市','上櫃'):
        for day in days[1:]:
            g=[x for x in rows if x['market']==market and x['target_date']==day]
            for name,rule in fixed_rules.items():
                subset=[x for x in g if rule(x)]
                n=len(subset);hits=sum(x['label_attention'] for x in subset)
                daily_stability.append(dict(market=market,target_date=day,condition=name,
                    samples=n,hits=hits,rate=round(hits/n,5) if n else None,
                    hit_tickers=' '.join(sorted(x['ticker'] for x in subset if x['label_attention'])),
                    candidate_tickers=' '.join(sorted(x['ticker'] for x in subset))))
    save(out/'daily_stability.csv',daily_stability,list(daily_stability[0]))

    # Contrast event capture vs events outside the attention-based risk set.
    coverage=[]
    for market in ('上市','上櫃'):
        known={x['ticker'] for x in notices if x['market']==market}
        event_rows=[x for x in events if x['kind']=='attention_trading' and x['ticker'] in known]
        coverage.append(dict(market=market,matched_events=len(event_rows),
                             matched_risk_set=sum(bool(x['found_in_risk_set']) for x in event_rows),
                             unmatched_events=sum(not x['found_in_risk_set'] for x in event_rows)))
    save(out/'event_coverage.csv',coverage,list(coverage[0]))
    report={'version':VERSION,'cross_rate_rows':len(cross),'daily_stability_rows':len(daily_stability),'market_event_coverage':coverage,'excluded_non_self_report':len(rejected),'asof':a.asof,'study_start':a.start,'attention_start':a.attention_start,'official_source_status':source_info,'complete_market_coverage':all(x['status']=='ok' for x in source_info),'attention_records':len(notices),'historical_self_report_events':len(reports),'study_events':len(events),'risk_set_rows':len(rows),'caveats':['This is descriptive event research, not a predictive model or optimized backtest.','Trading dates use weekdays, not exchange holiday calendars; verify holiday periods.','Attention event dates and reason fields depend on official feed layout.','Historical self-report history may miss real announcements; missing labels bias conditional rates downward.','Prior attention events before attention-start are not available; earliest windows are left-truncated.','Only prior-known data enter candidate features; event labels come from target date.','One-day rate denominator is candidate-stock/day exposures, not unique tickers.','If an official market source is unavailable, that market is excluded; results must not be interpreted as full-market rates.','Self-report events with ambiguous subjects are excluded and exported for manual audit.','A parsed announcement may be published after market hours; the study does not yet reconstruct exact intraday information availability.','Cross-analysis rows with fewer than 30 stock-days or fewer than 5 distinct days are exploratory only.','Rates describe stock-day exposures, which are correlated within ticker and should not be interpreted as independent trials.','The risk set includes only stocks with recent attention; event coverage must be audited before claiming population recall.']}
    (out/'research_metadata.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
