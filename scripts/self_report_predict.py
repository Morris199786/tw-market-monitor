#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Self-report forecast: time-ordered, market-specific candidate calibration.
No API credits, Telegram, or live self-report collector changes.
"""
import argparse
import collections
import csv
import datetime as dt
import json
import os
import re
import urllib.request
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
TZ = ZoneInfo('Asia/Taipei')
VERSION = '2026-10-20-walkforward-market-pattern-v5'
CAP = 10
MIN_PROBABILITY = .15
MARKET_RULES = {
    'twse': '前日注意交易；分開評估20日首次、重複注意、注意原因及公告冷卻期',
    'tpex': '前日注意交易；分開評估5日1次、2次、3次以上及公告冷卻期',
}

def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))

def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + '.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    temp.replace(path)

def csvout(path, rows):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text('', encoding='utf-8')
        return
    keys = list(dict.fromkeys(k for r in rows for k in r))
    with path.open('w', newline='', encoding='utf-8-sig') as stream:
        writer = csv.DictWriter(stream, fieldnames=keys, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(rows)

def notice_date(value):
    m = re.search(r'(\d{2,4})[./-](\d{1,2})[./-](\d{1,2})', str(value))
    if not m:
        return None
    year = int(m[1]); year += 1911 if year < 1911 else 0
    try:
        return dt.date(year, int(m[2]), int(m[3])).isoformat()
    except ValueError:
        return None

def parse_notices(obj, market, start, end):
    table = (obj.get('tables') or [{}])[0]
    fields = obj.get('fields') or table.get('fields') or []
    data = obj.get('data') or table.get('data') or []
    def col(pattern, fallback):
        return next((i for i, name in enumerate(fields) if re.search(pattern, str(name))), fallback)
    ti, ni, ri, di = col('證券代號|股票代號', 1), col('證券名稱|股票名稱', 2), col('注意交易資訊|注意原因', 4), col('日期', 5)
    result = {}
    for row in data:
        if not isinstance(row, list) or len(row) <= max(ti, ni, ri, di):
            continue
        ticker, day = str(row[ti]).strip(), notice_date(row[di])
        if not re.fullmatch(r'[1-9]\d{3}', ticker) or not day or not start <= day <= end:
            continue
        key = (day, ticker)
        if key in result:
            result[key]['reason'] += ' ' + str(row[ri])
        else:
            result[key] = dict(date=day, ticker=ticker, name=str(row[ni]), market=market, reason=str(row[ri]))
    if not result:
        raise RuntimeError(f'{market}: official attention records unavailable')
    return list(result.values())

def attention(start, end, cache=None, markets=('twse', 'tpex')):
    urls = {
        'twse': f'https://www.twse.com.tw/rwd/zh/announcement/notice?response=json&startDate={start.replace("-", "")}&endDate={end.replace("-", "")}',
        'tpex': f'https://www.tpex.org.tw/www/zh-tw/bulletin/attention?startDate={start.replace("-", "/")}&endDate={end.replace("-", "/")}&response=json',
    }
    result, status = [], {}
    for market in markets:
        if cache:
            obj = read(Path(cache) / f'{market}.json')
        else:
            request = urllib.request.Request(urls[market], headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(request, timeout=45) as response:
                obj = json.load(response)
        rows = parse_notices(obj, market, start, end)
        result.extend(rows)
        status[market] = dict(ok=True, rows=len(rows), source=urls[market], offline=bool(cache))
    return result, status

def reports(path, master, markets):
    data = read(path)
    raw = data.get('items', []) + data.get('parse_failed', []) + data.get('diagnostics', {}).get('parse_failed', [])
    events, audit = {}, []
    for x in raw:
        ticker, day = str(x.get('ticker', '')), str(x.get('publish_date', ''))
        subject, reason = str(x.get('subject') or ''), x.get('match_reason')
        market = master.get(ticker, {}).get('market')
        month = x.get('monthly_period')
        month = month if re.fullmatch(r'20\d\d-(0[1-9]|1[0-2])', str(month or '')) else None
        attention_event = reason == 'attention_trading' and bool(re.search(r'注意交易|注意股|達公[布佈]注意', subject))
        voluntary = reason == 'direct_self_report' and bool(re.search(r'自結|自編|自行結算', subject))
        excluded = None
        if market not in markets:
            excluded = '非本次上市上櫃範圍'
        elif re.search(r'公司債|資金貸與|背書保證|取得或處分資產|衍生性商品', subject):
            excluded = '非個股單月自結'
        elif not (attention_event or voluntary):
            excluded = '公告種類需人工確認'
        elif voluntary and not month:
            excluded = '自主公告未確認單月期間'
        elif not re.fullmatch(r'20\d\d-\d\d-\d\d', day):
            excluded = '日期無效'
        if excluded:
            audit.append(dict(date=day, ticker=ticker, reason=excluded, subject=subject))
            continue
        key = (ticker, month or day)
        item = dict(date=day, ticker=ticker, month=month, market=market,
                    kind='attention' if attention_event else 'voluntary', name=x.get('name', ''),
                    monthly_eps=x.get('monthly_eps'), quarter_eps=x.get('quarter_eps'))
        if key not in events or day < events[key]['date']:
            events[key] = item
    return sorted(events.values(), key=lambda x: (x['date'], x['ticker'])), audit

def calendar(root, start, end, notices):
    obj = read(root / 'data/market_monitor.json')
    days = {x['date'] for x in obj.get('raw', []) if x.get('index') is not None}
    days.update(p.stem for p in (root / 'data/history/market').glob('????-??-??.json'))
    days.update(x['date'] for x in notices)
    days = sorted(x for x in days if start <= x <= end)
    if len(days) < 20:
        raise ValueError('交易日曆不足20日')
    return days

def previous_month(day):
    return (dt.date.fromisoformat(day).replace(day=1) - dt.timedelta(days=1)).strftime('%Y-%m')

def bucket(row):
    if row['market'] == 'twse':
        return '20d=1' if row['n20'] == 1 else '20d=2' if row['n20'] == 2 else '20d>=3'
    return '5d=1' if row['n5'] == 1 else '5d=2' if row['n5'] == 2 else '5d>=3'

def eligible(row):
    if row['n1'] == 0:
        return False
    if row['days_since_report'] is not None and row['days_since_report'] <= 5:
        return False
    # Unlike v4, don't discard all repeated TWSE attention cases or first TPEx notices.
    # Probability + chronological calibration decides whether to include them.
    return True

def make_rows(cutoff, target, cal, notices, events, master):
    past = [d for d in cal if d <= cutoff]
    windows = {n: set(past[-n:]) for n in (1, 3, 5, 10, 20)}
    by_ticker, prior = collections.defaultdict(list), collections.defaultdict(list)
    for x in notices:
        if x['date'] <= cutoff:
            by_ticker[x['ticker']].append(x)
    for x in events:
        if x['date'] <= cutoff:
            prior[x['ticker']].append(x)
    pool = set(by_ticker) | {t for t, items in prior.items() if any(x['kind'] == 'voluntary' for x in items)}
    labels = {x['ticker'] for x in events if x['date'] == target}
    out = []
    for ticker in sorted(pool):
        if ticker not in master:
            continue
        hist = sorted(by_ticker[ticker], key=lambda x: x['date'])
        history = prior[ticker]
        if any(x['month'] == previous_month(target) for x in history):
            continue
        last_report = max((x['date'] for x in history), default=None)
        report_gap = (dt.date.fromisoformat(cutoff) - dt.date.fromisoformat(last_report)).days if last_report else None
        if any(x['month'] is None and x['date'] >= (dt.date.fromisoformat(cutoff) - dt.timedelta(days=5)).isoformat() for x in history):
            continue
        counts = {f'n{n}': sum(x['date'] in ds for x in hist) for n, ds in windows.items()}
        if not counts['n20'] and not any(x['kind'] == 'voluntary' for x in history):
            continue
        gap = sum(d > hist[-1]['date'] for d in past) if hist else 99
        recent = 0 if gap == 0 else 1 if gap <= 2 else 2 if gap <= 5 else 3
        cooldown = '0-5' if report_gap is not None and report_gap <= 5 else '6-10' if report_gap is not None and report_gap <= 10 else '11+' if report_gap is not None else 'never'
        reason6 = sum(bool(x['date'] in windows[10] and re.search(r'第\s*[六6]\s*款', x['reason'])) for x in hist)
        row = dict(date=target, cutoff=cutoff, ticker=ticker, name=master[ticker].get('name', ticker),
                   market=master[ticker]['market'], label=int(ticker in labels), recent=recent,
                   gap=gap, cooldown=cooldown, days_since_report=report_gap, reason6=reason6, **counts)
        row['market_pattern'] = bucket(row)
        row['rule_eligible'] = eligible(row)
        row['reason6_flag'] = int(reason6 > 0)
        row['notice_intensity'] = 'high' if counts['n5'] >= 3 else 'mid' if counts['n5'] == 2 else 'low'
        out.append(row)
    return out

class Model:
    # All statistics computed only from days strictly preceding prediction day.
    LEVELS = (('market',), ('market', 'market_pattern'),
              ('market', 'market_pattern', 'reason6_flag'),
              ('market', 'market_pattern', 'cooldown'),
              ('market', 'notice_intensity', 'reason6_flag'))
    PRIOR_WEIGHT = 24
    def __init__(self, rows):
        self.base = (sum(r['label'] for r in rows) + 1) / (len(rows) + 20)
        self.stats = []
        for keys in self.LEVELS:
            groups = collections.defaultdict(lambda: [0, 0])
            for row in rows:
                if not row['rule_eligible']:
                    continue
                cell = groups[tuple(row[k] for k in keys)]
                cell[0] += row['label']; cell[1] += 1
            self.stats.append(groups)
    def predict(self, row):
        p = self.base
        support = 0
        for keys, groups in zip(self.LEVELS, self.stats):
            hits, n = groups.get(tuple(row[k] for k in keys), (0, 0))
            if n:
                estimate = (hits + self.PRIOR_WEIGHT * p) / (n + self.PRIOR_WEIGHT)
                # Don't let a tiny last-level group override a larger reliable parent.
                p = (p + estimate) / 2 if n < 12 else estimate
                support = max(support, n)
        return p, support

def choose(rows, threshold=MIN_PROBABILITY):
    return sorted((r for r in rows if r['rule_eligible'] and r['probability'] >= threshold),
                  key=lambda r: (-r['probability'], -r['cell_samples'], r['ticker']))[:CAP]

def metrics(predictions, actual):
    n = len(predictions); hits = sum(x['label'] for x in predictions)
    return dict(hits=hits, predictions=n, actual=actual,
                precision=hits/n if n else None, recall=hits/actual if actual else None,
                f1=2*hits/(n+actual) if n+actual else None)

def evaluate(day_rows, events):
    training, daily, picks_all, scores_all, baseline_all = [], [], [], [], []
    evaluated_days = set()
    for day, rows in sorted(day_rows.items()):
        enough = len({r['date'] for r in training}) >= 5 and sum(r['label'] for r in training) >= 15
        if enough:
            model = Model(training)
            scored = []
            for row in rows:
                p, support = model.predict(row)
                scored.append(dict(row, probability=p, cell_samples=support))
            picks = choose(scored)
            baseline = sorted((r for r in rows if r['rule_eligible'] and (r['n20'] == 1 if r['market'] == 'twse' else r['n5'] >= 3)),
                              key=lambda r: (-r['n5'], r['ticker']))[:CAP]
            baseline_all.extend(baseline)
            actual_codes = {e['ticker'] for e in events if e['date'] == day}
            predicted_codes = {r['ticker'] for r in picks}
            daily.append(dict(date=day, threshold=MIN_PROBABILITY, **metrics(picks, len(actual_codes)),
                              eligible_candidates=sum(r['rule_eligible'] for r in rows),
                              tickers=' '.join(r['ticker'] for r in picks),
                              hit_tickers=' '.join(sorted(predicted_codes & actual_codes)),
                              missed_tickers=' '.join(sorted(actual_codes - predicted_codes)),
                              baseline_hits=sum(r['label'] for r in baseline), baseline_predictions=len(baseline)))
            picks_all.extend(picks); scores_all.extend(scored); evaluated_days.add(day)
        training.extend(rows)
    actual = sum(len({e['ticker'] for e in events if e['date'] == day}) for day in evaluated_days)
    summary = dict(model=metrics(picks_all, actual), baseline_same_dates=metrics(baseline_all, actual),
                   evaluated_days=len(daily), warmup_days=len(day_rows)-len(daily),
                   first_evaluated_date=daily[0]['date'] if daily else None,
                   last_evaluated_date=daily[-1]['date'] if daily else None,
                   daily_pick_counts=[dict(date=x['date'], count=x['predictions']) for x in daily])
    for market in ('twse', 'tpex'):
        count = sum(len({e['ticker'] for e in events if e['date'] == day and e['market'] == market}) for day in evaluated_days)
        summary[market] = metrics([r for r in picks_all if r['market'] == market], count)
    return summary, daily, picks_all, training, scores_all

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, default=ROOT)
    parser.add_argument('--start', default='2026-09-01')
    parser.add_argument('--backtest-start', default='2026-09-29')
    parser.add_argument('--asof', default='')
    parser.add_argument('--reports', default='data/self_reports_history.json')
    parser.add_argument('--out', default='self_report_model')
    parser.add_argument('--backtest', action='store_true')
    parser.add_argument('--attention-cache', type=Path)
    parser.add_argument('--markets', choices=['both', 'twse', 'tpex'], default='both')
    parser.add_argument('--prediction-date', default='')
    args = parser.parse_args()
    now = dt.datetime.now(TZ)
    latest_complete = (now.date() - dt.timedelta(days=1)).isoformat()
    requested = args.asof or latest_complete
    end = min(requested, latest_complete)
    markets = ('twse', 'tpex') if args.markets == 'both' else (args.markets,)
    out = args.root / args.out
    out.mkdir(parents=True, exist_ok=True)
    notices, status = attention(args.start, end, args.attention_cache, markets)
    master = read(args.root / 'data/master.json')['stocks']
    events, rejected = reports(args.root / args.reports, master, markets)
    events = [x for x in events if x['date'] <= end]
    cal = calendar(args.root, args.start, end, notices)
    cutoff = cal[-1]
    days = [d for d in cal if args.backtest_start <= d <= end]
    rows = {d: make_rows(cal[cal.index(d)-1], d, cal, notices, events, master)
            for d in days if cal.index(d) > 0}
    summary, daily, picks, training, scores = evaluate(rows, events)
    future_known = sorted({x['date'] for x in read(args.root / 'data/market_monitor.json').get('raw', [])
                           if x.get('index') is not None and x['date'] > cutoff})
    target = args.prediction_date or (future_known[0] if future_known else None)
    if target and target <= cutoff:
        raise ValueError('prediction-date must follow cutoff')
    provisional = target or (dt.date.fromisoformat(cutoff) + dt.timedelta(days=1)).isoformat()
    candidates = make_rows(cutoff, provisional, cal, notices, events, master)
    enough = len(rows) >= 5 and sum(r['label'] for r in training) >= 15
    forecast = []
    if enough and (target or provisional[:7] == cutoff[:7]):
        model = Model(training)
        for row in candidates:
            p, support = model.predict(row)
            reasons = [f'最近注意交易距今{row["gap"]}交易日',
                       f'近3日注意{row["n3"]}次、近5日注意{row["n5"]}次、近20日注意{row["n20"]}次',
                       MARKET_RULES.get(row['market'], '未知市場'),
                       '無歷史自結' if row['days_since_report'] is None else f'距前次自結{row["days_since_report"]}天']
            clean = {k: v for k, v in row.items() if k not in ('label', 'date')}
            clean.update(probability=p, score=round(p*100, 2), cell_samples=support, reasons=reasons)
            forecast.append(clean)
        forecast = choose(forecast)
    warnings = [
        '新模型將上市重複注意及上櫃首次注意納入候選，再依歷史條件機率篩選',
        '每日0至10檔，不強制補滿；最低估計機率15%',
        '回測按日期順序訓練；新規則仍需與既有版本在相同期間比較，不能保證改善',
        '自結標籤依MOPS解析結果；公告漏抓會影響Precision與Recall',
    ]
    if not target:
        warnings.append('下一交易日尚未由正式交易日曆確認，日期暫不標示')
    summary.update(version=VERSION, source_status=status, asof=cutoff,
                   requested_asof=requested, incomplete_current_day_excluded=requested > latest_complete,
                   scope=args.markets, warnings=warnings, future_threshold=MIN_PROBABILITY,
                   model_ready=enough, training_events=sum(r['label'] for r in training),
                   event_count=sum(args.backtest_start <= e['date'] <= end for e in events),
                   market_rules=MARKET_RULES)
    obj = dict(version=VERSION, updated_at=now.isoformat(timespec='seconds'),
               asof=cutoff, prediction_day=target, prediction_window='下一交易日',
               count=len(forecast), model='market-pattern-hierarchical-walkforward',
               threshold=MIN_PROBABILITY, items=forecast, candidates=forecast,
               source_status=status, evaluation=summary, warnings=warnings)
    write(out / 'predictions.json', obj)
    write(out / 'backtest_summary.json', summary)
    csvout(out / 'backtest_daily.csv', daily)
    csvout(out / 'backtest_picks.csv', picks)
    csvout(out / 'walk_forward_scores.csv', scores)
    csvout(out / 'event_audit.csv', events)
    csvout(out / 'excluded_announcements.csv', rejected)
    csvout(out / 'predictions.csv', forecast)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print('Next-session picks:', ' '.join(x['ticker'] for x in forecast) or 'none')
    summary_path = os.environ.get('GITHUB_STEP_SUMMARY')
    if summary_path:
        def percent(value):
            return '—' if value is None else f'{value:.1%}'
        with open(summary_path, 'a', encoding='utf-8') as stream:
            stream.write('\n## 自結預測驗證｜上市與上櫃分流\n\n')
            stream.write(f'資料截至 {cutoff}；每日符合條件才推薦（0至10檔）\n\n')
            stream.write('| 市場 | 推薦 | 命中 | Precision | Recall |\n|---|---:|---:|---:|---:|\n')
            for market, name in [('twse', '上市'), ('tpex', '上櫃'), ('model', '合計')]:
                m = summary[market]
                stream.write(f'| {name} | {m["predictions"]} | {m["hits"]} | {percent(m["precision"])} | {percent(m["recall"])} |\n')
            stream.write('\n新模型放寬候選但以條件機率控制推薦；請以實際回測數字判斷是否升版\n')
            stream.write('\n下一交易日候選：' + (', '.join(x['ticker'] for x in forecast) or '無') + '\n')

if __name__ == '__main__':
    main()
