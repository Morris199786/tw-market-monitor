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
import http.client
import time
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
TZ = ZoneInfo('Asia/Taipei')
VERSION = '2026-10-21-listed-clause-probability-v15'
CAP = 10
MIN_PROBABILITY = .15
MARKET_RULES = {
    'twse': '近20日注意交易與款項機率評分；不以次數或前日注意硬性排除',
    'tpex': '前日注意；近5交易日注意剛好3次',
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

def fetch_json_retry(url, attempts=5):
    """Read the complete HTTP body, retrying truncated TWSE/TPEx responses."""
    last = None
    for attempt in range(attempts):
        try:
            request = urllib.request.Request(url, headers={
                'User-Agent': 'Mozilla/5.0', 'Accept': 'application/json',
                'Accept-Encoding': 'identity', 'Connection': 'close',
            })
            with urllib.request.urlopen(request, timeout=45) as response:
                payload = response.read()
            return json.loads(payload.decode('utf-8-sig'))
        except (http.client.IncompleteRead, OSError, TimeoutError,
                UnicodeDecodeError, json.JSONDecodeError) as exc:
            last = exc
            print(f'Attention download attempt {attempt+1}/{attempts} failed: {type(exc).__name__}: {exc}', flush=True)
            if attempt < attempts - 1:
                time.sleep(min(2 ** attempt, 8))
    raise RuntimeError(f'Official attention download failed after {attempts} attempts: {url}') from last


def attention(start, end, cache=None, markets=('twse', 'tpex')):
    def url_for(market, a, b):
        if market == 'twse':
            return f'https://www.twse.com.tw/rwd/zh/announcement/notice?response=json&startDate={a.replace("-", "")}&endDate={b.replace("-", "")}'
        return f'https://www.tpex.org.tw/www/zh-tw/bulletin/attention?startDate={a.replace("-", "/")}&endDate={b.replace("-", "/")}&response=json'

    result, status = [], {}
    cache_dir = Path(cache) if cache else ROOT / '.cache' / 'self_report_attention'
    cache_dir.mkdir(parents=True, exist_ok=True)
    for market in markets:
        cache_file = cache_dir / f'{market}_{start}_{end}.json'
        source = url_for(market, start, end)
        from_cache = False
        if cache_file.is_file():
            try:
                cached = read(cache_file)
                rows = cached['rows']
                if cached.get('market') != market or cached.get('start') != start or cached.get('end') != end or not rows:
                    raise ValueError('invalid attention cache')
                from_cache = True
            except (OSError, ValueError, KeyError, TypeError):
                cache_file.unlink(missing_ok=True)
                from_cache = False
        if not from_cache:
            try:
                rows = parse_notices(fetch_json_retry(source), market, start, end)
            except (RuntimeError, ValueError, KeyError) as exc:
                # Some official endpoints close long responses early. Smaller
                # date windows avoid truncation without silently losing records.
                print(f'{market}: full-range request failed; retrying in 14-day chunks: {exc}', flush=True)
                rows = []
                current = dt.date.fromisoformat(start)
                finish = dt.date.fromisoformat(end)
                while current <= finish:
                    chunk_end = min(current + dt.timedelta(days=13), finish)
                    a, b = current.isoformat(), chunk_end.isoformat()
                    try:
                        rows.extend(parse_notices(fetch_json_retry(url_for(market, a, b)), market, a, b))
                    except RuntimeError as e:
                        if 'official attention records unavailable' not in str(e):
                            raise
                    current = chunk_end + dt.timedelta(days=1)
                if not rows:
                    raise RuntimeError(f'{market}: no attention data in historical range')
            rows = list({(x['date'], x['ticker']): x for x in rows}.values())
            write(cache_file, {'market': market, 'start': start, 'end': end, 'rows': rows})
        result.extend(rows)
        status[market] = dict(ok=True, rows=len(rows), source=source, offline=from_cache)
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
    """Listed candidates use probability ranking; OTC structural rules unchanged."""
    if row['market'] == 'twse':
        return int(row.get('n20') or 0) >= 1
    if row['market'] == 'tpex':
        return int(row.get('n1') or 0) == 1 and int(row.get('n5') or 0) == 3
    return False

CLAUSE_RE = re.compile(r'第\s*(十[一二]?|[一二三四五六七八九]|1[012]|[1-9])\s*款')
CLAUSE_NUM = dict(zip('一二三四五六七八九', range(1, 10)), **{'十': 10, '十一': 11, '十二': 12})

def notice_clauses(reason):
    return {int(v) if v.isdigit() else CLAUSE_NUM[v]
            for v in CLAUSE_RE.findall(str(reason or ''))}

def clause_features(hist, windows):
    recent = [x for x in hist if x['date'] in windows[20]]
    last = notice_clauses(recent[-1].get('reason')) if recent else set()
    out = {}
    all_clauses = set()
    for n in range(1, 13):
        out[f'clause_{n}_20d'] = sum(n in notice_clauses(x.get('reason')) for x in recent)
        out[f'clause_{n}_last'] = int(n in last)
    for x in recent:
        all_clauses.update(notice_clauses(x.get('reason')))
    out['clause_last_known'] = int(bool(last))
    out['clause_last_count'] = len(last)
    out['clause_distinct_20d'] = len(all_clauses)
    return out


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
    labels = {x['ticker'] for x in events if x['date'] == target and x['kind'] == 'attention'}
    out = []
    for ticker in sorted(pool):
        if ticker not in master:
            continue
        hist = sorted(by_ticker[ticker], key=lambda x: x['date'])
        history = prior[ticker]
        # Hard exclusion for BOTH markets: once the latest target-month EPS/self-report
        # has been announced by cutoff, the company cannot announce it again.
        # This uses only filings known as of cutoff, never future labels.
        target_month = previous_month(target)
        if any(x['month'] == target_month for x in history):
            continue
        last_report = max((x['date'] for x in history), default=None)
        report_gap = (dt.date.fromisoformat(cutoff) - dt.date.fromisoformat(last_report)).days if last_report else None
        counts = {f'n{n}': sum(x['date'] in ds for x in hist) for n, ds in windows.items()}
        if not counts['n20'] and not any(x['kind'] == 'voluntary' for x in history):
            continue
        gap = sum(d > hist[-1]['date'] for d in past) if hist else 99
        recent = 0 if gap == 0 else 1 if gap <= 2 else 2 if gap <= 5 else 3
        cooldown = '0-5' if report_gap is not None and report_gap <= 5 else '6-10' if report_gap is not None and report_gap <= 10 else '11+' if report_gap is not None else 'never'
        reason6 = sum(bool(x['date'] in windows[10] and re.search(r'第\s*[六6]\s*款', x['reason'])) for x in hist)
        row = dict(date=target, cutoff=cutoff, ticker=ticker, name=master[ticker].get('name', ticker),
                   market=master[ticker]['market'], label=int(ticker in labels), recent=recent,
                   gap=gap, cooldown=cooldown, days_since_report=report_gap, reason6=reason6, **counts, **clause_features(hist, windows))
        row['market_pattern'] = bucket(row)
        row['clause_data_available'] = 1
        row['rule_eligible'] = eligible(row)
        row['reason6_flag'] = int(reason6 > 0)
        row['notice_intensity'] = 'high' if counts['n5'] >= 3 else 'mid' if counts['n5'] == 2 else 'low'
        out.append(row)
    return out

class Model:
    """Separate listed/OTC empirical probabilities; strictly past-only training.

    Smoothed evidence from the notice count, short streak, clause 6, prior
    reporting and notice intensity. Small groups shrink to their own market.
    """
    PRIOR_WEIGHT = 18
    TWSE_FEATURES = ('n1', 'n20_bucket', 'clause_last_known', 'clause_last_count',
                     'clause_distinct_20d') + tuple(f'clause_{n}_last' for n in range(1, 13))
    FEATURES = ('market_pattern', 'notice_intensity', 'reason6_flag',
                'cooldown', 'n3', 'n5')

    def __init__(self, rows):
        self.market_stats = collections.defaultdict(lambda: [0, 0])
        self.feature_stats = collections.defaultdict(lambda: [0, 0])
        for r in rows:
            if not r['rule_eligible']:
                continue
            market = r['market']
            self.market_stats[market][0] += r['label']
            self.market_stats[market][1] += 1
            for feature in (self.FEATURES + (self.TWSE_FEATURES if market == 'twse' and r.get('clause_data_available') else ())):
                value = self.value(r, feature)
                cell = self.feature_stats[(market, feature, value)]
                cell[0] += r['label']
                cell[1] += 1

    @staticmethod
    def value(r, feature):
        if feature == 'n20_bucket':
            n = int(r.get('n20') or 0)
            return 0 if n == 0 else 1 if n == 1 else 2 if n <= 3 else 3 if n <= 5 else 4
        if feature.startswith('clause_') or feature == 'n1':
            return min(int(r.get(feature) or 0), 3)
        if feature in ('n3', 'n5'):
            return min(int(r.get(feature) or 0), 3)
        return r.get(feature)

    def predict(self, row):
        market = row['market']
        hits, total = self.market_stats[market]
        base = (hits + 1) / (total + 2) if total else .10
        # Add independent feature evidence on log-odds scale, capped to avoid
        # tiny historical buckets creating overconfident probabilities.
        import math
        base = max(.005, min(.995, base))
        logit = math.log(base / (1 - base))
        support = total
        for feature in (self.FEATURES + (self.TWSE_FEATURES if market == 'twse' and row.get('clause_data_available') else ())):
            h, n = self.feature_stats[(market, feature, self.value(row, feature))]
            if n < 8:
                continue
            p = (h + self.PRIOR_WEIGHT * base) / (n + self.PRIOR_WEIGHT)
            p = max(.005, min(.995, p))
            weight = min(.30, n / (n + 80) * .45)
            logit += weight * (math.log(p / (1 - p)) - math.log(base / (1 - base)))
            support = max(support, n)
        probability = 1 / (1 + math.exp(-max(-12, min(12, logit))))
        return probability, support


def choose(rows, threshold=MIN_PROBABILITY):
    """Daily 0-10: protect listed slots, then rank by empirical probability.

    No artificial 10-stock padding. A small listed reserve prevents OTC
    names from occupying every slot when listed candidates exist.
    """
    eligible_rows = [r for r in rows if r['rule_eligible']]
    listed = sorted((r for r in eligible_rows if r['market'] == 'twse'),
                    key=lambda r: (-r['probability'], -r.get('cell_samples', 0), r['ticker']))
    otc = sorted((r for r in eligible_rows if r['market'] == 'tpex'),
                 key=lambda r: (-r['probability'], r['ticker']))
    # Listed candidates need at least 8 supporting historical examples.
    # A separate minimum keeps the broadened candidate pool from blindly
    # adding every newly noticed stock.
    listed = [r for r in listed if r['probability'] >= .10 and r.get('cell_samples', 0) >= 8]
    otc = [r for r in otc if r['probability'] >= .10]
    selected = listed[:4] + otc[:4]
    used = {(r['market'], r['ticker']) for r in selected}
    remaining = sorted((r for r in listed[4:] + otc[4:] if (r['market'], r['ticker']) not in used),
                       key=lambda r: (-r['probability'], r['ticker']))
    return (selected + remaining)[:CAP]


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
            actual_codes = {e['ticker'] for e in events if e['date'] == day and e.get('kind') == 'attention'}
            predicted_codes = {r['ticker'] for r in picks}
            daily.append(dict(date=day, threshold=MIN_PROBABILITY, **metrics(picks, len(actual_codes)),
                              eligible_candidates=sum(r['rule_eligible'] for r in rows),
                              tickers=' '.join(r['ticker'] for r in picks),
                              hit_tickers=' '.join(sorted(predicted_codes & actual_codes)),
                              missed_tickers=' '.join(sorted(actual_codes - predicted_codes)),
                              baseline_hits=sum(r['label'] for r in baseline), baseline_predictions=len(baseline)))
            picks_all.extend(picks); scores_all.extend(scored); evaluated_days.add(day)
        training.extend(rows)
    actual = sum(len({e['ticker'] for e in events if e['date'] == day and e.get('kind') == 'attention'}) for day in evaluated_days)
    summary = dict(model=metrics(picks_all, actual), baseline_same_dates=metrics(baseline_all, actual),
                   evaluated_days=len(daily), warmup_days=len(day_rows)-len(daily),
                   first_evaluated_date=daily[0]['date'] if daily else None,
                   last_evaluated_date=daily[-1]['date'] if daily else None,
                   daily_pick_counts=[dict(date=x['date'], count=x['predictions']) for x in daily])
    for market in ('twse', 'tpex'):
        count = sum(len({e['ticker'] for e in events if e['date'] == day and e['market'] == market and e.get('kind') == 'attention'}) for day in evaluated_days)
        summary[market] = metrics([r for r in picks_all if r['market'] == market], count)
    return summary, daily, picks_all, training, scores_all


def offline_replay(args, out, now):
    """Backtest strictly from archived daily feature snapshots; zero HTTP requests.

    These historical snapshots were generated by V5. Replay starts with the
    first archived scoring date and therefore needs a new chronological warmup.
    """
    source = args.offline_scores
    if not source.is_file():
        raise FileNotFoundError(f'Offline historical features missing: {source}')
    events_file = args.offline_events
    if not events_file or not events_file.is_file():
        raise FileNotFoundError(f'Offline historical event audit missing: {events_file}')
    days = collections.defaultdict(list)
    with source.open(encoding='utf-8-sig', newline='') as f:
        for raw in csv.DictReader(f):
            if not (args.backtest_start <= raw['date'] <= (args.asof or '9999-12-31')):
                continue
            row = dict(raw)
            for key in ('label', 'recent', 'gap', 'reason6', 'n1', 'n3', 'n5', 'n10', 'n20'):
                row[key] = int(row.get(key) or 0)
            # Archived CSVs may omit this derived column.
            row['reason6_flag'] = int(row.get('reason6_flag') or (row['reason6'] > 0))
            row['days_since_report'] = int(row['days_since_report']) if row.get('days_since_report') else None
            row['market_pattern'] = bucket(row)
            row['notice_intensity'] = 'high' if row['n5'] >= 3 else 'mid' if row['n5'] == 2 else 'low'
            row['clause_data_available'] = int('clause_last_known' in row and str(row.get('clause_last_known')) != '')
            row['rule_eligible'] = eligible(row)
            # Never use old model probabilities in the new model.
            row.pop('probability', None)
            row.pop('cell_samples', None)
            days[row['date']].append(row)
    events = []
    with events_file.open(encoding='utf-8-sig', newline='') as f:
        for row in csv.DictReader(f):
            if row['date'] <= (args.asof or '9999-12-31'):
                events.append(row)
    if not days:
        raise ValueError('No historical feature rows found in requested range')
    # Source snapshots already excluded companies that had announced target-month
    # EPS as of each cutoff. Verify this invariant again using event audit.
    prior_by_ticker = collections.defaultdict(list)
    for e in events:
        prior_by_ticker[e['ticker']].append(e)
    excluded = 0
    for day, rows in list(days.items()):
        kept = []
        for r in rows:
            known = any(e['date'] <= r['cutoff'] and e.get('month') == previous_month(day)
                        for e in prior_by_ticker[r['ticker']])
            if known:
                excluded += 1
            else:
                kept.append(r)
        days[day] = kept
    # Old snapshots labelled voluntary reports as positive. Rebuild labels from
    # actual attention-triggered filings, never trust archived model labels.
    attention_keys = {(e['date'], e['ticker']) for e in events if e.get('kind') == 'attention'}
    relabelled = 0
    for day, rows in days.items():
        for row in rows:
            label = int((day, row['ticker']) in attention_keys)
            relabelled += row['label'] != label
            row['label'] = label
    summary, daily, picks, training, scores = evaluate(days, events)
    summary.update(version=VERSION, source_status={'offline': True, 'network_requests': 0,
                   'snapshot': str(source), 'excluded_announced_month': excluded, 'relabelled_historical_rows': relabelled},
                   asof=max(days), scope=args.markets, future_threshold=MIN_PROBABILITY,
                   historical_snapshot_start=min(days),
                   warnings=['完全離線：使用前次回測保存的每日候選特徵，未下載MOPS或注意交易資料',
                             '歷史特徵檔僅包含前次已評估日期；本次重新暖機，因此回測日期可能少於舊版',
                             '這是既有候選特徵的離線重評分，不能補回舊版沒有保存的候選股票',
                             '只有因注意交易公告自結算命中與召回分母；自主公告僅用於已公告月份排除',
                             '上市近20日注意候選改機率排序；歷史快照未保存款項，不能用本次離線回測驗證款項增益；上櫃5日恰好3次',
                             '上市與上櫃：截至預測前日已公告目標月份EPS／自結者直接排除'])
    write(out / 'backtest_summary.json', summary)
    csvout(out / 'backtest_daily.csv', daily)
    csvout(out / 'backtest_picks.csv', picks)
    csvout(out / 'walk_forward_scores.csv', scores)
    write(out / 'predictions.json', {'version': VERSION, 'count': 0, 'items': [],
           'prediction_day': None, 'note': '離線歷史回測不產生即時預測', 'evaluation': summary})
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    summary_path = os.environ.get('GITHUB_STEP_SUMMARY')
    if summary_path:
        with open(summary_path, 'a', encoding='utf-8') as f:
            f.write('\n## 完全離線自結回測（0 次網路請求）\n\n')
            f.write('| 市場 | 推薦 | 命中 | 命中率 | 召回率 |\n|---|---:|---:|---:|---:|\n')
            for k, name in [('twse','上市'),('tpex','上櫃'),('model','合計')]:
                m=summary[k]
                f.write(f'| {name} | {m["predictions"]} | {m["hits"]} | '
                        f'{m["precision"]:.1%} | {m["recall"]:.1%} |\n')
            f.write(f'\n評估交易日：{summary["evaluated_days"]}；'
                    f'已公告目標月份排除：{excluded} 筆\n')



def extend_archive(args):
    """Build 9/30--10/19 features using current repository reports and one cached
    notice download. Preserve immutable earlier feature snapshots; replay offline.
    """
    old_scores, old_events = args.offline_scores, args.offline_events
    if not old_scores or not old_events or not old_scores.is_file() or not old_events.is_file():
        raise FileNotFoundError('Historical archive CSV files are required')
    end = args.asof or '2026-10-19'
    start_new = '2026-09-30'
    if end < start_new:
        raise ValueError('Extension end must be >= 2026-09-30')
    # A month of lookback ensures n20 and the latest notice streak are computed
    # using only information available before each prediction date.
    notices, source_status = attention('2026-09-01', end, args.attention_cache,
                                       ('twse', 'tpex'))
    master = read(args.root / 'data/master.json')['stocks']
    current_events, rejected = reports(args.root / args.reports, master, ('twse', 'tpex'))
    old_event_rows = []
    with old_events.open(encoding='utf-8-sig', newline='') as f:
        old_event_rows = list(csv.DictReader(f))
    all_events = {}
    for e in old_event_rows + current_events:
        if e.get('date', '') <= end and e.get('kind') in ('attention', 'voluntary'):
            key = (e['date'], e['ticker'], e.get('month'), e['kind'])
            all_events[key] = e
    events = sorted(all_events.values(), key=lambda e: (e['date'], e['ticker']))
    cal = calendar(args.root, '2026-09-01', end, notices)
    days_new = [d for d in cal if start_new <= d <= end]
    if not days_new or days_new[-1] != end:
        raise ValueError('Trading calendar does not reach requested end; cannot claim full coverage')
    new_rows = []
    for day in days_new:
        i = cal.index(day)
        if i == 0:
            raise ValueError('Missing previous trading session for '+day)
        new_rows.extend(make_rows(cal[i-1], day, cal, notices, events, master))
    old_rows = []
    with old_scores.open(encoding='utf-8-sig', newline='') as f:
        old_rows = [r for r in csv.DictReader(f) if r.get('date', '') < start_new]
    if not old_rows:
        raise ValueError('Historical scores before 9/30 missing')
    if not any(e['date'] >= start_new and e['kind'] == 'attention' for e in events):
        raise ValueError('No post-9/29 attention-triggered reports; repository data may be incomplete')
    tmp = args.root / args.out / 'merged_input'
    tmp.mkdir(parents=True, exist_ok=True)
    csvout(tmp / 'walk_forward_scores.csv', old_rows + new_rows)
    csvout(tmp / 'event_audit.csv', events)
    write(tmp / 'extension_status.json', dict(old_rows=len(old_rows), new_rows=len(new_rows),
          new_days=days_new, historical_events=len(old_event_rows),
          merged_events=len(events), rejected_current=len(rejected), attention=source_status))
    args.offline_scores = tmp / 'walk_forward_scores.csv'
    args.offline_events = tmp / 'event_audit.csv'
    print('Extension ready: '+str(len(days_new))+' new trading days, '
          +str(len(new_rows))+' new candidate rows', flush=True)
    offline_replay(args, args.root / args.out, dt.datetime.now(TZ))

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
    parser.add_argument('--offline-scores', type=Path, help='Archived walk_forward_scores.csv: do not fetch anything')
    parser.add_argument('--offline-events', type=Path, help='Archived event_audit.csv')
    parser.add_argument('--extend-archive', action='store_true', help='Append 9/30--10/19 using repository filings and cached notices, then offline replay')
    parser.add_argument('--markets', choices=['both', 'twse', 'tpex'], default='both')
    parser.add_argument('--prediction-date', default='')
    args = parser.parse_args()
    now = dt.datetime.now(TZ)
    latest_complete = (now.date() if now.hour >= 20 else now.date() - dt.timedelta(days=1)).isoformat()
    requested = args.asof or latest_complete
    end = min(requested, latest_complete)
    markets = ('twse', 'tpex') if args.markets == 'both' else (args.markets,)
    out = args.root / args.out
    out.mkdir(parents=True, exist_ok=True)
    if args.extend_archive:
        extend_archive(args)
        return
    if args.offline_scores:
        offline_replay(args, out, now)
        return
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
                       f'預測月份{previous_month(provisional)}尚未公告EPS／自結']
            clean = {k: v for k, v in row.items() if k not in ('label', 'date')}
            clean.update(probability=p, score=round(p*100, 2), cell_samples=support, reasons=reasons)
            forecast.append(clean)
        forecast = choose(forecast)
    warnings = [
        '上市及上櫃一致：已公告預測月份EPS／自結者在評分前排除；不以任意天數作為冷卻期',
        '每日0至10檔，不強制補滿；上市與上櫃分別校準、各優先保留最多4檔，再依機率補足',
        '回測按日期順序訓練；新規則仍需與既有版本在相同期間比較，不能保證改善',
        '只有注意交易觸發的自結計入命中及召回率；自主公告不計入',
        '自結標籤依MOPS解析結果；公告漏抓會影響Precision與Recall',
    ]
    if not target:
        warnings.append('下一交易日尚未由正式交易日曆確認，日期暫不標示')
    summary.update(version=VERSION, source_status=status, asof=cutoff,
                   requested_asof=requested, incomplete_current_day_excluded=requested > latest_complete,
                   scope=args.markets, warnings=warnings, future_threshold=MIN_PROBABILITY,
                   model_ready=enough, training_events=sum(r['label'] for r in training),
                   event_count=sum(args.backtest_start <= e['date'] <= end and e['kind'] == 'attention' for e in events),
                   market_rules=MARKET_RULES)
    obj = dict(version=VERSION, updated_at=now.isoformat(timespec='seconds'),
               asof=cutoff, prediction_day=target, prediction_window='下一交易日',
               count=len(forecast), model='monthly-eps-excluded-market-pattern-walkforward',
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
