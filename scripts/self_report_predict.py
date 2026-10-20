#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""自結預測：以 9/29 事件研究規律為基礎，上市與上櫃分別估計。

僅使用預測截止日前已知資料；逐日 walk-forward 驗證；不發送通知、不修改正式自結資料。
標準函式庫即可執行，沿用既有 self-report-predict.yml 與輸出檔名。
"""
import argparse
import collections
import csv
import datetime as dt
import json
import re
import urllib.request
from pathlib import Path
from zoneinfo import ZoneInfo

VERSION = '2026-10-20-event-rules-market-v2'
ROOT = Path(__file__).resolve().parents[1]
TZ = ZoneInfo('Asia/Taipei')
CAP = 10
# 固定的最低機率門檻：不在每個回測日反覆尋找最佳分數/門檻
MIN_PROBABILITY = 0.15


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    tmp.replace(path)


def csvout(path, rows):
    path = Path(path)
    if not rows:
        path.write_text('', encoding='utf-8')
        return
    with path.open('w', encoding='utf-8-sig', newline='') as stream:
        w = csv.DictWriter(stream, fieldnames=list(rows[0]), extrasaction='ignore')
        w.writeheader()
        w.writerows(rows)


def notice_date(value):
    m = re.search(r'(\d{2,4})[./-](\d{1,2})[./-](\d{1,2})', str(value))
    if not m:
        return None
    year = int(m[1])
    if year < 1911:
        year += 1911
    try:
        return dt.date(year, int(m[2]), int(m[3])).isoformat()
    except ValueError:
        return None


def parse_notices(obj, market, start, end):
    table = (obj.get('tables') or [{}])[0]
    fields = obj.get('fields') or table.get('fields') or []
    rows = obj.get('data') or table.get('data') or []

    def col(pattern, fallback):
        return next((i for i, f in enumerate(fields) if re.search(pattern, str(f))), fallback)

    ti = col('證券代號', 1)
    ni = col('證券名稱', 2)
    ri = col('注意交易資訊|注意原因', 4)
    di = col('日期', 5)
    found = {}
    for row in rows:
        if not isinstance(row, list) or len(row) <= max(ti, ni, ri, di):
            continue
        ticker = str(row[ti]).strip()
        date = notice_date(row[di])
        if not re.fullmatch(r'[1-9]\d{3}', ticker) or not date or not start <= date <= end:
            continue
        found[(date, ticker)] = dict(date=date, ticker=ticker, name=str(row[ni]),
                                     market=market, reason=str(row[ri]))
    if not found:
        raise ValueError(f'{market}: 官方注意交易資料為空或解析失敗，不產生部分市場預測')
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
            with urllib.request.urlopen(req, timeout=45) as response:
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
        subject = str(x.get('subject') or '')
        reason = x.get('match_reason')
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
            excluded = '自主公告未確認單月期間（可能是季度自結）'
        elif not re.fullmatch(r'20\d\d-\d\d-\d\d', day):
            excluded = '日期無效'
        if excluded:
            audit.append(dict(date=day, ticker=ticker, reason=excluded, subject=subject))
            continue
        # 缺上一季 EPS 仍算自結事件；同股票同月份的更正只算第一次。
        key = (ticker, month or day)
        item = dict(date=day, ticker=ticker, month=month, market=market,
                    kind='attention' if attention_event else 'voluntary',
                    name=x.get('name', ''), monthly_eps=x.get('monthly_eps'),
                    quarter_eps=x.get('quarter_eps'))
        if key not in events or day < events[key]['date']:
            events[key] = item
    return sorted(events.values(), key=lambda x: (x['date'], x['ticker'])), audit


def calendar(root, start, end, notices):
    obj = read(root / 'data/market_monitor.json')
    days = {x['date'] for x in obj.get('raw', []) if x.get('index') is not None}
    days.update(p.stem for p in (root / 'data/history/market').glob('????-??-??.json'))
    days.update(x['date'] for x in notices)
    days = sorted(d for d in days if start <= d <= end)
    if len(days) < 20:
        raise ValueError('交易日曆不足20日，不能把一般平日當成交易日')
    return days


def previous_month(day):
    d = dt.date.fromisoformat(day).replace(day=1) - dt.timedelta(days=1)
    return d.strftime('%Y-%m')


def market_bucket(row):
    """研究發現：上市重視最近一次觸發；上櫃須再區分近5日注意交易密集度。

    僅定義可解釋的類別，不在此硬塞人為加分；公布機率由過去資料估計。
    """
    if row['market'] == 'tpex':
        n5 = row['n5']
        return '5d>=3' if n5 >= 3 else '5d=2' if n5 == 2 else '5d<=1'
    # 上市仍保留近3日密集度作為檢查項，但不把高頻當成必然加分。
    return '3d>=2' if row['n3'] >= 2 else '3d<=1'


def make_rows(cutoff, target, cal, notices, events, master):
    past = [d for d in cal if d <= cutoff]
    windows = {n: set(past[-n:]) for n in (1, 3, 5, 10, 20)}
    by_ticker = collections.defaultdict(list)
    for x in notices:
        if x['date'] <= cutoff:
            by_ticker[x['ticker']].append(x)
    prior = collections.defaultdict(list)
    for x in events:
        if x['date'] <= cutoff:
            prior[x['ticker']].append(x)
    pool = set(by_ticker) | {c for c, xs in prior.items() if any(x['kind'] == 'voluntary' for x in xs)}
    labels = {x['ticker'] for x in events if x['date'] == target}
    out = []
    for ticker in sorted(pool):
        if ticker not in master:
            continue
        hist = sorted(by_ticker[ticker], key=lambda x: x['date'])
        history = prior[ticker]
        target_month = previous_month(target)
        # 同一月份已公布者不再推薦；若月份未知，短期內保守排除，避免重複推薦。
        if any(x['month'] == target_month for x in history):
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
        # 注意：這裡是距「自結公告」的天數，不能誤用最近一次注意交易日。
        cooldown = '0-5' if report_gap is not None and report_gap <= 5 else '6-10' if report_gap is not None and report_gap <= 10 else '11+' if report_gap is not None else 'never'
        reason6 = sum(bool(x['date'] in windows[10] and re.search(r'第\s*[六6]\s*款', x['reason'])) for x in hist)
        row = dict(date=target, cutoff=cutoff, ticker=ticker,
                   name=master[ticker].get('name', ticker), market=master[ticker]['market'],
                   label=int(ticker in labels), recent=recent, gap=gap, cooldown=cooldown,
                   days_since_report=report_gap, reason6=reason6, **counts)
        row['market_pattern'] = market_bucket(row)
        out.append(row)
    return out


class Model:
    """依上市/上櫃的不同研究規律分層，並向較大樣本平滑。

    固定分組：市場 → 最近注意交易 → 市場專屬密集度 → 公告冷卻期。
    每一層都只用訓練日期已經結束的公告，無當日答案洩漏。
    """
    LEVELS = (('market',), ('market', 'recent'),
              ('market', 'recent', 'market_pattern'),
              ('market', 'recent', 'market_pattern', 'cooldown'))
    # 固定保守先驗，避免少量樣本產生 0% 或 100% 的極端估計
    PRIOR_WEIGHT = 30

    def __init__(self, rows):
        self.base = (sum(r['label'] for r in rows) + 1) / (len(rows) + 20)
        self.stats = []
        for keys in self.LEVELS:
            group = collections.defaultdict(lambda: [0, 0])
            for r in rows:
                cell = group[tuple(r[k] for k in keys)]
                cell[0] += r['label']
                cell[1] += 1
            self.stats.append(group)

    def predict(self, row):
        p, support = self.base, 0
        for keys, group in zip(self.LEVELS, self.stats):
            hits, n = group.get(tuple(row[k] for k in keys), (0, 0))
            if n:
                p = (hits + self.PRIOR_WEIGHT * p) / (n + self.PRIOR_WEIGHT)
            support = n
        return p, support


def choose(rows, threshold=MIN_PROBABILITY):
    return sorted((r for r in rows if r['probability'] >= threshold),
                  key=lambda r: (-r['probability'], -r['n1'], r['ticker']))[:CAP]


def metrics(predictions, actual):
    n = len(predictions)
    hits = sum(x['label'] for x in predictions)
    return dict(hits=hits, predictions=n, actual=actual,
                precision=hits/n if n else None,
                recall=hits/actual if actual else None,
                f1=2*hits/(n+actual) if n+actual else None)


def evaluate(day_rows, events):
    training, daily, picks_all, scores_all, baseline_all = [], [], [], [], []
    evaluated_days = set()
    for day, rows in sorted(day_rows.items()):
        enough = len({r['date'] for r in training}) >= 5 and sum(r['label'] for r in training) >= 15
        if enough:
            model = Model(training)
            scored = []
            for r in rows:
                p, support = model.predict(r)
                scored.append(dict(r, probability=p, cell_samples=support))
            picks = choose(scored)
            # 保留上一版 Reason 7 規則作固定對照，不再優化舊規則。
            baseline = sorted((r for r in rows if 2*r['n3']+r['n10']+r['reason6'] >= 7),
                              key=lambda r: (-(2*r['n3']+r['n10']+r['reason6']), r['ticker']))[:CAP]
            baseline_all.extend(baseline)
            actual_codes = {e['ticker'] for e in events if e['date'] == day}
            predicted_codes = {r['ticker'] for r in picks}
            daily.append(dict(date=day, threshold=MIN_PROBABILITY, **metrics(picks, len(actual_codes)),
                              tickers=' '.join(r['ticker'] for r in picks),
                              hit_tickers=' '.join(sorted(predicted_codes & actual_codes)),
                              missed_tickers=' '.join(sorted(actual_codes - predicted_codes)),
                              baseline_hits=sum(r['label'] for r in baseline),
                              baseline_predictions=len(baseline)))
            picks_all.extend(picks)
            scores_all.extend(scored)
            evaluated_days.add(day)
        training.extend(rows)
    actual = sum(len({e['ticker'] for e in events if e['date'] == day}) for day in evaluated_days)
    summary = dict(model=metrics(picks_all, actual), baseline_same_dates=metrics(baseline_all, actual),
                   evaluated_days=len(daily), warmup_days=len(day_rows)-len(daily),
                   first_evaluated_date=daily[0]['date'] if daily else None,
                   last_evaluated_date=daily[-1]['date'] if daily else None)
    for market in ('twse', 'tpex'):
        count = sum(len({e['ticker'] for e in events if e['date'] == day and e['market'] == market}) for day in evaluated_days)
        summary[market] = metrics([r for r in picks_all if r['market'] == market], count)
    return summary, daily, picks_all, training, scores_all


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--root', type=Path, default=ROOT)
    ap.add_argument('--start', default='2026-09-01')
    ap.add_argument('--backtest-start', default='2026-09-29')
    ap.add_argument('--asof', default='')
    ap.add_argument('--reports', default='data/self_reports_history.json')
    ap.add_argument('--out', default='self_report_model')
    ap.add_argument('--backtest', action='store_true')
    ap.add_argument('--attention-cache', type=Path)
    ap.add_argument('--markets', choices=['both', 'twse', 'tpex'], default='both')
    ap.add_argument('--prediction-date', default='', help='已確認的下一交易日；留空不假裝已確認')
    a = ap.parse_args()
    now = dt.datetime.now(TZ)
    latest_complete = (now.date() - dt.timedelta(days=1)).isoformat()
    requested = a.asof or latest_complete
    end = min(requested, latest_complete)
    markets = ('twse', 'tpex') if a.markets == 'both' else (a.markets,)
    out = a.root / a.out
    out.mkdir(parents=True, exist_ok=True)
    notices, status = attention(a.start, end, a.attention_cache, markets)
    master = read(a.root / 'data/master.json')['stocks']
    events, rejected = reports(a.root / a.reports, master, markets)
    events = [x for x in events if x['date'] <= end]
    cal = calendar(a.root, a.start, end, notices)
    cutoff = cal[-1]
    days = [d for d in cal if a.backtest_start <= d <= end]
    rows = {d: make_rows(cal[cal.index(d)-1], d, cal, notices, events, master)
            for d in days if cal.index(d) > 0}
    summary, daily, picks, training, scores = evaluate(rows, events)

    future_known = sorted({x['date'] for x in read(a.root / 'data/market_monitor.json').get('raw', [])
                           if x.get('index') is not None and x['date'] > cutoff})
    target = a.prediction_date or (future_known[0] if future_known else None)
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
                       f'近3日注意{row["n3"]}次、近5日注意{row["n5"]}次',
                       '上櫃：採近5日密集度分組' if row['market'] == 'tpex' else '上市：採最近觸發與近3日分組',
                       '無歷史自結' if row['days_since_report'] is None else f'距前次自結{row["days_since_report"]}天']
            row = {k: v for k, v in row.items() if k not in ('label', 'date')}
            row.update(probability=p, score=round(p*100, 2), cell_samples=support, reasons=reasons)
            forecast.append(row)
        forecast = choose(forecast)

    warnings = ['規律來自2026/9/29起短期事件研究；機率尚未經獨立長期校準',
                '上市與上櫃使用不同密集度分組；不任意對第六款加分',
                '固定15%門檻，每日最多10檔，不為回測命中率反覆調整門檻',
                '冷卻期使用前次自結公告日，非前次注意交易日',
                '回測採逐日先訓練後預測；同股票同月份自結更正不重複計算',
                '歷史自結可能漏收，未知月份自結可能影響事件排除',
                '無法保證命中率或召回率高於舊模型']
    if not target:
        warnings.append('下一交易日尚未由正式交易日曆確認，日期暫不標示')
    summary.update(version=VERSION, source_status=status, asof=cutoff,
                   requested_asof=requested, incomplete_current_day_excluded=requested > latest_complete,
                   scope=a.markets, warnings=warnings, future_threshold=MIN_PROBABILITY,
                   model_ready=enough, training_events=sum(r['label'] for r in training),
                   event_count=sum(a.backtest_start <= e['date'] <= end for e in events),
                   market_rules={'twse': '最近注意交易日＋近3日密集度',
                                 'tpex': '最近注意交易日＋近5日密集度',
                                 'both': '已公布同月份排除、未知月份近5天排除'})
    obj = dict(version=VERSION, updated_at=now.isoformat(timespec='seconds'),
               asof=cutoff, prediction_day=target, prediction_window='下一交易日',
               count=len(forecast), model='event-rules-market-separated', threshold=MIN_PROBABILITY,
               items=forecast, candidates=forecast, source_status=status,
               evaluation=summary, warnings=warnings)
    write(out/'predictions.json', obj)
    write(out/'backtest_summary.json', summary)
    csvout(out/'backtest_daily.csv', daily)
    csvout(out/'backtest_picks.csv', picks)
    csvout(out/'walk_forward_scores.csv', scores)
    csvout(out/'event_audit.csv', events)
    csvout(out/'excluded_announcements.csv', rejected)
    csvout(out/'predictions.csv', forecast)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print('Next-session picks:', ' '.join(x['ticker'] for x in forecast) or 'none')
    import os
    summary_path = os.environ.get('GITHUB_STEP_SUMMARY')
    if summary_path:
        def percent(x):
            return '—' if x is None else f'{x:.1%}'
        m = summary['model']
        b = summary['baseline_same_dates']
        with open(summary_path, 'a', encoding='utf-8') as stream:
            stream.write(f'## 自結預測驗證｜上市與上櫃分流\n\n資料截至 {cutoff}，每日合計最多10檔\n\n')
            stream.write('|模型|命中/推薦|命中率|召回率|F1|\n|---|---:|---:|---:|---:|\n')
            for name, v in [('規律分流（逐日樣本外）', m), ('舊研究規則（同日期）', b)]:
                stream.write(f'|{name}|{v["hits"]}/{v["predictions"]}|{percent(v["precision"])}|{percent(v["recall"])}|{percent(v["f1"])}|\n')
            stream.write('\n|市場|命中/推薦|命中率|召回率|\n|---|---:|---:|---:|\n')
            for market, label in [('twse', '上市'), ('tpex', '上櫃')]:
                v = summary[market]
                stream.write(f'|{label}|{v["hits"]}/{v["predictions"]}|{percent(v["precision"])}|{percent(v["recall"])}|\n')
            stream.write('\n注意：' + '；'.join(warnings) + '\n\n下一開市日名單：' +
                         ('、'.join(x['name'] + ' ' + x['ticker'] for x in forecast) or '無符合門檻') + '\n')


if __name__ == '__main__':
    main()
