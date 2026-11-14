import json
from pathlib import Path
import sys
import tempfile
import unittest
from copy import deepcopy
from datetime import datetime,timedelta
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from ai_portfolio_engine import DEFAULTS,initial,frozen_decision,session,stamp
from update_ai_portfolio import run,write,proposal


def decision(day,tickers,valid=True,at=None):
    return dict(date=day,available_at=at or day+'T18:00:00+08:00',valid=valid,targets=[dict(ticker=t,name=t,evidence=['fixture']) for t in tickers],errors=[])

def bar(open=100,close=101):
    return dict(open=open,close=close,high=max(open,close)+1,low=min(open,close)-1,volume=1000000)


class Ledger(unittest.TestCase):
    def setUp(self):
        self.s=initial(DEFAULTS,'2026-11-16T18:00:00+08:00')
    def buy(self):
        frozen_decision(self.s,decision('2026-11-16',['1809']))
        session(self.s,'2026-11-17',{'1809':bar()},{'1809':101})
    def test_next_open_not_signal_close(self):
        frozen_decision(self.s,decision('2026-11-16',['1809']))
        session(self.s,'2026-11-16',{'1809':bar()},{'1809':101})
        self.assertEqual(self.s['trades'],[])
        session(self.s,'2026-11-17',{'1809':bar(103,104)},{'1809':104})
        self.assertEqual(self.s['trades'][0]['date'],'2026-11-17')
        self.assertGreater(self.s['trades'][0]['price'],103)
    def test_retain_same_shares_and_repeated_run(self):
        self.buy();shares=self.s['positions']['1809']['shares']
        frozen_decision(self.s,decision('2026-11-17',['1809']))
        session(self.s,'2026-11-18',{'1809':bar(110,111)},{'1809':111})
        self.assertEqual(shares,self.s['positions']['1809']['shares'])
        self.assertEqual(len(self.s['trades']),1)
        previous=deepcopy(self.s)
        self.assertFalse(session(self.s,'2026-11-18',{},{}));self.assertEqual(previous,self.s)
    def test_drop_sells_next_session_and_pnl_reconciles(self):
        self.buy();frozen_decision(self.s,decision('2026-11-17',[]))
        session(self.s,'2026-11-18',{'1809':bar(110,111)},{'1809':111})
        self.assertFalse(self.s['positions']);self.assertEqual(len(self.s['trades']),2)
        sell=self.s['trades'][-1];self.assertGreater(sell['tax'],0)
        self.assertAlmostEqual(self.s['cash']-DEFAULTS['initial_cash'],sell['realized_pnl'])
    def test_invalid_data_is_not_exit(self):
        self.buy();frozen_decision(self.s,decision('2026-11-17',[],False))
        session(self.s,'2026-11-18',{'1809':bar()},{'1809':101})
        self.assertIn('1809',self.s['positions']);self.assertEqual(len(self.s['trades']),1)
    def test_same_day_decision_is_immutable(self):
        self.buy();self.assertFalse(frozen_decision(self.s,decision('2026-11-16',[])))
        self.assertEqual(len(self.s['decisions'][0]['targets']),1)
    def test_late_signal_cannot_buy_past_open(self):
        frozen_decision(self.s,decision('2026-11-16',['1809'],at='2026-11-17T10:00:00+08:00'))
        session(self.s,'2026-11-17',{'1809':bar()},{'1809':101});self.assertFalse(self.s['trades'])
        session(self.s,'2026-11-18',{'1809':bar()},{'1809':101});self.assertEqual(len(self.s['trades']),1)
    def test_weekend_signal_waits_for_actual_session(self):
        self.s=initial(DEFAULTS,'2026-11-14T12:00:00+08:00')
        frozen_decision(self.s,decision('2026-11-13',['1809'],at='2026-11-14T12:00:00+08:00'))
        session(self.s,'2026-11-16',{'1809':bar()},{'1809':101})
        self.assertEqual(self.s['trades'][0]['date'],'2026-11-16')
    def test_missing_price_and_one_price_days_not_filled(self):
        frozen_decision(self.s,decision('2026-11-16',['1809']))
        session(self.s,'2026-11-17',{},{});self.assertFalse(self.s['trades'])
        b=bar();b.update(open=100,close=100,high=100,low=100)
        session(self.s,'2026-11-18',{'1809':b},{'1809':100});self.assertFalse(self.s['trades'])
        self.assertEqual(len(self.s['execution_warnings']),2)
    def test_failed_sale_keeps_position_and_no_leverage(self):
        cfg={**DEFAULTS,'max_positions':1,'entry_weight':1}
        self.s=initial(cfg,'2026-11-16T18:00:00+08:00');self.buy()
        frozen_decision(self.s,decision('2026-11-17',['2330']))
        session(self.s,'2026-11-18',{'2330':bar()},{'2330':101})
        self.assertIn('1809',self.s['positions']);self.assertNotIn('2330',self.s['positions']);self.assertGreaterEqual(self.s['cash'],0)
    def test_corporate_action_stays_blocked_without_manual_adjustment(self):
        self.buy();prior=self.s['positions']['1809']['mark']
        b=bar(50,50);b['corporate_action']=True
        session(self.s,'2026-11-18',{'1809':b},{'1809':50})
        frozen_decision(self.s,decision('2026-11-18',[]))
        session(self.s,'2026-11-19',{'1809':bar(50,50)},{'1809':50})
        self.assertIn('1809',self.s['positions'])
        self.assertEqual(self.s['positions']['1809']['mark'],prior)
        self.assertEqual(self.s['equity'][-1]['stale_marks'],['1809'])
    def test_cash_conservation_and_drawdown(self):
        self.buy();session(self.s,'2026-11-18',{'1809':bar(90,90)},{'1809':90})
        expected=DEFAULTS['initial_cash']+sum(t['cash_flow'] for t in self.s['trades'])
        self.assertAlmostEqual(self.s['cash'],expected);self.assertLess(self.s['equity'][-1]['drawdown_pct'],0)
        self.assertAlmostEqual(self.s['equity'][-1]['equity'],self.s['cash']+self.s['positions']['1809']['shares']*90)


class Pipeline(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.data=self.root/'data'
        day='2026-11-16';codes=[str(2000+i) for i in range(30)]
        stocks={t:dict(ticker=t,name='測試'+t,price=100,turnover=100000000,volume=1000000,market='twse') for t in codes}
        write(self.data/'market_latest.json',dict(date=day,stocks=stocks))
        write(self.data/'master.json',dict(stocks={t:dict(name='測試'+t,market='twse') for t in codes}))
        write(self.data/'heatmap.json',dict(sectors=[dict(name='測試族群',stocks=[dict(ticker=t) for t in codes])]))
        inst=dict(date=day,periods={'1d':{'twse':{'total':{'buy':[dict(ticker=t,shares=100000) for t in codes]}}}})
        write(self.data/'institutional.json',inst)
        write(self.data/'holders.json',dict(date='20261113',complete=True,twse={'400':[dict(ticker=t,delta=1) for t in codes]}))
        write(self.data/'etf-flow-v2/manifest.json',{'path':'versions/test/','version':'test'})
        write(self.data/'etf-flow-v2/versions/test/meta.json',dict(funds=[dict(code='00981A',region='TW',listing='2025-01-01')]))
        write(self.data/'etf-flow-v2/versions/test/etfs/00981A.json',dict(fund={'latest':day},events=[dict(date=day,code=t,delta=10000) for t in codes]))
        write(self.data/'quarterly_earnings.json',dict(reports=[dict(ticker=t,period='2026-Q3',prev_period='2026-Q2',publish_date='2026-11-13',publish_time='16:00:00',eps=1,prev_eps=.5,gross_margin=30,prev_gross_margin=20) for t in codes]))
        write(self.data/'quarterly_opm.json',dict(metrics={t+'|'+p:dict(value=v) for t in codes for p,v in [('2026-Q3',20),('2026-Q2',10)]}))
        write(self.data/'reports.json',dict(items=[dict(ticker=t,date='2026-11-13',received_at='2026-11-13T18:00:00+08:00',rating='Buy',broker='fixture') for t in codes]))
        days=[];d=datetime(2026,11,16)
        while len(days)<21:
            if d.weekday()<5:days.append(d.date().isoformat())
            d-=timedelta(days=1)
        for t in codes:write(self.data/'daily_k'/(t+'.json'),dict(ticker=t,bars=[dict(time=x,**bar(100,100)) for x in sorted(days)]))
    def tearDown(self):self.tmp.cleanup()
    def test_pipeline_builds_real_targets_no_fictitious_history(self):
        s=run(self.root,stamp('2026-11-16T18:00:00+08:00'))
        self.assertEqual(s['status'],'ready');self.assertEqual(len(s['decisions'][0]['targets']),10)
        self.assertFalse(s['trades']);self.assertFalse(s['positions']);self.assertFalse(s['equity'])
        self.assertEqual(s['decisions'][0]['targets'][0]['ticker'],'2000')
        self.assertTrue(any('OPM 10 → 20' in e for e in s['decisions'][0]['targets'][0]['evidence']))
        again=run(self.root,stamp('2026-11-16T18:20:00+08:00'))
        self.assertEqual(again['decisions'],s['decisions']);self.assertEqual(len(again['decisions']),1)
    def test_end_to_end_second_day_executes_then_keeps_lots(self):
        run(self.root,stamp('2026-11-16T18:00:00+08:00'))
        for day in ['2026-11-17','2026-11-18']:
            latest=json.loads((self.data/'market_latest.json').read_text());latest['date']=day;write(self.data/'market_latest.json',latest)
            inst=json.loads((self.data/'institutional.json').read_text());inst['date']=day;write(self.data/'institutional.json',inst)
            fpath=self.data/'etf-flow-v2/versions/test/etfs/00981A.json';f=json.loads(fpath.read_text());f['fund']['latest']=day
            for e in f['events']:e['date']=day
            write(fpath,f)
            for p in (self.data/'daily_k').glob('*.json'):
                d=json.loads(p.read_text());d['bars'].append(dict(time=day,**bar(100,100)));write(p,d)
            s=run(self.root,stamp(day+'T18:00:00+08:00'))
            self.assertEqual(len(s['positions']),10)
            self.assertEqual(len(s['trades']),10)
            self.assertGreaterEqual(s['cash'],0)
            self.assertAlmostEqual(s['cash'],DEFAULTS['initial_cash']+sum(t['cash_flow'] for t in s['trades']))
        self.assertEqual(len(s['equity']),2)
    def test_future_report_and_zero_eps_not_conflated_with_missing(self):
        p=self.data/'quarterly_earnings.json';d=json.loads(p.read_text());d['reports'][0]['eps']=0
        d['reports'].append(dict(ticker='2000',period='2026-Q4',publish_date='2027-02-01',eps=100,prev_eps=0));write(p,d)
        o=proposal(self.data,DEFAULTS,stamp('2026-11-16T18:00:00+08:00'))
        self.assertTrue(o['valid']);x=next(x for x in o['candidates'] if x['ticker']=='2000')
        self.assertTrue(any('EPS 0.5 → 0' in e for e in x['evidence']));self.assertFalse(any('100'==e for e in x['evidence']))
    def test_missing_entire_source_cannot_liquidate(self):
        s=run(self.root,stamp('2026-11-16T18:00:00+08:00'));(self.data/'institutional.json').unlink()
        s=run(self.root,stamp('2026-11-16T18:20:00+08:00'))
        self.assertEqual(s['status'],'data_pending');self.assertEqual(len(s['decisions']),1);self.assertTrue(s['latest_attempt']['errors'])
    def test_individual_missing_bar_cannot_trigger_exit(self):
        run(self.root,stamp('2026-11-16T18:00:00+08:00'))
        (self.data/'daily_k/2000.json').unlink()
        s=run(self.root,stamp('2026-11-16T18:20:00+08:00'))
        self.assertEqual(s['status'],'data_pending')
        self.assertTrue(any('2000' in e for e in s['latest_attempt']['errors']))
        self.assertEqual(s['decisions'][0]['targets'][0]['ticker'],'2000')
    def test_corrupted_state_never_resets(self):
        (self.data/'ai_portfolio.json').write_text('{broken')
        with self.assertRaises(json.JSONDecodeError):run(self.root,stamp('2026-11-16T18:00:00+08:00'))
    def test_config_change_never_rewrites_account(self):
        run(self.root,stamp('2026-11-16T18:00:00+08:00'));write(self.root/'config/ai_portfolio.json',{'initial_cash':2000000})
        with self.assertRaises(ValueError):run(self.root,stamp('2026-11-17T18:00:00+08:00'))

if __name__=='__main__':unittest.main()
