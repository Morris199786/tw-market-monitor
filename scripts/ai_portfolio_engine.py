"""Versioned, self-financing long-only paper account with weighted allocation."""
from copy import deepcopy
from datetime import datetime
from zoneinfo import ZoneInfo
import math
TZ=ZoneInfo('Asia/Taipei')
VERSION='allocation-paper-v2'
DEFAULTS=dict(initial_cash=20000000,max_positions=12,commission_rate=.001425,minimum_commission=20,
              sell_tax=.003,etf_sell_tax=.001,slippage=.0005,minimum_score=60,
              max_stock_weight=.15,max_etf_weight=.25,max_sector_weight=.35,
              discovery_weight=.05,rebalance_band=.02,rebalance_relative=.20,
              participation_rate=.01,bootstrap_days_per_run=7,min_exposure=.40)

def stamp(value):
    d=datetime.fromisoformat(value.replace('Z','+00:00'))
    return d.replace(tzinfo=TZ) if d.tzinfo is None else d.astimezone(TZ)

def number(value):
    try:
        n=float(value);return n if math.isfinite(n) else None
    except (ValueError,TypeError):return None

def initial(config,now):
    return dict(schema=2,strategy=VERSION,started_at=now,config=deepcopy(config),cash=float(config['initial_cash']),
                positions={},decisions=[],trades=[],equity=[],processed_sessions=[],execution_warnings=[],configuration_events=[])

def migrate(state,config,now):
    if state.get('strategy')==VERSION:
        if state['config']!=config:raise ValueError('Account configuration changed; explicit versioned migration required')
        return state,None
    if state.get('strategy')!='three-pillar-paper-v1':raise ValueError('Unknown previous account version')
    if state.get('positions') or state.get('trades') or state.get('equity') or state.get('processed_sessions'):
        raise ValueError('V1 account already traded: preserve it; do not rewrite its capital or performance')
    if abs(state['cash']-state['config']['initial_cash'])>.001:raise ValueError('V1 cash changed; cannot migrate silently')
    new=initial(config,now)
    new['configuration_events'].append(dict(at=now,reason='User requested 20M capital, weighted stock/ETF allocation and market regime',
        previous_strategy=state['strategy'],previous_capital=state['config']['initial_cash'],new_capital=config['initial_cash'],previous_started_at=state['started_at']))
    return new,deepcopy(state)

def frozen_decision(state,proposal):
    state['latest_attempt']=deepcopy(proposal)
    if not proposal.get('valid'):return False
    if any(d['date']==proposal['date'] for d in state['decisions']):return False
    if state['decisions'] and proposal['date']<state['decisions'][-1]['date']:raise ValueError('Cannot backdate a decision')
    if stamp(proposal['available_at'])<stamp(proposal['date']+'T13:30:00+08:00'):raise ValueError('Not a completed session')
    if sum(x.get('weight',0) for x in proposal['targets'])<state['config']['min_exposure']-1e-7:raise ValueError('Below user minimum 40% target exposure')
    targets=proposal['targets'];codes=[t['ticker'] for t in targets]
    if len(set(codes))!=len(codes) or len(codes)>state['config']['max_positions']:raise ValueError('Invalid targets')
    weights=[number(t.get('weight')) for t in targets]
    if any(w is None or w<=0 for w in weights) or sum(weights)>min(1,proposal['regime']['target_exposure'])+1e-6:raise ValueError('Invalid exposure')
    for t in targets:
        cap=state['config']['max_etf_weight'] if t.get('asset_type')=='etf' else state['config']['max_stock_weight']
        if t['weight']>cap+1e-6:raise ValueError('Position exceeds instrument cap')
    state['decisions'].append(deepcopy(proposal));return True

def fee(value,config):return max(config['minimum_commission'],value*config['commission_rate'])

def tradable(bar):
    if not bar or bar.get('corporate_action') or bar.get('suspended'):return False
    op,hi,lo,cl,vol=(number(bar.get(k)) for k in ('open','high','low','close','volume'))
    return all(x is not None and x>0 for x in (op,hi,lo,cl,vol)) and hi>lo and lo<=min(op,cl)<=max(op,cl)<=hi

def session(state,day,bars,closes):
    if day in state['processed_sessions'] or day<=state['started_at'][:10]:return False
    if state['processed_sessions'] and day<=state['processed_sessions'][-1]:raise ValueError('Sessions out of order')
    eligible=[d for d in state['decisions'] if stamp(d['available_at'])<stamp(day+'T09:00:00+08:00')]
    decision=eligible[-1] if eligible else None
    cfg=state['config'];pos=state['positions'];warnings=[]
    for t,p in pos.items():
        if (bars.get(t) or {}).get('corporate_action'):p['valuation_blocked']=True
    opening_equity=state['cash']+sum(p['shares']*(p['mark'] if p.get('valuation_blocked') else number((bars.get(t) or {}).get('open')) or p['mark']) for t,p in pos.items())
    targets={x['ticker']:x for x in decision['targets']} if decision else None
    if targets is not None:
        desired={};force=(sum(p['shares']*(number((bars.get(t) or {}).get('open')) or p['mark']) for t,p in pos.items())/opening_equity)>decision['regime']['target_exposure']+.03
        for t in set(pos)|set(targets):
            p=pos.get(t);target=targets.get(t);op=number((bars.get(t) or {}).get('open'))
            if target is None:desired[t]=0;continue
            if not op:continue
            target_value=opening_equity*target['weight'];current=(p['shares']*op) if p else 0
            difference=abs(current-target_value)
            if p and not force and difference/opening_equity<cfg['rebalance_band'] and difference/max(target_value,1)<cfg['rebalance_relative']:
                desired[t]=p['shares']
            else:desired[t]=int(target_value/op)
        # Sells, including partial reductions, fund subsequent purchases.
        for t in list(pos):
            p=pos[t];qty=p['shares']-desired.get(t,p['shares'])
            if qty<=0:continue
            b=bars.get(t)
            if p.get('valuation_blocked') or not tradable(b):
                warnings.append(dict(date=day,ticker=t,side='sell',reason='缺價／單一價／公司行動，賣出暫緩'));continue
            avg=(targets.get(t) or {}).get('avg_volume',p.get('avg_volume',0))
            limit=int(avg*cfg['participation_rate']) if avg else 0
            if limit<=0:
                warnings.append(dict(date=day,ticker=t,side='sell',reason='缺已知歷史成交量，避免假設流動性'));continue
            qty=min(qty,limit)
            price=max(b['low'],b['open']*(1-cfg['slippage']));gross=qty*price;commission=fee(gross,cfg)
            tax=gross*(cfg['etf_sell_tax'] if p.get('asset_type')=='etf' else cfg['sell_tax'])
            allocated_cost=p['cost']*qty/p['shares'];net=gross-commission-tax;state['cash']+=net
            full=qty==p['shares'];p['shares']-=qty;p['cost']-=allocated_cost
            state['trades'].append(dict(date=day,ticker=t,name=p['name'],asset_type=p.get('asset_type','stock'),side='sell',shares=qty,
                price=price,commission=commission,tax=tax,cash_flow=net,realized_pnl=net-allocated_cost,closed=full,decision_date=decision['date'],
                reason='移出名單' if t not in targets else '降低目標權重／大盤降曝險'))
            if full:del pos[t]
        for t,target in targets.items():
            p=pos.get(t);b=bars.get(t);qty=desired.get(t,0)-(p['shares'] if p else 0)
            if qty<=0:continue
            if (p and p.get('valuation_blocked')) or not tradable(b):
                warnings.append(dict(date=day,ticker=t,side='buy',reason='開盤資料不可驗證／單一價／公司行動，買入暫緩'));continue
            if p is None and len(pos)>=cfg['max_positions']:continue
            price=min(b['high'],b['open']*(1+cfg['slippage']))
            limit=int(target.get('avg_volume',0)*cfg['participation_rate'])
            # Reserve both target cash and the transaction costs; never borrow.
            investable=max(0,state['cash']-opening_equity*(1-sum(x['weight'] for x in targets.values())))
            afford=int(max(0,investable-cfg['minimum_commission'])/(price*(1+cfg['commission_rate'])))
            qty=min(qty,afford,limit)
            if qty<1:continue
            gross=qty*price;commission=fee(gross,cfg);cost=gross+commission
            if cost>state['cash']+1e-6:raise ValueError('Negative cash')
            state['cash']-=cost
            if p:
                p['shares']+=qty;p['cost']+=cost
            else:
                pos[t]=dict(ticker=t,name=target['name'],asset_type=target.get('asset_type','stock'),shares=qty,cost=cost,mark=price,
                    entry_date=day,entry_reason=target.get('evidence',[]),decision_date=decision['date'],avg_volume=target.get('avg_volume',0))
            pos[t]['avg_volume']=target.get('avg_volume',pos[t].get('avg_volume',0));pos[t]['target_weight']=target['weight']
            state['trades'].append(dict(date=day,ticker=t,name=target['name'],asset_type=target.get('asset_type','stock'),side='buy',shares=qty,
                price=price,commission=commission,tax=0,cash_flow=-cost,decision_date=decision['date'],reason='調高目標權重' if p else '新入選'))
    stale=[]
    for t,p in pos.items():
        cl=number(closes.get(t))
        if p.get('valuation_blocked'):stale.append(t)
        elif cl and cl>0:p['mark']=cl;p['mark_date']=day
        else:stale.append(t)
        if targets is not None:p['target_weight']=targets.get(t,{}).get('weight',0)
    value=sum(p['shares']*p['mark'] for p in pos.values());equity=state['cash']+value
    peak=max([cfg['initial_cash'],equity]+[r['equity'] for r in state['equity']])
    state['equity'].append(dict(date=day,equity=equity,cash=state['cash'],exposure=value/equity,return_pct=(equity/cfg['initial_cash']-1)*100,
        drawdown_pct=(equity/peak-1)*100,stale_marks=stale))
    state['processed_sessions'].append(day);state['execution_warnings'].extend(warnings)
    return True
