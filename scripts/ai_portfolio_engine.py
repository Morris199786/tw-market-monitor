"""Forward-only, self-financing paper portfolio. No historical target reconstruction."""
from copy import deepcopy
from datetime import datetime
from zoneinfo import ZoneInfo
import math

TZ = ZoneInfo('Asia/Taipei')
VERSION = 'three-pillar-paper-v1'
DEFAULTS = dict(initial_cash=1000000, max_positions=10, entry_weight=.10,
                commission_rate=.001425, minimum_commission=20,
                sell_tax=.003, slippage=.0005, minimum_score=60)


def stamp(value):
    d = datetime.fromisoformat(value.replace('Z', '+00:00'))
    return d.replace(tzinfo=TZ) if d.tzinfo is None else d.astimezone(TZ)


def number(value):
    try:
        n = float(value)
        return n if math.isfinite(n) else None
    except (ValueError, TypeError):
        return None


def initial(config, now):
    return dict(schema=1, strategy=VERSION, started_at=now, config=deepcopy(config),
                cash=float(config['initial_cash']), positions={}, decisions=[],
                trades=[], equity=[], processed_sessions=[], execution_warnings=[])


def frozen_decision(state, proposal):
    """One immutable published decision per market date. Missing sources != empty target."""
    state['latest_attempt'] = proposal
    if not proposal.get('valid'):
        state['latest_attempt'] = proposal
        return False
    if any(d['date'] == proposal['date'] for d in state['decisions']):
        return False
    if state['decisions'] and proposal['date'] < state['decisions'][-1]['date']:
        raise ValueError('Cannot append an older decision')
    if stamp(proposal['available_at']) < stamp(proposal['date'] + 'T13:30:00+08:00'):
        raise ValueError('Decision must be after the close')
    symbols = [x['ticker'] for x in proposal['targets']]
    if len(set(symbols)) != len(symbols) or len(symbols) > state['config']['max_positions']:
        raise ValueError('Invalid target list')
    state['decisions'].append(deepcopy(proposal))
    state['latest_attempt'] = proposal
    return True


def fee(value, config):
    return max(config['minimum_commission'], value * config['commission_rate'])


def tradable(bar):
    if not bar or bar.get('corporate_action') or bar.get('suspended'):
        return False
    op, hi, lo, cl, vol = (number(bar.get(k)) for k in ('open','high','low','close','volume'))
    # Conservative: all one-price days are left unfilled; avoids fictitious limit fills.
    return all(x is not None and x > 0 for x in (op,hi,lo,cl,vol)) and hi > lo and lo <= min(op,cl) <= max(op,cl) <= hi


def session(state, day, bars, closes):
    """Use only a decision that existed BEFORE this session's opening auction."""
    if day in state['processed_sessions'] or day <= state['started_at'][:10]:
        return False
    if state['processed_sessions'] and day <= state['processed_sessions'][-1]:
        raise ValueError('Sessions must be processed chronologically')
    opening = stamp(day + 'T09:00:00+08:00')
    eligible = [d for d in state['decisions'] if stamp(d['available_at']) < opening]
    decision = eligible[-1] if eligible else None
    config = state['config']; positions = state['positions']
    warnings = []
    for ticker,p in positions.items():
        if (bars.get(ticker) or {}).get('corporate_action'):
            p['valuation_blocked']=True
    # Existing lots remain unchanged when the ticker is retained. No daily rebalancing.
    targets = {x['ticker']: x for x in decision['targets']} if decision else None
    opening_equity = state['cash'] + sum(p['shares'] * (p['mark'] if p.get('valuation_blocked') else number((bars.get(t) or {}).get('open')) or p['mark']) for t,p in positions.items())
    if targets is not None:
        for ticker in list(positions):
            if ticker in targets:
                continue
            p = positions[ticker]; bar = bars.get(ticker)
            if p.get('valuation_blocked') or not tradable(bar):
                warnings.append(dict(date=day,ticker=ticker,side='sell',reason='缺開盤資料／單一價／暫停交易／公司行動，保留持倉等待確認'))
                continue
            price = max(bar['low'], bar['open'] * (1-config['slippage']))
            gross = p['shares'] * price; commission = fee(gross,config); tax = gross*config['sell_tax']
            net = gross-commission-tax
            state['cash'] += net
            state['trades'].append(dict(date=day,ticker=ticker,name=p['name'],side='sell',shares=p['shares'],price=price,
                commission=commission,tax=tax,cash_flow=net,realized_pnl=net-p['cost'],decision_date=decision['date'],reason='移出正式持倉名單'))
            del positions[ticker]
        for ticker, target in targets.items():
            if ticker in positions:
                continue
            if len(positions) >= config['max_positions']:
                warnings.append(dict(date=day,ticker=ticker,side='buy',reason='未成交賣單仍占持倉，暫緩買入'))
                continue
            bar = bars.get(ticker)
            if not tradable(bar):
                warnings.append(dict(date=day,ticker=ticker,side='buy',reason='無可驗證開盤資料或單一價，暫緩買入'))
                continue
            price = min(bar['high'], bar['open']*(1+config['slippage']))
            budget = min(state['cash'],opening_equity*config['entry_weight'])
            shares = int(max(0,budget-config['minimum_commission'])/(price*(1+config['commission_rate'])))
            if shares < 1:
                continue
            gross=shares*price; commission=fee(gross,config); cost=gross+commission
            if cost>state['cash']+1e-7:
                raise ValueError('Cash cannot become negative')
            state['cash']-=cost
            positions[ticker]=dict(ticker=ticker,name=target['name'],shares=shares,cost=cost,entry_date=day,mark=price,
                entry_reason=target.get('evidence',[]),decision_date=decision['date'])
            state['trades'].append(dict(date=day,ticker=ticker,name=target['name'],side='buy',shares=shares,price=price,
                commission=commission,tax=0,cash_flow=-cost,decision_date=decision['date'],reason='新入選正式持倉名單'))
    stale=[]
    for ticker,p in positions.items():
        close=number(closes.get(ticker))
        if p.get('valuation_blocked'):
            stale.append(ticker)
            warnings.append(dict(date=day,ticker=ticker,side='mark',reason='疑似價格調整／公司行動，暫沿用前次標記，待確認'))
        elif close and close>0:
            p['mark']=close;p['mark_date']=day
        else:
            stale.append(ticker)
    equity=state['cash']+sum(p['shares']*p['mark'] for p in positions.values())
    peak=max([config['initial_cash'],equity]+[r['equity'] for r in state['equity']])
    state['equity'].append(dict(date=day,equity=equity,cash=state['cash'],return_pct=(equity/config['initial_cash']-1)*100,
        drawdown_pct=(equity/peak-1)*100,stale_marks=stale))
    state['processed_sessions'].append(day)
    state['execution_warnings'].extend(warnings)
    return True
