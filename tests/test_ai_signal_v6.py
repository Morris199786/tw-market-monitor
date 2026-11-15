import sys,unittest,math
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from ai_holder_signal import holder_signal,publication
from ai_portfolio_engine import stamp
from ai_signal_model import monthly_bonus,quarter_signal
class SelfReports(unittest.TestCase):
 def score(self,eps,base=3):
  row=dict(ticker='2330',monthly_eps=eps,monthly_period='2026-10',publish_date='2026-11-13',publish_time='15:00:00')
  return monthly_bonus('2330',[row],{('2330','2026-Q3'):{'eps':base}},stamp('2026-11-14T22:00:00+08:00'),['2026-11-13'])
 def test_buffer_and_strict_threshold(self):
  for eps in [1,1.1,1.2]:self.assertEqual(self.score(eps)['bonus'],0)
  self.assertGreater(self.score(1.20001)['bonus'],0)
 def test_lower_eps_stronger_penalties(self):
  vals=[self.score(x)['bonus'] for x in [1,.99,.8,.79,.4,0,-.1]]
  self.assertEqual(vals,sorted(vals,reverse=True));self.assertLess(vals[-1],-6)
 def test_loss_transitions_and_near_zero_finite(self):
  self.assertGreater(self.score(.2,-3)['bonus'],self.score(-.1,-3)['bonus'])
  self.assertGreater(self.score(-.5,-3)['bonus'],0)
  self.assertLess(self.score(-2,-3)['bonus'],0)
  for b in [0,1e-12,-1e-12,.149999,.15]:
   self.assertTrue(math.isfinite(self.score(.02,b)['bonus']))
 def test_unknown_quarter_not_neutral_negative_eps(self):
  # Missing denominator is unknown, not proof of a profit-to-loss transition.
  row=dict(ticker='2330',monthly_eps=-1,monthly_period='2026-10',publish_date='2026-11-13')
  self.assertEqual(monthly_bonus('2330',[row],{},stamp('2026-11-14T22:00:00+08:00'),[])['bonus'],0)
 def test_quarter_loss_not_hidden_by_margin_improvement(self):
  row=dict(period='2026-Q3',prev_period='2026-Q2',eps=-1,prev_eps=1,gross_margin=31,prev_gross_margin=30,operating_margin=11,prev_operating_margin=10)
  _,_,trend,ev,risks=quarter_signal(row,{},'2330')
  self.assertLess(trend,50);self.assertTrue(any('盈轉虧' in x for x in risks));self.assertFalse(any('降低EPS扣分' in x for x in risks))
class Holders(unittest.TestCase):
 def setUp(self):
  self.cal=['2026-11-13','2026-11-16','2026-11-17','2026-11-18','2026-11-19','2026-11-20','2026-11-23','2026-11-24','2026-11-25']
  self.holder={'date':'20261113'};self.market={d:100 for d in self.cal}
  self.hist={'2330':{d:{'close':100,'low':99} for d in self.cal}}
 def score(self,n,tiers=(90,70)):
  d=self.cal[n];return holder_signal('2330',tiers,self.holder,stamp(d+'T22:00:00+08:00'),d,self.cal,self.hist,self.market,[])
 def test_publication_not_statistics_date_and_no_future_use(self):
  self.assertEqual(publication(self.holder)[0].isoformat(),'2026-11-14T15:00:00+08:00')
  self.assertEqual(self.score(0)['score'],50)
  x=holder_signal('2330',[90,70],self.holder,stamp('2026-11-15T22:00:00+08:00'),'2026-11-13',self.cal,self.hist,self.market,[])
  self.assertEqual(x['score'],80);self.assertEqual(x['sessions'],0)
 def test_first_two_sessions_fresh_then_fade_to_neutral(self):
  scores=[self.score(n)['score'] for n in range(1,9)]
  self.assertEqual(scores[:2],[80,74]);self.assertEqual(scores[-1],50)
  self.assertEqual(scores,sorted(scores,reverse=True))
 def test_stock_and_market_fall_together_not_false_invalidation(self):
  for d,v in zip(self.cal[1:4],[98,96,93]):self.hist['2330'][d]['close']=v;self.market[d]=v
  self.assertEqual(self.score(3)['confirmation_multiplier'],1)
 def test_persistent_underperformance_halves_only_positive_tiers(self):
  self.hist['2330'][self.cal[1]]['close']=99;self.hist['2330'][self.cal[2]]['close']=97
  a=self.score(2,(90,30));self.assertEqual(a['confirmation_multiplier'],.5)
  self.assertAlmostEqual(a['score'],50) # +40*.8*.5 offsets -20*.8
 def test_breakdown_invalidates_positive_not_negative(self):
  for d,v in zip(self.cal[1:4],[99,97,94]):self.hist['2330'][d]['close']=v
  self.assertEqual(self.score(3)['confirmation_multiplier'],0)
  self.assertEqual(self.score(3)['score'],50)
  self.assertLess(self.score(3,(20,30))['score'],50)
 def test_relative_rebound_not_two_daily_underperformances(self):
  for d,v in zip(self.cal[1:4],[98,94,96]):self.hist['2330'][d]['close']=v
  self.assertEqual(self.score(3)['confirmation_multiplier'],1)
 def test_new_week_resets_age_and_overrides_old_positive(self):
  self.holder={'date':'20261120'}
  x=self.score(6,(20,30));self.assertEqual(x['sessions'],1);self.assertEqual(x['score'],25)
 def test_holiday_does_not_age_signal(self):
  self.cal.remove('2026-11-16');x=self.score(1)
  self.assertEqual(x['weight'],1);self.assertEqual(x['sessions'],1)
 def test_actual_release_timestamp_overrides_estimate(self):
  self.holder['published_at']='2026-11-16T16:00:00+08:00'
  self.assertEqual(self.score(1)['score'],80);self.assertEqual(self.score(1)['sessions'],0)
  self.assertEqual(self.score(2)['weight'],1)
 def test_missing_comparison_not_false_strength(self):
  del self.hist['2330']['2026-11-16']
  x=self.score(2);self.assertEqual(x['confirmation_multiplier'],.5)
 def test_peer_strength_detects_weak_stock_even_if_market_flat(self):
  from ai_holder_signal import confirmation
  for t in ['a','b','c']:
   self.hist[t]={d:{'close':100 if d==self.cal[0] else 110 if d==self.cal[1] else 120} for d in self.cal}
  x=confirmation('2330',publication(self.holder)[0],self.cal[2],self.cal,self.hist,self.market,[{'name':'同業','depth':0,'members':{'2330','a','b','c'}}])
  self.assertEqual(x['multiplier'],.5);self.assertEqual(x['benchmark'],'同期大盤60%＋族群40%')
if __name__=='__main__':unittest.main()
