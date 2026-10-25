import copy
from datetime import date
import unittest
from unittest.mock import Mock
from research_dedup import Matcher,content_key,stable_key
from ai_research_backfill import make_plan,execute,window,validate_cache
from sync_line_research import attach_ai

def row(**kw):
    r=dict(id='line-a',date='2026-10-23',original_type='個股報告',type='個股報告',company='緯穎',ticker='6669.TW',source='統一投顧',period='Q3',story='成長展望'*30,full_text='營收1.5億元，EPS預估3.0元。'*30,display={})
    r.update(kw);return r

def broker(**kw):
    r=dict(id='original-broker-id',date='2026-10-21',group_date='2026-10-23',name='緯穎',ticker='6669',broker='統一',report_type='company',title='既有標題')
    r.update(kw);return r

class ResearchTests(unittest.TestCase):
    def plan(self,rows,cache=None,brokers=None):return make_plan(rows,brokers or [],[],cache or {},date(2026,10,25))
    def test_window_and_types(self):
        self.assertEqual(window(date(2026,3,31))[0],date(2026,2,28))
        rows=[row(),row(id='old',date='2026-09-24'),row(id='future',date='2026-10-26'),row(id='memo',original_type='法說會')]
        self.assertEqual(len(self.plan(rows)['items']),1)
    def test_two_day_match(self):
        b=broker(group_date='2026-10-21')
        self.assertEqual(Matcher([b]).decide(row())['status'],'broker_duplicate')
        self.assertEqual(Matcher([b]).decide(row(source='元大'))['status'],'new')
        self.assertEqual(Matcher([b]).decide(row(ticker='2330'))['status'],'new')
    def test_ambiguous_matches_never_pay(self):
        p=self.plan([row()],brokers=[broker(),broker(id='other')])
        self.assertEqual(p['items'][0]['status'],'needs_review')
        api=Mock();execute([row()],p,{},10,save=Mock(),analyze=api);api.assert_not_called()
    def test_sector_not_dropped_by_date(self):
        r=row(original_type='產業報告',ticker='')
        self.assertEqual(Matcher([broker(report_type='sector',ticker='')]).decide(r)['status'],'needs_review')
    def test_file_id_reuses_sector(self):
        b=broker(source_file_id='1234567890123456789',report_type='sector')
        r=row(original_type='產業報告',source_row='https://drive.google.com/file/d/1234567890123456789/view')
        self.assertEqual(Matcher([b]).decide(r)['status'],'broker_duplicate')
    def test_one_call_then_rerun_and_edit(self):
        rows=[row()];cache={};events=[]
        def save(c):events.append(c['line-a']['status'])
        def api(src):
            self.assertEqual(events,['api_reserved']);return {'summary':['摘要'],'title':'標題','detail':'內容'}
        self.assertEqual(execute(rows,self.plan(rows),cache,10,save,api),1)
        self.assertEqual(events,['api_reserved','success'])
        changed=row(id='changed',story='修改摘要',full_text='新內容'*50)
        api=Mock()
        execute([changed],self.plan([changed],cache),cache,10,save=Mock(),analyze=api)
        api.assert_not_called();self.assertEqual(cache['changed']['status'],'alias')
        self.assertEqual(attach_ai(changed,cache)['title'],'標題')
    def test_timeout_no_retry(self):
        r=row();cache={};api=Mock(side_effect=TimeoutError)
        execute([r],self.plan([r]),cache,10,Mock(),api)
        self.assertEqual(cache[r['id']]['status'],'unknown')
        execute([r],self.plan([r],cache),cache,10,Mock(),api)
        self.assertEqual(api.call_count,1)
    def test_failed_claim_push_zero_calls(self):
        r=row();api=Mock()
        with self.assertRaises(RuntimeError):execute([r],self.plan([r]),{},10,Mock(side_effect=RuntimeError),api)
        api.assert_not_called()
    def test_crash_after_response_claim_blocks(self):
        r=row();cache={};remote={}
        def save(c):
            if c[r['id']]['status']=='success':raise RuntimeError('push failed')
            remote.update(copy.deepcopy(c))
        with self.assertRaises(RuntimeError):execute([r],self.plan([r]),cache,10,save,Mock(return_value={'title':'t'}))
        api=Mock();execute([r],self.plan([r],remote),remote,10,Mock(),api);api.assert_not_called()
    def test_excel_duplicates_and_cap(self):
        a=row();b=row(id='line-b',source='另個券商');c=row(id='line-c',ticker='2330',full_text='不同原文'*90)
        rows=[a,b,c];cache={};api=Mock(return_value={'title':'t'})
        execute(rows,self.plan(rows),cache,1,Mock(),api)
        self.assertEqual(api.call_count,1);self.assertEqual(cache[b['id']]['status'],'alias')
        execute(rows,self.plan(rows,cache),cache,1,Mock(),api);self.assertEqual(api.call_count,2)
    def test_financial_punctuation_and_corrupt_cache(self):
        self.assertNotEqual(content_key(row(full_text='EPS1.5元'*50)),content_key(row(full_text='EPS15元'*50)))
        with self.assertRaises(ValueError):validate_cache({'id':None})
    def test_existing_legacy_success_preserved(self):
        r=row();cache={'old':{'status':'success','stable_key':stable_key(r),'result':{'summary':'舊摘要'}}}
        self.assertEqual(self.plan([r],cache)['items'][0]['status'],'cached')

if __name__=='__main__':unittest.main()

class PublicationTests(unittest.TestCase):
    def test_all_history_dedup_ai_render_metadata_and_rerun(self):
        import tempfile,json,os
        from pathlib import Path
        from unittest.mock import patch
        import sync_line_research as sync
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);data=root/'data';data.mkdir();shards=data/'research_shards';shards.mkdir()
            old=broker(id='old-history',date='2026-01-01',group_date='2026-01-01',source_kind='broker')
            sync.write_json_atomic(shards/'old.json',{'items':[old]})
            sync.write_json_atomic(data/'research_manifest.json',{'shards':[{'file':'old.json'}]})
            sync.write_json_atomic(data/'reports.json',{'items':[broker()]})
            rows=[row(),row(id='line-new',source='另一券商',ticker='2330',company='台積電',full_text='另一份報告'*80)]
            values=[list(sync.COLUMNS)]+[[r.get(k,'') for k in sync.COLUMNS] for r in rows]
            fixture=root/'sheet.json';fixture.write_text(json.dumps(values))
            transformed=sync.transform(values,[broker()],date(2026,10,25))[0]['items']
            new=next(r for r in transformed if r['ticker']=='2330')
            cache={new['id']:{'status':'success','schema':'broker-v1','stable_key':stable_key(new),'result':{'title':'API 原始標題','summary':['第一段','第二段'],'detail':'完整內文'}}}
            sync.write_json_atomic(data/'research_ai_cache.json',cache)
            paths={'ROOT':root,'BROKER_FILE':data/'reports.json','AUDIT_OUTPUT':data/'research_dedup_audit.json','OUTPUT':data/'line_research.json','PUBLIC_OUTPUT':data/'reports_merged.json'}
            with patch.multiple(sync,**paths),patch.dict(os.environ,{'LINE_SYNC_FIXTURE':str(fixture)},clear=False):
                sync.main();meta=json.loads((data/'research_meta.json').read_text())
                self.assertEqual(len(meta),3)
                self.assertIn('old-history',{r['id'] for r in meta})
                analyzed=next(r for r in meta if r.get('ai_processed'))
                self.assertEqual(analyzed['title'],'API 原始標題');self.assertEqual(analyzed['company'],'台積電')
                self.assertEqual(analyzed['story'],'第一段\n\n第二段')
                before=(data/'research_meta.json').read_bytes();sync.main()
                self.assertEqual(before,(data/'research_meta.json').read_bytes())
