import json
import tempfile
import unittest
from pathlib import Path
from shared_financial_shadow_compare import reconcile
class ShadowCompareTest(unittest.TestCase):
    def test_sidecar_dates_and_conflicts(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)
            def put(n,o): (p/n).write_text(json.dumps(o),encoding='utf-8')
            put('quarterly_earnings.json',{'reports':[{'ticker':'3665','period':'2026-Q3','publish_date':'2026-11-13','operating_margin':20.78,'gross_margin':32.53}]})
            put('quarterly_opm.json',{'schema':1,'metrics':{'3665|2026-Q3':{'value':20.52}}})
            row=dict(ticker='3665',period='2026-Q3',metric='operating_margin',report_id='early',report_date='2026-11-12',value=18,unit='%',broker='Test',source_url='',provenance=[],comparison_candidate=True,needs_review=False)
            rows=[row,{**row,'report_id':'same','report_date':'2026-11-13'},{**row,'report_id':'late','report_date':'2026-11-14'},{**row,'report_id':'conflict'},{**row,'report_id':'conflict','value':19}]
            result,audit=reconcile({'items':rows},p)
            self.assertEqual(len(result['operating_margin']['items']),1)
            self.assertEqual(result['operating_margin']['items'][0]['actual_operating_margin'],20.52)
            self.assertEqual(audit['quarantined_count'],1)
            self.assertEqual(audit['metrics']['operating_margin']['excluded_same_day'],1)
            self.assertEqual(audit['metrics']['operating_margin']['excluded_late'],1)
    def test_conflicting_eps_is_not_published(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)
            def put(n,o): (p/n).write_text(json.dumps(o),encoding='utf-8')
            put('quarterly_earnings.json',{'reports':[{'ticker':'7717','period':'2026-Q3','publish_date':'2026-11-13','eps':2.34},{'ticker':'7717','period':'2026-Q3','publish_date':'2026-11-14','eps':1.45}]})
            put('quarterly_opm.json',{'schema':1,'metrics':{}})
            row=dict(ticker='7717',period='2026-Q3',metric='eps',report_id='one',report_date='2026-10-12',value=2,unit='元/股',broker='Test',source_url='',provenance=[],comparison_candidate=True,needs_review=False)
            result,audit=reconcile({'items':[row]},p)
            self.assertEqual(result['eps']['items'],[])
            self.assertEqual(audit['actual_conflict_count'],1)
if __name__=='__main__':unittest.main()
