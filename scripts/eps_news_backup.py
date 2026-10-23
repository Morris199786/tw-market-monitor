"""Conservative public RSS EPS fallback. No API keys, AI, or notifications."""
import calendar
import html
import json
import re
import unicodedata
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import urlencode, urlparse
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / 'data/eps_news_backup.json'
TZ = ZoneInfo('Asia/Taipei')
HOSTS = ('moneydj.com', 'money-link.com.tw', 'cnyes.com', 'udn.com', 'yahoo.com', 'ctee.com.tw')
PARSER_VERSION = 'single-period-v4-margin-25days'


def read(path, default):
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return default


def plain(value):
    return re.sub(r'\s+', ' ', html.unescape(re.sub(r'<[^>]+>', ' ', value or ''))).strip()


def parse_article(article, stocks):
    title = unicodedata.normalize('NFKC', plain(article.get('title')))
    title = re.sub(r'\s+-\s+[^\n]+$', '', title)
    description = unicodedata.normalize('NFKC', plain(article.get('description')))
    description = description.replace(article.get('publisher') or '\0', '')
    text = title + '。' + description
    identities = [(t, s) for t, s in stocks.items() if re.search(r'(?<!\d)' + re.escape(t) + r'(?!\d)', title)
                  or (len(s.get('name', '')) >= 2 and s['name'] in title)]
    if len(identities) != 1:
        return [], 'ambiguous_company'
    ticker, company = identities[0]
    other_companies = [t for t,s in stocks.items() if t != ticker and
        ((len(s.get('name','')) >= 2 and s['name'] in text) or re.search(r'[(（]'+re.escape(t)+r'[)）]', text))]
    if other_companies:
        return [], 'multi_company_article'
    try:
        published = datetime.fromisoformat(article['published_at']).astimezone(TZ)
    except (KeyError, ValueError):
        return [], 'missing_date'

    # Never reject an entire story merely because an unrelated fundraising or
    # price-target sentence contains 上看/預估. Check the EPS clause itself.
    # Do not accept cumulative YTD figures such as 前三季EPS11.16.
    pattern = re.compile(
        r'(?<![\d前累計至\-~～])(?:(?P<year>20\d{2}|1\d{2})\s*年\s*)?'
        r'(?P<period>\d{1,2}\s*月|第\s*[一二三四1234]\s*季|[一二三四]\s*季|Q[1-4])'
        r'(?P<context>[^。；;!?！？]{0,45}?)'
        r'(?P<label>EPS|每股盈餘|每股純益|每股稅後盈餘|每股稅後|每股虧損|每股虧)'
        r'\s*(?:為|達|約|:|：)?\s*(?P<value>[+\-−]?\d+(?:\.\d+)?)\s*元?', re.I)
    found = {}
    for match in pattern.finditer(text):
        context = match.group('context')
        before = text[max(0, match.start()-14):match.start()]
        clause = text[max(0, match.start()-18):match.end()]
        # A report's period must refer to one month/quarter, not cumulative
        # first N quarters, year-to-date or a comparison with prior years.
        if re.search(r'累計|累積|前\s*$|[\d一二三四五六七八九十]\s*[\-~～至]\s*$', before):
            continue
        if re.search(r'累計|累積|前[一二三四五六七八九十\d]+[季月]|稅前|去年|前年|EPS|每股', context, re.I):
            continue
        if re.search(r'預估|預期|預測|估計|有望|挑戰|上看|法人估|調整後|排除.*損益', context):
            continue
        # Forecast terms near the EPS number are disqualifying; unrelated
        # future plans elsewhere in the headline are not.
        if re.search(r'(?:預估|預期|預測|估計|有望|上看|法人估|稅前|調整後)\s*(?:單季|本季|第?[一二三四1234]季|Q[1-4]|EPS|每股)', clause, re.I):
            continue
        raw_period = re.sub(r'\s+', '', match.group('period')).upper()
        year = int(match.group('year')) if match.group('year') else published.year
        if year < 1911:
            year += 1911
        monthly = raw_period.endswith('月')
        if monthly:
            month = int(raw_period[:-1])
            if not 1 <= month <= 12 or '自結' not in text:
                continue
            end_month = month
            period = f'{year}-{month:02d}'
        else:
            number = raw_period[1] if raw_period.startswith('Q') else raw_period.replace('第', '')[:-1]
            quarter = int(number) if number.isdigit() else '一二三四'.index(number)+1
            end_month = quarter*3
            period = f'{year}-Q{quarter}'
        if not match.group('year') and end_month > published.month:
            year -= 1
            period = str(year) + period[4:]
        end = datetime(year, end_month, calendar.monthrange(year,end_month)[1], tzinfo=TZ).date()
        if not 0 <= (published.date()-end).days <= 150:
            continue
        value = float(match.group('value').replace('−', '-'))
        if '虧' in match.group('label'):
            value = -abs(value)
        key = (ticker, period)
        if key in found and found[key]['eps'] != value:
            return [], 'conflicting_values'
        found[key] = dict(ticker=ticker, name=company['name'], market=company.get('market'),
            kind='monthly' if monthly else 'quarterly', period=period, eps=value,
            publish_date=published.date().isoformat(), publish_time=published.strftime('%H:%M:%S'),
            subject=title, source='news_backup', source_label='新聞備援｜'+article['publisher'],
            source_url=article['url'], evidence=match.group(0), eps_basis='news_reported_single',
            release_type='quarterly_preliminary' if '自結' in text else 'financial_report')
    # A separate margin pass: a story may report gross margin without EPS.
    # A quarter reference must precede the value in the same short clause.
    margin_pattern = re.compile(
        r'(?:(?P<year>20\d{2}|1\d{2})\s*年\s*)?'
        r'(?P<period>第\s*[一二三四1234]\s*季|[一二三四]\s*季|Q[1-4])'
        r'(?P<context>[^。；;!?！？]{0,48}?)'
        r'(?P<label>合併毛利率|單季毛利率|毛利率)'
        r'\s*(?:為|達|約|:|：)?\s*(?P<value>\d{1,2}(?:\.\d+)?)\s*[%％]', re.I)
    for match in margin_pattern.finditer(text):
        before = text[max(0, match.start()-18):match.start()]
        context = match.group('context')
        if re.search(r'累計|累積|前\s*[一二三四1234]\s*季|預估|預期|預測|估計|上看|法人估|指引|展望|去年|前年', before+context):
            continue
        raw = re.sub(r'\s+', '', match.group('period')).upper()
        number = raw[1] if raw.startswith('Q') else raw.replace('第', '')[:-1]
        q = int(number) if number.isdigit() else '一二三四'.index(number)+1
        year = int(match.group('year')) if match.group('year') else published.year
        if year < 1911: year += 1911
        if not match.group('year') and q*3 > published.month: year -= 1
        end_month=q*3
        end=datetime(year,end_month,calendar.monthrange(year,end_month)[1],tzinfo=TZ).date()
        if not 0 <= (published.date()-end).days <= 150: continue
        value=float(match.group('value'))
        if not 0 <= value <= 100: continue
        period=f'{year}-Q{q}'
        key=(ticker,period)
        if key not in found:
            found[key]=dict(ticker=ticker,name=company['name'],market=company.get('market'),
                kind='quarterly',period=period,eps=None,publish_date=published.date().isoformat(),
                publish_time=published.strftime('%H:%M:%S'),subject=title,source='news_backup',
                source_label='新聞備援｜'+article['publisher'],source_url=article['url'],
                evidence=match.group(0),eps_basis=None,
                release_type='quarterly_preliminary' if '自結' in text else 'financial_report')
        if found[key].get('gross_margin') is not None and found[key]['gross_margin'] != value:
            found[key]['margin_conflict']=True
        else:
            found[key]['gross_margin']=value
            found[key]['gross_margin_evidence']=match.group(0)
    for row in found.values():
        if row.pop('margin_conflict',False):
            row.pop('gross_margin',None)
            row.pop('gross_margin_evidence',None)
    return list(found.values()), 'accepted' if found else 'no_unambiguous_single_period_eps'


def current_items(kind, now=None):
    now = now or datetime.now(TZ)
    data = read(PATH, {})
    return [x for x in data.get('items', []) if x.get('kind') == kind
            and (now.date()-timedelta(days=25)).isoformat() <= x.get('publish_date','') <= now.date().isoformat()]


def monthly_fallback(official, now=None):
    result = []
    occupied = {(x.get('ticker'), x.get('monthly_period')) for x in official if x.get('monthly_eps') is not None and x.get('source') != 'news_backup'}
    for x in current_items('monthly', now):
        if x.get('eps') is None: continue
        key = (x['ticker'], x['period'])
        if key in occupied:
            continue
        occupied.add(key)
        result.append(dict(x, monthly_period=x['period'], monthly_eps=x['eps'],
            monthly_eps_yoy=None, quarter_period=None, quarter_eps=None, quarter_eps_yoy=None,
            subject='【新聞備援】'+x['subject'], detail=x['evidence'], match_reason='news_backup', eps_parse_status='parsed',
            eps_parse_reason='新聞明確單月稅後EPS；非官方核對資料'))
    return result


def collect():
    now = datetime.now(TZ)
    stocks = read(ROOT/'data/master.json', {}).get('stocks', {})
    if not stocks:
        raise RuntimeError('master.json company registry unavailable')
    queries = ['自結 (EPS OR 每股盈餘 OR 每股虧損)', '(財報 OR 單季 OR 第三季 OR 第四季 OR Q3 OR Q4) (EPS OR 每股盈餘 OR 每股純益 OR 毛利率)']
    accepted, audit, seen, errors = {}, [], set(), []
    for query in queries:
        query += ' when:25d (' + ' OR '.join('site:'+h for h in HOSTS) + ')'
        url = 'https://news.google.com/rss/search?' + urlencode(dict(q=query, hl='zh-TW', gl='TW', ceid='TW:zh-Hant'))
        try:
            req = urllib.request.Request(url, headers={'User-Agent':'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=25) as response:
                root = ET.fromstring(response.read(4_000_000))
            for node in root.findall('.//item')[:100]:
                link = node.findtext('link') or ''
                if link in seen:
                    continue
                seen.add(link)
                source = node.find('source')
                if source is None:
                    continue
                host = (urlparse(source.get('url','')).hostname or '').lower()
                if not any(host == h or host.endswith('.'+h) for h in HOSTS):
                    continue
                try:
                    pub = parsedate_to_datetime(node.findtext('pubDate')).astimezone(TZ)
                except (TypeError, ValueError):
                    continue
                if not now-timedelta(days=25) <= pub <= now+timedelta(minutes=5):
                    continue
                article = dict(title=node.findtext('title'), description=node.findtext('description'),
                    url=link, publisher=source.text or host, published_at=pub.isoformat())
                rows, reason = parse_article(article, stocks)
                audit.append(dict(title=article['title'], url=link, result=reason))
                for row in rows:
                    key = (row['ticker'],row['period'])
                    prior = accepted.get(key)
                    if prior is None:
                        accepted[key] = row
                    else:
                        if prior.get('eps') is not None and row.get('eps') is not None and prior['eps'] != row['eps']:
                            prior['conflict'] = True
                        elif prior.get('eps') is None and row.get('eps') is not None:
                            prior['eps'] = row['eps']
                            prior['eps_basis'] = row.get('eps_basis')
                        if prior.get('gross_margin') is not None and row.get('gross_margin') is not None and prior['gross_margin'] != row['gross_margin']:
                            prior.pop('gross_margin', None)
                            prior.pop('gross_margin_evidence', None)
                            prior['margin_conflict'] = True
                        elif prior.get('gross_margin') is None and row.get('gross_margin') is not None and not prior.get('margin_conflict'):
                            prior['gross_margin'] = row['gross_margin']
                            prior['gross_margin_evidence'] = row.get('gross_margin_evidence')
        except Exception as exc:
            errors.append(type(exc).__name__+': '+str(exc)[:160])
    prior_data = read(PATH, {})
    previous = prior_data.get('items', []) if prior_data.get('parser_version') in ('single-period-v2', 'single-period-v3-contextual-eps', PARSER_VERSION) else []
    for row in previous:
        if (now.date()-timedelta(days=25)).isoformat() <= row.get('publish_date','') <= now.date().isoformat():
            accepted.setdefault((row['ticker'],row['period']), row)
    items = [x for x in accepted.values() if not x.get('conflict')]
    payload = dict(updated_at=now.isoformat(timespec='minutes'), source='Google News RSS', parser_version=PARSER_VERSION,
        coverage='最近25天；明確單一公司／單月或單季 EPS、單季毛利率；新聞標題與 RSS 摘要，不保證涵蓋所有公告',
        source_errors=errors, conflict_count=sum(bool(x.get('conflict')) for x in accepted.values()),
        items=items, audit=audit)
    PATH.parent.mkdir(parents=True, exist_ok=True)
    temp = PATH.with_suffix('.tmp')
    temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    temp.replace(PATH)
    print('EPS news backup:', len(items), 'accepted;', len(errors), 'source errors; AI calls=0')


if __name__ == '__main__': collect()
