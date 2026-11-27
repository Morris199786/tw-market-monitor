import json
import tempfile
import unittest
from pathlib import Path
from shared_financial_catalog import build
class CatalogTest(unittest.TestCase):
    def test_precision_merge(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)
            row=dict(period='2026-Q4',metric='gross_margin',value=32.4,unit='%',type='forecast',source='broker',scope='company',evidence='上修毛利率預期至32.4%')
            report=dict(id='one',ticker='3037',date='2026-10-28',broker='Test',report_type='company',validation_status='verified',financial_forecasts=[row],visualizations=[dict(type='table',headers=['項目','3Q26實際','4Q26預估'],rows=[['毛利率（%）',28.85,32.37]])])
            def put(n,o): (p/n).write_text(json.dumps(o),encoding='utf-8')
            put('reports.json',{'items':[report]})
            put('business_reports_ai.json',{'items':[]})
            put('broker_eps_forecasts.json',{'items':[]})
            catalog,audit=build(p)
            self.assertEqual(audit['precision_resolved'],1)
            self.assertEqual(audit['conflict_groups'],0)
            self.assertEqual([r['value'] for r in catalog['items']],[32.37])
            self.assertTrue(catalog['items'][0]['comparison_candidate'])
            self.assertEqual({r['original_value'] for r in catalog['items'][0]['provenance']},{32.37,32.4})
            report['financial_forecasts'][0]['value']=32.5
            put('reports.json',{'items':[report]})
            catalog,audit=build(p)
            self.assertEqual(audit['conflict_groups'],1)
            self.assertFalse(any(r['comparison_candidate'] for r in catalog['items']))
    def test_archive_keeps_unknown_and_nonquarter_without_promoting(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)
            row=dict(period='2026-Q3',metric='eps',value=2,unit='元/股',type='forecast',source='broker',scope='company',evidence='EPS 2元')
            rows=[row,{**row,'period':'2026-10'},{**row,'period':'2026-H1'},{**row,'period':'2026-YTD'},{**row,'period':'2026-Q3-Q4'},{**row,'metric':'free_cash_flow','value':100},{**row,'type':'actual'},{**row,'source':'consensus'},{**row,'scope':'segment'},{**row,'period':'','value':'2–3'},{**row,'value':True}]
            def put(n,o): (p/n).write_text(json.dumps(o),encoding='utf-8')
            put('reports.json',{'items':[dict(id='one',ticker='3037',date='2026-10-28',broker='Test',financial_forecasts=rows)]})
            put('business_reports_ai.json',{'items':[]})
            put('broker_eps_forecasts.json',{'items':[]})
            catalog,audit=build(p)
            self.assertEqual([r['record'] for r in catalog['raw_records']],rows)
            self.assertEqual(len(catalog['items']),9)
            self.assertEqual(audit['comparison_candidates'],{'eps':1})
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
            self.assertEqual(len(catalog['items']),6)
            self.assertFalse(any(x['report_kind']=='meeting' for x in catalog['items']))
            report['financial_forecasts'].append({**row,'value':19})
            put('reports.json',{'items':[report]})
            catalog,audit=build(p)
            self.assertEqual(audit['conflict_groups'],1)
            self.assertFalse(any(x['comparison_candidate'] for x in catalog['items']))
if __name__=='__main__': unittest.main()
