import json
import tempfile
import unittest
from pathlib import Path
from broker_eps_compare import compare

class CompareTest(unittest.TestCase):
    def test_dates_periods_and_idempotence(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t); d=root/'data';d.mkdir()
            def put(name,value): (d/name).write_text(json.dumps(value),encoding='utf-8')
            put('broker_eps_forecasts.json',{'items':[
                {'ticker':'6213','period':'2026-Q4','report_date':'2026-10-05','report_id':'old','broker':'甲','eps':10},
                {'ticker':'6213','period':'2026-Q4','report_date':'2026-10-20','report_id':'late','broker':'乙','eps':8},
                {'ticker':'6213','period':'2026-Q4','report_date':'2026-10-08','report_id':'same','broker':'丙','eps':7},
                {'ticker':'6213','period':'2026-Q3','report_date':'2026-10-05','report_id':'wrong-quarter','broker':'丁','eps':10}]})
            put('self_reports.json',{'items':[{'ticker':'6213','name':'聯茂','monthly_period':'2026-10','monthly_eps':3,'publish_date':'2026-10-08'}]})
            put('quarterly_earnings.json',{'reports':[{'ticker':'6213','name':'聯茂','period':'2026-Q4','eps':12,'publish_date':'2027-02-01'}]})
            out=compare(root)['items']
            self.assertEqual(len(out),4)
            self.assertEqual({x['report_id'] for x in out if x['actual_kind']=='monthly'},{'old'})
            self.assertEqual(next(x['ratio_pct'] for x in out if x['actual_kind']=='monthly'),30.0)
            self.assertEqual({x['report_id'] for x in out if x['actual_kind']=='quarterly'},{'old','late','same'})
            first=(d/'broker_eps_comparisons.json').read_bytes();compare(root)
            self.assertEqual(first,(d/'broker_eps_comparisons.json').read_bytes())
    def test_no_announcement_date(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);d=root/'data';d.mkdir()
            for name,content in [('broker_eps_forecasts.json',{'items':[{'ticker':'6213','period':'2026-Q4','report_date':'2026-10-05','report_id':'a','eps':10}]}),('self_reports.json',{'items':[{'ticker':'6213','monthly_period':'2026-10','monthly_eps':2}]}),('quarterly_earnings.json',{'reports':[]})]:
                (d/name).write_text(json.dumps(content))
            self.assertEqual(compare(root)['items'],[])
if __name__=='__main__':unittest.main()
