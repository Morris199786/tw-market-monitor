#!/usr/bin/env python3
"""TWSE/TPEx foreign and investment-trust net-buy streak event study. Python 3.11+, standard library only.
Does not modify the website, publish results, send messages or place orders.
"""
from __future__ import annotations
import argparse, collections, concurrent.futures, csv, datetime as dt, html
import json, math, statistics, sys, time, urllib.parse, urllib.request
from pathlib import Path
from zoneinfo import ZoneInfo

SCHEMA = 2
TZ = ZoneInfo('Asia/Taipei')
HORIZONS = (3, 5, 10, 20)
THRESHOLDS = (3, 5)
URLS = {
    ('twse', 'quotes'): 'https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX',
    ('twse', 'flows'): 'https://www.twse.com.tw/rwd/zh/fund/T86',
    ('tpex', 'quotes'): 'https://www.tpex.org.tw/www/zh-tw/afterTrading/dailyQuotes',
    ('tpex', 'flows'): 'https://www.tpex.org.tw/www/zh-tw/insti/dailyTrade',
}

def clean(x):
    import re
    return re.sub('<[^>]*>', '', html.unescape(str(x))).strip()

def num(x):
    try:
        v = float(clean(x).replace(',', '').replace('−', '-').replace('－', '-').replace('＋', '+'))
        return v if math.isfinite(v) else None
    except (ValueError, TypeError):
        return None

def ordinary(t):
    # Historical daily universe, NOT today's listing roster (avoid survivor-only sample).
    return len(t) == 4 and t.isdigit() and t[0] != '0' and not t.startswith('91')

def atomic(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(value, ensure_ascii=False, allow_nan=False), encoding='utf-8')
    tmp.replace(path)

def read(path):
    return json.loads(path.read_text(encoding='utf-8'))

def get_json(url, params, delay=0.8):
    request = urllib.request.Request(url + '?' + urllib.parse.urlencode(params), headers={
        'User-Agent': 'Mozilla/5.0 (historical event study)', 'Accept': 'application/json'})
    error = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(request, timeout=40) as response:
                data = json.load(response)
            time.sleep(delay)
            if not isinstance(data, dict):
                raise ValueError('Expected JSON object')
            return data
        except Exception as exc:
            error = exc
            if attempt < 2:
                time.sleep(2 * (attempt + 1))
    raise RuntimeError(f'{url}: {type(error).__name__}: {error}')

def iso_date(text):
    s = clean(text).replace('-', '/').replace('.', '/')
    if '/' in s:
        y, m, d = map(int, s.split('/'))
        return dt.date(y + 1911 if y < 1911 else y, m, d).isoformat()
    if len(s) == 8 and s.isdigit():
        return dt.date(int(s[:4]), int(s[4:6]), int(s[6:8])).isoformat()
    raise ValueError(f'Unrecognized report date {text!r}')

def check_date(data, day):
    if iso_date(data.get('date', '')) != day:
        raise ValueError(f'Requested {day}, response date {data.get("date")}')

def calendar(start, end, cache, delay, refresh=False):
    """Official TWSE trading calendar from monthly market statistics (includes makeup sessions)."""
    months = []
    month = start.replace(day=1)
    while month <= end:
        months.append(month)
        month = (month.replace(day=28) + dt.timedelta(days=4)).replace(day=1)
    dates = set()
    for month in months:
        path = cache / 'calendar' / (month.strftime('%Y-%m') + '.json')
        # Current/as-of month may have acquired new sessions since the previous run.
        if path.exists() and not refresh and month.strftime('%Y-%m') != end.strftime('%Y-%m'):
            data = read(path)
        else:
            data = get_json('https://www.twse.com.tw/rwd/zh/afterTrading/FMTQIK',
                            {'date': month.strftime('%Y%m01'), 'response': 'json'}, delay)
            check_date(data, month.isoformat())
            if data.get('stat') != 'OK' or not data.get('data'):
                raise ValueError(f'Missing official monthly calendar: {month}')
            atomic(path, data)
        fields = data.get('fields', [])
        if '日期' not in fields:
            raise ValueError('Calendar fields changed')
        idx = fields.index('日期')
        for row in data['data']:
            day = iso_date(row[idx])
            if not day.startswith(month.strftime('%Y-%m')):
                raise ValueError('Wrong calendar month')
            if start.isoformat() <= day <= end.isoformat():
                dates.add(day)
    return sorted(dates)

def tables(data):
    out = list(data.get('tables', []))
    if data.get('fields') and data.get('data'):
        out.append({'fields': data['fields'], 'data': data['data']})
    return out

def parse_quotes(data, market, day):
    check_date(data, day)
    code, name = ('證券代號', '證券名稱') if market == 'twse' else ('代號', '名稱')
    cols = ('開盤價', '最高價', '最低價', '收盤價', '成交股數', '漲跌價差') if market == 'twse' else ('開盤', '最高', '最低', '收盤', '成交股數', '漲跌')
    candidates = [t for t in tables(data) if code in t.get('fields', []) and cols[0] in t.get('fields', [])]
    # TPEx contains additional non-stock tables; use the official main stock table only.
    if market == 'tpex':
        candidates = [t for t in candidates if t.get('title') == '上櫃股票行情']
    if len(candidates) != 1:
        raise ValueError(f'{market} quote table absent/ambiguous')
    t = candidates[0]
    if market == 'tpex' and iso_date(t.get('date', '')) != day:
        raise ValueError('Wrong TPEx quote table date')
    fs = t['fields']; positions = [fs.index(c) for c in cols]
    ci, ni = fs.index(code), fs.index(name)
    out = {}
    for row in t['data']:
        ticker = clean(row[ci])
        if not ordinary(ticker):
            continue
        op, hi, lo, cl, volume, change = [num(row[i]) for i in positions]
        if market == 'twse' and change is not None:
            sign = clean(row[fs.index('漲跌(+/-)')])
            if '-' in sign or '－' in sign:
                change = -abs(change)
            elif '+' in sign or '＋' in sign:
                change = abs(change)
            elif sign not in ('', ' '):
                change = None  # X: ex-right/ex-dividend reference unavailable.
        out[ticker] = dict(name=clean(row[ni]), open=op, high=hi, low=lo,
                           close=cl, volume=volume, change=change)
    if len(out) < 100:
        raise ValueError(f'{market} quotes too few: {len(out)}')
    return out

def parse_flows(data, market, day, investor="foreign"):
    if investor not in ("foreign", "trust"):
        raise ValueError("Unknown investor")
    check_date(data, day)
    out = {}
    if market == 'twse':
        label = '外陸資買賣超股數(不含外資自營商)' if investor == 'foreign' else '投信買賣超股數'
        candidates = [t for t in tables(data) if label in t.get('fields', [])]
        if len(candidates) != 1:
            raise ValueError('TWSE institutional flow header changed')
        t = candidates[0]; fs = t['fields']
        ci, ni = fs.index('證券代號'), fs.index(label)
        buy_label, sell_label = ('外陸資買進股數(不含外資自營商)', '外陸資賣出股數(不含外資自營商)') if investor == 'foreign' else ('投信買進股數', '投信賣出股數')
        bi, si = fs.index(buy_label), fs.index(sell_label)
        for row in t['data']:
            ticker = clean(row[ci])
            if not ordinary(ticker):
                continue
            b, s, n = [num(row[i]) for i in (bi, si, ni)]
            if None in (b, s, n) or b - s != n:
                raise ValueError('TWSE institutional buy/sell identity mismatch')
            out[ticker] = int(n)
    else:
        candidates = [t for t in tables(data) if t.get('title') == '三大法人買賣明細資訊']
        if len(candidates) != 1:
            raise ValueError('TPEx flow table absent/ambiguous')
        t = candidates[0]; fs = t.get('fields', [])
        if iso_date(t.get('date', '')) != day or len(fs) != 24 or fs[:2] != ['代號', '名稱'] or fs[-1] != '三大法人買賣超股數合計':
            raise ValueError('TPEx institutional schema/date changed')
        if int(t.get('totalCount', -1)) != len(t['data']):
            raise ValueError('TPEx institutional row count mismatch')
        for row in t['data']:
            ticker = clean(row[0])
            if not ordinary(ticker):
                continue
            if len(row) != 24:
                raise ValueError('TPEx institutional row width changed')
            b, s, n = [num(row[i]) for i in ((2, 3, 4) if investor == 'foreign' else (11, 12, 13))]
            if None in (b, s, n) or b - s != n:
                raise ValueError('TPEx institutional buy/sell identity mismatch')
            out[ticker] = int(n)  # Foreign group: columns 2/3/4. Investment trust: columns 11/12/13.
    if len(out) < 100:
        raise ValueError(f'{market} flows too few: {len(out)}')
    return out

def fetch_day(day, market, cache, delay, refresh=False):
    path = cache / market / (day + '.json')
    saved = {}
    if path.exists() and not refresh:
        candidate = read(path)
        if (candidate.get('schema') in (1, SCHEMA) and candidate.get('date') == day
                and candidate.get('market') == market and len(candidate.get('quotes', {})) >= 100):
            saved = candidate
            if len(saved.get('flows', {})) >= 100 and len(saved.get('trust_flows', {})) >= 100:
                return saved
    date_param = day.replace('-', '') if market == 'twse' else day.replace('-', '/')
    qp = {'date': date_param, 'response': 'json'}
    fp = dict(qp)
    if market == 'twse':
        qp['type'] = 'ALLBUT0999'; fp['selectType'] = 'ALLBUT0999'
    else:
        qp['id'] = ''; fp.update(type='Daily', sect='EW')
    # Upgrade the existing v1 cache without downloading its verified OHLC again.
    quotes = saved.get('quotes')
    if quotes is None:
        q = get_json(URLS[market, 'quotes'], qp, delay)
        quotes = parse_quotes(q, market, day)
    f = get_json(URLS[market, 'flows'], fp, delay)
    d = dict(schema=SCHEMA, date=day, market=market,
             retrieved_at=dt.datetime.now(TZ).isoformat(timespec='seconds'),
             sources=[URLS[market, 'quotes'], URLS[market, 'flows']],
             quotes=quotes, flows=parse_flows(f, market, day, 'foreign'),
             trust_flows=parse_flows(f, market, day, 'trust'))
    atomic(path, d)
    return d


def download(dates, markets, cache, delay, refresh=False):
    """At most two workers; one sequential worker per market. No mass per-stock requests."""
    all_data, failures, coverage = {}, [], []
    def one_market(market):
        loaded, bad, cov = {}, [], []
        for i, day in enumerate(dates):
            try:
                d = fetch_day(day, market, cache, delay, refresh)
                loaded[day] = d
                cov.append(dict(market=market, date=day, status='ok', quotes=len(d['quotes']), flows=len(d['flows']), trust_flows=len(d['trust_flows']), error=''))
            except Exception as exc:
                error = str(exc)
                bad.append(dict(market=market, date=day, error=error))
                cov.append(dict(market=market, date=day, status='failed', quotes=0, flows=0, trust_flows=0, error=error))
                print('MISSING', market, day, error, flush=True)
            if (i + 1) % 10 == 0 or i + 1 == len(dates):
                print(f'{market}: {i+1}/{len(dates)} sessions, failed={len(bad)}', flush=True)
        return market, loaded, bad, cov
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(markets)) as pool:
        for market, loaded, bad, cov in pool.map(one_market, markets):
            all_data[market] = loaded; failures.extend(bad); coverage.extend(cov)
    return all_data, failures, coverage

def tradable(q):
    if not q or any(q.get(k) is None or q[k] <= 0 for k in ('open', 'high', 'low', 'close', 'volume')):
        return False
    return q['low'] <= min(q['open'], q['close']) <= max(q['open'], q['close']) <= q['high']

def locked(q):
    # Daily bars cannot prove queue execution; conservatively exclude every one-price session.
    return q['high'] == q['low']

def action_reason(prev, q):
    if not prev or not q or num(prev.get('close')) is None or num(q.get('close')) is None:
        return 'missing_corporate_action_check'
    if q.get('change') is None:
        return 'reference_price_unavailable'
    reference = q['close'] - q['change']
    if abs(reference - prev['close']) > max(.025, prev['close'] * .001):
        return 'suspected_ex_dividend_split_or_capital_action'
    return ''

def study(data, dates, year, mode='first', fee=.001425, tax=.003, slippage=.0005, investor='foreign', stop_loss=.08):
    if stop_loss is not None and not 0 < stop_loss < 1:raise ValueError('Invalid stop loss')
    if investor not in ('foreign','trust'):raise ValueError('Unknown investor')
    trades = []
    for market, days in data.items():
        runs, known = {}, {}
        for i, day in enumerate(dates):
            d = days.get(day)
            if d is None:
                runs.clear(); known.clear()  # Never splice across a missing market session.
                continue
            flow = d['trust_flows' if investor == 'trust' else 'flows']
            for ticker in set(runs) - set(flow):
                runs.pop(ticker, None); known.pop(ticker, None)
            for ticker, net in flow.items():
                if net <= 0:
                    runs[ticker] = 0; known[ticker] = True
                    continue
                runs[ticker] = runs.get(ticker, 0) + 1
                if day[:4] != str(year):
                    continue
                for threshold in THRESHOLDS:
                    hit = runs[ticker] == threshold if mode == 'first' else runs[ticker] >= threshold
                    # Left-censored runs cannot be called the first threshold crossing.
                    if not hit or (mode == 'first' and not known.get(ticker, False)):
                        continue
                    entry_i = i + 1
                    if entry_i < len(dates) and dates[entry_i][:4] != str(year):
                        continue
                    name = d['quotes'].get(ticker, {}).get('name', ticker)
                    for horizon in HORIZONS:
                        t = dict(investor=investor, market=market, ticker=ticker, name=name, streak=threshold, run_length=runs[ticker],
                                 signal_date=day, horizon=horizon, entry_date='', exit_date='', status='', reason='',
                                 entry_open='', exit_close='', gross_pct='', net_pct='', planned_exit_date='',
                                 exit_price='', exit_type='', actual_holding_days='', stop_price='')
                        trades.append(t)
                        if entry_i >= len(dates):
                            t.update(status='pending_entry', reason='next_session_not_observed'); continue
                        t['entry_date'] = dates[entry_i]
                        exit_i = entry_i + horizon - 1  # Entry day counts as holding day 1.
                        t.update(planned_exit_date=dates[exit_i] if exit_i < len(dates) else '',
                                 exit_price='', exit_type='', actual_holding_days='', stop_price='')
                        prev = d['quotes'].get(ticker)
                        op = None
                        for j in range(entry_i, min(exit_i+1, len(dates))):
                            q = days.get(dates[j], {}).get('quotes', {}).get(ticker)
                            if not tradable(q):
                                t.update(status='excluded', reason='missing_suspended_or_invalid_OHLCV'); break
                            if j == entry_i and locked(q):
                                t.update(status='excluded', reason='one_price_entry_or_exit_execution_unverified'); break
                            why = action_reason(prev, q)
                            if why:
                                t.update(status='excluded', reason=why); break
                            if op is None:
                                op = q['open']
                                t['entry_open'] = op
                                t['stop_price'] = op*(1-stop_loss) if stop_loss is not None else ''
                            price, kind = None, ''
                            # Strictly greater than 8% loss: touching exactly -8% alone is not a breach.
                            # Stop-market proxy: gaps fill at opening price; intraday breaches at threshold.
                            if stop_loss is not None and q['open'] < t['stop_price']:
                                price, kind = q['open'], 'stop_gap'
                            elif stop_loss is not None and q['low'] < t['stop_price']:
                                price, kind = t['stop_price'], 'stop_intraday'
                            elif j == exit_i:
                                price, kind = q['close'], 'expiry'
                            if price is not None:
                                if locked(q):
                                    t.update(status='excluded', reason='one_price_entry_or_exit_execution_unverified'); break
                                gross = price/op-1
                                net_return = price*(1-slippage)*(1-fee-tax)/(op*(1+slippage)*(1+fee))-1
                                t.update(status='completed', exit_date=dates[j], exit_price=price,
                                         exit_close=q['close'], exit_type=kind, actual_holding_days=j-entry_i+1,
                                         gross_pct=round(gross*100,8), net_pct=round(net_return*100,8))
                                break
                            prev = q
                        if not t['status']:
                            t.update(status='pending_exit', reason='holding_period_not_mature')
    return trades

def summarize(trades):
    summary, cohorts = [], []
    for investor in sorted({t['investor'] for t in trades}):
      for market in ('all', 'twse', 'tpex'):
          group = [t for t in trades if t['investor'] == investor and (market == 'all' or t['market'] == market)]
          if not group:continue
          for streak in THRESHOLDS:
              for horizon in HORIZONS:
                  ts = [t for t in group if t['streak'] == streak and t['horizon'] == horizon]
                  done = [t for t in ts if t['status'] == 'completed']
                  statuses = collections.Counter(t['status'] for t in ts)
                  values = [t['net_pct'] for t in done]
                  by_date = collections.defaultdict(list)
                  for t in done:by_date[t['entry_date']].append(t['net_pct'])
                  for day, vs in sorted(by_date.items()):
                      cohorts.append(dict(investor=investor, market=market, streak=streak, horizon=horizon, entry_date=day,
                                          trades=len(vs), equal_weight_net_pct=statistics.mean(vs)))
                  summary.append(dict(investor=investor, market=market, streak=streak, horizon=horizon, signals=len(ts),
                      completed=len(done), stopped=sum(t.get('exit_type','').startswith('stop_') for t in done),
                      stop_rate_pct=100*sum(t.get('exit_type','').startswith('stop_') for t in done)/len(done) if done else '', pending=statuses['pending_entry']+statuses['pending_exit'], excluded=statuses['excluded'],
                      gross_mean_pct=statistics.mean(t['gross_pct'] for t in done) if done else '',
                      net_mean_pct=statistics.mean(values) if values else '',
                      net_median_pct=statistics.median(values) if values else '',
                      net_win_rate_pct=100*sum(v>0 for v in values)/len(values) if values else '',
                      net_best_pct=max(values) if values else '', net_worst_pct=min(values) if values else '',
                      entry_dates=len(by_date),
                      entry_date_equal_weight_mean_pct=statistics.mean(statistics.mean(v) for v in by_date.values()) if by_date else ''))
    return summary, cohorts

def write_csv(path, rows):
    if not rows:
        path.write_text('\ufeff', encoding='utf-8'); return
    with path.open('w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0])); writer.writeheader(); writer.writerows(rows)

def report(out, summary, meta):
    rows = ''.join('<tr>'+''.join(f'<td>{html.escape(str(r[k]) if not isinstance(r[k],float) else f"{r[k]:.3f}")}</td>'
                   for k in ('investor','market','streak','horizon','completed','stopped','pending','excluded','gross_mean_pct','net_mean_pct','net_median_pct','net_win_rate_pct'))+'</tr>' for r in summary)
    title=f"法人連買回測 {meta['year']}（{'投信' if meta['investor']=='trust' else '外資' if meta['investor']=='foreign' else '外資＋投信'}）"
    doc=f'''<!doctype html><html lang="zh-Hant"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title><style>body{{font:16px system-ui;max-width:1150px;margin:32px auto;padding:0 16px;color:#182436}}table{{border-collapse:collapse;width:100%;font-variant-numeric:tabular-nums}}td,th{{border-bottom:1px solid #ddd;padding:10px;text-align:right;white-space:nowrap}}th{{background:#edf2f8}}.scroll{{overflow:auto}}p{{line-height:1.7}}code{{overflow-wrap:anywhere}}</style>
<h1>{title}</h1><p>截至 {meta['as_of']}；訊號模式：{meta['signal_mode']}。連買達標後下一交易日開盤買入，買入日算第1天；第3／5／10／20個交易日收盤賣出。零或賣超中斷連買，缺值不當成零。</p>
<p>停損：{'關閉' if not meta['stop_loss'] else str(round(meta['stop_loss']*100,4))+'%'}；以進場開盤價計算，不含交易成本。每日依序檢查開盤與最低價；虧損嚴格超過門檻時，跳空以開盤價、盤中以門檻價模擬賣出，再計滑價及稅費。恰好觸及門檻不算跌破；到期日也先檢查停損。未觸發才到期收盤出場。停損後不再檢查後續價格。日K無法確認成交或價格限制，一價出場保守排除，因此不保證實際損失只到8%。</p>
<p>foreign＝外資及陸資（不含外資自營商），trust＝投信；各自以本身每日淨買超辨識連買，兩者不混合。歷史每日股票池，排除0開頭及91開頭TDR；不以目前上市名單回篩。含稅費與滑價，未計最低手續費、股數取整或現金利息。未到期另列；一價成交無法驗證、缺價、疑似除權息／分割／減資區間保守排除。</p>
<p><strong>這是每筆訊號的事件研究，不是固定本金投資組合績效。</strong>不同訊號可能重疊，平均報酬與勝率不能當作可實現的累積／年化報酬；買賣成交仍是日K模擬，非逐筆成交驗證。新下市或停牌缺價排除可能形成選樣偏誤，完整狀態保留於trades.csv。</p>
<div class="scroll"><table><thead><tr>{''.join('<th>'+s+'</th>' for s in ['法人','市場','連買天數','持有天數','完成','停損筆數','未到期','排除','平均毛報酬%','平均淨報酬%','中位淨報酬%','淨勝率%'])}</tr></thead><tbody>{rows}</tbody></table></div>
<p>平均淨報酬已計雙邊手續費各 {meta['fee']*100:.4f}%、賣出稅 {meta['tax']*100:.3f}%、雙邊滑價各 {meta['slippage']*100:.3f}%。另附每日進場批次等權平均，避免訊號多的日期完全主導統計。所有結果均非投資建議。</p></html>'''
    (out/'report.html').write_text(doc,encoding='utf-8')

def self_test():
    import copy
    def fixture(n=35):
        dates=[(dt.date(2026,1,1)+dt.timedelta(days=i)).isoformat() for i in range(n)]
        quote=dict(name='測試公司',open=100.,high=103.,low=99.,close=102.,volume=10000.,change=0.)
        days={d:dict(quotes={'2330':dict(quote)},flows={'2330':0 if i==0 else 100}) for i,d in enumerate(dates)}
        return dates,{'twse':days}
    dates,data=fixture()
    ts=study(data,dates,2026)
    assert len(ts)==8 and all(t['status']=='completed' for t in ts)
    t=next(t for t in ts if t['streak']==3 and t['horizon']==3)
    assert t['signal_date']==dates[3] and t['entry_date']==dates[4] and t['exit_date']==dates[6]
    assert abs(t['gross_pct']-2)<1e-8
    assert t['net_pct']<t['gross_pct']
    assert next(t for t in ts if t['streak']==5)['entry_date']==dates[6]
    # Later prices cannot create an earlier signal.
    modified=copy.deepcopy(data)
    for day in dates[10:]:modified['twse'][day]['quotes']['2330']['close']=50
    assert {(t['signal_date'],t['streak']) for t in study(modified,dates,2026)}=={(t['signal_date'],t['streak']) for t in ts}
    # Rolling mode explicitly creates overlapping windows; default mode does not.
    assert len(study(data,dates,2026,'rolling'))>len(ts)
    dates2,data2=fixture(7)
    short=study(data2,dates2,2026)
    assert any(t['status']=='pending_exit' for t in short)
    assert next(t for t in short if t['streak']==3 and t['horizon']==3)['status']=='completed'
    # Zero breaks a run; missing flow does not become a fabricated zero or connect old buys.
    dates3,data3=fixture(9)
    data3['twse'][dates3[2]]['flows']['2330']=0
    assert next(t for t in study(data3,dates3,2026) if t['streak']==3)['signal_date']==dates3[5]
    del data3['twse'][dates3[2]]['flows']['2330']
    assert not study(data3,dates3,2026)  # Next run's start is unknown until an observed zero/sell.
    dates4,data4=fixture();data4['twse'][dates4[4]]['quotes']['2330']['change']=5
    assert next(t for t in study(data4,dates4,2026) if t['streak']==3)['reason']=='suspected_ex_dividend_split_or_capital_action'
    dates4,data4=fixture();q=data4['twse'][dates4[4]]['quotes']['2330'];q.update(open=102.,high=102.,low=102.)
    assert next(t for t in study(data4,dates4,2026) if t['streak']==3)['reason']=='one_price_entry_or_exit_execution_unverified'
    dates4,data4=fixture();del data4['twse'][dates4[5]]['quotes']['2330']
    assert next(t for t in study(data4,dates4,2026) if t['streak']==3)['reason']=='missing_suspended_or_invalid_OHLCV'
    dates4,data4=fixture()
    for d in dates4:data4['twse'][d]['flows']['2330']=10
    assert not study(data4,dates4,2026)  # Left edge is not a known first streak crossing.
    summary,cohorts=summarize(ts)
    assert len(summary)==16 and len(cohorts)==16
    assert ordinary('2330') and not ordinary('0050') and not ordinary('9103')
    assert iso_date('115/01/02')=='2026-01-02'
    try:check_date({'date':'20260103'},'2026-01-02')
    except ValueError:pass
    else:raise AssertionError('Date mismatch accepted')
    dates5,data5=fixture()
    for i,day in enumerate(dates5):data5['twse'][day]['trust_flows']={'2330':0 if i==0 else -100}
    assert not study(data5,dates5,2026,investor='trust')
    assert len(study(data5,dates5,2026,investor='foreign'))==8
    for day in dates5:data5['twse'][day]['trust_flows']=dict(data5['twse'][day]['flows'])
    trust=study(data5,dates5,2026,investor='trust')
    assert len(trust)==8 and all(t['investor']=='trust' for t in trust)
    assert trust[0]['net_pct']==ts[0]['net_pct']
    assert len(summarize(ts+trust)[0])==32
    # Stop tests: apply identically to both investors and all holding horizons.
    def stop_fixture(n=35):
        ds,dd=fixture(n)
        for k,day in enumerate(ds):
            dd['twse'][day]['quotes']['2330'].update(open=100.,high=101.,low=99.,close=100.,change=0.)
            dd['twse'][day]['trust_flows']=dict(dd['twse'][day]['flows'])
        return ds,dd
    def picked(dd,ds,inv='foreign',stop=.08):
        return [t for t in study(dd,ds,2026,investor=inv,stop_loss=stop) if t['streak']==3]
    ds,dd=stop_fixture()
    dd['twse'][ds[4]]['quotes']['2330']['low']=91.
    for inv in ('foreign','trust'):
        result=picked(dd,ds,inv)
        assert all(t['exit_type']=='stop_intraday' and abs(t['gross_pct']+8)<1e-7 and t['actual_holding_days']==1 for t in result)
        assert all(t['net_pct'] < -8 for t in result)
    # Equality is not a breach; expiry still takes the usual closing price.
    dd['twse'][ds[4]]['quotes']['2330']['low']=92.
    assert all(t['exit_type']=='expiry' for t in picked(dd,ds))
    ds,dd=stop_fixture()
    dd['twse'][ds[5]]['quotes']['2330'].update(open=89.,high=100.,low=88.)
    assert all(t['exit_type']=='stop_gap' and t['gross_pct']==-11 for t in picked(dd,ds))
    # Missing prices AFTER actual stop must not exclude an already closed trade.
    del dd['twse'][ds[6]]['quotes']['2330']
    assert all(t['status']=='completed' for t in picked(dd,ds))
    ds,dd=stop_fixture(6)
    dd['twse'][ds[5]]['quotes']['2330']['low']=91.
    assert all(t['status']=='completed' for t in picked(dd,ds))
    assert all(t['status']=='pending_exit' for t in picked(dd,ds,stop=None))
    ds,dd=stop_fixture()
    dd['twse'][ds[6]]['quotes']['2330']['low']=91.
    assert picked(dd,ds)[0]['exit_type']=='stop_intraday'  # Expiry-day stop takes precedence.
    ds,dd=stop_fixture()
    dd['twse'][ds[5]]['quotes']['2330'].update(open=90.,high=90.,low=90.,close=90.,change=-10.)
    assert all(t['status']=='excluded' for t in picked(dd,ds))
    ds,dd=stop_fixture()
    assert [t['net_pct'] for t in picked(dd,ds)]==[t['net_pct'] for t in picked(dd,ds,stop=None)]
    print('PASS: 8% stop, strict threshold, intraday/gap/expiry timing, early exit before maturity, post-exit data isolation, locked limits, both investors, disabled-stop parity')
    print('PASS: independent foreign/trust signals, entry/exit timing, 3/5-day signals, all horizons, costs, first/rolling, missing data, censoring, action and execution exclusions, summaries and date validation')
    return 0

def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--year',type=int,default=2026)
    p.add_argument('--investor',choices=['foreign','trust','both'],default='trust',help='foreign=外資, trust=投信, both=分別回測兩者')
    p.add_argument('--as-of',help='YYYY-MM-DD; default latest day after 18:30 Taipei, otherwise yesterday')
    p.add_argument('--markets',default='twse,tpex')
    p.add_argument('--signal-mode',choices=['first','rolling'],default='first')
    p.add_argument('--cache-dir',type=Path,default=Path('.cache/foreign-streak-v1'))
    p.add_argument('--output',type=Path,default=Path('backtest-results/foreign_streak_2026'))
    p.add_argument('--delay',type=float,default=.8)
    p.add_argument('--fee',type=float,default=.001425)
    p.add_argument('--tax',type=float,default=.003)
    p.add_argument('--slippage',type=float,default=.0005)
    p.add_argument('--stop-loss',type=float,default=.08,help='Price loss fraction; default .08; 0 disables stop')
    p.add_argument('--refresh',action='store_true')
    p.add_argument('--offline',action='store_true',help='Use cached calendar and daily files only; no network')
    p.add_argument('--self-test',action='store_true',help='Run deterministic offline backtest tests')
    a=p.parse_args(argv)
    if a.self_test:
        return self_test()
    if not 0 <= a.stop_loss < 1:p.error('stop-loss must be >=0 and <1')
    now=dt.datetime.now(TZ)
    as_of=dt.date.fromisoformat(a.as_of) if a.as_of else now.date()-dt.timedelta(days=int(now.time()<dt.time(18,30)))
    if as_of>now.date() or (as_of==now.date() and now.time()<dt.time(18,30)):
        p.error('as-of must be a completed institutional reporting day (after 18:30 Taipei)')
    if a.year<2006 or as_of<dt.date(a.year,1,1):p.error('Invalid year/as-of')
    if not all(0<=x<.1 for x in (a.fee,a.tax,a.slippage)) or a.delay<.1:p.error('Invalid costs/delay')
    markets=tuple(dict.fromkeys(a.markets.split(',')))
    if not markets or any(m not in ('twse','tpex') for m in markets):p.error('markets must be twse,tpex')
    a.output.mkdir(parents=True,exist_ok=True)
    start=dt.date(a.year-1,12,1)
    # Allow subsequent January data only when explicitly requested via --as-of, to finish year-end entries.
    if as_of>dt.date(a.year+1,2,28):as_of=dt.date(a.year+1,2,28)
    meta=dict(year=a.year,as_of=as_of.isoformat(),signal_mode=a.signal_mode,fee=a.fee,tax=a.tax,slippage=a.slippage,
              stop_loss=a.stop_loss,investor=a.investor,generated_at=now.isoformat(),status='collecting',scope='historical_4digit_stocks_excluding_0_and_91',sources=URLS_AS_LIST)
    atomic(a.output/'metadata.json',meta)
    try:
        if a.offline:
            dates=[]
            for path in sorted((a.cache_dir/'calendar').glob('*.json')):
                d=read(path);idx=d['fields'].index('日期')
                dates.extend(iso_date(row[idx]) for row in d['data'])
            dates=sorted({d for d in dates if start.isoformat()<=d<=as_of.isoformat()})
            # Calendar must span every requested month even when its dates happen to be absent.
            cursor=start.replace(day=1)
            while cursor<=as_of:
                if not (a.cache_dir/'calendar'/(cursor.strftime('%Y-%m')+'.json')).exists():
                    raise ValueError('Missing offline calendar month '+str(cursor))
                cursor=(cursor.replace(day=28)+dt.timedelta(days=4)).replace(day=1)
            data={m:{day:read(a.cache_dir/m/(day+'.json')) for day in dates if (a.cache_dir/m/(day+'.json')).exists()} for m in markets}
            failures=[dict(market=m,date=day,error='Missing offline daily cache') for m in markets for day in dates if day not in data[m]]
            cov=[dict(market=m,date=day,status='ok' if day in data[m] else 'failed') for m in markets for day in dates]
        else:
            dates=calendar(start,as_of,a.cache_dir,a.delay,a.refresh)
            print(f'Official sessions {dates[0] if dates else None} to {dates[-1] if dates else None}: {len(dates)}; markets={markets}',flush=True)
            data,failures,cov=download(dates,markets,a.cache_dir,a.delay,a.refresh)
        write_csv(a.output/'coverage.csv',cov)
        if failures or not dates:
            atomic(a.output/'failures.json',failures)
            raise ValueError(f'{len(failures)} daily sources missing; statistics withheld to avoid false full-year results. Rerun to resume cache.')
        investors=('foreign','trust') if a.investor=='both' else (a.investor,)
        trades=[]
        for investor in investors:
            missing=[(m,day) for m in markets for day in dates if len(data[m][day].get('trust_flows' if investor=='trust' else 'flows',{}))<100]
            if missing:raise ValueError(f'Missing {investor} cache on {len(missing)} market-days; rerun without --offline to upgrade cache')
            trades.extend(study(data,dates,a.year,a.signal_mode,a.fee,a.tax,a.slippage,investor,a.stop_loss or None))
        summary,cohorts=summarize(trades)
        meta.update(status='complete',official_sessions=len(dates),last_session=dates[-1],trade_rows=len(trades),
                    note='Event study, not cumulative portfolio performance; see README and report.html')
        write_csv(a.output/'trades.csv',trades);write_csv(a.output/'summary.csv',summary);write_csv(a.output/'entry_date_cohorts.csv',cohorts)
        atomic(a.output/'metadata.json',meta);report(a.output,summary,meta)
        print(json.dumps({'status':'complete','output':str(a.output),'trade_rows':len(trades)},ensure_ascii=False))
    except Exception as exc:
        meta.update(status='failed',error=str(exc));atomic(a.output/'metadata.json',meta)
        print(str(exc),file=sys.stderr);return 1
    return 0

URLS_AS_LIST=sorted(set(URLS.values()))+['https://www.twse.com.tw/rwd/zh/afterTrading/FMTQIK']
if __name__=='__main__':raise SystemExit(main())


