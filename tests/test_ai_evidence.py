import json,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from ai_evidence import resolve_quote
from ai_content_research import prepare,document,validate,repair_citations,passages_for
from test_ai_model_content import row,result,QUOTE,NOW
class EvidenceEquivalence(unittest.TestCase):
 def test_pdf_line_breaks_return_literal_source(self):
  source='2027 年\n隨新產能開出及新應用導入，毛利率目標亦為 40%'
  fixed=resolve_quote('2027 年隨新產能開出及新應用導入，毛利率目標亦為 40%',source)
  self.assertEqual(fixed['quote'],source)
 def test_numeric_list_conjunction_equivalent(self):
  self.assertIsNotNone(resolve_quote('EPS分別下修3%、10%、8%','EPS分別下修3%、10%及8%'))
 def test_exact_units_preserve_actual_source(self):
  fixed=resolve_quote('預期營收至新台幣130,083百萬元','預期營收至新台幣1,300.83億元')
  self.assertEqual(fixed['quote'],'預期營收至新台幣1,300.83億元')
 def test_forecast_word_cannot_be_omitted(self):
  self.assertIsNone(resolve_quote('2027年營收8,143,386百萬元，年增45.45%','2027年營收預估8,143,386百萬元，年增45.45%'))
 def test_wrong_currency_number_period_and_direction_blocked(self):
  for q,source in [('EPS預估為10億元','EPS預估為1億元'),('2027年EPS1元','2026年EPS1元'),('EPS成長10%','EPS衰退10%'),('營收為USD10億元','營收為TWD10億元')]:
   self.assertIsNone(resolve_quote(q,source),(q,source))
 def test_negative_amount_never_matches_positive(self):self.assertIsNone(resolve_quote('單季損益為1億元','單季損益為-1億元'))
 def test_no_fuzzy_word_deletion(self):self.assertIsNone(resolve_quote('公司平均毛利率可能下降','公司整體平均毛利率可能下降'))
 def test_abbreviation_parentheses_layout(self):
  self.assertIsNotNone(resolve_quote('HPC：占比46%，營收年增61%','高效能運算（HPC）：占比46%，營收年增61%'))
 def test_accounting_parentheses_not_removed(self):self.assertIsNone(resolve_quote('單季損益為1億元','單季損益為(1億元)'))
 def test_no_rounding_tolerance(self):self.assertIsNone(resolve_quote('營收達1300億元','營收達1300.83億元'))
 def test_local_recovery_no_api(self):
  r=row(summary=QUOTE.replace('，','，\n'));key,doc=document(r,'fixture');raw=result()
  with tempfile.TemporaryDirectory() as td:
   p=Path(td);(p/'reports.json').write_text(json.dumps({'items':[r]}));(p/'ai_research_content.json').write_text(json.dumps({'model':'fixture','items':{key:{'status':'error','raw_result':raw}}}))
   with patch('ai_content_research.repair_citations',side_effect=AssertionError('API must not run')),patch.dict('os.environ',{'OPENAI_API_KEY':''}):c=prepare(p,NOW,'fixture')
   self.assertEqual(c['items'][key]['status'],'complete');self.assertIn('\n',c['items'][key]['result']['dimensions']['demand']['quote'])
 def test_passage_ids_restore_source_qualifier(self):
  source=row(summary='2027年營收預估800億元，公司尚未宣布實績。');_,doc=document(source,'fixture');raw=result();raw['dimensions']={k:{**d,'value':0,'quote':''} for k,d in raw['dimensions'].items()};raw['dimensions']['outlook']={'value':1,'confidence':.8,'quote':'2027年營收800億元','reason':'券商預估明年營收成長'}
  with patch('ai_content_research.request_json',return_value={'ticker':'2330','citations':{'outlook':{'supported':True,'passage_id':1}}}):
   fixed=repair_citations(doc,raw,'fixture','fixture')
  self.assertIn('預估',fixed['dimensions']['outlook']['quote']);self.assertEqual(fixed['dimensions']['outlook']['value'],1);self.assertIn(fixed['dimensions']['outlook']['quote'],doc['text'])
 def test_unsupported_judgment_not_forced_through(self):
  _,doc=document(row(),'fixture');raw=result();raw['dimensions']['demand']['quote']='並不存在的訂單大幅增加原文'
  with patch('ai_content_research.request_json',return_value={'ticker':'2330','citations':{'demand':{'supported':False,'passage_id':1}}}):
   with self.assertRaises(ValueError):repair_citations(doc,raw,'fixture','fixture')
 def test_repair_cannot_reuse_wrong_numeric_fact(self):
  _,doc=document(row(summary='2027年營收預估800億元。'),'fixture');raw=result();raw['dimensions']={k:{**d,'value':0,'quote':''} for k,d in raw['dimensions'].items()};raw['dimensions']['outlook']={'value':1,'confidence':.8,'quote':'2027年營收預估900億元','reason':'財測改善'}
  with patch('ai_content_research.request_json',return_value={'ticker':'2330','citations':{'outlook':{'supported':True,'passage_id':1}}}):
   with self.assertRaises(ValueError):repair_citations(doc,raw,'fixture','fixture')
 def test_source_passages_lossless_and_contiguous(self):
  doc={'text':('營收預估，非實績。\n'*500)};parts=passages_for(doc);self.assertEqual(''.join(p['text'] for p in parts),doc['text']);self.assertTrue(all(p['text']==doc['text'][p['start']:p['end']] for p in parts))
if __name__=='__main__':unittest.main()
