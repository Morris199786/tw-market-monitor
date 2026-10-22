import unittest
from broker_eps_structured import parse_layout,quarter_cols
class TestStructured(unittest.TestCase):
 def test_daiwa_grouped_year(self):
  txt='''ITEQ: quarterly and annual P&L statement
                    2026E                              2027E
                    1Q       2Q       3QE      4QE      1QE      2QE      3QE      4QE
Net revenue         9143     11530    15617    18371    18653    20297    22642    23357
Net EPS (TWD)       0.87     3.52     7.28     10.15    10.64    11.86    13.43    13.62
'''
  rows,_=parse_layout(txt,'2026-10-14');self.assertEqual({x['period']:x['eps'] for x in rows},{'2026-Q3':7.28,'2026-Q4':10.15,'2027-Q1':10.64,'2027-Q2':11.86,'2027-Q3':13.43,'2027-Q4':13.62})
 def test_gs_compact(self):
  txt='''Exhibit 4: P&L table
                  1Q25    2Q25    3Q25    4Q25    1Q26    2Q26    3Q26E   4Q26E
EPS, NT$          9.68    10.19   10.50   11.64   13.35   16.55   16.04   15.13
'''
  rows,_=parse_layout(txt,'2026-10-12');self.assertEqual({x['period']:x['eps'] for x in rows}['2026-Q3'],16.04)
 def test_actual_not_forecast(self):
  txt='''               1Q26A   2Q26A   3Q26E   4Q26E
EPS (NT$)      1.03    0.51    3.51    4.56
'''
  rows,_=parse_layout(txt,'2026-10-20');self.assertEqual([r['period'] for r in rows],['2026-Q3','2026-Q4'])
if __name__=='__main__':unittest.main()
