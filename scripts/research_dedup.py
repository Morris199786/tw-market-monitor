"""Conservative, shared duplicate decisions for billing and publication."""
import hashlib
import re
import unicodedata
from datetime import date

TEXT_FIELDS = ('full_text', 'full_text_2', 'full_text_3')
ALIASES = {
 '國泰':'國泰','cathay':'國泰',
 'citiresearch':'citi','花旗':'citi','citigroup':'citi',
 'morganstanley':'ms','摩根士丹利':'ms','大摩':'ms',
 'jpmorgan':'jpm','摩根大通':'jpm','小摩':'jpm',
 'bankofamerica':'bofa','美銀':'bofa','merrilllynch':'bofa',
 'goldmansachs':'gs','高盛':'gs','瑞銀':'ubs','瑞士銀行':'ubs',
 '大和':'daiwa','中國信託':'中信','中信投顧':'中信','中信託':'中信',
}

def norm(s):
    if isinstance(s,list): s=' '.join(map(str,s))
    return re.sub(r'[^\w\u3400-\u9fff]', '', unicodedata.normalize('NFKC',str(s or '')).casefold())

def multi_broker_source(value):
    """A broker roundup is NOT an individual brokerage report."""
    raw = unicodedata.normalize('NFKC', str(value or ''))
    if re.search(r'多家(?:券商|投顧)|(?:券商|機構)(?:彙整|綜合|整理)|(?:multiple|various)\s+brokers?', raw, re.I):
        return True
    # Source like '凱基/統一/元富' or '國泰、瑞銀'; do not split ordinary English names.
    head = re.split(r'[（(]', raw)[0].strip()
    return bool(re.search(r'[/／、，,;+＋]', head))

def broker_name(s):
    if multi_broker_source(s): return ''
    s=norm(re.split(r'[（(]',str(s or ''))[0])
    for alias,target in sorted(ALIASES.items(),key=lambda x:-len(x[0])):
        if alias in s: return target
    return re.sub(r'(?:securities|research|證券|投顧|證期)$','',s)

def codes(row):
    value=str(row.get('ticker') or row.get('stock_id') or '').upper()
    value=re.sub(r'\.(?:TWO|TW|US)\b','',value)
    return {x for x in re.split(r'[;；,，\s]+',value) if re.fullmatch(r'(?:\d{4,6}|[A-Z]{1,5})',x)}


def source_ids(row):
    values=[row.get(k,'') for k in ('source_row','source_url','drive_url')]
    result=set()
    for value in values:
        result.update(re.findall(r'(?:/d/|[?&]id=)([A-Za-z0-9_-]{15,})',str(value)))
    for k in ('source_file_id','drive_file_id'):
        if row.get(k): result.add(str(row[k]))
    if row.get('source_kind')=='broker' and row.get('id'): result.add(str(row['id']))
    return result

def text(row):
    return '\n'.join(str(row.get(k) or '') for k in TEXT_FIELDS) or ''

def body_norm(value):
    # Preserve signs, decimal points and units: 1.5 must not equal 15.
    return re.sub(r'\s+', '', unicodedata.normalize('NFKC', str(value or '')).casefold())

def digest(value):
    return hashlib.sha256(body_norm(value).encode()).hexdigest()

def content_key(row):
    body=text(row).strip() or '\n'.join(str(row.get(k) or '') for k in
        ('story','revenue','eps','guidance','trend','rating_target','numbers'))
    return digest(body) if len(norm(body)) >= 80 else ''

def stable_key(row):
    # Legacy key retained to prevent charging again after narrative edits.
    return '|'.join(re.sub(r'\s+','',str(row.get(k) or '')).casefold() for k in
                    ('date','original_type','source','company','ticker','period'))

def dedicated(row):
    """Only single-company analyst research; sector/multi-stock reports are excluded."""
    typ = row.get('original_type') or row.get('report_type') or ''
    if typ not in ('個股報告', '券商評等', 'company'):
        return False
    if row.get('is_multi_company') or multi_broker_source(row.get('source') or row.get('broker')):
        return False
    # A roundup sometimes has only one ticker despite containing multiple brokers.
    if re.search(r'多家券商|券商彙整|綜合評等', str(row.get('company') or '') + ' ' + str(row.get('title') or '')):
        return False
    c = codes(row)
    return len(c) == 1 and bool(re.fullmatch(r'\d{4,6}', next(iter(c))))


def same_dedicated(row, other, days=3):
    if not dedicated(row) or not dedicated(other):
        return False
    a = broker_name(row.get('source') or row.get('broker'))
    b = broker_name(other.get('source') or other.get('broker'))
    if not a or a != b or codes(row) != codes(other):
        return False
    try:
        da = date.fromisoformat(str(row.get('date') or '')[:10])
        db = date.fromisoformat(str(other.get('report_date') or other.get('date') or '')[:10])
    except ValueError:
        return False
    return abs((da - db).days) <= days


def evidence(row, broker):
    """A positive match suppresses the Excel copy, never the original broker."""
    if row.get('original_type') not in ('個股報告','產業報告','券商評等'): return ''
    if multi_broker_source(row.get('source')): return ''
    ids=source_ids(row)
    if len(ids)==1 and ids & source_ids(broker): return 'same_source_file_id'
    a=row['_body'] if '_body' in row else body_norm(text(row))
    b=broker['_body'] if '_body' in broker else body_norm(broker.get('text') or text(broker))
    if len(a)>=300 and a==b: return 'identical_original_text'
    if same_dedicated(row, broker): return 'same_broker_stock_within_3_days'
    if not candidate(row,broker): return ''
    # Require substantial bidirectional overlap; one company mentioned in a
    # multi-company report or a small summary is not proof of identical reports.
    if min(len(a),len(b))>=500 and min(len(a),len(b))/max(len(a),len(b))>=.8:
        sa={a[i:i+24] for i in range(0,len(a)-23,12)}
        sb={b[i:i+24] for i in range(0,len(b)-23,12)}
        # Offset-independent membership to tolerate PDF whitespace differences.
        if sum(x in b for x in sa)/len(sa)>=.9 and sum(x in a for x in sb)/len(sb)>=.9:
            return 'same_original_text_90pct'
    return ''

def candidate(row,broker):
    try:
        day=date.fromisoformat(str(row['date'])[:10])
        dates=[date.fromisoformat(str(broker[k])[:10]) for k in ('date','group_date') if broker.get(k)]
    except (ValueError,KeyError): return False
    if not dates or min(abs((day-d).days) for d in dates)>3: return False
    a=broker_name(row.get('source')); b=broker_name(broker.get('broker'))
    if not a or not b or a!=b: return False
    ca,cb=codes(row),codes(broker)
    if ca and cb: return ca==cb
    if row.get('original_type')=='產業報告' and broker.get('report_type') in ('sector','theme'):
        return True  # Review only: topic equivalence is not assumed.
    return bool(norm(row.get('company')) and norm(row.get('company'))==norm(broker.get('name')))

class Matcher:
    def __init__(self, brokers, inbox=()):
        self.brokers=[]
        inbox_by_id={str(x.get('drive_file_id')):x for x in inbox}
        for b in brokers:
            r=dict(b,source_kind='broker')
            original=inbox_by_id.get(str(b.get('source_file_id') or b.get('id')), {})
            r['text']=original.get('text') or b.get('text') or text(b)
            r['_body']=body_norm(r['text'])
            self.brokers.append(r)
        completed={str(b.get('source_file_id') or b.get('id')) for b in brokers}
        self.pending=[dict(x,id=x.get('drive_file_id'),source_file_id=x.get('drive_file_id'))
                      for x in inbox if str(x.get('drive_file_id')) not in completed]
    def decide(self,row):
        row=dict(row,_body=body_norm(text(row)))
        matches=[(b,evidence(row,b)) for b in self.brokers]
        matches=[(b,e) for b,e in matches if e]
        if len(matches)==1:
            b,e=matches[0]
            return {'status':'broker_duplicate','broker_report_id':str(b['id']),'evidence':e}
        if len(matches)>1:
            return {'status':'needs_review','reason':'multiple_broker_matches',
                    'broker_ids':[str(b['id']) for b,_ in matches]}
        for b in self.pending:
            if (source_ids(row) & source_ids(b)) or (len(norm(text(row)))>=300 and norm(text(row))==norm(b.get('text'))):
                return {'status':'needs_review','reason':'broker_inbox_pending','broker_ids':[str(b['id'])]}
        # Single-stock reports are already matched above with a 3-day window.
        # Preserve conservative fallback for non-dedicated reports.
        same=[]
        for b in self.brokers:
            if row.get('original_type') not in ('個股報告','券商評等') or not candidate(row,b) or b.get('report_type')!='company': continue
            ca,cb=codes(row),codes(b)
            if len(ca)!=1 or ca!=cb: continue
            day=date.fromisoformat(row['date'])
            dates=[date.fromisoformat(str(b[k])[:10]) for k in ('date','group_date') if b.get(k)]
            if min(abs((day-d).days) for d in dates)<=2: same.append(b)
        if len(same)==1:
            return {'status':'broker_duplicate','broker_report_id':str(same[0]['id']),
                    'evidence':'unique_broker_company_within_2_days'}
        candidates=[str(b['id']) for b in self.brokers if candidate(row,b)]
        return {'status':'needs_review','reason':'possible_broker_duplicate','broker_ids':candidates} if candidates else {'status':'new'}


def excel_document_key(row):
    """Only an explicit document filename + same broker/stock, not vague date."""
    raw='\n'.join(str(row.get(k) or '')[:1500] for k in ('source_row','story','full_text','full_text_2'))
    names=re.findall(r'(?im)(?:原始檔(?:名)?|檔案(?:名稱)?|filename|file name)\s*[:：]\s*([^\n\r|]{3,180}?\.(?:pdf|docx?|pptx?))',raw)
    if not names: return ''
    name=norm(names[0].strip().replace('\\','/').split('/')[-1])
    broker=broker_name(row.get('source'))
    code=','.join(sorted(codes(row))) or norm(row.get('company'))
    return f'{broker}|{code}|{name}' if broker and code and name else ''

def _price(row):
    s='\n'.join(str(row.get(k) or '') for k in ('rating_target','story','numbers'))
    matches=re.findall(r'(?:目標價|target\s*price|\bTP\b)\s*[:：]?\s*(?:\d+(?:\.\d+)?\s*(?:→|->|至|調升至|調降至)\s*)?(\d+(?:\.\d+)?)',s,re.I)
    return float(matches[0]) if matches else None

def _annual_eps(row):
    s='\n'.join(str(row.get(k) or '') for k in ('eps','numbers','story'))
    pairs=re.findall(r'(?<!\d)(20\d{2})\s*(?:年|E|F|預估|預測)?\s*(?:EPS|每股盈餘)?\s*[:：=]?\s*(\d{1,3}\.\d{1,2})(?!\d)',s,re.I)
    pairs+=re.findall(r'(?:EPS|每股盈餘)\s*(?:預估)?\s*(20\d{2})\s*[:：=]?\s*(\d{1,3}\.\d{1,2})(?!\d)',s,re.I)
    return {(int(y),float(v)) for y,v in pairs}

def excel_rating_duplicate(report,rating):
    """Cross-type duplicate only when stock, broker, date, target and annual EPS agree."""
    if report.get('original_type')!='個股報告' or rating.get('original_type')!='券商評等': return False
    if multi_broker_source(report.get('source')) or multi_broker_source(rating.get('source')): return False
    a,b=broker_name(report.get('source')),broker_name(rating.get('source'))
    if not a or a!=b: return False
    ca,cb=codes(report),codes(rating)
    if len(ca)!=1 or ca!=cb: return False
    try:
        da=date.fromisoformat(str(report['date'])[:10]); db=date.fromisoformat(str(rating['date'])[:10])
    except (ValueError,KeyError): return False
    if abs((da-db).days)>3: return False
    if same_dedicated(report,rating): return True
    pa,pb=_price(report),_price(rating)
    if pa is None or pb is None or abs(pa-pb)>.01: return False
    if _annual_eps(report) & _annual_eps(rating): return True
    # Some Sheet rows show '2026/2027 EPS 3.95/3.99' without per-year labels.
    # Require TWO matching decimal EPS figures to avoid accidental merging.
    def eps_values(row):
        raw=str(row.get('eps') or '')
        return {float(v) for v in re.findall(r'(?<!\d)\d{1,2}\.\d{1,2}(?!\d)',raw)}
    return len(eps_values(report) & eps_values(rating))>=2
