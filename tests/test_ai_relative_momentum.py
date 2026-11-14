import sys,unittest
from pathlib import Path
from copy import deepcopy
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from ai_relative_momentum import momentum,sector_groups,benchmark_returns,relative_score
from ai_allocation import allocate
from ai_portfolio_engine import initial,DEFAULTS,frozen_decision,session
from test_ai_portfolio import target,plan,bar
class RelativeMomentum(unittest.TestCase):
 def test_positive_return_underperforming_market_below_neutral(self):
  s=momentum('x',{5:{'x':10},20:{'x':10}},{5:15,20:15},[]);self.assertLess(s['score'],50)
 def test_negative_return_outperforming_market_above_neutral(self):
  s=momentum('x',{5:{'x':-2},20:{'x':-2}},{5:-10,20:-10},[]);self.assertGreater(s['score'],50)
 def test_unlisted_in_heatmap_uses_market_only(self):
  s=momentum('x',{5:{'x':10},20:{'x':10}},{5:10,20:10},[]);self.assertEqual(s['score'],50);self.assertIsNone(s['horizons']['5']['peer_return'])
 def test_self_excluded_from_equal_weight_peer_average(self):
  groups=sector_groups({'sectors':[{'name':'peer','stocks':[{'ticker':t} for t in ('x','a','b','c')]}]})
  returns={5:{'x':30,'a':1,'b':2,'c':3},20:{'x':40,'a':2,'b':3,'c':4}}
  s=momentum('x',returns,{5:0,20:0},groups);self.assertEqual(s['horizons']['5']['peer_return'],2);self.assertEqual(s['horizons']['20']['peer_return'],3)
 def test_thin_peer_group_falls_back_to_market(self):
  groups=sector_groups({'sectors':[{'name':'peer','stocks':['x','a','b']}]});s=momentum('x',{5:{'x':10,'a':1,'b':2},20:{'x':10,'a':1,'b':2}},{5:0,20:0},groups);self.assertIsNone(s['horizons']['5']['peer_return'])
 def test_missing_seventy_percent_coverage_falls_back(self):
  groups=sector_groups({'sectors':[{'name':'peer','stocks':['x','a','b','c','d','e']}]});returns={5:{'x':10,'a':1,'b':2,'c':3},20:{'x':10,'a':1,'b':2,'c':3}};s=momentum('x',returns,{5:0,20:0},groups);self.assertIsNone(s['horizons']['5']['peer_return'])
 def test_subgroup_preferred_when_valid(self):
  config={'sectors':[{'name':'broad','stocks':['x','a','b','c','d'],'subgroups':[{'name':'narrow','tickers':['x','a','b','c']}]}]};returns={h:{'x':20,'a':1,'b':2,'c':3,'d':100} for h in (5,20)};s=momentum('x',returns,{5:0,20:0},sector_groups(config));self.assertEqual(s['horizons']['5']['peer_return'],2)
 def test_overlapping_groups_average_not_cherry_picked(self):
  groups=sector_groups({'sectors':[{'name':'a','stocks':['x','a','b','c']},{'name':'b','stocks':['x','d','e','f']}]});returns={h:{'x':10,'a':0,'b':0,'c':0,'d':20,'e':20,'f':20} for h in (5,20)};s=momentum('x',returns,{5:10,20:10},groups);self.assertEqual(s['score'],50)
 def test_same_session_endpoints_and_future_rows_ignored(self):
  dates=[f'2026-10-{i:02}' for i in range(1,22)];rows=[dict(date=d,index=100+i) for i,d in enumerate(dates)]+[dict(date='2099-01-01',index=9999)];r=benchmark_returns({'raw':rows},dates);self.assertAlmostEqual(r[5],100*(120/115-1));self.assertAlmostEqual(r[20],20)
 def test_missing_endpoint_fails_explicitly(self):
  dates=[f'2026-10-{i:02}' for i in range(1,22)]
  with self.assertRaises(ValueError):benchmark_returns({'raw':[]},dates)
class PositionSizing(unittest.TestCase):
 def test_same_conviction_equal_weight_despite_volatility(self):
  a=target('1000',score=80,sector='a');b=target('1001',score=80,sector='b');a['volatility']=1;b['volatility']=10
  out=allocate([a,b],.2,DEFAULTS);self.assertEqual(out[0]['weight'],out[1]['weight'])
 def test_higher_conviction_not_demoted_for_higher_volatility(self):
  a=target('1000',score=90,sector='a');b=target('1001',score=70,sector='b');a['volatility']=10;b['volatility']=1
  out=allocate([a,b],.2,DEFAULTS);self.assertGreater(out[0]['weight'],out[1]['weight'])
class FreshDecisionGuard(unittest.TestCase):
 def state(self):return initial({**DEFAULTS,'min_exposure':0},'2026-11-13T18:00:00+08:00')
 def test_failed_refresh_suspends_old_target_orders(self):
  s=self.state();frozen_decision(s,plan('2026-11-13',[target()]));bad=plan('2026-11-13',[],at='2026-11-14T22:00:00+08:00',valid=False);frozen_decision(s,bad);session(s,'2026-11-16',{'1815':bar()},{'1815':100});self.assertFalse(s['trades']);self.assertFalse(s['positions']);self.assertTrue(s['execution_warnings'])
 def test_failed_refresh_after_open_cannot_change_prior_open(self):
  s=self.state();frozen_decision(s,plan('2026-11-13',[target()]));frozen_decision(s,plan('2026-11-13',[],at='2026-11-16T10:00:00+08:00',valid=False));session(s,'2026-11-16',{'1815':bar()},{'1815':100});self.assertTrue(s['trades'])
if __name__=='__main__':unittest.main()
