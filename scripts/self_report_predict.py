#!/usr/bin/env python3
"""Next-session monthly self-report prediction. No notifications or paid API calls.
Standard-library-only, chronological evaluation; at most ten picks across both markets.
"""
import argparse
import collections
import csv
import datetime as dt
import json
import math
import re
import urllib.request
from pathlib import Path
from zoneinfo import ZoneInfo

VERSION = '2026-10-20-walk-forward-monthly-v1'
ROOT = Path(__file__).resolve().parents[1]
TZ = ZoneInfo('Asia/Taipei')
CAP = 10
THRESHOLDS = (0.10, 0.15, 0.20, 0.25, 0.30, 0.40, 0.50)


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def write(path, value):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    tmp.replace(path)


def csvout(path, rows):
    if not rows:
        Path(path).write_text('', encoding='utf-8'); return
    with open(path, 'w', encoding='utf-8-sig', newline='') as stream:
        w = csv.DictWriter(stream, fieldnames=list(rows[0]), extrasaction='ignore')
        w.writeheader(); w.writerows(rows)


def notice_date(value):
    m = re.search(r'(\d{2,4})[./-](\d{1,2})[./-](\d{1,2})', str(value))
    if not m: return None
    y = int(m[1]); y += 1911 if y < 1911 else 0
    try: return dt.date(y, int(m[2]), int(m[3])).isoformat()
    except ValueError: return None


def parse_notices(obj, market, start, end):
    table = (obj.get('tables') or [{}])[0]
    fields = obj.get('fields') or table.get('fields') or []
    rows = obj.get('data') or table.get('data') or []
    def col(pattern, fallback):
        return next((i for i, f in enumerate(fields) if re.search(pattern, str(f))), fallback)
    ti, ni, ri, di = col('證券代號', 1), col('證券名稱', 2), col('注意交易資訊|注意原因', 4), col('日期', 5)
    found = {}
    for row in rows:
        if not isinstance(row, list) or len(row) <= max(ti, ni, ri, di): continue
        ticker = str(row[ti]).strip(); date = notice_date(row[di])
        if not re.fullmatch(r'[1-9]\d{3}', ticker) or not date or not start <= date <= end: continue
        found[(date, ticker)] = dict(date=date, ticker=ticker, name=str(row[ni]), market=market, reason=str(row[ri]))
    if not found: raise ValueError(f'{market}: official attention response empty/unparsed')
    return sorted(found.values(), key=lambda x: (x['date'], x['ticker']))


def attention(start, end, cache=None, markets=('twse', 'tpex')):
    urls = {
        'twse': f'https://www.twse.com.tw/rwd/zh/announcement/notice?response=json&startDate={start.replace("-", "")}&endDate={end.replace("-", "")}',
        'tpex': f'https://www.tpex.org.tw/www/zh-tw/bulletin/attention?startDate={start.replace("-", "/")}&endDate={end.replace("-", "/")}&response=json',
    }
    result, status = [], {}
    for market in markets:
        if cache:
            obj = read(Path(cache) / (market + '.json'))
        else:
            req = urllib.request.Request(urls[market], headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=45) as response: obj = json.load(response)
        rows = parse_notices(obj, market, start, end)
        result.extend(rows); status[market] = dict(ok=True, rows=len(rows), source=urls[market], offline=bool(cache))
    # Missing one market aborts production; never replace a complete forecast with partial data.
    return result, status


def reports(path, master, markets):
    data = read(path)
    raw = data.get('items', []) + data.get('parse_failed', []) + data.get('diagnostics', {}).get('parse_failed', [])
    events, audit = {}, []
    for x in raw:
        ticker, day = str(x.get('ticker', '')), str(x.get('publish_date', ''))
        subject = str(x.get('subject') or '')
        reason = x.get('match_reason')
        market = master.get(ticker, {}).get('market')
        month = x.get('monthly_period')
        month = month if re.fullmatch(r'20\d\d-(0[1-9]|1[0-2])', str(month or '')) else None
        attention_event = reason == 'attention_trading' and bool(re.search(r'注意交易|注意股|達公[布佈]注意', subject))
        voluntary = reason == 'direct_self_report' and bool(re.search(r'自結|自編|自行結算', subject))
        excluded = None
        if market not in markets: excluded = '非本次上市上櫃範圍'
        elif re.search(r'公司債|資金貸與|背書保證|取得或處分資產|衍生性商品', subject): excluded = '非個股單月自結'
        elif not (attention_event or voluntary): excluded = '公告種類需人工確認'
        elif voluntary and not month: excluded = '自主公告未確認單月期間（可能是季度自結）'
        elif not re.fullmatch(r'20\d\d-\d\d-\d\d', day): excluded = '日期無效'
        if excluded:
            audit.append(dict(date=day, ticker=ticker, reason=excluded, subject=subject)); continue
        # EPS need not parse: an actual announcement is still a positive event.
        # Same stock/month is one event, retaining earliest publication, not later corrections.
        key = (ticker, month or day)
        item = dict(date=day, ticker=ticker, month=month, market=market,
                    kind='attention' if attention_event else 'voluntary', name=x.get('name', ''),
                    monthly_eps=x.get('monthly_eps'), quarter_eps=x.get('quarter_eps'))
        if key not in events or day < events[key]['date']: events[key] = item
    return sorted(events.values(), key=lambda x: (x['date'], x['ticker'])), audit


def calendar(root, start, end, notices):
    # Recorded exchange sessions, not weekdays (9/25, 9/28, 10/9 are not silently added).
    obj = read(root / 'data/market_monitor.json')
    days = {x['date'] for x in obj.get('raw', []) if x.get('index') is not None}
    days.update(p.stem for p in (root / 'data/history/market').glob('????-??-??.json'))
    days.update(x['date'] for x in notices)
    days = sorted(d for d in days if start <= d <= end)
    if len(days) < 20: raise ValueError('Insufficient exchange-session calendar; need at least 20 sessions')
    return days


def previous_month(day):
    d = dt.date.fromisoformat(day).replace(day=1) - dt.timedelta(days=1)
    return d.strftime('%Y-%m')


def make_rows(cutoff, target, cal, notices, events, master):
    past = [d for d in cal if d <= cutoff]
    windows = {n: set(past[-n:]) for n in (1, 3, 5, 10, 20)}
    by_ticker = collections.defaultdict(list)
    for x in notices:
        if x['date'] <= cutoff: by_ticker[x['ticker']].append(x)
    prior = collections.defaultdict(list)
    for x in events:
        if x['date'] <= cutoff: prior[x['ticker']].append(x)
    # Known voluntary reporters enter even without attention. Cold-start misses remain in recall.
    pool = set(by_ticker) | {c for c, xs in prior.items() if any(x['kind'] == 'voluntary' for x in xs)}
    labels = {x['ticker'] for x in events if x['date'] == target}
    out = []
    for c in sorted(pool):
        if c not in master: continue
        hist = sorted(by_ticker[c], key=lambda x: x['date'])
        history = prior[c]
        if any(x['month'] == previous_month(target) for x in history): continue
        counts = {f'n{n}': sum(x['date'] in ds for x in hist) for n, ds in windows.items()}
        if not counts['n20'] and not any(x['kind'] == 'voluntary' for x in history): continue
        gap = sum(d > hist[-1]['date'] for d in past) if hist else 99
        recent = 0 if gap == 0 else 1 if gap <= 2 else 2 if gap <= 5 else 3
        elapsed = (dt.date.fromisoformat(cutoff) - dt.date.fromisoformat(history[-1]['date'])).days if history else 999
        cooldown = 0 if elapsed <= 5 else 1 if elapsed <= 15 else 2 if elapsed < 999 else 3
        density = min(counts['n3'], 3)
        reason6 = sum(bool(x['date'] in windows[10] and re.search(r'第\s*[六6]\s*款', x['reason'])) for x in hist)
        out.append(dict(date=target, cutoff=cutoff, ticker=c, name=master[c].get('name', c),
                        market=master[c]['market'], label=int(c in labels), recent=recent,
                        density=density, cooldown=cooldown, reason6=reason6, gap=gap,
                        days_since_report=None if elapsed == 999 else elapsed, **counts))
    return out


class Model:
    """Fixed hierarchical bins; small market-specific cells shrink toward shared observations.
    No ticker identity, future prices, or same-day announcement features.
    """
    levels = (('recent',), ('market', 'recent'), ('market', 'recent', 'density'),
              ('market', 'recent', 'density', 'cooldown'))

    def __init__(self, rows):
        self.base = (sum(r['label'] for r in rows) + 1) / (len(rows) + 20)
        self.stats = []
        for keys in self.levels:
            group = collections.defaultdict(lambda: [0, 0])
            for r in rows:
                cell = group[tuple(r[k] for k in keys)]; cell[0] += r['label']; cell[1] += 1
            self.stats.append(group)

    def predict(self, r):
        p, n = self.base, 0
        for keys, group in zip(self.levels, self.stats):
            hits, n = group.get(tuple(r[k] for k in keys), (0, 0))
            p = (hits + 30 * p) / (n + 30)
        return p, n


def choose(rows, threshold):
    return sorted((r for r in rows if r['probability'] >= threshold),
                  key=lambda r: (-r['probability'], r['ticker']))[:CAP]


def metrics(predictions, actual):
    n = len(predictions); hits = sum(x['label'] for x in predictions)
    precision = hits / n if n else None; recall = hits / actual if actual else None
    f1 = 2 * hits / (n + actual) if n + actual else None
    return dict(hits=hits, predictions=n, actual=actual, precision=precision, recall=recall, f1=f1)


def threshold_from_past(scored_days, actual_by_day):
    # Calibration uses only earlier walk-forward predictions, never the scored day's outcomes.
    if len(scored_days) < 3: return 0.15
    total = sum(actual_by_day[d] for d in scored_days)
    options = []
    for t in THRESHOLDS:
        picks = [p for rows in scored_days.values() for p in choose(rows, t)]
        m = metrics(picks, total)
        # F1 balances precision/recall. A floor prevents forcing weak candidates to fill ten slots.
        options.append((m['f1'] or 0, m['precision'] or 0, t))
    return max(options)[2]


def evaluate(day_rows, events):
    training, prior_oof, daily, picks_all, scored_all, baseline_all = [], {}, [], [], [], []
    totals = {day: len({e['ticker'] for e in events if e['date'] == day}) for day in day_rows}
    for day, rows in sorted(day_rows.items()):
        enough = len({r['date'] for r in training}) >= 5 and sum(r['label'] for r in training) >= 15
        if enough:
            model = Model(training); threshold = threshold_from_past(prior_oof, totals)
            scored = []
            for r in rows:
                p, support = model.predict(r); scored.append(dict(r, probability=p, cell_samples=support))
            picks = choose(scored, threshold)
            # Old research rule, evaluated on exactly the same dates and candidate/event definition.
            baseline = sorted((r for r in rows if 2*r['n3']+r['n10']+r['reason6'] >= 7),
                              key=lambda r: (-(2*r['n3']+r['n10']+r['reason6']), r['ticker']))[:CAP]
            baseline_all.extend(baseline)
            actual_codes = {e['ticker'] for e in events if e['date'] == day}
            predicted_codes = {r['ticker'] for r in picks}
            daily.append(dict(date=day, threshold=threshold, **metrics(picks, totals[day]),
                              tickers=' '.join(r['ticker'] for r in picks),
                              hit_tickers=' '.join(sorted(predicted_codes & actual_codes)),
                              missed_tickers=' '.join(sorted(actual_codes - predicted_codes)),
                              baseline_hits=sum(r['label'] for r in baseline), baseline_predictions=len(baseline)))
            picks_all.extend(picks); scored_all.extend(scored); prior_oof[day] = scored
        training.extend(rows)
    total = sum(r['actual'] for r in daily)
    summary = dict(model=metrics(picks_all, total), baseline_same_dates=metrics(baseline_all, total),
                   evaluated_days=len(daily), warmup_days=len(day_rows)-len(daily),
                   first_evaluated_date=daily[0]['date'] if daily else None,
                   last_evaluated_date=daily[-1]['date'] if daily else None)
    for market in ('twse', 'tpex'):
        actual = sum(e['market'] == market and e['date'] in prior_oof for e in events)
        summary[market] = metrics([r for r in picks_all if r['market'] == market], actual)
    return summary, daily, picks_all, training, prior_oof, totals, scored_all


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--root', type=Path, default=ROOT)
    ap.add_argument('--start', default='2026-09-01')
    ap.add_argument('--backtest-start', default='2026-09-29')
    ap.add_argument('--asof', default='')
    ap.add_argument('--reports', default='data/self_reports_history.json')
    ap.add_argument('--out', default='self_report_model')
    ap.add_argument('--backtest', action='store_true')  # compatible; always run honest evaluation
    ap.add_argument('--attention-cache', type=Path)
    ap.add_argument('--markets', choices=['both', 'twse', 'tpex'], default='both', help='single-market research only')
    ap.add_argument('--prediction-date', default='', help='Confirmed next exchange session; blank = unconfirmed')
    a = ap.parse_args(); now = dt.datetime.now(TZ)
    # A whole day is not labeled negative while announcements are still arriving.
    latest_complete = (now.date() - dt.timedelta(days=1)).isoformat()
    requested = a.asof or latest_complete
    end = min(requested, latest_complete)
    markets = ('twse', 'tpex') if a.markets == 'both' else (a.markets,)
    out = a.root / a.out; out.mkdir(parents=True, exist_ok=True)
    notices, status = attention(a.start, end, a.attention_cache, markets)
    master = read(a.root / 'data/master.json')['stocks']
    events, rejected = reports(a.root / a.reports, master, markets)
    events = [x for x in events if x['date'] <= end]
    cal = calendar(a.root, a.start, end, notices); cutoff = cal[-1]
    days = [d for d in cal if a.backtest_start <= d <= end]
    rows = {d: make_rows(cal[cal.index(d)-1], d, cal, notices, events, master) for d in days if cal.index(d)>0}
    summary, daily, picks, training, oof, totals, scores = evaluate(rows, events)
    threshold = threshold_from_past(oof, totals)
    # Date must be confirmed from an official exchange calendar or a recorded later session.
    # Do not pretend next weekday is always a trading session.
    full_calendar = read(a.root / 'data/market_monitor.json').get('raw', [])
    future_known = sorted({x['date'] for x in full_calendar if x.get('index') is not None and x['date'] > cutoff})
    target = a.prediction_date or (future_known[0] if future_known else None)
    if target and target <= cutoff: raise ValueError('prediction-date must follow cutoff')
    # If next session unconfirmed at a month boundary, abstain (target month's exclusion is unknown).
    provisional = target or (dt.date.fromisoformat(cutoff) + dt.timedelta(days=1)).isoformat()
    candidates = make_rows(cutoff, provisional, cal, notices, events, master)
    enough = len(rows) >= 5 and sum(r['label'] for r in training) >= 15
    forecast = []
    if enough and (target or provisional[:7] == cutoff[:7]):
        model = Model(training)
        for r in candidates:
            p, support = model.predict(r)
            r = {k:v for k,v in r.items() if k not in ('label', 'date')}
            r.update(probability=p, score=round(p*100, 2), cell_samples=support,
                     reasons=[f'近3交易日注意{r["n3"]}次', f'近5交易日注意{r["n5"]}次',
                              '近期無自結紀錄' if r['days_since_report'] is None else f'距前次自結{r["days_since_report"]}天'])
            forecast.append(r)
        forecast = choose(forecast, threshold)
    warning = ['小樣本探索模型，估計機率未經獨立長期驗證',
               '回測只計算下一交易日新單月自結；同股票同月份更正不重複算命中',
               '歷史公告可能漏收；缺上一季EPS不排除事件',
               '目前主檔可能有存活者偏差；未知單月期間的注意公告以股票/日去重',
               '上市上櫃合計最多10檔；未達門檻不補滿',
               '每日期望提高命中率與召回率，但無法保證兩者同時改善']
    if not target: warning.append('下一交易日日期尚未確認，名單以最新完整交易日資料預測下一開市日')
    summary.update(version=VERSION, source_status=status, asof=cutoff, requested_asof=requested,
                   incomplete_current_day_excluded=requested > latest_complete, scope=a.markets,
                   warnings=warning, future_threshold=threshold,
                   model_ready=enough, training_events=sum(r['label'] for r in training),
                   event_count=sum(a.backtest_start<=e['date']<=end for e in events))
    forecast_obj = dict(version=VERSION, updated_at=now.isoformat(timespec='seconds'), asof=cutoff,
                        prediction_day=target, prediction_window='下一交易日', count=len(forecast),
                        model='market-shrunk-frequency', threshold=threshold, items=forecast,
                        candidates=forecast, source_status=status, evaluation=summary, warnings=warning)
    write(out/'predictions.json', forecast_obj); write(out/'backtest_summary.json', summary)
    csvout(out/'backtest_daily.csv', daily); csvout(out/'backtest_picks.csv', picks)
    csvout(out/'walk_forward_scores.csv', scores); csvout(out/'event_audit.csv', events)
    csvout(out/'excluded_announcements.csv', rejected); csvout(out/'predictions.csv', forecast)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print('Next-session picks:', ' '.join(x['ticker'] for x in forecast) or 'none')
    summary_path = __import__('os').environ.get('GITHUB_STEP_SUMMARY')
    if summary_path:
        def percent(x): return '—' if x is None else f'{x:.1%}'
        m=summary['model']; b=summary['baseline_same_dates']
        with open(summary_path, 'a', encoding='utf-8') as stream:
            stream.write(f'## 自結預測驗證\n\n資料截至 {cutoff}，每日合計最多10檔\n\n|模型|命中/推薦|命中率|召回率|F1|\n|---|---:|---:|---:|---:|\n')
            for name, v in [('逐日樣本外',m),('舊研究規則（同日期）',b)]:
                stream.write(f'|{name}|{v["hits"]}/{v["predictions"]}|{percent(v["precision"])}|{percent(v["recall"])}|{percent(v["f1"])}|\n')
            stream.write('\n注意：'+ '；'.join(warning)+'\n\n下一開市日名單：'+('、'.join(x['name']+' '+x['ticker'] for x in forecast) or '無符合門檻')+'\n')


if __name__ == '__main__': main()
