"""Conservative public RSS EPS fallback. No API keys, AI, or notifications."""
import calendar
from decimal import Decimal, ROUND_HALF_UP
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
PARSER_VERSION = 'single-period-v10-verified-q3-margin-and-h1-guard'
MARGIN_VALIDATION = 'actual-margin-v1'


def read(path, default):
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return default


def plain(value):
    return re.sub(r'\s+', ' ', html.unescape(re.sub(r'<[^>]+>', ' ', value or ''))).strip()


def compatible_rounding(a, b):
    """Compare only at the precision actually carried by both values."""
    da, db = Decimal(str(a)), Decimal(str(b))
    places = min(max(0, -da.as_tuple().exponent), max(0, -db.as_tuple().exponent))
    unit = Decimal(1).scaleb(-places)
    return da.quantize(unit, rounding=ROUND_HALF_UP) == db.quantize(unit, rounding=ROUND_HALF_UP)


def more_precise(a, b):
    return max((a, b), key=lambda v: max(0, -Decimal(str(v)).as_tuple().exponent))


def margin_is_estimate(text, match):
    """Bind forecast cues to this metric, not to a later-quarter outlook."""
    left = max([text.rfind(mark, 0, match.start()) for mark in ('。', '；', ';', '!', '！', '?', '？', '\n')] + [-1]) + 1
    prefix = text[left:match.start('value')]
    # Realised results may beat estimates; these phrases do not make them forecasts.
    prefix = re.sub(r'(?:優於|高於|低於|超越|超出|符合|不如)(?:市場|法人|公司|原先|先前)?(?:預估|預期|預測)', '', prefix)
    # An explicit actual-result marker starts a new attribution scope.
    markers = list(re.finditer(r'實際(?:公布)?|實績(?:為)?|公布(?:財報|財務報告|業績)', prefix))
    if markers:
        prefix = prefix[markers[-1].end():]
    if re.search(r'預估|預期|預測|估計|估算|推估|估\s*|財測|指引|展望|上看|有望|可望|料將|預料|目標|挑戰|預計|預告|預覽|將達|將至|有機會|假設|forecast|guidance|estimate|expected', prefix, re.I):
        return True
    # Trailing attribution e.g. "67.5%（法人預估）", without rejecting
    # "66.4%，預估Q4..." following a complete actual-result statement.
    tail = text[match.end():match.end()+45]
    if re.match(r'\s*(?:[（(][^）)]{0,20}(?:估|財測|指引|目標|forecast)|(?:為|屬於|係|是).{0,8}(?:預估|預測|財測|指引))', tail, re.I):
        return True
    if re.match(r'\s*(?:[-~～至到]|以上|以下|左右|附近|上下)', tail):
        return True
    return False


def sanitize_news_margin(row):
    """Legacy RSS margins were not screened for bare 估; revalidate by refetching.

    Preserve EPS and all official fields. Only this news-margin cache is invalidated.
    """
    out = dict(row)
    if out.get('gross_margin_validation') != MARGIN_VALIDATION or out.get('margin_conflict'):
        for key in ('gross_margin', 'gross_margin_evidence', 'gross_margin_validation', 'gross_margin_source'):
            out.pop(key, None)
    return out


# Verified 2026-Q3 actual margins. These are fallback values only; official
# financial-statement data always takes precedence in the earnings updater.
# Keep the source and period attached so a future quarter cannot reuse them.
VERIFIED_Q3_MARGINS = {
    ('2330', '2026-Q3'): (66.4, '台積電第三季財報新聞稿', 'https://pr.tsmc.com/chinese/news/3346'),
    ('2408', '2026-Q3'): (85.7, '南亞科第三季財報新聞稿', 'https://www.nanya.com/tw/IR/16/%E6%96%B0%E8%81%9E%E7%A8%BF?IRId=14188'),
    ('2402', '2026-Q3'): (14.0, '毅嘉第三季自結公告（約14%）', 'https://www.moneydj.com/kmdj/news/newsviewer.aspx?a=3ca57a7d-563c-4241-90a3-9de6a3dcd312'),
    ('7747', '2026-Q3'): (15.9, '昕奇雲端第三季獲利報導', 'https://ieknet.iek.org.tw/ieknews/news_open.aspx?nsl_id=612bd12b363e4f0ca14d3bc2ab4d78a3'),
}


def verified_margin(ticker, period):
    """Return a source-labelled verified historical margin, or None."""
    item = VERIFIED_Q3_MARGINS.get((str(ticker), str(period)))
    if item is None:
        return None
    value, label, url = item
    return {'gross_margin': value, 'gross_margin_validation': MARGIN_VALIDATION,
            'gross_margin_source': {'source_label': label, 'source_url': url,
                                    'gross_margin_evidence': '2026 Q3 已公布實際毛利率'}}


def invalid_quarterly_news(row):
    """Known H1 EPS wrongly attributed to a Q3 earnings-call headline."""
    return (str(row.get('ticker')) == '7689' and row.get('period') == '2026-Q3'
            and (row.get('source') == 'news_backup' or row.get('kind') == 'quarterly')
            and bool(re.search(r'上半年|前二季|前兩季|H1|半年EPS',
                               str(row.get('subject', '')) + ' ' + str(row.get('evidence', '')), re.I)))


def parse_article(article, stocks):
    title = unicodedata.normalize('NFKC', plain(article.get('title')))
    title = re.sub(r'\s+-\s+[^\n]+$', '', title)
    description = unicodedata.normalize('NFKC', plain(article.get('description')))
    description = description.replace(article.get('publisher') or '\0', '')
    text = title + '。' + description
    # Longest name wins only within the same text span: 南亞科 is not 南亞;
    # a separate mention of 南亞 elsewhere still makes the story ambiguous.
    spans = [(m.start(), m.end(), t) for t, stock in stocks.items()
             if len(stock.get('name', '')) >= 2
             for m in re.finditer(re.escape(stock['name']), title)]
    named = {t for start, end, t in spans if not any(
        a <= start and end <= b and b-a > end-start for a,b,_ in spans)}
    coded = {t for t in stocks if re.search(r'[(（]\s*'+re.escape(t)+r'\s*[)）]|^'+re.escape(t)+r'\s', title)}
    identities = [(t, stocks[t]) for t in named | coded]
    if len(identities) != 1:
        return [], 'ambiguous_company'
    ticker, company = identities[0]
    other_companies = [t for t,s in stocks.items() if t != ticker and
        ((len(s.get('name','')) >= 2 and s['name'] in text) or re.search(r'[(（]'+re.escape(t)+r'[)）]', text))]
    # Other companies in the summary do not invalidate a title that uniquely
    # identifies the reporting issuer; extracted values still need a period.
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
        r'(?P<context>[^。；;!?！？]{0,75}?)'
        r'(?P<label>EPS|每股盈餘|每股純益|每股稅後盈餘|每股稅後|每股大賺|每股賺|每股虧損|每股虧)'
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
    # Reject a Q3 headline that actually reports first-half EPS.
    found = {key: row for key, row in found.items() if not invalid_quarterly_news(row)}
    # A separate margin pass: a story may report gross margin without EPS.
    # A quarter reference must precede the value in the same short clause.
    margin_pattern = re.compile(
        r'(?:(?P<year>20\d{2}|1\d{2})\s*年\s*)?'
        r'(?P<period>第\s*[一二三四1234]\s*季|[一二三四]\s*季|Q[1-4])'
        r'(?P<context>[^。；;!?！？]{0,75}?)'
        r'(?P<label>合併毛利率|單季毛利率|毛利率)'
        r'\s*(?:為|達|約|:|：|衝上|衝至|衝|飆達|飆至|飆|下探|降至|跌至|升至|回升至|提升至)?\s*(?P<value>[+\-−]?\d{1,3}(?:\.\d+)?)\s*[%％]', re.I)
    for match in margin_pattern.finditer(text):
        before = text[max(0, match.start()-18):match.start()]
        context = match.group('context')
        if re.search(r'前\s*$|[\d一二三四]\s*[-~～至]\s*$', before):
            continue
        if margin_is_estimate(text, match):
            continue
        if re.search(r'累計|累積|前\s*[一二三四1234]\s*季|預估|預期|預測|估計|上看|法人估|指引|展望|去年|前年', before+context):
            continue
        if re.search(r'第?\s*[一二三四1234]\s*季|Q[1-4]', context, re.I):
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
        value=float(match.group('value').replace('−','-'))
        if not -100 <= value <= 100: continue
        period=f'{year}-Q{q}'
        key=(ticker,period)
        if key not in found:
            found[key]=dict(ticker=ticker,name=company['name'],market=company.get('market'),
                kind='quarterly',period=period,eps=None,publish_date=published.date().isoformat(),
                publish_time=published.strftime('%H:%M:%S'),subject=title,source='news_backup',
                source_label='新聞備援｜'+article['publisher'],source_url=article['url'],
                evidence=match.group(0),eps_basis=None,
                release_type='quarterly_preliminary' if '自結' in text else 'financial_report')
        if found[key].get('gross_margin') is not None and not compatible_rounding(found[key]['gross_margin'], value):
            found[key]['margin_conflict']=True
        else:
            old_value=found[key].get('gross_margin')
            found[key]['gross_margin']=more_precise(old_value,value) if old_value is not None else value
            found[key]['gross_margin_evidence']=match.group(0)
            found[key]['gross_margin_validation']=MARGIN_VALIDATION
            found[key]['gross_margin_source']={
                'source_url':article['url'], 'source_label':'新聞備援｜'+article['publisher'],
                'gross_margin_evidence':match.group(0), 'subject':title,
                'published_at':article['published_at']}

    for row in found.values():
        if row.pop('margin_conflict',False):
            row.pop('gross_margin',None)
            row.pop('gross_margin_evidence',None)
    return list(found.values()), 'accepted' if found else 'no_unambiguous_single_period_eps'


NEWS_START = '2026-10-01'

def current_items(kind, now=None):
    now = now or datetime.now(TZ)
    data = read(PATH, {})
    return [sanitize_news_margin(x) for x in data.get('items', []) if not invalid_quarterly_news(x) and x.get('kind') == kind
            and NEWS_START <= x.get('publish_date','') <= now.date().isoformat()]


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
    base_queries = [
        '自結 (EPS OR 每股盈餘 OR 每股虧損)',
        '(財報 OR 單季 OR 第三季 OR 第四季 OR Q3 OR Q4) (EPS OR 每股盈餘 OR 每股純益 OR 毛利率)',
        '(第三季 OR Q3) (獲利 OR 毛利率 OR 稅後純益)',
    ]
    # Fixed historical starting date; never search before 2026-10-01.
    queries = []
    start_date = datetime.fromisoformat(NEWS_START).date()
    cursor = start_date
    while cursor <= now.date():
        end = min(cursor + timedelta(days=5), now.date() + timedelta(days=1))
        for base in base_queries:
            queries.append(f'{base} after:{(cursor-timedelta(days=1)).isoformat()} before:{end.isoformat()}')
        cursor = end
    # Known high-value gaps get independent searches rather than competing with
    # hundreds of unrelated earnings headlines for the same RSS result window.
    for ticker in ('2330','2408','3008','3211','6933'):
        name = stocks.get(ticker, {}).get('name','')
        if name:
            queries.append(f'"{name}" (第三季 OR Q3) (EPS OR 每股 OR 毛利率) after:{(start_date-timedelta(days=1)).isoformat()}')
    accepted, audit, seen, errors = {}, [], set(), []
    for query in queries:
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
                # Source domain is not a correctness criterion; article text is.
                try:
                    pub = parsedate_to_datetime(node.findtext('pubDate')).astimezone(TZ)
                except (TypeError, ValueError):
                    continue
                if not datetime.fromisoformat(NEWS_START).date() <= pub.date() <= now.date():
                    continue
                article = dict(title=node.findtext('title'), description=node.findtext('description'),
                    url=link, publisher=source.text or host, published_at=pub.isoformat())
                rows, reason = parse_article(article, stocks)
                audit.append(dict(title=article['title'], url=link, result=reason,
                    published_at=article['published_at'], publisher=article['publisher'],
                    metrics=[{k:row.get(k) for k in ('ticker','period','eps','gross_margin','gross_margin_evidence')} for row in rows]))
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
                        if prior.get('gross_margin') is not None and row.get('gross_margin') is not None and not compatible_rounding(prior['gross_margin'], row['gross_margin']):
                            prior.pop('gross_margin', None)
                            prior.pop('gross_margin_evidence', None)
                            prior['margin_conflict'] = True
                        elif prior.get('gross_margin') is not None and row.get('gross_margin') is not None and not prior.get('margin_conflict'):
                            chosen = more_precise(prior['gross_margin'], row['gross_margin'])
                            if chosen == row['gross_margin']:
                                prior['gross_margin'] = chosen
                                prior['gross_margin_evidence'] = row.get('gross_margin_evidence')
                                prior['gross_margin_validation'] = row.get('gross_margin_validation')
                                prior['gross_margin_source'] = row.get('gross_margin_source')
                        elif prior.get('gross_margin') is None and row.get('gross_margin') is not None and not prior.get('margin_conflict'):
                            prior['gross_margin'] = row['gross_margin']
                            prior['gross_margin_evidence'] = row.get('gross_margin_evidence')
                            prior['gross_margin_validation'] = row.get('gross_margin_validation')
                            prior['gross_margin_source'] = row.get('gross_margin_source')
        except Exception as exc:
            errors.append(type(exc).__name__+': '+str(exc)[:160])
    prior_data = read(PATH, {})
    previous = prior_data.get('items', []) if prior_data.get('parser_version') in ('single-period-v2', 'single-period-v3-contextual-eps', 'single-period-v5-windowed-25days', 'single-period-v7-since-2026-10-01', 'single-period-v8-company-spans-margins', 'single-period-v9-actual-margin-only', PARSER_VERSION) else []
    for cached_row in previous:
        row = sanitize_news_margin(cached_row)
        if NEWS_START <= row.get('publish_date','') <= now.date().isoformat():
            key=(row['ticker'],row['period'])
            if key not in accepted:
                accepted[key]=row
            else:
                for field in ('eps','gross_margin','eps_basis','gross_margin_evidence','gross_margin_validation','gross_margin_source'):
                    if (not accepted[key].get('conflict' if field in ('eps','eps_basis') else 'margin_conflict')
                            and accepted[key].get(field) is None and row.get(field) is not None):
                        accepted[key][field]=row[field]
    items = [x for x in accepted.values() if not x.get('conflict')]
    payload = dict(updated_at=now.isoformat(timespec='minutes'), source='Google News RSS', parser_version=PARSER_VERSION,
        coverage='自2026-10-01起；明確單一公司／單月或單季 EPS、單季毛利率；新聞標題與 RSS 摘要，不保證涵蓋所有公告',
        source_errors=errors, conflict_count=sum(bool(x.get('conflict')) for x in accepted.values()),
        items=items, audit=audit)
    PATH.parent.mkdir(parents=True, exist_ok=True)
    temp = PATH.with_suffix('.tmp')
    temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    temp.replace(PATH)
    print('EPS news backup:', len(items), 'accepted;', len(errors), 'source errors; AI calls=0')


if __name__ == '__main__': collect()


