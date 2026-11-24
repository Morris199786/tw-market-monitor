#!/usr/bin/env python3
"""Incremental SOX archive refresh. Never rebuild the 2008+ archive implicitly."""
import argparse
import json
import os
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from backfill_sox_history import OUT, NY, TW, retry, fetch_yahoo, fetch_fred, positive, indicators


def refresh(path, now=None):
    import pandas_market_calendars as mcal
    now=now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError('Timezone-aware clock required')
    archive=json.loads(path.read_text(encoding='utf-8'))
    if archive.get('schema')!=1 or archive.get('symbol')!='^SOX':
        raise ValueError('Invalid SOX archive; run manual backfill first')
    previous=archive['rows']
    dates=[r['date'] for r in previous]
    if len(dates)<61 or dates!=sorted(set(dates)) or any(positive(r.get('close')) is None for r in previous):
        raise ValueError('Invalid or incomplete SOX archive; manual repair required')
    old={r['date']:r for r in previous}
    last=date.fromisoformat(dates[-1]); today=now.astimezone(NY).date()
    # Fetch five recent completed sessions, plus any sessions missed since last save.
    # Historical data is never downloaded again in this workflow.
    start=min(last-timedelta(days=14),today-timedelta(days=14))
    end=today+timedelta(days=14)
    sched=mcal.get_calendar('NASDAQ').schedule(start_date=start,end_date=end)
    sessions=[]
    for d,row in sched.iterrows():
        closed=row['market_close'].to_pydatetime()
        # Nasdaq index corrections can continue to 17:15 ET. On short sessions
        # conservatively use the same local cutoff; also respect actual close.
        local=closed.astimezone(NY)
        ready=max(closed,local.replace(hour=17,minute=15,second=0,microsecond=0))
        sessions.append(dict(date=d.date().isoformat(),closed_at=closed.astimezone(TW).isoformat(),ready_at=ready.astimezone(TW).isoformat()))
    ready=[s for s in sessions if datetime.fromisoformat(s['ready_at'])<=now]
    if not ready:raise ValueError('No finalized SOX sessions')
    expected=ready[-1]['date']
    if expected<dates[-1]:raise ValueError('Refusing to truncate archive or use unfinished bar')
    recent=[s for s in ready if s['date']>=ready[-5]['date'] or s['date']>dates[-1]] if len(ready)>=5 else ready
    a=date.fromisoformat(recent[0]['date']);b=date.fromisoformat(expected)
    errors={}; sources={}
    for name,fetch in [('yahoo',fetch_yahoo),('fred',fetch_fred)]:
        try:sources[name]=retry(lambda:fetch(a,b))
        except Exception as exc:errors[name]=str(exc);sources[name]={}
    # Keep older rows byte-equivalent as objects; only touch fetched recent dates.
    revised=dict(old); conflicts=[]; missing=[]
    observed=now.astimezone(TW).isoformat()
    for session in recent:
        d=session['date']; prior=old.get(d,{})
        y=sources['yahoo'].get(d,{});yc=positive(y.get('close'));f=positive(sources['fred'].get(d));fresh_f=f is not None
        if yc is None and f is None:
            if not prior:missing.append(d)
            continue
        # When Yahoo is temporarily unavailable, don't overwrite its known OHLC
        # with a later FRED-only bar. FRED is a fallback for a new date.
        old_y=positive(prior.get('close')) if prior.get('close_source')=='yahoo' else None
        close=yc if yc is not None else old_y if old_y is not None else f
        source='yahoo' if yc is not None or old_y is not None else 'fred'
        if f is None and prior.get('fred_close') is not None:f=positive(prior['fred_close'])
        conflict=f is not None and abs(close/f-1)>.001
        if conflict:conflicts.append(dict(date=d,yahoo=close,fred=f))
        bar=y if yc is not None else prior if old_y is not None else {}
        prices={k:positive(bar.get(k)) for k in ('open','high','low')}
        if all(v is not None for v in prices.values()) and (prices['high']<max(prices['open'],close)-.02 or prices['low']>min(prices['open'],close)+.02 or prices['low']>prices['high']):
            prices=dict(open=None,high=None,low=None)
        row=dict(prior,date=d,available_at=session['closed_at'],**prices,close=close,close_source=source,fred_close=f,close_verified=f is not None and not conflict,close_conflict=conflict)
        # First post-finalization observation or changed source/price, not every run.
        old_observed=prior.get('observed_at')
        if not old_observed or datetime.fromisoformat(old_observed)<datetime.fromisoformat(session['ready_at']) or any(row.get(k)!=prior.get(k) for k in ('close','close_source','open','high','low','close_conflict')):
            # Only a fresh vendor observation can qualify the stored close.
            if yc is not None or (fresh_f and (source=='fred' or not conflict)):
                row['observed_at']=observed
        revised[d]=row
    if missing or expected not in revised:
        raise RuntimeError(f'Latest SOX sessions missing: {missing}; previous archive preserved')
    # Do not accept an archive with an undetected gap since last saved session.
    if any(s['date'] not in revised for s in ready if s['date']>dates[-1]):raise RuntimeError('Missing new SOX sessions')
    rows=[revised[d] for d in sorted(revised)]
    # Recompute indicators locally on all stored closes, never download old prices.
    # Preserve old rows outside the affected range, including verification metadata.
    idx=next(i for i,r in enumerate(rows) if r['date']>=recent[0]['date'])
    work=[dict(r) for r in rows[max(0,idx-60):]]
    indicators(work,{r['date']:None for r in work})
    lookup={r['date']:r for r in work}
    rows=[lookup[r['date']] if i>=idx else r for i,r in enumerate(rows)]
    # Calendar covers the latest past session and upcoming holidays. Stable anchor
    # on the last ready date prevents rewriting unchanged data on repeat runs.
    anchor=date.fromisoformat(expected)
    cal_start=anchor-timedelta(days=7);cal_end=anchor+timedelta(days=14)
    cal_sched=mcal.get_calendar('NASDAQ').schedule(start_date=cal_start,end_date=cal_end)
    cal_rows=[]
    for d,row in cal_sched.iterrows():
        closed=row['market_close'].to_pydatetime();local=closed.astimezone(NY)
        final=max(closed,local.replace(hour=17,minute=15,second=0,microsecond=0))
        cal_rows.append(dict(date=d.date().isoformat(),closed_at=closed.astimezone(TW).isoformat(),ready_at=final.astimezone(TW).isoformat()))
    from datetime import time
    archive['daily_calendar']=dict(valid_from=datetime.combine(cal_start,time.min,NY).astimezone(TW).isoformat(),valid_until=datetime.combine(cal_end,time.max,NY).astimezone(TW).isoformat(),sessions=cal_rows)
    archive.update(rows=rows,as_of_date=rows[-1]['date'])
    quality=dict(archive.get('quality',{}));quality.update(expected_sessions=max(len(rows),int(quality.get('expected_sessions',0))),actual_sessions=len(rows),missing_dates=[d for d in quality.get('missing_dates',[]) if d not in revised],fred_verified=sum(bool(r.get('close_verified')) for r in rows),incomplete_ohlc_dates=[r['date'] for r in rows if any(r.get(k) is None for k in ('open','high','low'))],close_conflicts=[dict(date=r['date'],yahoo=r['close'],fred=r.get('fred_close')) for r in rows if r.get('close_conflict')],daily_source_errors=errors)
    archive['quality']=quality
    before=path.read_text(encoding='utf-8'); after=json.dumps(archive,ensure_ascii=False,allow_nan=False,separators=(',',':'))+'\n'
    if json.loads(before)!=archive:
        tmp=path.with_suffix('.json.tmp');tmp.write_text(after,encoding='utf-8');os.replace(tmp,path)
        print(f'SOX_UPDATED {expected} ({len(recent)} sessions requested)')
    else:print(f'SOX_UNCHANGED {expected}')
    latest=rows[-1]
    if latest.get('close_conflict') or not latest.get('observed_at') or datetime.fromisoformat(latest['observed_at'])<datetime.fromisoformat(ready[-1]['ready_at']):
        raise RuntimeError('Latest close not verified as usable after finalization; K20 must fall back')
    print(f"SOX_READY {expected} return20={latest.get('return20')} source={latest.get('close_source')}")
    return archive

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,default=OUT);args=parser.parse_args();refresh(args.output)
