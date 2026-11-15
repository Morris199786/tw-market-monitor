"""Bounded, evidence-preserving recovery of *missing* published quarter fields.

Runs after existing MOPS/news collection. No announcement creation, overwrites,
notifications, AI calls or schedule changes. Official issuer documents first;
Named 財訊快報 actuals or two matching news publishers are a last resort. Never use chart data attributes.
"""
from __future__ import annotations
import argparse,hashlib,html,io,ipaddress,json,math,re,time,unicodedata
from collections import defaultdict
from datetime import datetime,timedelta
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin,urlparse,urlencode
import xml.etree.ElementTree as ET
import requests
from sources import ROOT,TZ,load_json,save_json,now_tpe

VERSION='quarter-missing-fields-v1'
FIELDS=('eps','gross_margin','operating_margin')
CACHE='financial_backups.json'
DIRECTORY='financial_issuer_sites.json'
REGISTRIES=(
 'https://openapi.twse.com.tw/v1/opendata/t187ap03_L',
 'https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap03_O',
)
# Addresses only, never financial values; generic discovery covers other issuers.
SEEDS={'3665':{'name':'貿聯-KY','urls':['https://www.bizlinktech.com/zh-tw/financial-information']}}
LABELS={'eps':r'(?:基本)?每股(?:稅後)?(?:盈餘|純益|損益)|(?<![A-Za-z])EPS(?![A-Za-z])',
 'gross_margin':r'(?:營業)?毛利率|gross\s+(?:profit\s+)?margin',
 'operating_margin':r'營業利益率|營益率|operating\s+(?:profit\s+)?margin|(?<![A-Za-z])OPM(?![A-Za-z])'}
FINANCIAL_NEWS_HOSTS={'www.investor.com.tw','investor.com.tw','ww2.money-link.com.tw','www.money-link.com.tw'}
NEWS_FAMILIES={'money.udn.com':'udn','udn.com':'udn','www.cna.com.tw':'cna','www.moneydj.com':'moneydj',
 'moneydj.com':'moneydj','ww2.money-link.com.tw':'moneylink','www.money-link.com.tw':'moneylink',
 'news.cnyes.com':'cnyes','anuenews.cnyes.com':'cnyes','stock.ltn.com.tw':'ltn',
 'www.ctee.com.tw':'ctee','www.chinatimes.com':'chinatimes'}

def num(x):
 try:
  n=float(str(x).replace(',',''));return n if math.isfinite(n) else None
 except (TypeError,ValueError):return None

def valid_url(url):
 try:
  p=urlparse(str(url));host=p.hostname or ''
  if p.scheme!='https' or not host or p.username or p.password or host=='localhost' or host.endswith('.local'):return False
  try:return ipaddress.ip_address(host).is_global
  except ValueError:return '.' in host and not re.search(r'[\s/\\]',host)
 except ValueError:return False

def normalize(text):
 text=re.sub(r'[ \t\r\f\v]+',' ',unicodedata.normalize('NFKC',html.unescape(str(text))))
 return re.sub(r'(?<=[\u3400-\u9fff])\s+(?=[\u3400-\u9fff])','',text)

def quarter_tokens(text):
 """Recognize explicit quarters; never interpret YTD as a standalone quarter."""
 patterns=[r'(?<!\d)(20\d{2})\s*[- /]?\s*[Qq]([1-4])',r'(?<!\w)([1-4])[Qq]\s*(20\d{2}|\d{2})(?!\d)',
  r'(20\d{2}|1\d{2})\s*年(?:度)?\s*第?\s*([一二三四1-4])\s*季',r'[Qq]([1-4])\s+(20\d{2})(?!\d)']
 out=[]
 for i,pat in enumerate(patterns):
  for m in re.finditer(pat,text):
   a,b=m.groups()
   if i in (1,3):q,y=int(a),int(b);y=y+2000 if y<100 else y
   else:y=int(a);y=y+1911 if y<1911 else y;q=int(b) if b.isdigit() else '一二三四'.index(b)+1
   out.append((m.start(),m.end(),f'{y}-Q{q}'))
 return sorted(out)

class Page(HTMLParser):
 def __init__(self):super().__init__();self.parts=[];self.links=[];self.tables=[];self.rows=[];self.cells=[];self.cell=None;self.skip=0;self.anchor=None;self.meta={};self.heading=None;self.titles=[]
 def handle_starttag(self,tag,attrs):
  a=dict(attrs)
  if tag in ('script','style','noscript','title'):self.skip+=1
  if tag=='meta':self.meta[a.get('property',a.get('name',''))]=a.get('content','')
  if tag=='a':self.anchor=[a.get('href',''),[]]
  if tag in ('h1','h2','h3'):self.heading=[]
  if tag=='table':self.rows=[]
  if tag=='tr':self.cells=[]
  if tag in ('td','th'):self.cell=[]
  if tag in ('p','div','br','li','tr'):self.parts.append('\n')
 def handle_data(self,data):
  if self.skip:return
  self.parts.append(data)
  if self.heading is not None:self.heading.append(data)
  if self.anchor is not None:self.anchor[1].append(data)
  if self.cell is not None:self.cell.append(data)
 def handle_endtag(self,tag):
  if tag in ('script','style','noscript','title'):self.skip=max(0,self.skip-1)
  if tag in ('h1','h2','h3') and self.heading is not None:self.titles.append(normalize(''.join(self.heading)).strip());self.heading=None;self.parts.append('\n')
  if tag=='a' and self.anchor is not None:
   self.links.append((self.anchor[0],normalize(' '.join(self.anchor[1])).strip()));self.anchor=None
  if tag in ('td','th') and self.cell is not None:self.cells.append(normalize(' '.join(self.cell)).strip());self.cell=None;self.parts.append('\t')
  if tag=='tr' and self.cells:self.rows.append(self.cells);self.parts.append('\n')
  if tag=='table' and self.rows:self.tables.append(self.rows);self.rows=[]
 def text(self):return normalize(''.join(self.parts))

def identity(text,row):
 compact=re.sub(r'\s+','',text).casefold();ticker=str(row['ticker'])
 aliases=[str(row.get('name','')).replace('-KY','').rstrip('*')]+list(row.get('aliases',[]))
 return bool(re.search(rf'(?<!\d){re.escape(ticker)}(?!\d)',text) or any(len(a)>=2 and re.sub(r'\s+','',a).casefold() in compact for a in aliases))

def values_from_text(text,period,*,scoped=False):
 """Only actual standalone-quarter narrative; conflicting field values fail closed."""
 text=normalize(text);flat=re.sub(r'\s+',' ',text);year=int(period[:4]);q=int(period[-1]);found=defaultdict(list)
 explicit=quarter_tokens(flat)
 if period not in [p for a,b,p in explicit]:return {}
 for sentence in re.split(r'[。;；]',flat):
  if re.search(r'預估|預期|預測|估計|上看|有望|展望|指引|forecast|guidance|expect(?:s|ed)?|estimat(?:e|es|ed)|project(?:s|ed)|adjusted|調整後',sentence,re.I):continue
  if re.search(r'子公司|事業部|事業群|分部|部門',sentence):continue
  quarters={p for a,b,p in quarter_tokens(sentence)}
  if quarters and quarters!={period}:continue
  years=[int(v) for v in re.findall(r'(20\d{2}|1\d{2})\s*年',sentence)]
  if any(v not in (year,year-1911) for v in years):continue
  # Chinese bare-quarter wording needs the document's explicit year/quarter.
  bare=re.findall(r'第?\s*([一二三四1-4])\s*季',sentence)
  if any((int(v) if v.isdigit() else '一二三四'.index(v)+1)!=q for v in bare):continue
  for field,label in LABELS.items():
   pat=rf'(?:{label})\s*(?:提升至|提高至|增加至|下降至|降至|升至|達到|達|為|約|至|(?:increased|declined|rose|fell|improved|expanded)\s+to|came\s+in\s+at|stood\s+at|of|was|is|:|：)?\s*(?:新[台臺]幣|NT\$|NTD)?\s*([+-]?\d+(?:\.\d+)?)'+(r'\s*%' if field!='eps' else '')
   for m in re.finditer(pat,sentence,re.I):
    context=sentence[max(0,m.start()-100):m.end()+10]
    if re.search(r'累計|前[一二三四1-4]季|上半年|下半年|全年|YTD|year.to.date|first\s+(?:six|nine|three|twelve|\d+)\s+months|1\s*[-~至]\s*(?:6|9|12)\s*月',context,re.I):continue
    if not quarters and not bare and not scoped:continue
    if field=='eps' and (not re.search(r'新[台臺]幣|NT\$|NTD|元',context,re.I) or re.match(r'\s*(?:USD|美元|美金|JPY|日圓)',sentence[m.end():],re.I)):continue
    value=num(m.group(1))
    if value is None or (field!='eps' and not -100<=value<=100) or (field=='eps' and abs(value)>1000):continue
    evidence=sentence[max(0,m.start()-80):min(len(sentence),m.end()+80)].strip()
    found[field].append((value,evidence))
 out={}
 for field,items in found.items():
  vals={round(v,4) for v,e in items}
  if len(vals)==1:out[field]={'value':items[0][0],'evidence':items[0][1],'period':period,'scope':'single_quarter'}
 return out

def values_from_tables(tables,period):
 found=defaultdict(list)
 for rows in tables:
  header=None
  for cells in rows:
   periods=[(i,quarter_tokens(v)) for i,v in enumerate(cells)];matches=[i for i,ps in periods if len(ps)==1 and ps[0][2]==period]
   if len(matches)==1 and sum(bool(ps) for i,ps in periods)>=2:
    quarters={p[-1] for i,ps in periods for a,b,p in ps}
    explicit_single=bool(re.search(r'單季|single.?quarter', ' '.join(cells),re.I)) or len(quarters)>=2
    header=(matches[0],len(cells)) if explicit_single and not re.search(r'累計|YTD|year.to.date', ' '.join(cells),re.I) else None
    continue
   if not header or len(cells)!=header[1]:continue
   label=cells[0];value_cell=cells[header[0]]
   if re.search(r'累計|YTD|預估|forecast|adjusted',label,re.I):continue
   for field,pat in LABELS.items():
    if not re.fullmatch(r'\s*(?:'+pat+r')\s*(?:\(%\)|\(元\))?\s*',label,re.I):continue
    m=re.fullmatch(r'\s*([+-]?\d+(?:\.\d+)?)\s*%?\s*',value_cell)
    if m:
     n=num(m.group(1))
     if n is not None and abs(n)<=(1000 if field=='eps' else 100):found[field].append((n,' | '.join(cells)))
 return {k:{'value':v[0][0],'evidence':v[0][1],'period':period,'scope':'single_quarter'} for k,v in found.items() if len({x for x,e in v})==1}

def document_values(body,kind,row,period,label=''):
 if kind=='pdf':
  from pypdf import PdfReader
  reader=PdfReader(io.BytesIO(body));text='\n'.join(p.extract_text() or '' for p in reader.pages[:12]);page=None
 else:page=Page();page.feed(decode_html(body));text=page.text()
 if not identity(text,row):return {},page
 scoped=period in [p for a,b,p in quarter_tokens(label)] and bool(re.search(r'新聞稿|press|results|earnings|法說|簡報|presentation',label,re.I))
 values=values_from_text(text,period,scoped=scoped)
 if page:
  table=values_from_tables(page.tables,period)
  for field,v in table.items():
   if field in values and abs(values[field]['value']-v['value'])>.02:values.pop(field,None)
   else:values.setdefault(field,v)
 return values,page

class Fetcher:
 def __init__(self,seconds=75):self.deadline=time.monotonic()+seconds;self.session=requests.Session();self.session.headers['User-Agent']='Mozilla/5.0 (Taiwan Market Monitor financial backfill)'
 def __call__(self,url):
  if not valid_url(url):raise ValueError('invalid_source_url')
  remaining=self.deadline-time.monotonic()
  if remaining<1:raise TimeoutError('backup_time_budget')
  with self.session.get(url,timeout=(min(12,remaining),min(20,remaining)),stream=True) as r:
   r.raise_for_status()
   if not valid_url(r.url):raise ValueError('invalid_redirect')
   chunks=[];size=0
   for chunk in r.iter_content(65536):
    size+=len(chunk)
    if size>8_000_000 or time.monotonic()>self.deadline:raise TimeoutError('document_size_or_time_budget')
    chunks.append(chunk)
   body=b''.join(chunks)
   return body,('pdf' if body.startswith(b'%PDF') else 'html'),r.url

def downloadable(url):
 m=re.match(r'https://drive\.google\.com/file/d/([A-Za-z0-9_-]+)/',url)
 return 'https://drive.google.com/uc?'+urlencode({'export':'download','id':m[1]}) if m else url

def refresh_directory(root,now,fetch,*,force=False):
 path=root/'data'/DIRECTORY;old=load_json(path,{})
 try:
  if not force and (now-datetime.fromisoformat(old['updated_at'])).days<7 and set(old.get('registry_sources',[]))>=set(REGISTRIES):return old.get('issuers',{})
 except (ValueError,KeyError,TypeError):pass
 issuers=dict(old.get('issuers',{}));successes=0;registry_sources=[]
 for endpoint in REGISTRIES:
  try:
   body,kind,url=fetch(endpoint)
   records=json.loads(body)
   if not isinstance(records,list) or not records:raise ValueError('empty_directory')
   successes+=1;registry_sources.append(endpoint)
   for item in records:
    t=str(item.get('公司代號',item.get('股票代號',item.get('SecuritiesCompanyCode',''))));site=item.get('網址') or item.get('公司網址') or item.get('公司網站') or item.get('WebAddress')
    if not re.fullmatch(r'\d{4}',t) or not site:continue
    site=re.sub(r'^http:','https:',str(site).replace('\\u3000','').strip())
    if not site.startswith('https://'):site='https://'+site
    if valid_url(site):issuers[t]={**issuers.get(t,{}),'name':item.get('公司簡稱',item.get('公司名稱',item.get('CompanyAbbreviation',t))),'urls':[site],'aliases':[item.get('公司名稱',item.get('CompanyName','')),item.get('英文簡稱',item.get('Symbol',''))],'registry_source':endpoint}
  except Exception:continue
 for t,seed in SEEDS.items():
  entry=issuers.setdefault(t,dict(seed));entry['urls']=list(dict.fromkeys(seed['urls']+entry.get('urls',[])))
 save_json(path,{'version':VERSION,'updated_at':now.isoformat(timespec='seconds') if successes else old.get('updated_at'),'checked_at':now.isoformat(timespec='seconds'),'registry_sources':registry_sources,'issuers':issuers})
 return issuers

def source_priority(kind,label):
 if kind=='pdf' and re.search(r'財務報表|財務報告|financial\s+statements?',label,re.I):return 0
 if re.search(r'新聞稿|press',label,re.I):return 1
 if kind=='pdf':return 2
 return 3

def discover_issuer(row,period,issuer,fetch,required=FIELDS):
 """Follow links published by the registered issuer, not arbitrary guessed URLs."""
 known={urlparse(u).hostname for u in issuer.get('urls',[]) if valid_url(u)};queue=[tuple(item) for item in issuer.get('documents',{}).get(period,[]) if isinstance(item,(list,tuple)) and len(item)==2]+[(u,'') for u in issuer.get('urls',[])];seen=set();documents=[];notes=[]
 while queue and len(seen)<5:
  url,label=queue.pop(0)
  if url in seen or not valid_url(url):continue
  seen.add(url)
  try:
   body,kind,final=fetch(downloadable(url));values,page=document_values(body,kind,{**row,'aliases':issuer.get('aliases',[])},period,label)
   if values:
    documents.append({'priority':source_priority(kind,label),'source_type':'company_ir','source_url':url,'discovery_url':issuer['urls'][0],'document_hash':hashlib.sha256(body).hexdigest(),'metrics':values})
    # A clearly quarter-labelled issuer press release is sufficient evidence.
    # Stop once all missing fields are found instead of crawling unrelated pages.
    if set(required).issubset(values) and re.search(r'新聞稿|press',label,re.I):break
   if page:
    known.add(urlparse(final).hostname)
    links=[]
    for href,title in page.links:
     link=urljoin(final,href)
     if not valid_url(link) or href.startswith('#') or link in seen:continue
     tokens={p for a,b,p in quarter_tokens(title+' '+href)}
     if period in tokens and re.search(r'財報|新聞稿|法說|簡報|results|earnings|presentation|press',title,re.I):
      priority=0 if re.search(r'新聞稿|press',title,re.I) else 1 if re.search(r'簡報|法說|presentation',title,re.I) else 2
      if re.search(r'文字稿|影音|transcript|replay',title,re.I):continue
      links.append((priority,link,title))
     elif urlparse(link).hostname in known and re.search(r'財務|財報|投資人|investor|financial|quarterly|earnings|IR',title+' '+href,re.I):links.append((5,link,title))
    official_links=[(u,l) for priority,u,l in links if priority<5]
    if official_links:issuer.setdefault('documents',{})[period]=official_links
    queue=sorted(links+[(9,u,l) for u,l in queue],key=lambda z:(z[0],z[1]))[:8];queue=[(u,l) for pri,u,l in queue]
  except Exception as exc:notes.append(type(exc).__name__+':'+str(exc)[:120])
 # High-trust document conflicts are field-specific, never averaged.
 merged={}
 for field in FIELDS:
  candidates=[(doc,doc['metrics'][field]) for doc in documents if field in doc['metrics']]
  if candidates:
   best=min(d['priority'] for d,v in candidates)
   primary=[(d,v) for d,v in candidates if d['priority']==best]
   if any(abs(v['value']-primary[0][1]['value'])>.02 for d,v in candidates if d['priority']>best):notes.append('lower_priority_source_differs:'+field)
   candidates=primary
  if candidates and max(v['value'] for d,v in candidates)-min(v['value'] for d,v in candidates)<=.02:
   doc,v=candidates[0];merged[field]={**v,**{k:doc[k] for k in ('source_type','source_url','discovery_url','document_hash')},'source_priority':doc['priority']}
  elif candidates:notes.append('conflicting_issuer_documents:'+field)
 return merged,notes

def decode_html(body):
 m=re.search(br'charset\s*=\s*["\']?([A-Za-z0-9_-]+)',body[:8000],re.I)
 encoding=m[1].decode('ascii').lower() if m else 'utf-8'
 if encoding not in ('utf-8','utf8','big5','cp950','utf-8-sig'):encoding='utf-8'
 return body.decode(encoding,errors='replace')

def financial_article(body,url,row,period,now):
 """Parse a full 財訊快報 article with its own heading, date and reporter byline."""
 if urlparse(url).hostname not in FINANCIAL_NEWS_HOSTS:return {}
 page=Page();page.feed(decode_html(body));text=page.text()
 titles=[page.meta.get('og:title','')]+page.titles
 title=next((t for t in titles if identity(t,row) and len(t)>8),'')
 if not title:return {}
 title=re.sub(r'[_|｜]富聯網.*$','',title).strip();start=text.find(title)
 if start<0:return {}
 content=text[start+len(title):]
 m=re.search(r'(20\d{2})[年/-](\d{1,2})[月/-](\d{1,2})日?\s+(\d{1,2}):(\d{2})',content[:400])
 if not m:return {}
 try:at=datetime(*map(int,m.groups()),tzinfo=TZ)
 except ValueError:return {}
 if not 0<=(now-at).total_seconds()<=120*86400:return {}
 year=int(period[:4]);q=int(period[-1])
 if at.year!=year and not(q==4 and at.year==year+1 and at.month<=4):return {}
 content=re.split(r'注目焦點|推薦排行|點閱排行|你的新聞|網站地圖',content[m.end():])[0]
 if not re.search(r'[【\[]財訊快報[／/]\s*(?:記者|編輯|新聞中心)',content):return {}
 # A standalone quarter must really occur in the article, not only a YTD headline.
 bare=rf'(?<!前)(?:第\s*)?[{q}{"一二三四"[q-1]}]\s*季|Q\s*{q}(?!\d)|{q}Q(?:{str(year)[2:]}|{year})'
 if not re.search(bare,content,re.I):return {}
 found=defaultdict(list)
 for paragraph in re.split(r'\n+',content):
  paragraph=paragraph.strip()
  if not identity(paragraph,row):continue
  other={t for t in re.findall(r'(?<!\d)(\d{4})(?!\d)',paragraph) if t!=str(row['ticker']) and not 1900<=int(t)<=2100}
  if other:continue
  # The date anchors a bare Q3 to its fiscal year; it does not change the text.
  values=values_from_text(period+' '+paragraph,period,scoped=True)
  for field,v in values.items():found[field].append(v)
 out={}
 for field,values in found.items():
  if len({v['value'] for v in values})!=1:continue
  out[field]={**values[0],'source_type':'financial_news','publisher':'財訊快報',
   'source_url':url,'document_hash':hashlib.sha256(body).hexdigest(),'published_at':at.isoformat()}
 return out

def financial_news_fallback(row,period,now,fetch,article_urls=()):
 """Search leads are never facts; a named original full-text report can suffice."""
 found=defaultdict(list);notes=[];seen=set()
 def read_article(url):
  if url in seen or urlparse(url).hostname not in FINANCIAL_NEWS_HOSTS or not valid_url(url):return
  seen.add(url)
  try:
   body,kind,final=fetch(url);values=financial_article(body,final,row,period,now)
   for field,v in values.items():found[field].append(v)
  except Exception as exc:notes.append(type(exc).__name__+':financial_news_article')
 # Previously discovered original URLs avoid dependence on search indexing.
 for url in article_urls[:5]:read_article(url)
 if not found:
  # Publisher's public company-news page, before external search indexes.
  endpoint='https://ww2.money-link.com.tw/TWStock/StockNews.aspx?'+urlencode({'SymId':str(row['ticker'])})
  try:
   body,kind,final=fetch(endpoint);page=Page();page.feed(decode_html(body));leads=[]
   for href,title in page.links:
    if identity(title,row) and re.search(r'財報|EPS|毛利|營益|營業利益|第[一二三四1-4]季|Q[1-4]',title,re.I):
     url=urljoin(final,href)
     if 'newscontent.aspx' in url.lower() and url not in leads:leads.append(url)
   for url in leads[:3]:read_article(url)
  except Exception as exc:notes.append(type(exc).__name__+':financial_news_company_page')
 if not found:
  name=str(row['name']).replace('-KY','').rstrip('*')
  for domain in ('investor.com.tw','money-link.com.tw'):
   query=f'{name} 財訊快報 site:{domain}'
   endpoint='https://www.bing.com/search?'+urlencode({'q':query,'format':'rss'})
   try:body,kind,url=fetch(endpoint);feed=ET.fromstring(body)
   except Exception as exc:notes.append(type(exc).__name__+':financial_news_discovery');continue
   items=feed.findall('.//item')[:5]
   if not items:notes.append('no_search_results:'+domain)
   for item in items:read_article(item.findtext('link') or '')
   if found:break
 out={}
 for field,values in found.items():
  if max(v['value'] for v in values)-min(v['value'] for v in values)<=.02:out[field]=values[0]
  else:notes.append('conflicting_financial_news:'+field)
 return out,notes

def news_fallback(row,period,now,fetch):
 """Full article evidence + date + company + quarter, two publisher families."""
 q=f'{row["ticker"]} {row["name"]} {period[:4]} 第{period[-1]}季 毛利率 營業利益率 財報'
 endpoint='https://www.bing.com/search?'+urlencode({'q':q,'format':'rss'});votes=defaultdict(list);seen=set();notes=[]
 try:body,kind,url=fetch(endpoint);feed=ET.fromstring(body)
 except Exception as exc:return {},[type(exc).__name__+':news_discovery']
 for item in feed.findall('.//item')[:8]:
  url=item.findtext('link') or '';family=NEWS_FAMILIES.get(urlparse(url).hostname)
  if not family or not valid_url(url):continue
  try:
   body,kind,final=fetch(url)
   if NEWS_FAMILIES.get(urlparse(final).hostname)!=family:continue
   values,page=document_values(body,kind,row,period,'')
   if not page:continue
   published=page.meta.get('article:published_time') or page.meta.get('datePublished') or item.findtext('pubDate')
   try:at=datetime.fromisoformat(published.replace('Z','+00:00'))
   except (ValueError,TypeError,AttributeError):at=parsedate_to_datetime(published)
   if at.tzinfo is None:at=at.replace(tzinfo=TZ)
   if not 0<=(now-at).total_seconds()<=120*86400:continue
   bodyhash=hashlib.sha256(page.text().encode()).hexdigest()
   if bodyhash in seen:continue
   seen.add(bodyhash)
   for field,v in values.items():
    if not identity(v['evidence'],row):continue
    votes[field].append((family,{**v,'source_type':'news_agreement','source_url':final,'document_hash':bodyhash,'published_at':at.isoformat()}))
  except Exception as exc:notes.append(type(exc).__name__+':news_article')
 out={}
 for field,items in votes.items():
  if max(v['value'] for f,v in items)-min(v['value'] for f,v in items)>.02:notes.append('conflicting_news:'+field);continue
  if len({f for f,v in items})>=2:
   out[field]={**items[0][1],'sources':list(dict.fromkeys(v['source_url'] for f,v in items))}
 return out,notes

def cached_metric(fact,field,period):
 if not isinstance(fact,dict) or fact.get('scope')!='single_quarter' or fact.get('period')!=period:return None
 value=num(fact.get('value'))
 if value is None or abs(value)>(1000 if field=='eps' else 100):return None
 if fact.get('source_type') not in ('company_ir','financial_news','news_agreement') or not valid_url(fact.get('source_url')) or not fact.get('document_hash') or not fact.get('evidence'):return None
 if fact['source_type']=='financial_news' and (urlparse(fact['source_url']).hostname not in FINANCIAL_NEWS_HOSTS or fact.get('publisher')!='財訊快報' or not fact.get('published_at')):return None
 if fact['source_type']=='news_agreement':
  families={NEWS_FAMILIES.get(urlparse(u).hostname) for u in fact.get('sources',[]) if valid_url(u)}-{None}
  if len(families)<2:return None
 return value

def entry_metrics(cache,ticker,period):
 entry=cache.get('items',{}).get(f'{ticker}|{period}',{})
 return entry.get('metrics',{}) if entry.get('ticker')==str(ticker) and entry.get('period')==period else {}

def backup_opm(cache,ticker,period):
 fact=entry_metrics(cache,ticker,period).get('operating_margin')
 value=cached_metric(fact,'operating_margin',period)
 if value is None:return None
 return {'value':value,'basis':'issuer_reported_single' if fact['source_type']=='company_ir' else 'financial_news_reported_single' if fact['source_type']=='financial_news' else 'news_confirmed_single',
  'sources':fact.get('sources') or [fact['source_url']],'evidence':fact['evidence'],'backup_version':VERSION}

def enrich_reports(reports,root,now,*,fetch=None,max_companies=10,budget_seconds=75,only=None):
 """Mutates only missing fields on existing reports. All failures are isolated."""
 root=Path(root);path=root/'data'/CACHE;cache=load_json(path,{});cache.setdefault('items',{});cache.setdefault('attempts',{})
 opm=load_json(root/'data/quarterly_opm.json',{}).get('metrics',{});targets={};completed=0;errors=[];eligible_rows=[]
 for row in reports:
  try:
   if not re.fullmatch(r'\d{4}',str(row.get('ticker',''))) or (only and str(row['ticker']) not in only):continue
   published=datetime.fromisoformat(row['publish_date']).date()
   if not 0<=(now.date()-published).days<=120:continue
  except (ValueError,KeyError,TypeError):continue
  eligible_rows.append(row)
  for prefix,period in [('',row.get('period')),('prev_',row.get('prev_period'))]:
   if not re.fullmatch(r'20\d{2}-Q[1-4]',str(period)):continue
   key=f'{row["ticker"]}|{period}'
   missing=[f for f in FIELDS if row.get(prefix+f) is None and not (f=='operating_margin' and opm.get(key,{}).get('value') is not None)]
   if missing:targets.setdefault(key,{'row':row,'period':period,'date':published.isoformat(),'fields':set()})['fields'].update(missing)
 fetch=fetch or Fetcher(budget_seconds);issuers=None;attempted=0
 ordered=sorted(targets.items(),key=lambda z:(cache['attempts'].get(z[0],{}).get('at',''),-int(z[1]['date'].replace('-','')),z[0]))
 for key,target in ordered:
  if isinstance(getattr(fetch,'deadline',None),(int,float)) and time.monotonic()>=fetch.deadline-1:break
  entry=cache['items'].get(key,{});metrics=dict(entry_metrics(cache,str(target['row']['ticker']),target['period']));pending=[f for f in target['fields'] if cached_metric(metrics.get(f),f,target['period']) is None]
  if not pending:continue
  previous=cache['attempts'].get(key,{})
  age=(now.date()-datetime.fromisoformat(target['date']).date()).days
  cooldown=1800 if age<=2 else 7200 if age<=14 else 21600
  try:
   if previous.get('version')==VERSION and (now-datetime.fromisoformat(previous['at'])).total_seconds()<cooldown:continue
  except (KeyError,ValueError,TypeError):pass
  if attempted>=max_companies:continue
  attempted+=1;row=target['row'];notes=[]
  try:
   if issuers is None:issuers=refresh_directory(root,now,fetch)
   found={};issuer=issuers.get(str(row['ticker']))
   if issuer:
    deadline=getattr(fetch,'deadline',None)
    try:
     # Keep part of the run budget for news when an issuer's server is slow.
     if isinstance(deadline,(int,float)):fetch.deadline=min(deadline,time.monotonic()+35)
     found,notes=discover_issuer(row,target['period'],issuer,fetch,required=pending)
    finally:
     if isinstance(deadline,(int,float)):fetch.deadline=deadline
   else:notes.append('official_issuer_website_unavailable')
   if any(f not in found and cached_metric(metrics.get(f),f,target['period']) is None for f in pending) and not any('conflicting_issuer' in n for n in notes):
    financial,nn=financial_news_fallback(row,target['period'],now,fetch,(issuer or {}).get('news_documents',{}).get(target['period'],[]));notes+=nn
    if financial and issuer is not None:
     issuer.setdefault('news_documents',{})[target['period']]=list(dict.fromkeys(v['source_url'] for v in financial.values()))
    for f,v in financial.items():found.setdefault(f,v)
    if any(f not in found and cached_metric(metrics.get(f),f,target['period']) is None for f in pending):
     news,nn=news_fallback(row,target['period'],now,fetch);notes+=nn
     for f,v in news.items():found.setdefault(f,v)
   for f,v in found.items():
    if f in pending and cached_metric(v,f,target['period']) is not None:metrics[f]=v
   cache['items'][key]={'ticker':str(row['ticker']),'period':target['period'],'metrics':metrics,'checked_at':now.isoformat(timespec='seconds')}
  except Exception as exc:notes.append(type(exc).__name__+':'+str(exc)[:120])
  remaining=[f for f in target['fields'] if cached_metric(metrics.get(f),f,target['period']) is None]
  cache['attempts'][key]={'at':now.isoformat(timespec='seconds'),'version':VERSION,'status':'pending' if remaining else 'complete','missing':sorted(remaining),'notes':notes[:12]}
  if notes:errors.append({'key':key,'notes':notes[:12]})
 if issuers is not None:
  directory_path=root/'data'/DIRECTORY;directory=load_json(directory_path,{})
  save_json(directory_path,{**directory,'issuers':issuers})
 # Apply only missing values; keep original event dates, source, EPS and statuses.
 for row in eligible_rows:
  changed=False
  for prefix,period in [('',row.get('period')),('prev_',row.get('prev_period'))]:
   metrics=entry_metrics(cache,str(row.get('ticker')),period)
   for field in FIELDS:
    if row.get(prefix+field) is not None:continue
    if field=='operating_margin' and opm.get(f'{row.get("ticker")}|{period}',{}).get('value') is not None:continue
    fact=metrics.get(field);value=cached_metric(fact,field,period)
    if value is None:continue
    row[prefix+field]=value;row[prefix+field+'_backup_source']=fact;completed+=1;changed=True
    if field=='eps':row[prefix+'eps_basis']='issuer_reported_single' if fact['source_type']=='company_ir' else 'news_reported_single'
    if field=='operating_margin':row[prefix+'operating_margin_source']=backup_opm(cache,str(row['ticker']),period)
  if changed:row['data_status']='complete' if all(row.get(k) is not None for k in ('eps','gross_margin','prev_eps','prev_gross_margin')) else 'pending_financial_data'
 cache.update(version=VERSION,updated_at=now.isoformat(timespec='seconds'),last_run={'attempted':attempted,'fields_filled':completed,'targets':len(targets),'errors':errors})
 save_json(path,cache)
 return cache['last_run']

if __name__=='__main__':
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--root',type=Path,default=ROOT);parser.add_argument('--ticker',action='append');parser.add_argument('--budget-seconds',type=int,default=75);args=parser.parse_args()
 path=args.root/'data/quarterly_earnings.json';data=load_json(path,{})
 at=now_tpe()
 result=enrich_reports(data.get('reports',[]),args.root,at,budget_seconds=args.budget_seconds,only=set(args.ticker) if args.ticker else None)
 if result['fields_filled']:data['updated_at']=at.isoformat(timespec='minutes')
 save_json(path,data)
 events_path=args.root/'data/quarterly_earnings_events.json';events=load_json(events_path,{})
 index={(str(r['ticker']),r['period']):r for r in data.get('reports',[])}
 for row in events.get('reports',[]):
  other=index.get((str(row.get('ticker')),row.get('period')),{})
  for field in list(FIELDS)+['prev_'+f for f in FIELDS]:
   if row.get(field) is None and other.get(field) is not None:
    row[field]=other[field]
    for suffix in ('_backup_source','_source'):
     if field+suffix in other:row[field+suffix]=other[field+suffix]
  if all(row.get(k) is not None for k in ('eps','gross_margin','prev_eps','prev_gross_margin')):row['data_status']='complete'
 if events:
  if result['fields_filled']:events['updated_at']=at.isoformat(timespec='minutes')
  save_json(events_path,events)
 print(json.dumps(result,ensure_ascii=False))
