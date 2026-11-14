import json,sys,tempfile,unittest
from pathlib import Path
from copy import deepcopy
from datetime import datetime,timedelta
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from ai_portfolio_engine import *
from ai_allocation import allocate,market_regime,fundamentals,decay,ensure_floor
from collect_ai_universe import parse_quotes,finance_rows
from update_ai_portfolio import run,write

def bar(price=100):return dict(open=price,high=price+1,low=price-1,close=price,volume=10000000)
def target(t='1815',weight=.1,asset='stock',score=80,sector='01'):
    return dict(ticker=t,name='fixture'+t,weight=weight,asset_type=asset,score=score,sector=sector,eligible=True,avg_volume=10000000,volatility=2,evidence=['fixture'])
def plan(day,targets,exposure=.9,at=None,valid=True):return dict(date=day,available_at=at or day+'T18:00:00+08:00',valid=valid,targets=targets,errors=[],regime={'target_exposure':exposure})
class Accounting(unittest.TestCase):
    def setUp(self):self.s=initial({**DEFAULTS,'min_exposure':0},'2026-11-13T18:00:00+08:00')
    def start(self,w=.1,asset='stock'):
        frozen_decision(self.s,plan('2026-11-13',[target(weight=w,asset=asset)]));session(self.s,'2026-11-16',{'1815':bar()},{'1815':100})
    def test_initial_capital_and_no_leverage(self):self.assertEqual(self.s['cash'],20000000)
    def test_next_open_and_immutable_signal(self):
        frozen_decision(self.s,plan('2026-11-13',[target()]));self.assertFalse(frozen_decision(self.s,plan('2026-11-13',[])))
        self.assertEqual(len(self.s['decisions'][0]['targets']),1);session(self.s,'2026-11-16',{'1815':bar()},{'1815':100});self.assertEqual(self.s['trades'][0]['decision_date'],'2026-11-13')
    def test_can_buy_odd_shares(self):
        frozen_decision(self.s,plan('2026-11-13',[target(weight=.123456)]));session(self.s,'2026-11-16',{'1815':bar(117.3)},{'1815':117.3});self.assertNotEqual(self.s['positions']['1815']['shares']%1000,0)
    def test_hold_does_not_churn(self):
        self.start();n=self.s['positions']['1815']['shares'];frozen_decision(self.s,plan('2026-11-16',[target()]));session(self.s,'2026-11-17',{'1815':bar()},{'1815':100})
        self.assertEqual(n,self.s['positions']['1815']['shares']);self.assertEqual(len(self.s['trades']),1)
    def test_market_de_risk_partially_sells(self):
        self.start(.15);before=self.s['positions']['1815']['shares'];frozen_decision(self.s,plan('2026-11-16',[target(weight=.04)],.10));session(self.s,'2026-11-17',{'1815':bar()},{'1815':100})
        self.assertGreater(self.s['positions']['1815']['shares'],0);self.assertLess(self.s['positions']['1815']['shares'],before)
        self.assertEqual(self.s['trades'][-1]['closed'],False);self.assertGreater(self.s['cash'],18000000)
    def test_reduction_cost_and_realized_pnl_reconcile(self):
        self.start(.15);frozen_decision(self.s,plan('2026-11-16',[target(weight=.04)],.10));session(self.s,'2026-11-17',{'1815':bar(110)},{'1815':110})
        realized=sum(x.get('realized_pnl',0) for x in self.s['trades']);unreal=sum(p['shares']*p['mark']-p['cost'] for p in self.s['positions'].values())
        self.assertAlmostEqual(self.s['equity'][-1]['equity']-20000000,realized+unreal)
        self.assertAlmostEqual(self.s['cash'],20000000+sum(x['cash_flow'] for x in self.s['trades']))
    def test_exit_and_empty_valid_target(self):
        self.start();frozen_decision(self.s,plan('2026-11-16',[],.1));session(self.s,'2026-11-17',{'1815':bar()},{'1815':100});self.assertFalse(self.s['positions']);self.assertTrue(self.s['trades'][-1]['closed'])
    def test_invalid_data_does_not_exit(self):
        self.start();frozen_decision(self.s,plan('2026-11-16',[],.1,valid=False));session(self.s,'2026-11-17',{'1815':bar()},{'1815':100});self.assertIn('1815',self.s['positions'])
    def test_repeat_is_idempotent(self):
        self.start();old=deepcopy(self.s);self.assertFalse(session(self.s,'2026-11-16',{},{}));self.assertEqual(old,self.s)
    def test_late_signal_cannot_trade_old_open(self):
        frozen_decision(self.s,plan('2026-11-13',[target()],at='2026-11-16T10:00:00+08:00'));session(self.s,'2026-11-16',{'1815':bar()},{'1815':100});self.assertFalse(self.s['trades'])
    def test_etf_sell_tax_is_distinct(self):
        self.start(asset='etf');frozen_decision(self.s,plan('2026-11-16',[]));session(self.s,'2026-11-17',{'1815':bar()},{'1815':100});t=self.s['trades'][-1];self.assertAlmostEqual(t['tax'],t['price']*t['shares']*.001)
    def test_one_price_not_filled(self):
        frozen_decision(self.s,plan('2026-11-13',[target()]));b=bar();b.update(high=100,low=100);session(self.s,'2026-11-16',{'1815':b},{'1815':100});self.assertFalse(self.s['trades'])
    def test_no_borrow_and_preserve_cash_floor(self):
        frozen_decision(self.s,plan('2026-11-13',[target(str(1000+i),.15) for i in range(6)]));bars={str(1000+i):bar() for i in range(6)};session(self.s,'2026-11-16',bars,{t:100 for t in bars});self.assertGreaterEqual(self.s['cash'],2000000)
    def test_prior_known_volume_limits_fill(self):
        t=target();t['avg_volume']=10000;frozen_decision(self.s,plan('2026-11-13',[t]));session(self.s,'2026-11-16',{'1815':bar()},{'1815':100});self.assertEqual(self.s['positions']['1815']['shares'],100)
    def test_untraded_v1_migrates_and_archives(self):
        old=initial({**DEFAULTS,'initial_cash':1000000},'2026-11-14T12:00:00+08:00');old['strategy']='three-pillar-paper-v1';new,archive=migrate(old,DEFAULTS,'2026-11-14T13:00:00+08:00')
        self.assertEqual(new['cash'],20000000);self.assertEqual(archive['cash'],1000000);self.assertEqual(new['configuration_events'][0]['previous_capital'],1000000)
    def test_traded_v1_never_resets(self):
        self.start();self.s['strategy']='three-pillar-paper-v1'
        with self.assertRaises(ValueError):migrate(self.s,DEFAULTS,'2026-11-17T18:00:00+08:00')
    def test_overweight_rejected(self):
        with self.assertRaises(ValueError):frozen_decision(self.s,plan('2026-11-13',[target(weight=.5)]))

class Model(unittest.TestCase):
    def test_weights_differ_and_caps_hold(self):
        xs=[target(str(1000+i),score=90-i*2,sector=str(i%4)) for i in range(10)]+[target('00981A',asset='etf',score=91)]
        out=allocate(xs,.9,DEFAULTS);w={x['ticker']:x['weight'] for x in out};self.assertNotEqual(w['1000'],w['1007']);self.assertLessEqual(sum(w.values()),.9)
        for x in out:self.assertLessEqual(x['weight'],.25 if x['asset_type']=='etf' else .15)
        for sector in {x['sector'] for x in xs if x['asset_type']=='stock'}:self.assertLessEqual(sum(x['weight'] for x in out if x['asset_type']=='stock' and x['sector']==sector),.350001)
    def test_floor_uses_verified_core_etfs(self):
        core=[target('0050',asset='etf'),target('006208',asset='etf')]
        out,ok=ensure_floor([],core,DEFAULTS)
        self.assertTrue(ok);self.assertAlmostEqual(sum(x['weight'] for x in out),.4)
        self.assertTrue(all(x['weight']<=.25 for x in out))
    def test_missing_core_cannot_fake_floor(self):
        out,ok=ensure_floor([],[],DEFAULTS);self.assertFalse(ok);self.assertEqual(out,[])
    def test_all_production_regimes_have_minimum_40_percent(self):
        dates=[(datetime(2026,8,1)+timedelta(days=i)).date().isoformat() for i in range(70)]
        rows=[dict(date=d,index=200-i,foreign=-10,foreign_light='red',margin_light='red',intersection='red') for i,d in enumerate(dates)]
        self.assertEqual(market_regime({'rows':rows},dates[-1],.1)['target_exposure'],.4)
        s=initial(DEFAULTS,'2026-11-13T18:00:00+08:00')
        with self.assertRaises(ValueError):frozen_decision(s,plan('2026-11-13',[]))
    def test_discovery_small_and_insufficient_candidates_keep_cash(self):
        t=target();t['discovery']=True;out=allocate([t],.9,DEFAULTS);self.assertLessEqual(out[0]['weight'],.05)
    def test_regime_changes_cash_target(self):
        dates=[(datetime(2026,8,1)+timedelta(days=i)).date().isoformat() for i in range(70)]
        def m(up):return {'rows':[dict(date=d,index=100+i if up else 200-i,foreign=10 if up else -10,foreign_light='normal',margin_light='normal',intersection='normal') for i,d in enumerate(dates)]}
        good=market_regime(m(True),dates[-1],.8);bad=market_regime(m(False),dates[-1],.2);self.assertEqual(good['target_exposure'],.9);self.assertLess(bad['target_exposure'],good['target_exposure'])
    def test_stale_macro_not_used(self):self.assertFalse(market_regime({'rows':[]},'2026-11-13',.8)['valid'])
    def test_event_fades_but_financial_quality_persists(self):
        cal=[(datetime(2026,10,1)+timedelta(days=i)).date().isoformat() for i in range(45)]
        row=dict(period='2026-Q3',prev_period='2026-Q2',publish_date='2026-11-01',eps=2,prev_eps=1,gross_margin=30,prev_gross_margin=20,operating_margin=20,prev_operating_margin=10)
        early=fundamentals('1815',row,None,{},[],stamp('2026-11-02T18:00:00+08:00'),cal);late=fundamentals('1815',row,None,{},[],stamp('2026-11-13T18:00:00+08:00'),cal)
        self.assertLess(late['freshness']['earnings_event_weight'],early['freshness']['earnings_event_weight']);self.assertGreater(late['score'],50)
    def test_new_broker_downgrade_replaces_old_buy(self):
        cal=['2026-11-01','2026-11-02','2026-11-03'];reports=[dict(broker='A',received_at='2026-11-01T18:00:00+08:00',rating='Buy'),dict(broker='A',received_at='2026-11-02T18:00:00+08:00',rating='Sell')]
        f=fundamentals('1815',None,None,{},reports,stamp('2026-11-03T18:00:00+08:00'),cal);self.assertEqual(f['research_count'],1);self.assertLess(f['score'],50)
    def test_future_research_does_not_leak(self):
        f=fundamentals('1815',None,None,{},[dict(broker='A',received_at='2027-01-01T18:00:00+08:00',rating='Buy')],stamp('2026-11-13T18:00:00+08:00'),['2026-11-13']);self.assertEqual(f['research_count'],0)
    def test_official_ytd_not_mislabeled_single_quarter(self):
        f=fundamentals('1101',None,dict(observed_at='2026-11-14T12:00:00+08:00',period='2026-Q3',eps=2,gross_margin=30,operating_margin=20),{},[],stamp('2026-11-14T13:00:00+08:00'),['2026-11-13']);self.assertTrue(f['verified']);self.assertTrue(any('累計 OPM' in x for x in f['evidence']));self.assertFalse(any(' 單季 ' in x for x in f['evidence']));self.assertEqual(f['basis'],'official_ytd_or_unknown')
    def test_wrong_date_official_quotes_rejected(self):
        with self.assertRaises(ValueError):parse_quotes({'date':'20261112','tables':[]},'twse','2026-11-13',{'1815'})
    def test_official_financial_parser_handles_negative_values(self):
        rows=[{'年度':'115','季別':'3','公司代號':'1101','營業收入':'1000','營業毛利（毛損）淨額':'100','營業利益（損失）':'(20)','基本每股盈餘（元）':'-1'}]
        f=finance_rows(rows,'twse','2026-11-14T12:00:00+08:00')['1101'];self.assertEqual(f['operating_margin'],-2);self.assertEqual(f['scope'],'year_to_date')

class Integration(unittest.TestCase):
    def test_full_market_not_limited_to_heatmap_and_migration_is_safe(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);data=root/'data';codes=[str(1000+i) for i in range(1100)];day='2026-11-13';now=stamp('2026-11-14T13:00:00+08:00')
            dates=[];d=datetime(2026,11,13)
            while len(dates)<65:
                if d.weekday()<5:dates.append(d.date().isoformat())
                d-=timedelta(days=1)
            dates.sort();rows=[dict(date=x,index=100+i,foreign=10,foreign_light='normal',margin_light='normal',intersection='normal') for i,x in enumerate(dates)]
            write(data/'market_monitor.json',dict(raw=rows,rows=rows));quotes={t:dict(ticker=t,name='非熱力圖'+t,price=100,**bar(),market='twse',asset_type='stock',industry=str(i%10),turnover=1000000000) for i,t in enumerate(codes)}
            write(data/'ai_universe.json',dict(date=day,complete=True,register_count=1500,stock_quote_count=1100,etf_count=0,stocks=quotes))
            for i,x in enumerate(dates[-21:]):write(data/'ai_universe_days'/(x+'.json'),dict(date=x,complete=True,stocks={t:{**q,'close':80+i,'price':80+i,'open':80+i,'high':81+i,'low':79+i} for t,q in quotes.items()}))
            write(data/'institutional.json',dict(date=day,periods={'1d':{'twse':{'total':{'buy':[dict(ticker=t,shares=10000) for t in codes]}}}}))
            write(data/'holders.json',dict(date='20261113',complete=True,twse={'400':[dict(ticker=t,delta=1) for t in codes]}))
            write(data/'etf-flow-v2/manifest.json',{'path':'versions/test/'});base=data/'etf-flow-v2/versions/test'
            write(base/'meta.json',dict(funds=[dict(code='00981A',region='TW',listing='2025-01-01')]))
            write(base/'etfs/00981A.json',dict(fund={'latest':day},events=[dict(date=day,code=t,delta=1000) for t in codes]))
            write(data/'quarterly_earnings.json',{'reports':[{'ticker':'9999','publish_date':'2026-11-13'}]});write(data/'reports.json',{'items':[{'ticker':'9999','date':'2026-11-13'}]})
            write(data/'ai_fundamentals.json',{'stocks':{t:dict(period='2026-Q3',scope='year_to_date',observed_at='2026-11-14T12:00:00+08:00',eps=2,gross_margin=30,operating_margin=20) for t in codes}})
            old=initial({**DEFAULTS,'initial_cash':1000000},'2026-11-14T12:00:00+08:00');old['strategy']='three-pillar-paper-v1';write(data/'ai_portfolio.json',old)
            s=run(root,now);self.assertEqual(s['status'],'ready');self.assertTrue(s['decisions'][0]['targets']);self.assertEqual(s['cash'],20000000)
            self.assertEqual(s['decisions'][0]['coverage']['usable_stocks'],1100);self.assertTrue(list((data/'ai_portfolio_archives').glob('*.json')))
            again=run(root,stamp('2026-11-14T13:05:00+08:00'));self.assertEqual(again['decisions'],s['decisions']);self.assertFalse(again['trades'])
if __name__=='__main__':unittest.main()
