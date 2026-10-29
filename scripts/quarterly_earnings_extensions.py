"""Additive official-format recovery and today's scheduled-company news discovery.
No AI, Telegram calls, hardcoded financial results or changes to existing history.
"""
import html
import re
import unicodedata
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from html.parser import HTMLParser
from urllib.parse import urlencode, urlparse
from zoneinfo import ZoneInfo

TZ = ZoneInfo('Asia/Taipei')

def cumulative_period(text):
    m = re.search(r'(20\d{2}|1\d{2})\s*年(?:度)?\s*前\s*([一二三四1234])\s*季', text)
    if not m: return ''
    y = int(m[1]); q = int(m[2]) if m[2].isdigit() else '一二三四'.index(m[2])+1
    return f'{y+1911 if y<1911 else y}-Q{q}'

def cumulative_table(text, period):
    """Current-year YTD first, prior-year YTD second. Return YTD, never Q3 EPS."""
    text = unicodedata.normalize('NFKC', text)
    y, q = int(period[:4]), int(period[-1]); z = '一二三四'[q-1]
    header = rf'(?:{y}|{y-1911})年(?:度)?前(?:{q}|{z})季\s+(?:{y-1}|{y-1912})年(?:度)?前(?:{q}|{z})季'
    m = re.search(header, text)
    if not m or not re.search(r'單位\s*[:：]?\s*新[台臺]幣[千仟]元', text): return {}
    body = text[m.end():]
    out = {}
    for key, label in [('cum_eps',r'基本每股盈餘\s*\(元\)'),('cum_revenue',r'營業收入'),('cum_gross',r'營業毛利')]:
        hit = re.search(label+r'\s+([+-]?[\d,]+(?:\.\d+)?)\s+([+-]?[\d,]+(?:\.\d+)?)',body)
        if hit: out[key]=float(hit[1].replace(',',''))
    return out

def narrative_metrics(text, period):
    """Explicit quarter narrative, including 季度 / NT$ / 單季每股稅後盈餘."""
    text=unicodedata.normalize('NFKC',html.unescape(text)); y,q=int(period[:4]),int(period[-1])
    quarter=rf'(?:第\s*)?(?:{q}|{"一二三四"[q-1]})\s*季(?:度)?'
    found={'eps':set(),'gross_margin':set()}
    for sentence in re.split(r'[。\n]',text):
        if not re.search(quarter,sentence): continue
        if re.search(r'子公司|貢獻.*每股|事業部|部門|產品線|分部|稅前每股|調整後',sentence): continue
        if re.search(r'前\s*[一二三四1234]\s*季|累計|上半年|下半年|去年第|前年|預估|預期|預測|上看|有望|指引|展望',sentence): continue
        years=[int(a) for a in re.findall(r'(20\d{2}|1\d{2})年',sentence)]
        if any(a not in (y,y-1911) for a in years): continue
        quarters=re.findall(r'第?\s*([一二三四1234])\s*季(?:度)?',sentence)
        if any((int(a) if a.isdigit() else '一二三四'.index(a)+1)!=q for a in quarters): continue
        for key,label in [('eps',r'(?:單季)?(?:基本)?每股(?:稅後)?(?:盈餘|純益)|EPS'),('gross_margin',r'(?:合併)?毛利率')]:
            pattern=rf'(?:{label})\s*(?:為|達|降至|升至|:|：)?\s*(?:NT\$|新[台臺]幣)?\s*([+-]?\d+(?:\.\d+)?)'+(r'\s*%' if key=='gross_margin' else '')
            for hit in re.finditer(pattern,sentence,re.I):
                value=float(hit[1])
                if key!='gross_margin' or -100<=value<=100: found[key].add(value)
    return {k:next(iter(v)) for k,v in found.items() if len(v)==1}

class NewsHTML(HTMLParser):
    def __init__(self):
        super().__init__(); self.parts=[];self.skip=0;self.meta={};self.heading=False;self.titles=[]
    def handle_starttag(self,tag,attrs):
        a=dict(attrs)
        if tag in ('script','style'): self.skip+=1
        if tag=='meta': self.meta[a.get('property',a.get('name',''))]=a.get('content','')
        if tag in ('h1','h2','h3'): self.heading=True
        if tag in ('p','br','div','h1','h2','h3'): self.parts.append('\n')
    def handle_endtag(self,tag):
        if tag in ('script','style'): self.skip=max(0,self.skip-1)
        if tag in ('h1','h2','h3'): self.heading=False
        if tag in ('p','div'): self.parts.append('\n')
    def handle_data(self,data):
        if not self.skip:
            self.parts.append(data)
            if self.heading:self.titles.append(data.strip())

def moneylink_article(page,url,today):
    """Read the publisher article, not a search snippet or AI overview."""
    p=NewsHTML();p.feed(page)
    title=p.meta.get('og:title') or next((x for x in p.titles if len(x)>8),'')
    title=re.sub(r'[_|｜]富聯網.*$', '', title).strip()
    text=' '.join(''.join(p.parts).split())
    start=text.find(title)
    if start<0:return None
    text=text[start+len(title):]
    # The article's date must immediately follow its heading/publisher.
    m=re.search(r'(20\d{2})[/-](\d{1,2})[/-](\d{1,2})\s+(\d{1,2}):(\d{2})',text[:250])
    if not m:return None
    dt=datetime(*map(int,m.groups()),tzinfo=TZ)
    if dt.date().isoformat()!=today:return None
    body=re.split(r'注目焦點|推薦排行|點閱排行|你的新聞|網站地圖',text[m.end():])[0].strip()
    if len(body)<40:return None
    return dict(title=title,description=body,url=url,publisher='富聯網',published_at=dt.isoformat())

def scheduled_news(planned,events,stocks,now,session,parse_article,errors):
    """Only today's roster with missing current-quarter EPS or margin; fail isolated."""
    today=now.astimezone(TZ).date().isoformat();targets={}
    for row in planned:
        if row.get('planned_date')!=today:continue
        key=(str(row.get('ticker','')),row.get('period',''))
        if key[0] not in stocks or not re.fullmatch(r'20\d{2}-Q[1-4]',key[1]):continue
        old=events.get(key,{})
        if old.get('eps') is not None and old.get('gross_margin') is not None:continue
        targets[key]=row
    found={};seen=set()
    for key,row in targets.items():
        name=stocks[key[0]].get('name',row.get('name','')).rstrip('*')
        candidates=[]
        for query in (f'"{name}" 財訊快報 site:money-link.com.tw',f'"{name}" 財報 site:money-link.com.tw'):
            try:
                response=session.get('https://www.bing.com/search?'+urlencode({'q':query,'format':'rss'}),timeout=(5,12));response.raise_for_status()
                feed=ET.fromstring(response.content)
                for item in feed.findall('.//item')[:4]:
                    url=item.findtext('link') or ''
                    if urlparse(url).hostname not in ('ww2.money-link.com.tw','www.money-link.com.tw'):continue
                    if '/realtimenews/NewsContent.aspx' not in url:continue
                    if (key,url) in seen:continue
                    seen.add((key,url))
                    res=session.get(url,timeout=(5,12));res.raise_for_status();res.encoding='utf-8'
                    article=moneylink_article(res.text,url,today)
                    if not article:continue
                    published=datetime.fromisoformat(article['published_at'])
                    if published>now.astimezone(TZ):continue
                    # Existing strict parser remains authoritative. Add sentence-level
                    # compression only for an explicit quarter and metric in that sentence.
                    rows,_=parse_article(article,stocks)
                    scoped='。'.join(sentence for sentence in re.split(r'[。\n]',article['description'])
                        if not any(t!=key[0] and len(stock.get('name',''))>=2 and stock['name'] in sentence
                                   for t,stock in stocks.items()))
                    extra=narrative_metrics(scoped,key[1])
                    if extra:
                        short=[]
                        for field,label in [('eps','每股盈餘'),('gross_margin','毛利率')]:
                            if field in extra: short.append(f"{key[1][:4]}年第{key[1][-1]}季{label}{extra[field]}"+('%' if field=='gross_margin' else '元'))
                        extra_article={**article,'description':'。'.join(short)}
                        extra_rows,_=parse_article(extra_article,stocks)
                        for x in extra_rows:
                            x['evidence']=article['description']
                            if x.get('gross_margin') is not None:
                                x['gross_margin_evidence']=article['description']
                                x['gross_margin_source']['gross_margin_evidence']=article['description']
                            rows.append(x)
                    candidates.extend(x for x in rows if (x.get('ticker'),x.get('period'))==key and x.get('kind')=='quarterly')
            except Exception as exc:errors.append('scheduled_news/'+key[0]+':'+type(exc).__name__)
        if not candidates:continue
        result=dict(candidates[0]); result['eps']=None;result.pop('gross_margin',None)
        for field in ('eps','gross_margin'):
            vals={x[field] for x in candidates if x.get(field) is not None}
            if len(vals)==1:
                source=next(x for x in candidates if x.get(field) is not None)
                result[field]=source[field]
                if field=='gross_margin':
                    for k in ('gross_margin_source','gross_margin_validation','gross_margin_evidence'):result[k]=source.get(k)
                else:
                    for k in ('source_url','source_label','evidence','eps_basis'):result[k]=source.get(k)
            elif len(vals)>1:errors.append('scheduled_news/'+key[0]+'/'+field+':conflict')
        if result.get('eps') is not None or result.get('gross_margin') is not None:found[key]=result
    return found
