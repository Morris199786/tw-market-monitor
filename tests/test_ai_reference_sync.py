import unittest,sys
from pathlib import Path
from copy import deepcopy
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from ai_reference_data import digest,holder_values,research_index,merge_earnings,reference_snapshot
from ai_portfolio_engine import initial,DEFAULTS,frozen_decision,session,number

def plan(hash,at='2026-11-13T22:00:00+08:00',ticker='2330'):
 return dict(date='2026-11-13',available_at=at,valid=True,input_hash=hash,targets=[dict(ticker=ticker,name=ticker,weight=.1,asset_type='stock',avg_volume=10000000,evidence=[])],regime={'target_exposure':.9})
def bar():return dict(open=100,high=101,low=99,close=100,volume=10000000)
class References(unittest.TestCase):
 def test_content_not_refresh_clock(self):
  self.assertEqual(digest({'updated_at':'A','observed_at':'2026-11-14T10:00:00','eps':2}),digest({'updated_at':'B','observed_at':'2026-11-14T22:00:00','eps':2}))
  self.assertNotEqual(digest({'eps':2}),digest({'eps':3}))
 def test_full_400_and_1000_without_top_rank(self):
  h=dict(date='20261113',previous_date='20261106');c=dict(date='20261113',stocks={'9999':{'400_ratio':60,'1000_ratio':40}});p=dict(date='20261106',stocks={'9999':{'400_ratio':62,'1000_ratio':35}})
  v,mode=holder_values(h,c,p,number)
  self.assertEqual(mode,'full_weekly_history');self.assertEqual(v['9999']['400']['delta'],-2);self.assertEqual(v['9999']['1000']['delta'],5)
 def test_fallback_keeps_both_tiers(self):
  h={'date':'20261113','twse':{'400':[dict(ticker='2330',delta=1,ratio=50)],'1000':[dict(ticker='2330',delta=-1,ratio=40)]}}
  v,mode=holder_values(h,{}, {},number)
  self.assertEqual(mode,'ranked_fallback');self.assertEqual(set(v['2330']),{'400','1000'})
 def test_wrong_week_not_mixed(self):
  h=dict(date='20261113',previous_date='20261106');c=dict(date='20261030',stocks={'2330':{'400_ratio':80}})
  v,mode=holder_values(h,c,{},number);self.assertEqual(v,{})
 def test_industry_views_are_assigned_explicitly(self):
  rows=[dict(id='A',ticker=None,broker='X',rating='Sell',stock_views=[dict(ticker='2330',rating='Buy'),dict(ticker='2454',rating='Sell')])]
  out=research_index(rows);self.assertEqual(out['2330'][0]['rating'],'Buy');self.assertEqual(out['2454'][0]['rating'],'Sell');self.assertNotIn('None',out)
 def test_no_parent_target_leaks_to_peer(self):
  row=dict(ticker='2330',target_price_new=2000,stock_views=[dict(ticker='2454',rating='Buy')]);out=research_index([row]);self.assertNotIn('target_price_new',out['2454'][0])
 def test_recovered_metrics_follow_website_merge(self):
  old={'reports':[dict(ticker='2330',period='2026-Q3',eps=3,gross_margin=50)]};cur={'reports':[dict(ticker='2330',period='2026-Q3',eps=None,gross_margin=55)]}
  merged=merge_earnings(cur,old);self.assertEqual(merged[0]['eps'],3);self.assertEqual(merged[0]['gross_margin'],55)
class Revisions(unittest.TestCase):
 def setUp(self):self.state=initial({**DEFAULTS,'min_exposure':0},'2026-11-13T18:00:00+08:00')
 def test_same_reference_no_new_version(self):
  frozen_decision(self.state,plan('A'));self.assertFalse(frozen_decision(self.state,plan('A','2026-11-13T23:00:00+08:00')));self.assertEqual(len(self.state['decisions']),1)
 def test_changed_reference_new_revision_preserves_history(self):
  frozen_decision(self.state,plan('A'));old=deepcopy(self.state['decisions'][0]);frozen_decision(self.state,plan('B','2026-11-13T23:00:00+08:00','2454'))
  self.assertEqual(self.state['decisions'][0],old);self.assertEqual(self.state['decisions'][-1]['revision'],2)
 def test_only_latest_preopen_revision_trades(self):
  frozen_decision(self.state,plan('A'));frozen_decision(self.state,plan('B','2026-11-14T22:00:00+08:00','2454'))
  session(self.state,'2026-11-16',{'2330':bar(),'2454':bar()},{'2330':100,'2454':100})
  self.assertEqual(set(self.state['positions']),{'2454'});self.assertEqual(self.state['trades'][0]['decision_id'],self.state['decisions'][-1]['decision_id'])
 def test_after_open_revision_cannot_rewrite_that_open(self):
  frozen_decision(self.state,plan('A'));frozen_decision(self.state,plan('B','2026-11-16T10:00:00+08:00','2454'))
  session(self.state,'2026-11-16',{'2330':bar(),'2454':bar()},{'2330':100,'2454':100})
  self.assertEqual(set(self.state['positions']),{'2330'})
  previous=deepcopy(self.state['trades']);self.assertFalse(session(self.state,'2026-11-16',{},{}));self.assertEqual(previous,self.state['trades'])
 def test_invalid_refresh_preserves_last_valid_list(self):
  frozen_decision(self.state,plan('A'));bad=plan('B');bad['valid']=False;self.assertFalse(frozen_decision(self.state,bad));self.assertEqual(self.state['decisions'][-1]['input_hash'],'A')
if __name__=='__main__':unittest.main()
