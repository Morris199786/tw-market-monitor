import copy,json,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch,Mock
from datetime import timedelta
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from sources import TZ,save_json,load_json
from datetime import datetime
import financial_backups as fb
NOW=datetime(2026,11,15,12,tzinfo=TZ)
PERIOD='2026-Q3';URL='https://issuer.example/ir'
ROW={'ticker':'3665','name':'貿聯-KY','period':PERIOD,'publish_date':'2026-11-13','eps':21.93,'gross_margin':None,'prev_period':'2026-Q2','prev_eps':15.28,'prev_gross_margin':30.73,'prev_operating_margin':17.22,'source':'news_backup','publish_time':'14:29:58'}
# Minimal fixture based on the verified issuer release; no production values are hardcoded.
TEXT='貿聯-KY（3665）2026年第3季財務數據。第三季每股稅後盈餘21.93元。產品組合改善，毛利率提升至32.53%。第三季營業利益率20.78%。累計前三季EPS為48.77元。'
def fact(value=20.78,field='operating_margin',kind='company_ir'):
 return dict(value=value,evidence='貿聯-KY 2026年第3季營業利益率20.78%',period=PERIOD,scope='single_quarter',source_type=kind,source_url=URL,document_hash='fixture-sha')
def cache(metrics,ticker='3665'):
 return {'items':{f'{ticker}|{PERIOD}':{'ticker':ticker,'period':PERIOD,'metrics':metrics}}}
class Parsing(unittest.TestCase):
 def test_real_issuer_release_not_chart(self):
  values=fb.values_from_text(TEXT,PERIOD,scoped=True)
  self.assertEqual({k:v['value'] for k,v in values.items()},{'eps':21.93,'gross_margin':32.53,'operating_margin':20.78})
 def test_formal_release_beats_stale_ir_summary(self):
  def fetch(url):
   if url==URL:
    return '<h1>貿聯3665</h1><table><tr><th>指標</th><th>2Q26</th><th>3Q26</th></tr><tr><td>OPM</td><td>17.22%</td><td>20.52%</td></tr></table><a href="/release">3Q26 財報新聞稿</a>'.encode(),'html',url
   return ('<article>'+TEXT+'</article>').encode(),'html',url
  values,notes=fb.discover_issuer(ROW,PERIOD,{'urls':[URL]},fetch)
  self.assertEqual(values['operating_margin']['value'],20.78)
  self.assertIn('lower_priority_source_differs:operating_margin',notes)
 def test_wrong_quarter_rejected(self):self.assertEqual(fb.values_from_text(TEXT,'2026-Q2',scoped=True),{})
 def test_ytd_forecast_segment_not_single_quarter(self):
  for sentence in ['貿聯2026年第3季累計前三季毛利率30.86%。','貿聯2026年第3季預估毛利率40%。','貿聯2026年第3季子公司毛利率40%。','BizLink Q3 2026 expects gross margin of 40%.']:
   self.assertEqual(fb.values_from_text(sentence,PERIOD,scoped=True),{})
 def test_previous_year_not_current_quarter(self):
  s='貿聯2026年第3季財報。2025年第3季毛利率33.25%。'
  self.assertEqual(fb.values_from_text(s,PERIOD,scoped=True),{})
 def test_conflicting_values_not_averaged(self):
  text='貿聯2026年第3季毛利率32.53%。貿聯2026年第3季毛利率30.86%。'
  self.assertNotIn('gross_margin',fb.values_from_text(text,PERIOD,scoped=True))
 def test_html_chart_attributes_ignored(self):
  body=b'<h1>3665 Q3 2026</h1><div data-label="3Q26" data-gross="32.53" data-operating="20.52"></div>'
  self.assertEqual(fb.document_values(body,'html',ROW,PERIOD)[0],{})
 def test_wrong_company_rejected(self):
  body='<h1>2330 2026年第3季毛利率50%</h1>'.encode()
  self.assertEqual(fb.document_values(body,'html',ROW,PERIOD)[0],{})
 def test_exact_quarter_table_column(self):
  table=[[['指標','2Q26','3Q26'],['毛利率','30.73%','32.53%'],['OPM','17.22%','20.78%']]]
  values=fb.values_from_tables(table,PERIOD);self.assertEqual(values['gross_margin']['value'],32.53);self.assertEqual(values['operating_margin']['value'],20.78)
 def test_ytd_table_never_used(self):
  self.assertEqual(fb.values_from_tables([[['指標 累計','3Q26','3Q25'],['毛利率','30.86%','31.65%']]],PERIOD),{})
 def test_no_year_ambiguous_report_rejected(self):self.assertEqual(fb.values_from_text('貿聯第三季毛利率32.53%',PERIOD,scoped=True),{})
 def test_negative_margin_allowed_and_eps_separate(self):
  v=fb.values_from_text('貿聯2026年第3季。第三季營業利益率為-3.5%，EPS為-1.2元。',PERIOD,scoped=True)
  self.assertEqual(v['operating_margin']['value'],-3.5);self.assertEqual(v['eps']['value'],-1.2)
 def test_both_english_quarter_orders(self):
  for q in ['Q3 2026','3Q26','2026-Q3']:
   v=fb.values_from_text(f'BizLink {q} gross margin was 32.53%.',PERIOD)
   self.assertEqual(v['gross_margin']['value'],32.53)
class Recovery(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);(self.root/'data').mkdir();self.rows=[copy.deepcopy(ROW)]
  save_json(self.root/'data'/fb.DIRECTORY,{'updated_at':NOW.isoformat(),'registry_sources':list(fb.REGISTRIES),'issuers':{'3665':{'name':'貿聯-KY','urls':[URL]}}})
 def tearDown(self):self.temp.cleanup()
 def fetch(self,url):
  if url==URL:return ('<h1>貿聯-KY</h1><a href="/release">3Q26 財報新聞稿</a>').encode(),'html',url
  if url=='https://issuer.example/release':return ('<article>'+TEXT+'</article>').encode(),'html',url
  raise RuntimeError('unexpected network '+url)
 def run_backup(self,**kw):return fb.enrich_reports(self.rows,self.root,NOW,fetch=kw.pop('fetch',self.fetch),**kw)
 def test_missing_rates_filled_without_changing_eps_dates_or_previous(self):
  before=copy.deepcopy(self.rows[0]);stats=self.run_backup();after=self.rows[0]
  self.assertEqual(after['gross_margin'],32.53);self.assertEqual(after['operating_margin'],20.78);self.assertEqual(stats['fields_filled'],2)
  for k,v in before.items():
   if k!='gross_margin':self.assertEqual(after[k],v)
  self.assertEqual(after['operating_margin_source']['basis'],'issuer_reported_single')
 def test_complete_record_identical_and_no_network(self):
  self.rows[0].update(gross_margin=32.5,operating_margin=20.7);before=copy.deepcopy(self.rows);fetch=Mock(side_effect=AssertionError('must not fetch'))
  self.run_backup(fetch=fetch);fetch.assert_not_called();self.assertEqual(self.rows,before)
 def test_replay_uses_cache_without_refetch(self):
  self.run_backup();self.rows=[copy.deepcopy(ROW)];fetch=Mock(side_effect=AssertionError('cached'))
  self.run_backup(fetch=fetch);fetch.assert_not_called();self.assertEqual(self.rows[0]['operating_margin'],20.78)
 def test_error_preserves_all_original_fields(self):
  before=copy.deepcopy(self.rows);fetch=Mock(side_effect=TimeoutError('source down'));self.run_backup(fetch=fetch);self.assertEqual(self.rows,before)
 def test_future_and_old_reports_untouched(self):
  self.rows=[dict(ROW,publish_date=d) for d in ['2026-11-16','2026-06-01']];before=copy.deepcopy(self.rows);fetch=Mock(side_effect=AssertionError())
  self.run_backup(fetch=fetch);self.assertEqual(self.rows,before);fetch.assert_not_called()
 def test_official_opm_cache_not_overwritten_by_backup(self):
  save_json(self.root/'data/quarterly_opm.json',{'metrics':{'3665|2026-Q3':{'value':20.79}}})
  self.run_backup();self.assertNotIn('operating_margin',self.rows[0]);self.assertEqual(self.rows[0]['gross_margin'],32.53)
 def test_retry_is_cross_day_and_cooldown_is_bounded(self):
  fetch=Mock(side_effect=TimeoutError());self.run_backup(fetch=fetch);self.assertTrue(fetch.called)
  fetch.reset_mock();self.run_backup(fetch=fetch);fetch.assert_not_called()
  stats=fb.enrich_reports(self.rows,self.root,NOW+timedelta(days=1),fetch=self.fetch)
  self.assertEqual(self.rows[0]['gross_margin'],32.53)
 def test_fresh_report_retries_after_thirty_minutes(self):
  self.run_backup(fetch=Mock(side_effect=TimeoutError()))
  fb.enrich_reports(self.rows,self.root,NOW+timedelta(minutes=31),fetch=self.fetch)
  self.assertEqual(self.rows[0]['gross_margin'],32.53)
 def test_oldest_attempt_gets_turn(self):
  self.rows=[dict(ROW,ticker=str(t),name=str(t)) for t in [3665,3666]]
  save_json(self.root/'data'/fb.CACHE,{'items':{},'attempts':{'3665|2026-Q3':{'at':(NOW-timedelta(hours=7)).isoformat(),'version':fb.VERSION}}})
  self.run_backup(fetch=Mock(side_effect=TimeoutError()),max_companies=1)
  a=load_json(self.root/'data'/fb.CACHE,{})['attempts'];self.assertIn('3666|2026-Q3',a)
class Provenance(unittest.TestCase):
 def test_invalid_or_cross_period_cache_rejected(self):
  for change in [{'source_url':'javascript:alert(1)'},{'scope':'ytd'},{'period':'2026-Q2'},{'value':float('nan')},{'document_hash':''}]:
   self.assertIsNone(fb.cached_metric({**fact(),**change},'operating_margin',PERIOD))
 def test_cross_company_cache_key_rejected(self):
  c=cache({'operating_margin':fact()});c['items']['3665|2026-Q3']['ticker']='2330';self.assertIsNone(fb.backup_opm(c,'3665',PERIOD))
 def test_news_requires_two_families_not_two_udn_domains(self):
  f=fact(kind='news_agreement');f.update(source_url='https://money.udn.com/a',sources=['https://money.udn.com/a','https://udn.com/b'])
  self.assertIsNone(fb.cached_metric(f,'operating_margin',PERIOD))
  f['sources'].append('https://www.cna.com.tw/a');self.assertEqual(fb.cached_metric(f,'operating_margin',PERIOD),20.78)
 def test_opm_official_priority_and_cache_survives_backfill(self):
  import quarterly_opm as opm
  with tempfile.TemporaryDirectory() as td:
   root=Path(td);(root/'data').mkdir();save_json(root/'data'/fb.CACHE,cache({'operating_margin':fact()}))
   official={'ticker':'3665','period':PERIOD,'revenue':100,'operating_profit':21,'source_url':'https://mops.twse.com.tw/x'}
   save_json(root/'data/quarterly_opm.json',{'facts':{'3665|2026-Q3':{'single':official}}})
   with patch.object(opm,'ROOT',root),patch.object(opm,'now_tpe',return_value=NOW),patch.object(opm,'snapshot_facts',return_value=[]):
    a=opm.update_opm(history_rows=[],reports=[ROW],budget=0)
   self.assertEqual(a['metrics']['3665|2026-Q3']['value'],21)
   save_json(root/'data/quarterly_opm.json',{})
   with patch.object(opm,'ROOT',root),patch.object(opm,'now_tpe',return_value=NOW),patch.object(opm,'snapshot_facts',return_value=[]):
    b=opm.update_opm(history_rows=[],reports=[ROW],budget=0)
   self.assertEqual(b['metrics']['3665|2026-Q3']['value'],20.78)
class FinancialNews(unittest.TestCase):
 def article(self,date='2026/11/13',byline='財訊快報／記者測試報導',eps='21.93'):
  return f'<html><h3>貿聯-KY第三季財報數字</h3><div>財訊新聞 {date} 14:27</div><p>【{byline}】貿聯-KY(3665)第三季EPS為{eps}元。累計前三季EPS為48.77元。</p><p>貿聯-KY第三季營收成長。產品組合改善，毛利率提升至32.53%。營益率為20.78%。</p><h2>注目焦點</h2><p>其他公司的毛利率為90%。</p></html>'.encode()
 def test_single_financial_news_article_can_fill_missing_metrics(self):
  v=fb.financial_article(self.article(),'https://www.investor.com.tw/a',ROW,PERIOD,NOW)
  self.assertEqual({k:z['value'] for k,z in v.items()},{'eps':21.93,'gross_margin':32.53,'operating_margin':20.78})
 def test_cumulative_eps_never_confused_with_single(self):
  v=fb.financial_article(self.article(),'https://ww2.money-link.com.tw/a',ROW,PERIOD,NOW)
  self.assertEqual(v['eps']['value'],21.93);self.assertNotEqual(v['eps']['value'],48.77)
 def test_head_title_does_not_hide_article_date(self):
  body=self.article().replace(b'<html>', '<html><head><title>貿聯-KY第三季財報數字</title></head>'.encode())
  self.assertEqual(fb.financial_article(body,'https://www.investor.com.tw/a',ROW,PERIOD,NOW)['eps']['value'],21.93)
 def test_date_company_quarter_and_byline_are_required(self):
  for body,url,period in [(self.article(date='2026/11/16'),'https://www.investor.com.tw/a',PERIOD),(self.article(),'https://www.investor.com.tw/a','2026-Q2'),(self.article(byline='其他網站記者'),'https://www.investor.com.tw/a',PERIOD),(self.article(),'https://random.example/a',PERIOD),(self.article().replace('貿聯'.encode(),'其他公司'.encode()).replace(b'3665',b'2330'),'https://www.investor.com.tw/a',PERIOD)]:
   self.assertEqual(fb.financial_article(body,url,ROW,period,NOW),{})
 def test_search_snippet_is_not_used_as_data(self):
  def fetch(url):
   if 'bing.com' in url:return b'<rss><channel><item><link>https://www.investor.com.tw/a</link><description>EPS 999</description></item></channel></rss>','xml',url
   return self.article(),'html',url
  v,notes=fb.financial_news_fallback(ROW,PERIOD,NOW,fetch)
  self.assertEqual(v['eps']['value'],21.93)
 def test_cached_original_url_avoids_search(self):
  calls=[]
  def fetch(url):
   calls.append(url);return self.article(),'html',url
  url='https://ww2.money-link.com.tw/realtimenews/NewsContent.aspx?SN=example'
  v,notes=fb.financial_news_fallback(ROW,PERIOD,NOW,fetch,[url])
  self.assertEqual(v['gross_margin']['value'],32.53);self.assertEqual(calls,[url])
 def test_company_news_page_discovers_original_article(self):
  def fetch(url):
   if 'StockNews.aspx' in url:return '<a href="/RealtimeNews/NewsContent.aspx?SN=example">貿聯-KY第三季EPS創高</a>'.encode(),'html',url
   if 'bing.com' in url:raise AssertionError('company-news link should suffice')
   return self.article(),'html',url
  v,notes=fb.financial_news_fallback(ROW,PERIOD,NOW,fetch)
  self.assertEqual(v['operating_margin']['value'],20.78);self.assertEqual(notes,[])
 def test_empty_search_logged_instead_of_claiming_no_financial_data(self):
  def fetch(url):return b'<rss><channel/></rss>','html',url
  v,notes=fb.financial_news_fallback(ROW,PERIOD,NOW,fetch)
  self.assertEqual(v,{});self.assertTrue(any('no_search_results:' in n for n in notes))
 def test_validated_financial_news_cache_is_usable(self):
  v=fb.financial_article(self.article(),'https://www.investor.com.tw/a',ROW,PERIOD,NOW)
  c=cache(v);opm=fb.backup_opm(c,'3665',PERIOD)
  self.assertEqual(opm['value'],20.78);self.assertEqual(opm['basis'],'financial_news_reported_single')
 def test_registry_handles_tpex_english_fields(self):
  with tempfile.TemporaryDirectory() as td:
   root=Path(td);(root/'data').mkdir()
   def fetch(url):
    rows=[{'公司代號':'2330','公司簡稱':'台積電','網址':'https://www.tsmc.com'}] if url==fb.REGISTRIES[0] else [{'SecuritiesCompanyCode':'6510','CompanyAbbreviation':'精測','CompanyName':'中華精測','WebAddress':'https://www.chpt.com/\\u3000'}]
    return json.dumps(rows).encode(),'json',url
   issuers=fb.refresh_directory(root,NOW,fetch)
   self.assertIn('6510',issuers);self.assertEqual(issuers['6510']['urls'],['https://www.chpt.com/'])

class NewsRecovery(unittest.TestCase):
 def feed(self,hosts):
  return ('<rss><channel>'+''.join(f'<item><link>https://{host}/article</link><pubDate>Fri, 13 Nov 2026 16:00:00 +0800</pubDate></item>' for host in hosts)+'</channel></rss>').encode()
 def fetcher(self,hosts,values=None,date=None,identical=False,other=False):
  def fetch(url):
   if 'bing.com' in url:return self.feed(hosts),'xml',url
   host=fb.urlparse(url).hostname;v=(values or {}).get(host,'32.53')
   company='其他公司2330' if other else '貿聯3665'
   meta=f'<meta property="article:published_time" content="{date}">' if date else ''
   suffix='' if identical else host
   return f'{meta}<article>{company}2026年第3季毛利率{v}%。{suffix}</article>'.encode(),'html',url
  return fetch
 def test_two_matching_publishers_fill(self):
  hosts=['money.udn.com','www.cna.com.tw'];v,notes=fb.news_fallback(ROW,PERIOD,NOW,self.fetcher(hosts))
  self.assertEqual(v['gross_margin']['value'],32.53);self.assertEqual(len(v['gross_margin']['sources']),2)
 def test_single_publisher_not_enough(self):
  v,notes=fb.news_fallback(ROW,PERIOD,NOW,self.fetcher(['money.udn.com']));self.assertEqual(v,{})
 def test_conflicting_news_not_averaged(self):
  hosts=['money.udn.com','www.cna.com.tw'];v,notes=fb.news_fallback(ROW,PERIOD,NOW,self.fetcher(hosts,{'www.cna.com.tw':'30.86'}))
  self.assertEqual(v,{});self.assertIn('conflicting_news:gross_margin',notes)
 def test_future_articles_ignored(self):
  hosts=['money.udn.com','www.cna.com.tw'];v,notes=fb.news_fallback(ROW,PERIOD,NOW,self.fetcher(hosts,date='2026-11-16T15:00:00+08:00'));self.assertEqual(v,{})
 def test_duplicate_reprints_do_not_form_consensus(self):
  hosts=['money.udn.com','www.cna.com.tw'];v,notes=fb.news_fallback(ROW,PERIOD,NOW,self.fetcher(hosts,identical=True));self.assertEqual(v,{})
 def test_other_company_numbers_rejected(self):
  hosts=['money.udn.com','www.cna.com.tw'];v,notes=fb.news_fallback(ROW,PERIOD,NOW,self.fetcher(hosts,other=True));self.assertEqual(v,{})

class Notifications(unittest.TestCase):
 def test_historical_and_previously_notified_backfills_stay_silent(self):
  import update_quarterly_earnings as earnings
  for published in ['2026-11-13','2026-11-15']:
   with tempfile.TemporaryDirectory() as td:
    root=Path(td);row=dict(ROW,publish_date=published,gross_margin=32.53,operating_margin=20.78)
    sent=root/'sent.json';save_json(sent,{'ids':[f'report|3665|2026-Q3|{published}']})
    with patch.object(earnings,'DATA',root),patch.object(earnings,'SENT',sent),patch.object(earnings,'send_digest',return_value=True) as send:
     earnings.notify_earnings([], [row], NOW, True,[ROW])
    send.assert_not_called()
 def test_new_same_day_release_keeps_existing_notification(self):
  import update_quarterly_earnings as earnings
  with tempfile.TemporaryDirectory() as td:
   root=Path(td);row=dict(ROW,publish_date='2026-11-15',gross_margin=32.53,operating_margin=20.78)
   with patch.object(earnings,'DATA',root),patch.object(earnings,'SENT',root/'sent.json'),patch.object(earnings,'send_digest',return_value=True) as send:
    earnings.notify_earnings([], [row], NOW, True,[])
   self.assertEqual(send.call_count,1);self.assertIn('21.93',send.call_args.args[3][0])
if __name__=='__main__':unittest.main()
