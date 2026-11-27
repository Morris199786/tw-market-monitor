import json
import tempfile
import unittest
from pathlib import Path
from shared_financial_catalog import build
class CatalogTest(unittest.TestCase):
    def test_shadow_classification(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)
            def put(n,o): (p/n).write_text(json.dumps(o),encoding='utf-8')
            row=dict(period='2026-Q3',metric='operating_margin',value=18,unit='%',type='forecast',source='broker',scope='company',evidence='broker forecast 18%')
            report=dict(id='one',ticker='3665',date='2026-10-01',broker='Test',financial_forecasts=[row,{**row,'type':'actual','value':20},{**row,'period':'2026'},{**row,'source':'consensus'},{**row,'scope':'segment'},{**row,'type':'previous_forecast'}])
            put('reports.json',{'items':[report]})
            put('business_reports_ai.json',{'items':[{'id':'pending','status':'pending','financial_forecasts':[row]}]})
            put('research_financial_forecasts.json',{'reports':{'meeting':{'forecasts':[dict(row,status='E')]}}})
            put('broker_eps_forecasts.json',{'items':[]})
            catalog,audit=build(p)
            self.assertEqual(audit['comparison_candidates'],{'operating_margin':1})
            self.assertEqual(len(catalog['items']),7)
            self.assertFalse(any(x['comparison_candidate'] for x in catalog['items'] if x['report_kind']=='meeting'))
            report['financial_forecasts'].append({**row,'value':19})
            put('reports.json',{'items':[report]})
            catalog,audit=build(p)
            self.assertEqual(audit['conflict_groups'],1)
            self.assertFalse(any(x['comparison_candidate'] for x in catalog['items']))
if __name__=='__main__': unittest.main()
