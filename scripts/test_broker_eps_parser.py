"""Offline regression tests for broker quarterly EPS parser (no Drive/API)."""
import importlib.util
from pathlib import Path
import unittest

spec=importlib.util.spec_from_file_location('eps_parser',Path(__file__).with_name('test_broker_eps_pdf.py'))
p=importlib.util.module_from_spec(spec)
spec.loader.exec_module(p)

class BrokerEpsParserTests(unittest.TestCase):
    def test_multiple_eps_labels_same_header(self):
        words=[{'text':'年季','x0':20,'x1':40},
               {'text':'稅前EPS','x0':380,'x1':420},
               {'text':'稅後EPS','x0':530,'x1':570}]
        line={'words':words,'text':'年季 稅前EPS 稅後EPS'}
        labels=p._eps_anchors(line)
        self.assertEqual(len(labels),1)
        self.assertEqual(labels[0]['kind'],'after_tax')

    def test_vertical_compact_period_sequence(self):
        tokens=[]
        for q in ['202601(A)','202602(A)','202603(F)','202604(F)','202701(F)']:
            a,b,per,fc,act=p._period_tokens(q,True)[0]
            tokens.append({'period':per,'explicit':fc,'actual':act})
        self.assertTrue(p._quarter_sequence(tokens))
        self.assertEqual([t['period'] for t in tokens if t['explicit']],
                         ['2026-Q3','2026-Q4','2027-Q1'])

    def test_quarter_headers(self):
        cases={'26Q3(F)':'2026-Q3','202603(F)':'2026-Q3','3Q26SP':'2026-Q3',
               '3Q26e':'2026-Q3','Q326E':'2026-Q3','27Q4(F)':'2027-Q4'}
        for raw,expected in cases.items():
            with self.subTest(raw=raw):
                match=p.Q.search(raw)
                self.assertIsNotNone(match)
                self.assertEqual(p.period(match),expected)
                self.assertTrue(p.is_forecast(match))
    def test_apostrophe_quarters(self):
        for raw in ("3Q'26(F)","3Q’26(F)","3Q26F"):
            with self.subTest(raw=raw):
                m=p.Q.search(raw)
                self.assertIsNotNone(m)
                self.assertEqual(p.period(m),'2026-Q3')
                self.assertTrue(p.is_forecast(m))
    def test_compact_quarters_are_context_gated(self):
        self.assertFalse(p.Q.search('2603(F)'))
        self.assertFalse(p._period_tokens('2603(F)',allow_compact=False))
        tokens=p._period_tokens('2603(F)',allow_compact=True)
        self.assertEqual(tokens[0][2],'2026-Q3')
        self.assertTrue(tokens[0][3])
        self.assertEqual(p._period_tokens('202604(F)',allow_compact=True)[0][2],'2026-Q4')
    def test_quarter_and_annual_mix(self):
        quarters=p._period_tokens("2Q26 3Q'26(F) 4Q'26(F) 1Q27(F) 2026(F) 2027(F)")
        self.assertEqual([t[2] for t in quarters],['2026-Q2','2026-Q3','2026-Q4','2027-Q1'])
    def test_annual_not_quarter(self):
        self.assertFalse(p.Q.search('2026(F)'))
    def test_eps_kinds(self):
        self.assertEqual(p.eps_kind('稅前EPS'), 'pretax')
        self.assertEqual(p.eps_kind('稅後EPS'), 'after_tax')
        self.assertEqual(p.eps_kind('Reported Diluted EPS'), 'diluted')
        self.assertEqual(p.eps_kind('Reported Basic EPS'), 'basic')
    def test_negative(self):
        self.assertEqual(p.parse_number('-0.37'),-0.37)
        self.assertEqual(p.parse_number('(0.37)'),-0.37)
    def test_reconcile_diluted_over_basic(self):
        rows=[{'period':'2026-Q3','eps':15.62,'eps_kind':'basic','method':'text'},
              {'period':'2026-Q3','eps':15.60,'eps_kind':'diluted','method':'text'}]
        safe,review=p.reconcile_results(rows,[],[])
        self.assertEqual(len(safe),1)
        self.assertEqual(safe[0]['eps'],15.60)
        self.assertFalse(review)
    def test_layout_mixed_annual_gis(self):
        t="""1Q26       2Q26    3Q26E    4Q26F      FY25    FY26E    FY27F
Revenue     100 200 300 400 500 600 700
EPS                   -0.61    -3.14      -0.10     0.61    -0.79    -3.25     3.28
"""
        rows,_=p.layout_block_extract(t)
        self.assertEqual([(r['period'],r['eps']) for r in rows],[('2026-Q3',-0.1),('2026-Q4',0.61)])

    def test_layout_side_by_side_tenghui(self):
        t="""1Q26F        2Q26                     3Q26F         4Q26F      Year-end Dec. 31         FY24       FY25                   FY26 F         FY27 F
Revenue 100 200 300 400
EPS                        1.73      2.96                        4.38          6.04   Capex                      -86      -326                     -326           -326
"""
        rows,_=p.layout_block_extract(t)
        self.assertEqual([(r['period'],r['eps']) for r in rows],[('2026-Q1',1.73),('2026-Q3',4.38),('2026-Q4',6.04)])

    def test_layout_no_forecast_header_no_guess(self):
        rows,_=p.layout_block_extract('1Q26 2Q26 3Q26 4Q26\nEPS 1 2 3 4')
        self.assertEqual(rows,[])

    def test_same_kind_conflict_is_rejected(self):
        rows=[{'period':'2026-Q3','eps':15.60,'eps_kind':'diluted','method':'text'},
              {'period':'2026-Q3','eps':15.70,'eps_kind':'diluted','method':'text'}]
        safe,review=p.reconcile_results(rows,[],[])
        self.assertFalse(safe)
        self.assertEqual(review[0]['reason'],'conflicting_methods_or_tables')

if __name__=='__main__':unittest.main()
