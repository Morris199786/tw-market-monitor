import json,sys,tempfile,unittest
from pathlib import Path
from copy import deepcopy
from unittest.mock import patch
from datetime import datetime,timedelta
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from ai_portfolio_engine import *
from ai_allocation import t6_exposure,allocate,market_regime,fundamentals,decay,ensure_floor
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

    def test_migrate_30_to_50_preserves_account(self):
        self.start()
        old=deepcopy(self.s)
        old['config'].update(max_positions=8,min_exposure=0,max_stock_weight=.3,max_sector_weight=.35)
        cfg={**old['config'],'max_stock_weight':.5,'max_sector_weight':.5}
        before=deepcopy(old)
        new,archive=migrate(old,cfg,'2026-11-17T18:00:00+08:00')
        self.assertIsNone(archive)
        self.assertEqual(old,before)
        self.assertEqual(new['config'],cfg)
        for key in before:
            if key not in ('config','configuration_events'):self.assertEqual(new[key],before[key])
        self.assertEqual(len(new['configuration_events']),len(before['configuration_events'])+1)
        self.assertEqual(migrate(new,cfg,'2026-11-18T18:00:00+08:00'),(new,None))
        with self.assertRaises(ValueError):migrate(old,{**cfg,'initial_cash':1},'2026-11-17T18:00:00+08:00')
        with self.assertRaises(ValueError):migrate(old,{**cfg,'max_sector_weight':.35},'2026-11-17T18:00:00+08:00')
    def test_new_stock_cap_accepts_50_rejects_above(self):
        cfg={**DEFAULTS,'max_positions':8,'min_exposure':0,'max_stock_weight':.5,'max_sector_weight':.5}
        state=initial(cfg,'2026-11-13T18:00:00+08:00')
        self.assertTrue(frozen_decision(state,plan('2026-11-13',[target(weight=.5)])))
        with self.assertRaises(ValueError):frozen_decision(state,plan('2026-11-16',[target(weight=.5001)]))
        with self.assertRaises(ValueError):frozen_decision(state,plan('2026-11-17',[target(weight=.26,asset='etf')]))

class T6Model(unittest.TestCase):
    def setUp(self):
        self.cfg={**DEFAULTS,**{'exposure_model': 'H2+T6', 'exposure_down_alpha': 0.5, 'exposure_up_alpha': 0.8, 'exposure_down_band': 0.05, 'exposure_up_band': 0.15, 'trial_risk_max': 70, 'trial_extra': 0.275, 'trial_sessions': 20, 'trial_exit_points': 5}}
    def rows(self,scores,trials=()):
        return [dict(date=(datetime(2026,1,1)+timedelta(days=i)).date().isoformat(),score=v,trial=i in trials) for i,v in enumerate(scores)]
    def test_trial_activation_and_expiry(self):
        a=t6_exposure(self.rows([60]*20,[0]),self.cfg)
        self.assertTrue(a['trial_active']);self.assertFalse(a['trial_today']);self.assertEqual(a['trial_remaining'],1)
        self.assertAlmostEqual(a['trial_extra'],.275)
        self.assertFalse(t6_exposure(self.rows([60]*21,[0]),self.cfg)['trial_active'])
    def test_trial_risk_and_exit(self):
        self.assertFalse(t6_exposure(self.rows([70],[0]),self.cfg)['trial_active'])
        self.assertFalse(t6_exposure(self.rows([60,65],[0]),self.cfg)['trial_active'])
        self.assertTrue(t6_exposure(self.rows([60,30,50],[0]),self.cfg)['trial_active'])
    def test_asymmetric_smoothing(self):
        self.assertAlmostEqual(t6_exposure(self.rows([0,100]),self.cfg)['smoothed_exposure'],.5)
        self.assertAlmostEqual(t6_exposure(self.rows([100,0]),self.cfg)['smoothed_exposure'],.8)
    def test_cap_and_daily_tag(self):
        a=t6_exposure(self.rows([0],[0]),self.cfg)
        self.assertEqual(a['target_exposure'],1);self.assertTrue(a['trial_today'])
    def test_below_buy_band_stays_cash(self):
        state=initial({**self.cfg,'min_exposure':0},'2026-11-13T18:00:00+08:00')
        p=plan('2026-11-13',[target(weight=.1)],.1)
        p['regime'].update(exposure_model='H2+T6',exposure_up_band=.15,exposure_down_band=.05)
        frozen_decision(state,p);session(state,'2026-11-16',{'1815':bar()},{'1815':100})
        self.assertFalse(state['trades']);self.assertFalse(state['exposure_execution'][-1]['adjust'])

    def test_migration_preserves_existing_ledger(self):
        oldcfg={**DEFAULTS,'max_positions':8,'min_exposure':0,'max_stock_weight':.5,'max_sector_weight':.5}
        state=initial(oldcfg,'2026-11-13T18:00:00+08:00')
        frozen_decision(state,plan('2026-11-13',[target(weight=.2)]))
        session(state,'2026-11-16',{'1815':bar()},{'1815':100})
        before=deepcopy(state);newcfg={**self.cfg,**{k:oldcfg[k] for k in ('max_positions','min_exposure','max_stock_weight','max_sector_weight')}}
        updated,archive=migrate(state,newcfg,'2026-11-16T18:00:00+08:00')
        self.assertIsNone(archive);self.assertEqual(state,before)
        for k in ('cash','positions','equity','trades','decisions','started_at','processed_sessions'):
            self.assertEqual(updated[k],before[k])
        self.assertEqual(migrate(updated,newcfg,'2026-11-17T18:00:00+08:00'),(updated,None))
    def test_buy_and_sell_bands(self):
        state=initial({**self.cfg,'min_exposure':0,'max_stock_weight':.5},'2026-11-13T18:00:00+08:00')
        def decision(day,w):
            p=plan(day,[target(weight=w)] if w else [],w)
            p['regime'].update(exposure_model='H2+T6',exposure_up_band=.15,exposure_down_band=.05)
            frozen_decision(state,p)
        decision('2026-11-13',.25);session(state,'2026-11-16',{'1815':bar()},{'1815':100})
        self.assertTrue(state['exposure_execution'][-1]['adjust']);self.assertEqual(len(state['trades']),1)
        decision('2026-11-16',.22);session(state,'2026-11-17',{'1815':bar()},{'1815':100})
        self.assertFalse(state['exposure_execution'][-1]['adjust']);self.assertEqual(len(state['trades']),1)
        decision('2026-11-17',.10);session(state,'2026-11-18',{'1815':bar()},{'1815':100})
        self.assertTrue(state['exposure_execution'][-1]['adjust']);self.assertEqual(state['trades'][-1]['side'],'sell')
    def test_duplicate_history_rejected(self):
        rows=self.rows([50,60]);rows[1]['date']=rows[0]['date']
        with self.assertRaises(ValueError):t6_exposure(rows,self.cfg)
    def test_retrigger_replaces_window_without_stacking(self):
        rows=self.rows([50]*12,[0,11]);a=t6_exposure(rows,self.cfg)
        self.assertEqual(a['trial_remaining'],20);self.assertAlmostEqual(a['trial_extra'],.275)
    def test_ineligible_retrigger_ends_previous_trial(self):
        a=t6_exposure(self.rows([69]*11+[70],[0,11]),self.cfg)
        self.assertTrue(a['trial_today']);self.assertFalse(a['trial_active'])

class Model(unittest.TestCase):
    def test_50_percent_allocation_and_sector_cap(self):
        cfg={**DEFAULTS,'max_positions':8,'min_exposure':0,'max_stock_weight':.5,'max_sector_weight':.5}
        out=allocate([target(score=95)],.8,cfg)
        self.assertAlmostEqual(out[0]['weight'],.5,places=5)
        xs=[target('1000',score=95,sector='A'),target('1001',score=85,sector='A'),target('1002',score=70,sector='B')]
        out=allocate(xs,.8,cfg)
        weights={x['ticker']:x['weight'] for x in out}
        self.assertGreater(weights['1000'],weights['1001'])
        self.assertLessEqual(weights['1000']+weights['1001'],.500001)
        self.assertLessEqual(sum(weights.values()),.800001)
        self.assertLessEqual(allocate([target(asset='etf')],.8,cfg)[0]['weight'],.25)
        discovery=target();discovery['discovery']=True
        self.assertLessEqual(allocate([discovery],.8,cfg)[0]['weight'],.05)
        self.assertLessEqual(allocate([target()],.2,cfg)[0]['weight'],.2)

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
    def test_v12_continuous_exposure_zero_to_full(self):
        dates=[(datetime(2026,8,1)+timedelta(days=i)).date().isoformat() for i in range(70)]
        rows=[dict(date=d,index=100+i,foreign=10,foreign_light='normal',margin_light='normal',intersection='normal') for i,d in enumerate(dates)]
        macro={'rows':rows};day=dates[-1]
        for risk,expected in ((0,1.0),(20,.896),(50,.5),(65,.28175),(80,.104),(100,0.0),(120,0.0)):
            v12=dict(valid=True,date=day,score=risk,level=3 if risk>=65 else 2 if risk>=52 else 1 if risk>=38 else 0)
            regime=market_regime(macro,day,.8,v12)
            self.assertTrue(regime['valid'])
            self.assertAlmostEqual(regime['target_exposure'],expected,places=5)
        invalid=market_regime(macro,day,.8,dict(valid=True,date=dates[-2],score=20,level=0))
        self.assertFalse(invalid['valid'])
    def test_zero_exposure_decision_really_can_exit(self):
        state=initial({**DEFAULTS,'min_exposure':0},'2026-11-13T18:00:00+08:00')
        self.assertTrue(frozen_decision(state,plan('2026-11-13',[],exposure=0)))
        self.assertEqual(state['decisions'][-1]['targets'],[])
    def test_event_fades_but_financial_quality_persists(self):
        cal=[(datetime(2026,10,1)+timedelta(days=i)).date().isoformat() for i in range(45)]
        row=dict(period='2026-Q3',prev_period='2026-Q2',publish_date='2026-11-01',eps=2,prev_eps=1,gross_margin=30,prev_gross_margin=20,operating_margin=20,prev_operating_margin=10)
        early=fundamentals('1815',row,None,{},[],stamp('2026-11-02T18:00:00+08:00'),cal);late=fundamentals('1815',row,None,{},[],stamp('2026-11-13T18:00:00+08:00'),cal)
        self.assertLess(late['freshness']['earnings_event_weight'],early['freshness']['earnings_event_weight']);self.assertGreater(late['score'],50)
    def test_rating_only_does_not_substitute_for_missing_content(self):
        cal=['2026-11-01','2026-11-02','2026-11-03'];reports=[dict(broker='A',received_at='2026-11-01T18:00:00+08:00',rating='Buy'),dict(broker='A',received_at='2026-11-02T18:00:00+08:00',rating='Sell')]
        f=fundamentals('1815',None,None,{},reports,stamp('2026-11-03T18:00:00+08:00'),cal);self.assertEqual(f['research_count'],0);self.assertEqual(f['research_score'],50);self.assertEqual(len(f['research_missing']),1)
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
            write(data/'quarterly_earnings.json',{'reports':[dict(ticker=t,period='2026-Q3',prev_period='2026-Q2',publish_date='2026-11-13',publish_time='18:00:00',eps=3,prev_eps=1,gross_margin=40,prev_gross_margin=20,operating_margin=30,prev_operating_margin=10) for t in codes]});write(data/'reports.json',{'items':[{'ticker':'9999','date':'2026-11-13'}]})
            write(data/'ai_fundamentals.json',{'stocks':{t:dict(period='2026-Q3',scope='year_to_date',observed_at='2026-11-14T12:00:00+08:00',eps=2,gross_margin=30,operating_margin=20) for t in codes}})
            old=initial({**DEFAULTS,'initial_cash':1000000},'2026-11-14T12:00:00+08:00');old['strategy']='three-pillar-paper-v1';write(data/'ai_portfolio.json',old)
            # Mock the V12 signal ONLY in this synthetic integration fixture. The
            # fixture has neither real monitor JS assets nor daily breadth archives.
            # Production must still reject missing real same-date data.
            fixture_v12=dict(date=day,valid=True,score=20.0,level=0)
            with patch('update_ai_portfolio.v12_market_signal',return_value=fixture_v12):
                s=run(root,now);self.assertEqual(s['status'],'ready');self.assertTrue(s['decisions'][0]['targets']);self.assertEqual(s['cash'],20000000)
                self.assertEqual(s['decisions'][0]['coverage']['usable_stocks'],1100);self.assertTrue(list((data/'ai_portfolio_archives').glob('*.json')))
                self.assertAlmostEqual(s['decisions'][0]['regime']['target_exposure'],.896)
                again=run(root,stamp('2026-11-14T13:05:00+08:00'));self.assertEqual(again['decisions'],s['decisions']);self.assertFalse(again['trades'])

class SOXK20(unittest.TestCase):
    def fixture(self,ret,base=.25):
        from ai_allocation import sox_k20
        now=stamp('2026-11-24T08:00:00+08:00');d='2026-11-23'
        rows=[dict(date=f'2026-10-{i:02d}',close=100.) for i in range(1,21)]+[dict(date=d,available_at='2026-11-24T05:00:00+08:00',observed_at='2026-11-24T07:00:00+08:00',close_source='yahoo',return20=ret,close=100+ret)]
        archive=dict(symbol='^SOX',rows=rows,daily_calendar=dict(valid_from='2026-11-23T00:00:00+08:00',valid_until='2026-11-30T00:00:00+08:00',sessions=[dict(date=d,closed_at='2026-11-24T05:00:00+08:00',ready_at='2026-11-24T06:15:00+08:00')]))
        regime=dict(valid=True,exposure_model='H2+T6',target_exposure=base,reasons=[])
        return sox_k20,regime,archive,now
    def test_boundaries(self):
        for ret,base,want in [(1,.39,.59),(1,.4,1),(1,.1,.3),(1,.95,1),(-8,.9,.7),(-8,.1,0),(.99,.5,.5),(-7.99,.5,.5)]:
            f,r,a,n=self.fixture(ret,base);self.assertAlmostEqual(f(r,a,n)['target_exposure'],want)
    def test_fallback(self):
        for mode in ('missing','future','conflict','old','stale_calendar'):
            f,r,a,n=self.fixture(3)
            if mode=='missing':a['rows'].pop()
            if mode=='future':a['rows'][-1]['observed_at']='2026-11-24T09:00:00+08:00'
            if mode=='conflict':a['rows'][-1]['close_conflict']=True
            if mode=='old':a['rows'][-1]['observed_at']='2026-11-24T05:01:00+08:00'
            if mode=='stale_calendar':a['daily_calendar']['valid_until']='2026-11-24T07:00:00+08:00'
            got=f(r,a,n);self.assertEqual(got['target_exposure'],.25);self.assertEqual(got['sox_status'],'unavailable')
    def test_migration(self):
        cfg={**DEFAULTS,'max_positions':8,'min_exposure':0,'max_stock_weight':.5,'max_sector_weight':.5,'exposure_model':'H2+T6','exposure_down_alpha':.5,'exposure_up_alpha':.8,'exposure_down_band':.05,'exposure_up_band':.15,'trial_risk_max':70,'trial_extra':.275,'trial_sessions':20,'trial_exit_points':5}
        old=initial(cfg,'2026-11-23T18:00:00+08:00');old['equity']=[{'date':'2026-11-23','equity':20000000}]
        new,_=migrate(old,{**cfg,'sox_overlay':'K20'},'2026-11-24T08:00:00+08:00');self.assertEqual(new['equity'],old['equity']);self.assertEqual(new['config']['sox_overlay'],'K20')

class SOXDailyRefresh(unittest.TestCase):
    def test_incremental_append_repeat_and_missing(self):
        import types
        import pandas as pd
        from update_sox_daily import refresh
        from datetime import timezone
        from zoneinfo import ZoneInfo
        ny=ZoneInfo('America/New_York');tw=ZoneInfo('Asia/Taipei')
        def schedule(start_date,end_date):
            days=pd.bdate_range(start_date,end_date)
            return pd.DataFrame({'market_close':[pd.Timestamp(d.date().isoformat()+'T16:00:00',tz=ny).tz_convert('UTC') for d in days]},index=days)
        fake=types.SimpleNamespace(get_calendar=lambda name:types.SimpleNamespace(schedule=schedule))
        now=datetime(2026,11,24,7,tzinfo=tw)
        dates=[d.date().isoformat() for d in pd.bdate_range(end='2026-11-20',periods=80)]
        rows=[dict(date=d,close=100+i,open=100+i,high=101+i,low=99+i,close_source='yahoo') for i,d in enumerate(dates)]
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'sox.json';path.write_text(json.dumps(dict(schema=1,symbol='^SOX',rows=rows,quality={})))
            def yahoo(a,b):
                self.assertGreaterEqual(a.isoformat(),'2026-11-17')
                return {d:dict(open=c,high=c+1,low=c-1,close=c) for d,c in [(r['date'],r['close']) for r in rows]+[('2026-11-23',180)] if a.isoformat()<=d<=b.isoformat()}
            with patch.dict(sys.modules,{'pandas_market_calendars':fake}),patch('update_sox_daily.fetch_yahoo',side_effect=yahoo),patch('update_sox_daily.fetch_fred',return_value={}):
                result=refresh(path,now);self.assertEqual(len(result['rows']),81);self.assertEqual(result['rows'][0],rows[0]);self.assertEqual(result['as_of_date'],'2026-11-23');self.assertAlmostEqual(result['rows'][-1]['return20'],12.5)
                before=path.read_bytes();refresh(path,now+timedelta(hours=1));self.assertEqual(path.read_bytes(),before)
                with patch('update_sox_daily.fetch_yahoo',return_value={}):
                    with self.assertRaises(RuntimeError):refresh(path,now+timedelta(days=1))
                self.assertEqual(path.read_bytes(),before)
if __name__=='__main__':unittest.main()
