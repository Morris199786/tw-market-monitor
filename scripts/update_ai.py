"""Production AI selector: exact BAL_MA_SLOPE_RANK_HEAT25_30 shadow scoring.
Keeps website JSON structure and historical shadow backtest independent.
"""
from sources import *
from tech_universe import tech_tickers
from statistics import mean
import math

LABELS = {
    'flow': '近五日法人資金流入', 'flow_accel': '法人買盤加速度',
    'r5': '五日漲幅', 'breakout': '突破20日高點', 'r10': '十日漲幅',
    'trend': '多頭排列', 'liquidity': '成交金額',
    'ma5_slope': '5MA斜率', 'ma10_slope': '10MA斜率',
    'volume_guard': '異常爆量', 'overheat': '股價過熱',
}
STRATEGY = 'BAL_MA_SLOPE_RANK_HEAT25_30'


def num(x):
    try:
        v = float(str(x).replace(',', ''))
        return v if math.isfinite(v) else None
    except (ValueError, TypeError):
        return None


def pct(a, b):
    return 100 * (b / a - 1) if a is not None and b is not None and a > 0 else None


def percentile(pool, field):
    values = sorted((r[field], r['ticker']) for r in pool if r.get(field) is not None)
    ranks = {t: 100 * i / max(1, len(values) - 1) for i, (_, t) in enumerate(values)}
    for r in pool:
        r[field + '_rank'] = ranks.get(r['ticker'], 0)


def load_snapshots(latest_date):
    result = []
    for p in sorted((ROOT / 'data/history/market').glob('*.json')):
        if latest_date and p.stem > str(latest_date):
            continue
        d = load_json(p, {})
        if isinstance(d.get('stocks'), dict) and d['stocks']:
            result.append((p.stem, d['stocks']))
    return result


def get_pool(exchange, candidates, snapshots, inst):
    today = snapshots[-1][1]
    pool = []
    for ticker, master_row in candidates.items():
        if master_row.get('market') != exchange or ticker not in today:
            continue
        q = today[ticker]
        price = num(q.get('price'))
        if price is None or price <= 0:
            continue
        close = [num(s[1].get(ticker, {}).get('price')) for s in snapshots[-21:]]
        vol = [num(s[1].get(ticker, {}).get('volume')) for s in snapshots[-6:]]
        r5, r10 = pct(close[-6], price), pct(close[-11], price)
        ma5 = mean(close[-5:]) if all(v is not None and v > 0 for v in close[-5:]) else None
        ma5_old = mean(close[-8:-3]) if all(v is not None and v > 0 for v in close[-8:-3]) else None
        ma10 = mean(close[-10:]) if all(v is not None and v > 0 for v in close[-10:]) else None
        ma10_old = mean(close[-13:-3]) if all(v is not None and v > 0 for v in close[-13:-3]) else None
        ma20 = mean(close[-20:]) if all(v is not None and v > 0 for v in close[-20:]) else None
        breakout = pct(max(close[:-1]), price) if all(v is not None and v > 0 for v in close[:-1]) else None
        ratio = vol[-1] / mean(vol[:-1]) if all(v is not None for v in vol) and mean(vol[:-1]) > 0 else None

        flow_sum, turnover_sum, daily_ratios = 0., 0., []
        healthy = True
        for day, stocks in snapshots[-5:]:
            daily = stocks.get(ticker, {})
            row = inst.get(day, {}).get(ticker)
            p, turnover = num(daily.get('price')), num(daily.get('turnover'))
            if not isinstance(row, dict) or p is None or turnover is None:
                healthy = False
                break
            net_amount = sum(num(row.get(k)) or 0 for k in ('foreign', 'trust', 'dealer')) * p
            flow_sum += net_amount
            turnover_sum += turnover
            daily_ratios.append(net_amount / turnover * 100 if turnover > 0 else None)
        flow = flow_sum / turnover_sum * 100 if healthy and turnover_sum > 0 else None
        accel = (mean(daily_ratios[-2:]) - mean(daily_ratios[:3])
                 if healthy and len(daily_ratios) == 5 and all(v is not None for v in daily_ratios)
                 else None)
        pool.append({
            'ticker': ticker, 'name': master_row.get('name', ''), 'entry': price,
            'r5': r5, 'r10': r10, 'flow': flow, 'flow_accel': accel,
            'breakout': breakout, 'volume_ratio': ratio,
            'daily_turnover': num(q.get('turnover')),
            'ma5_slope': pct(ma5_old, ma5), 'ma10_slope': pct(ma10_old, ma10),
            'ma20_gap_pct': pct(ma20, price),
            'trend': int(ma10 is not None and ma20 is not None and price > ma10 > ma20),
            'change_pct': q.get('change_pct'),
        })
    if len(pool) < 20:
        raise RuntimeError(f'AI {exchange} fewer than 20 candidates')
    for field in ('flow', 'flow_accel', 'r5', 'r10', 'breakout', 'daily_turnover', 'ma5_slope', 'ma10_slope'):
        percentile(pool, field)
    for r in pool:
        heat = (1.5 * max(0, r['r5'] - 25) + max(0, r['ma20_gap_pct'] - 30)
                if r['r5'] is not None and r['ma20_gap_pct'] is not None else 0.)
        volume_penalty = min(6., 2. * max(0., (r['volume_ratio'] or 0.) - 3.))
        r['contributions'] = {
            'flow': .25 * r['flow_rank'],
            'flow_accel': .10 * r['flow_accel_rank'],
            'r5': .25 * r['r5_rank'],
            'breakout': .20 * r['breakout_rank'],
            'r10': .10 * r['r10_rank'],
            'trend': 10. * r['trend'],
            'liquidity': .05 * (r['daily_turnover_rank'] - 50),
            'ma5_slope': (.05 * (r['ma5_slope_rank'] - 50) if r['ma5_slope'] is not None else 0.),
            'ma10_slope': (.05 * (r['ma10_slope_rank'] - 50) if r['ma10_slope'] is not None else 0.),
            'volume_guard': -volume_penalty,
            'overheat': -1.5 * heat,
        }
        r['score'] = sum(r['contributions'].values())
    return sorted(pool, key=lambda r: (-r['score'], r['ticker']))


def main():
    master = load_json(ROOT / 'data/master.json', {}).get('stocks', {})
    market_data = load_json(ROOT / 'data/market_latest.json', {})
    market = market_data.get('stocks', {})
    latest_date = market_data.get('date')
    tech = tech_tickers(master)
    candidates = {
        str(t): m for t, m in master.items()
        if str(t) in tech and ordinary_ticker(t)
        and m.get('market') in ('twse', 'tpex') and str(t) in market
    }
    if len(candidates) < 100:
        raise RuntimeError('AI technology universe incomplete')
    snapshots = load_snapshots(latest_date)
    if len(snapshots) < 21 or snapshots[-1][0] != str(latest_date):
        raise RuntimeError(f'AI requires 21 market snapshots ending {latest_date}')
    inst = {}
    for path in (ROOT / 'data/history/institutional').glob('*.json'):
        d = load_json(path, {})
        inst[path.stem] = {**d.get('twse', {}), **d.get('tpex', {})}
    if any(day not in inst for day, _ in snapshots[-5:]):
        raise RuntimeError('AI requires institutional data for five latest trading dates')

    display_names = {str(t): str(m.get('name') or '') for t, m in master.items()}
    for sector in load_json(ROOT / 'data/sectors.json', {}).get('sectors', []):
        for stock in sector.get('stocks', []):
            t, name = str(stock.get('ticker') or ''), str(stock.get('name') or '')
            if t and name:
                display_names[t] = name
    out = {
        'updated_at': now_tpe().isoformat(timespec='minutes'),
        'mode': 'trade_day', 'complete': True, 'universe': '全台股科技普通股',
        'universe_count': {
            mk: sum(m.get('market') == mk for m in candidates.values())
            for mk in ('twse', 'tpex')
        },
        'logic': {
            'version': '2026-10-13-BAL_MA_SLOPE_RANK_HEAT25_30',
            'strategy': STRATEGY, 'mode': 'trade_day',
            'universe': '全台股科技普通股', 'lookback_days': 20,
            'institutional_dates': [day for day, _ in snapshots[-5:]],
            'factors': [
                {'key': k, 'label': LABELS[k], 'weight': w, 'weight_pct': w * 100}
                for k, w in (('flow', .25), ('flow_accel', .10), ('r5', .25),
                             ('breakout', .20), ('r10', .10), ('trend', .10))
            ],
            'details': [
                '目前正式選股策略：放寬B（BAL_MA_SLOPE_RANK_HEAT25_30），與後台36套策略的獨立回測並行',
                '股票池：全台股科技普通股，上市、上櫃分別以同市場百分位排名，各選分數最高20檔；沒有要求所有因子都為正值',
                '近5日法人資金流入率（25分）：外資＋投信＋自營商每日淨買賣超股數×當日收盤價，五日加總後除以五日成交金額，再換算同市場百分位',
                '法人買盤加速度（10分）：最近2日平均法人流入率－前3日平均法人流入率，再換算百分位',
                '五日股價漲幅（25分）：近5個交易日報酬的同市場百分位',
                '突破前20日高點（20分）：收盤價相對前20日最高收盤價的突破程度，再換算百分位；未突破仍可入選',
                '十日股價漲幅（10分）：近10個交易日報酬的同市場百分位',
                '多頭均線排列（10分）：今日收盤價 > 10MA > 20MA 加10分，否則0分',
                '成交金額：0.05×（成交金額百分位－50），介於－2.5至＋2.5分',
                '5MA與10MA斜率：各比較今日均線與3個交易日前均線，分別以0.05×（斜率百分位－50）加減分，各最多±2.5分',
                '異常爆量扣分：－min(6, 2×max(0, 今日成交量／前5日均量－3))，最多扣6分',
                '放寬B過熱扣分：五日漲幅超過25%後，每多1個百分點扣2.25分；20MA正乖離超過30%後，每多1個百分點扣1.5分；兩者累加',
                '最終分數＝上述基本因子與加減分總和；分數可高於100或低於0，並非未來上漲機率',
                '出場回測（5%停損、10%停損、10MA停損）不參與當日選股評分；後台繼續保留所有策略獨立比較',
            ],
            'top_n_each_market': 20, 'markets_ranked_separately': True,
            'score_is_probability': False,
        },
        'twse': [], 'tpex': [],
    }
    for mk in ('twse', 'tpex'):
        pool = get_pool(mk, candidates, snapshots, inst)
        for r in pool[:20]:
            contrib = r['contributions']
            reason = '｜'.join(
                f'{LABELS[k]}貢獻{v:.1f}分'
                for k, v in sorted(contrib.items(), key=lambda x: -x[1])[:3] if v > 0
            )
            tags = []
            if r['trend']:
                tags.append('多頭排列')
            if r['ma5_slope'] is not None and r['ma5_slope'] > 0:
                tags.append('5MA向上')
            if r['ma10_slope'] is not None and r['ma10_slope'] > 0:
                tags.append('10MA向上')
            if r['flow'] is not None and r['flow'] > 0:
                tags.append('法人買超')
            out[mk].append({
                'ticker': r['ticker'], 'name': display_names.get(r['ticker']) or r['name'],
                'score': round(r['score'], 1), 'change_pct': r['change_pct'],
                'tags': tags, 'reason': reason or '無明顯正向因子',
                'factor_scores': {
                    LABELS['flow']: round(r['flow_rank'], 1),
                    LABELS['flow_accel']: round(r['flow_accel_rank'], 1),
                    LABELS['r5']: round(r['r5_rank'], 1),
                    LABELS['breakout']: round(r['breakout_rank'], 1),
                    LABELS['r10']: round(r['r10_rank'], 1),
                    LABELS['trend']: 100 if r['trend'] else 0,
                    LABELS['liquidity']: round(r['daily_turnover_rank'], 1),
                    LABELS['ma5_slope']: round(r['ma5_slope_rank'], 1),
                    LABELS['ma10_slope']: round(r['ma10_slope_rank'], 1),
                    LABELS['volume_guard']: 0,
                    LABELS['overheat']: 0,
                },
                'contributions': {LABELS[k]: round(v, 2) for k, v in contrib.items()},
                'raw': {
                    'flow_pct': r['flow'], 'flow_accel': r['flow_accel'],
                    'r5': r['r5'], 'r10': r['r10'], 'breakout': r['breakout'],
                    'ma5_slope': r['ma5_slope'], 'ma10_slope': r['ma10_slope'],
                    'ma20_gap_pct': r['ma20_gap_pct'],
                    'volume_ratio_5d': r['volume_ratio'],
                    'turnover_today': r['daily_turnover'],
                },
            })
    save_json(ROOT / 'data/ai_picks.json', out)
    print('AI', STRATEGY, latest_date, len(out['twse']), len(out['tpex']))


if __name__ == '__main__':
    main()
