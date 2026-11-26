#!/usr/bin/env python3
"""Offline tests; no Codex, Drive, Telegram or paid API network requests."""
import json
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch, Mock
from types import ModuleType

sys.path.insert(0, str(Path(__file__).resolve().parent))
import report_provider as provider
import update_business_reports_ai as ai

DAY = '2026-11-26'
YESTERDAY = '2026-11-25'

def row(id, day=DAY, fp='v1'):
    return {'id':id, 'date':day, 'filename':id+'.pdf', 'source_fingerprint':fp, 'company':'測試公司', 'ticker':'1234', 'broker':'測試券商'}

def result(r):
    return dict(id=r['id'], source_fingerprint=r['source_fingerprint'], status='ready', group_date=r['date'], summary=['這是完整測試摘要，不是實際券商觀點。'], detail='詳細測試', report_type='company', ticker='1234', name='測試公司', broker='測試券商')

def drive(r):
    return {'id':r['id'],'md5Checksum':r['source_fingerprint']}

class ProviderTest(unittest.TestCase):
    @patch.dict(os.environ, {'REPORT_AI_ROUTE':'plan-only','OPENAI_API_KEY':'dummy'})
    @patch('requests.post')
    @patch.object(provider,'plan_request')
    def test_never_paid_api(self, plan, post):
        plan.return_value={'status':'ok','text':'summary'}
        self.assertEqual(provider.complete_report({}), 'summary')
        plan.return_value={'status':'plan_limit'}
        with self.assertRaises(provider.NoReportCapacity): provider.complete_report({})
        plan.return_value={'status':'error'}
        with self.assertRaises(RuntimeError): provider.complete_report({})
        plan.side_effect=OSError('offline')
        with self.assertRaises(RuntimeError): provider.complete_report({})
        post.assert_not_called()
    @patch.dict(os.environ, {'REPORT_AI_ROUTE':'plan-first','OPENAI_API_KEY':'dummy'})
    @patch('requests.post')
    @patch.object(provider,'plan_request',return_value={'status':'plan_limit'})
    def test_broker_existing_route(self, plan, post):
        post.return_value=Mock(status_code=200)
        post.return_value.json.return_value={'output':[{'content':[{'type':'output_text','text':'fallback'}]}]}
        self.assertEqual(provider.complete_report({}), 'fallback')
        post.assert_called_once()

class DateAndFallbackTest(unittest.TestCase):
    def test_today_only_and_dedupe(self):
        r=row('done'); a=row('today'); old=row('old',YESTERDAY); changed=row('done',fp='v2'); invitation=dict(row('invite'),filename='邀請.pdf')
        self.assertEqual([x['id'] for x in ai.pending([r,a,a,old,changed,invitation],[result(r)],DAY)],['today','done'])
    def test_quota_stops_and_keeps_prior_results(self):
        old=row('old',YESTERDAY); a,b,c=[row(x) for x in 'abc']; rows=[old,a,b,c]; saved=[result(old)]
        analyzer=Mock(side_effect=[result(a),provider.NoReportCapacity('limit'),result(c)])
        extract=Mock(return_value='source')
        persist=Mock()
        count=ai.run(rows,saved,DAY,lambda:[drive(x) for x in rows],extract,analyzer,persist,lambda:DAY)
        self.assertEqual(count,1); self.assertEqual({x['id'] for x in saved},{'old','a'});self.assertEqual(analyzer.call_count,2);persist.assert_called_once()
        self.assertEqual([x['id'] for x in ai.pending(rows,saved,DAY)],['b','c'])
    def test_worker_down_no_other_calls(self):
        rows=[row('a'),row('b')]; saved=[]
        analyzer=Mock(side_effect=RuntimeError('SSH'))
        self.assertEqual(ai.run(rows,saved,DAY,lambda:[drive(x) for x in rows],lambda x:'source',analyzer,Mock(),lambda:DAY),0)
        analyzer.assert_called_once();self.assertFalse(saved)
    def test_pdf_failure_only_skips_one(self):
        rows=[row('a'),row('b')]; saved=[]
        extract=Mock(side_effect=[ValueError('scan'),'text']); analyzer=Mock(return_value=result(rows[1]));persist=Mock()
        self.assertEqual(ai.run(rows,saved,DAY,lambda:[drive(x) for x in rows],extract,analyzer,persist,lambda:DAY),1)
        self.assertEqual(saved,[result(rows[1])]);analyzer.assert_called_once()
    def test_cross_midnight_and_fingerprint(self):
        r=row('a'); analyzer=Mock();persist=Mock();extract=Mock()
        ai.run([r],[],DAY,lambda:[{'id':'a','md5Checksum':'wrong'}],extract,analyzer,persist,lambda:DAY)
        extract.assert_not_called();analyzer.assert_not_called()
        ai.run([r],[],DAY,lambda:[drive(r)],extract,analyzer,persist,lambda:'2026-11-27')
        analyzer.assert_not_called();persist.assert_not_called()
    def test_empty_pending_does_not_access_drive(self):
        r=row('old',YESTERDAY); files=Mock();self.assertEqual(ai.run([r],[],DAY,files,Mock(),Mock(),Mock(),lambda:DAY),0);files.assert_not_called()

class BrokerReuseTest(unittest.TestCase):
    def test_existing_analyzer_financial_prompt_and_no_raw_publication(self):
        broker=ModuleType('update_reports_ai'); eps=ModuleType('update_reports_ai_eps'); pipeline=ModuleType('broker_eps_pipeline'); identity=ModuleType('report_identity')
        broker.COMPanies=None; broker.COMPANIES={}; broker.complete_report=Mock(); broker.normalize_report=lambda obj,src: {'summary':['摘要'], 'detail':'內文摘要', 'raw_text':src['text'], 'source_text_hash':'secret'}
        def analyze_report(src):
            text=broker.complete_report({'input':[{'content':[{'text':'broker rules'}]}]})
            return broker.normalize_report(json.loads(text),src)
        broker.analyze_report=analyze_report
        eps.EPS_INSTRUCTION=' financial rules'; eps.normalize_financial=lambda x:x
        pipeline.normalize=lambda x:x; identity.registry=lambda refresh=False:{'1234':{}}
        with patch.dict(sys.modules,{'update_reports_ai':broker,'update_reports_ai_eps':eps,'broker_eps_pipeline':pipeline,'report_identity':identity}),patch.object(ai,'complete_plan_report',return_value='{"quarterly_eps":[],"financial_forecasts":[{"metric":"eps"}]}') as complete:
            r=ai.broker_analyzer()(row('a'),'PRIVATE ORIGINAL PDF')
            self.assertNotIn('raw_text',r);self.assertNotIn('PRIVATE ORIGINAL PDF',json.dumps(r));self.assertEqual(r['financial_forecasts'],[{'metric':'eps'}]);self.assertEqual(r['provider'],'codex-plan')
            complete.assert_called_once();self.assertIn('financial rules',complete.call_args.args[0]['input'][0]['content'][0]['text']);broker.complete_report.assert_not_called()

# Load real helper when running in the repo; use a local stand-in for offline bundle tests.
try:
    import report_presentation
except ImportError:
    helper=ModuleType('report_presentation');helper.complete_reason=lambda r:r.get('push_reason') or (r.get('summary') or [''])[0];helper.upside_text=lambda r:''
    sys.modules['report_presentation']=helper
import send_business_reports_summary as telegram

class TelegramTest(unittest.TestCase):
    def test_eligible_only_today_new_and_current_version(self):
        a,b,c,d=row('a'),row('b'),row('c',YESTERDAY),row('d',fp='v2')
        ledger={telegram.report_key(result(b)):{'status':'sent'}}
        eligible=list(telegram.eligible([a,b,c,d],[result(a),result(b),result(c),result(row('d'))],ledger,DAY))
        self.assertEqual([x[0]['id'] for x in eligible],['a'])
    def test_grouped_messages_and_length(self):
        rows=[row(str(i)) for i in range(25)]
        messages=telegram.batches([(dict(result(r),push_reason='內容。'*400),r) for r in rows],DAY,'https://example.org')
        self.assertGreater(len(messages),1);self.assertEqual(sum(len(keys) for _,keys in messages),25)
        self.assertTrue(all(telegram.units(text)<=telegram.LIMIT for text,_ in messages))
    def test_claim_before_send_and_no_duplicate(self):
        r=result(row('a')); k=telegram.report_key(r); ledger={}; snapshots=[]
        def save(value): snapshots.append(json.loads(json.dumps(value)))
        def post(text): self.assertEqual(snapshots[-1][k]['status'],'claimed');return Mock(ok=True,json=lambda:{'ok':True,'result':{'message_id':10}})
        self.assertEqual(telegram.send_batches([('message',[k])],ledger,save,post,lambda:'now'),1)
        self.assertEqual(ledger[k]['status'],'sent');self.assertEqual(list(telegram.eligible([row('a')],[r],ledger,DAY)),[])
    def test_unknown_delivery_no_resend_and_explicit_reject_retry(self):
        k=telegram.report_key(result(row('a'))); ledger={}
        telegram.send_batches([('x',[k])],ledger,Mock(),Mock(side_effect=TimeoutError()),lambda:'now')
        self.assertEqual(ledger[k]['status'],'claimed')
        ledger={}; telegram.send_batches([('x',[k])],ledger,Mock(),Mock(return_value=Mock(ok=False,json=lambda:{'ok':False})),lambda:'now');self.assertEqual(ledger,{})

if __name__=='__main__': unittest.main()
