import json,os,sys,tempfile,unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from ai_signal_model import quarter_signal,monthly_bonus,research_signal
from ai_content_research import DIMENSIONS,selected,document,validate,content_score,prepare,load_sources
from ai_portfolio_engine import stamp
NOW=stamp('2026-11-14T22:00:00+08:00')
CAL=['2026-10-20','2026-11-10','2026-11-11','2026-11-12','2026-11-13']
QUOTE='公司表示下一季度訂單明顯增加，毛利率改善。'
def row(**kw):return dict(dict(id='x',ticker='2330',broker='A',date='2026-11-13',summary=QUOTE),**kw)
def result(t='2330',value=1):return dict(ticker=t,summary='需求與獲利改善',one_off='none',dimensions={k:dict(value=value if k!='risk' else 0,confidence=1,quote=QUOTE if k!='risk' else '',reason='原文有具體營運依據') for k in DIMENSIONS})
def cache_for(rows):
 c={'model':'fixture','items':{}}
 for r in rows:
  k,d=document(r,'fixture');c['items'][k]={'status':'complete','result':result()}
 return c
class Flows(unittest.TestCase):
 def test_small_cap_strength_offsets_smaller_absolute_amount(self):
  from update_ai_portfolio import directional
  from ai_signal_model import mixed_flow_score
  values={'large':100000000,'small':10000000};caps={'large':1000000000000,'small':1000000000}
  result=mixed_flow_score(values,caps,directional)
  self.assertGreater(directional(values)['large'],directional(values)['small'])
  self.assertEqual(result['large'],result['small'])
 def test_missing_cap_is_neutral_not_infinite_ratio(self):
  from update_ai_portfolio import directional
  from ai_signal_model import mixed_flow_score
  self.assertEqual(mixed_flow_score({'a':100},{},directional)['a'],.5*directional({'a':100})['a']+.5*50)
class Financial(unittest.TestCase):
 def base(self,**kwargs):return dict(dict(period='2026-Q3',prev_period='2026-Q2',eps=20,prev_eps=22,gross_margin=30,prev_gross_margin=30,operating_margin=20,prev_operating_margin=20),**kwargs)
 def test_eps20_vs22_is_decline_not_growth(self):
  _,_,trend,ev,ri=quarter_signal(self.base(),{},'2330');self.assertLess(trend,50);self.assertGreater(trend,47);self.assertTrue(any('降低EPS扣分' in x for x in ri))
 def test_all_three_decline_gets_lower_score(self):
  a=quarter_signal(self.base(),{},'2330')[2];b=quarter_signal(self.base(gross_margin=25,operating_margin=15),{},'2330')[2];self.assertLess(b,a)
 def test_eps_magnitude_continuous(self):
  a=quarter_signal(self.base(eps=1),{},'2330')[1];b=quarter_signal(self.base(eps=10),{},'2330')[1];self.assertGreater(b,a)
 def test_eps_rise_with_margin_deterioration_is_not_big_bonus(self):
  _,_,t,_,r=quarter_signal(self.base(eps=40,gross_margin=25,operating_margin=15),{},'2330');self.assertLess(t,50);self.assertTrue(any('限制EPS加分' in x for x in r))
 def test_margin_points_not_percent(self):
  _,_,_,ev,_=quarter_signal(self.base(gross_margin=33),{},'2330');self.assertTrue(any('+3.00百分點' in x for x in ev))
 def test_negative_base_and_zero_are_finite(self):
  import math
  for v in [0,-1]:self.assertTrue(math.isfinite(quarter_signal(self.base(prev_eps=v),{},'2330')[2]))
class Monthly(unittest.TestCase):
 def item(self,eps=.66,month='2026-10',**kw):return dict(dict(ticker='2330',monthly_eps=eps,monthly_period=month,publish_date='2026-11-13',publish_time='18:00:00'),**kw)
 def bonus(self,items,base=1.2):return monthly_bonus('2330',items,{('2330','2026-Q3'):{'eps':base}},NOW,CAL)
 def test_fifty_five_percent_one_point(self):self.assertAlmostEqual(self.bonus([self.item()])['bonus'],1)
 def test_exact_forty_percent_no_bonus(self):self.assertEqual(self.bonus([self.item(.48)])['bonus'],0)
 def test_user_example_strict_threshold(self):
  self.assertEqual(self.bonus([self.item(.4)],1)['bonus'],0)
  self.assertEqual(self.bonus([self.item(.39)],1)['bonus'],0)
  self.assertGreater(self.bonus([self.item(.4001)],1)['bonus'],0)
 def test_seventy_percent_two_points(self):self.assertAlmostEqual(self.bonus([self.item(.84)])['bonus'],2)
 def test_no_disclosure_no_penalty(self):self.assertEqual(self.bonus([])['bonus'],0)
 def test_negative_or_zero_baseline_no_fake_ratio(self):
  for b in (0,-1):self.assertEqual(self.bonus([self.item()],b)['bonus'],0)
 def test_max_four_and_no_negative_penalty(self):
  self.assertEqual(self.bonus([self.item(10)])['bonus'],4);self.assertEqual(self.bonus([self.item(-1)])['bonus'],0)
 def test_same_quarter_never_denominator(self):
  x=self.item(1,month='2026-09',quarter_period='2026-Q3',quarter_eps=3);self.assertEqual(self.bonus([x])['bonus'],0)
 def test_future_announcement_ignored(self):self.assertEqual(self.bonus([self.item(publish_date='2026-11-15')])['bonus'],0)
 def test_duplicate_month_not_stacked(self):self.assertEqual(self.bonus([self.item(),self.item()])['bonus'],1)
class Research(unittest.TestCase):
 def test_latest_each_broker_no_three_limit(self):
  rows=[row(id=str(i),broker=str(i)) for i in range(6)]+[row(id='old',broker='0',date='2026-10-20')];self.assertEqual(len(selected(rows,NOW)),6)
 def test_only_latest_memo_event(self):
  rows=[row(id='old',category='法說／訪談',date='2026-10-20'),row(id='new',category='法說／訪談'),row(id='dup',category='法說／訪談')];out=selected(rows,NOW);self.assertEqual(len(out),1);self.assertEqual(out[0]['date'],'2026-11-13')
 def test_future_sources_excluded(self):self.assertEqual(selected([row(date='2026-11-15')],NOW),[])
 def test_unsupported_quote_rejected(self):
  _,d=document(row(),'fixture');r=result();r['dimensions']['outlook']['quote']='不存在的看好證據文字'
  with self.assertRaises(ValueError):validate(r,d)
 def test_cross_company_rejected(self):
  _,d=document(row(),'fixture')
  with self.assertRaises(ValueError):validate(result('2454'),d)
 def test_risk_cannot_add_positive_points(self):
  _,d=document(row(),'fixture');r=result();r['dimensions']['risk']=r['dimensions']['demand']
  with self.assertRaises(ValueError):validate(r,d)
 def test_content_not_rating_changes_score(self):
  a=row(rating='Buy');b=row(rating='Sell',target_price_new=5)
  self.assertEqual(document(a,'fixture')[0],document(b,'fixture')[0])
  c=cache_for([a]);self.assertEqual(research_signal([a],c,NOW,CAL)['score'],research_signal([b],c,NOW,CAL)['score'])
 def test_missing_new_memo_blocks_no_old_substitution(self):
  a=row(id='old',category='法說／訪談',date='2026-10-20');b=row(id='new',category='法說／訪談');s=research_signal([a,b],cache_for([a]),NOW,CAL);self.assertEqual(s['count'],0);self.assertEqual(len(s['missing']),1)
 def test_repeated_identical_cached_input_stable(self):
  a=row();c=cache_for([a]);self.assertEqual(research_signal([a],c,NOW,CAL),research_signal([a],c,NOW,CAL))
 def test_older_report_weighs_less(self):
  rows=[row(id='old',date='2026-10-20'),row(id='new',broker='B')];s=research_signal(rows,cache_for(rows),NOW,CAL);by={x['source']:x for x in s['details']};self.assertLess(by['A']['weight'],by['B']['weight'])
 def test_cache_prepare_once_no_paid_replay(self):
  with tempfile.TemporaryDirectory() as td:
   p=Path(td);(p/'reports.json').write_text(json.dumps({'items':[row()]}));calls=[]
   def infer(doc,model,key):calls.append(doc);return result()
   with patch.dict(os.environ,{'OPENAI_API_KEY':'fixture'}):
    a=deepcopy(prepare(p,NOW,'fixture',infer));b=prepare(p,NOW,'fixture',infer)
   self.assertEqual(len(calls),1);self.assertEqual(a,b)
 def test_cached_failure_not_rebilled(self):
  with tempfile.TemporaryDirectory() as td:
   p=Path(td);(p/'reports.json').write_text(json.dumps({'items':[row()]}));calls=[]
   def infer(*args):calls.append(1);raise ValueError('bad output')
   with patch.dict(os.environ,{'OPENAI_API_KEY':'fixture'}):prepare(p,NOW,'fixture',infer);c=prepare(p,NOW,'fixture',infer)
   self.assertEqual(len(calls),1);self.assertEqual(c['status']['errors'],1)
 def test_native_memo_shard_is_loaded(self):
  with tempfile.TemporaryDirectory() as td:
   p=Path(td);(p/'research_shards').mkdir();(p/'research_manifest.json').write_text(json.dumps({'shards':[{'file':'a.json'}]}));(p/'research_shards/a.json').write_text(json.dumps({'items':[row(ticker='2330.TW',category='法說／訪談',full_text=QUOTE)]}))
   read=lambda path:json.loads(path.read_text()) if path.exists() else {}
   self.assertEqual(load_sources(p,read,NOW)['2330'][0]['ticker'],'2330')
if __name__=='__main__':unittest.main()
