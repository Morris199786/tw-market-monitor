import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from minervini_patterns import clean_bars,pivots,rs_ranks,trend,setup_at,limit_companies,liquid_enough,unbroken_setup,analyze
class Patterns(unittest.TestCase):
 def bars(self,n=260):
  from datetime import date,timedelta
  return [dict(time=str(date(2025,1,1)+timedelta(days=i)),open=100+i,high=102+i,low=99+i,close=101+i,volume=1000) for i in range(n)]
 def test_future(self):
  b=self.bars();self.assertEqual(len(clean_bars(b,b[99]['time'])),100)
 def test_duplicate(self):
  b=self.bars();self.assertRaises(ValueError,clean_bars,b+[b[-1]],b[-1]['time'])
 def test_bad_ohlc(self):
  b=self.bars();b[-1]['low']=10000;self.assertEqual(len(clean_bars(b,b[-1]['time'])),259)
 def test_insufficient(self):self.assertEqual(trend(self.bars(200),90),[])
 def test_rs_ties(self):
  b=self.bars();r=rs_ranks({'a':b,'b':b});self.assertEqual(r['a'],r['b'])
 def test_trend(self):self.assertTrue(all(c['passed'] for c in trend(self.bars(),90)))
 def test_no_fake_swings(self):self.assertEqual([p[0] for p in pivots(self.bars(),0,260)],[])
 def test_flat_geometry(self):
  b=self.bars()
  for i in range(225,260):b[i].update(open=350,close=351,high=354 if i>225 else 360,low=345)
  candidates=[s for s in setup_at(b,260) if s['pattern']=='flat'];self.assertTrue(candidates)
  self.assertTrue(all(s['end']==259 and s['pivot']==360 for s in candidates))
class Limit(unittest.TestCase):
 def test_empty(self):self.assertEqual(limit_companies([]),[])
 def test_no_padding(self):self.assertEqual(len(limit_companies([{'ticker':'A'}])),1)
 def test_cap_unique(self):
  rows=[{'ticker':str(i)} for i in range(15)]+[{'ticker':'0'}]
  out=limit_companies(rows)
  self.assertEqual(len({x['ticker'] for x in out}),10)
  self.assertEqual(sum(x['ticker']=='0' for x in out),2)
class Audit(unittest.TestCase):
 def test_illiquid_rejected(self):
  b=Patterns().bars()
  self.assertFalse(liquid_enough(b))
  self.assertEqual(analyze(b,90),[])
 def test_prior_breakout_cannot_hide_in_base(self):
  b=Patterns().bars();s={'segments':[{'end':250}], 'pivot':355, 'start':240}
  self.assertFalse(unbroken_setup(b,s,260))
 def test_contracted_volume_required(self):
  from unittest.mock import patch
  b=Patterns().bars()
  for row in b:row['volume']=1000000
  setup={'segments':[], 'start':240,'pivot':1000}
  with patch('minervini_patterns.setup_at',return_value=[setup]):
   self.assertEqual(analyze(b,90),[])
if __name__=='__main__':unittest.main()
