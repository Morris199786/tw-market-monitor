import json
import tempfile
import unittest
from pathlib import Path
from broker_eps_compare import saved_metric_rows, compare_margin_metric

class MarginRegression(unittest.TestCase):
    def test_actual_not_forecast(self):
        report={'broker':'BofA','visualizations':[{'type':'table','title':'3Q26 季度業績與券商預估','headers':['指標','3Q26','券商預估'],'rows':[['毛利率','88.2%','85%'],['OPM','82.9%','80%']]}]}
        self.assertEqual([x[:2] for x in saved_metric_rows(report,'gross_margin')],[('2026-Q3',85)])
        self.assertEqual([x[:2] for x in saved_metric_rows(report,'operating_margin')],[('2026-Q3',80)])
    def test_sidecar_and_date(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); data=root/'data'; data.mkdir()
            def put(name,obj): (data/name).write_text(json.dumps(obj),encoding='utf-8')
            forecast={'period':'2026-Q3','metric':'operating_margin','type':'forecast','source':'broker','value':18,'unit':'%'}
            reports=[{'id':rid,'ticker':'3665','broker':'Test','date':day,'financial_forecasts':[forecast]} for rid,day in [('early','2026-11-12'),('same','2026-11-13'),('late','2026-11-14')]]
            put('reports.json',{'items':reports})
            put('quarterly_earnings.json',{'reports':[{'ticker':'3665','period':'2026-Q3','publish_date':'2026-11-13','operating_margin':20.78}]})
            put('quarterly_opm.json',{'schema':1,'metrics':{'3665|2026-Q3':{'value':20.52}}})
            rows=compare_margin_metric(root,'operating_margin')['items']
            self.assertEqual(len(rows),1)
            self.assertEqual(rows[0]['report_id'],'early')
            self.assertEqual(rows[0]['actual_operating_margin'],20.52)
if __name__=='__main__': unittest.main()
