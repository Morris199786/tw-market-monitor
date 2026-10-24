#!/usr/bin/env python3
"""Full-history LINE research integration. No AI calls or Telegram pushes."""
import calendar
import hashlib
import json
import ast
import os
import re
import sys
import unicodedata
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo
from urllib.parse import quote, urlparse, unquote

import requests

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / 'data/line_research.json'
PUBLIC_OUTPUT = ROOT / 'data/reports_merged.json'
AUDIT_OUTPUT = ROOT / 'data/research_dedup_audit.json'
BROKER_FILE = ROOT / 'data/reports.json'
SHEET_ID = os.getenv('LINE_SHEET_ID', '1ujXlmxd7h5lap-Np6saR9i9Dp1V8Q5orgO9Ko1ccISM').strip()
SHEET_TAB = os.getenv('LINE_SHEET_TAB', 'LINE產業研究資料庫').strip()
COLUMNS = ('date','type','source','industry','company','ticker','period','story',
           'revenue','eps','inventory','utilization','guidance','trend','rating_target',
           'numbers','dividend_current','dividend_next','dividend_policy',
           'source_row','full_text','full_text_2','full_text_3')
BROKER_TYPES = {'券商評等', '個股報告', '產業報告'}


def normalize(value):
    return re.sub(r'[^\w\u4e00-\u9fff]', '', unicodedata.normalize('NFKC', str(value or '')).casefold())


def cutoff_date(today):
    y, m = today.year, today.month - 3
    if m <= 0:
        y -= 1
        m += 12
    return date(y, m, min(today.day, calendar.monthrange(y, m)[1]))


def parse_date(value):
    match = re.search(r'(20\d{2})[-/年](\d{1,2})[-/月](\d{1,2})', str(value or ''))
    if not match:
        return None
    try:
        return date(*map(int, match.groups()))
    except ValueError:
        return None


def load_json(path):
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding='utf-8'))


def ticker(value):
    match = re.search(r'(?<!\d)\d{4}(?!\d)', str(value or ''))
    return match.group() if match else ''


BROKER_ALIASES = {
    '國泰': '國泰', '國泰證券': '國泰', '國泰證期': '國泰', '國泰期貨': '國泰',
    '花旗': 'citi', 'citiresearch': 'citi', 'citi': 'citi',
    '大和': 'daiwa', 'daiwa': 'daiwa',
    '中信託': '中信', '中信投顧': '中信', '中國信託': '中信',
    '美銀': 'bofa', 'bofa': 'bofa', 'merrilllynch': 'bofa',
    '凱基': '凱基', '凱基投顧': '凱基', '華南': '華南',
}

def broker_key(value):
    s = normalize(value)
    for alias, canonical in sorted(BROKER_ALIASES.items(), key=lambda x: -len(x[0])):
        if normalize(alias) in s:
            return canonical
    return s

def broker_candidates(row, brokers):
    """Only propose candidates; do not erase distinct reports based on company/date alone."""
    if row['type'] not in BROKER_TYPES:
        return []
    day = parse_date(row['date'])
    stock_code = ticker(row['ticker'])
    company = normalize(row['company'])
    src = broker_key(row['source'])
    matches = []
    for report in brokers:
        report_day = parse_date(report.get('date'))
        if not day or not report_day or abs((day-report_day).days) > 3:
            continue
        same_stock = (stock_code and ticker(report.get('ticker')) == stock_code) or (company and normalize(report.get('name')) == company)
        if not same_stock:
            continue
        target = broker_key(report.get('broker'))
        if not src or not target or (src not in target and target not in src):
            continue
        matches.append({'id': report.get('id'), 'broker': report.get('broker'),
                        'title': report.get('title'), 'date': report.get('date'),
                        'status': 'needs_review'})
    return matches


CATEGORIES = ('個股研究', '產業研究', '法說／訪談', '週報', '市場情報')


def classify(row):
    original = str(row.get('type') or '').strip()
    if original in ('個股報告', '券商評等'):
        return '個股研究'
    if original == '產業報告':
        return '產業研究'
    if original in ('call memo', '法說會'):
        return '法說／訪談'
    if original == '週報':
        return '週報'
    if original in ('小作文', '漲停強勢'):
        return '市場情報'
    if original == '產業訊息':
        text = ' '.join(str(row.get(k) or '') for k in ('source','story','full_text','full_text_2','full_text_3'))[:1500]
        if re.search(r'(?i)(call memo|法說會|電話會議|法說摘要|訪談紀要)', text):
            return '法說／訪談'
        if re.search(r'(?i)(週報|weekly report|weekly update)', text):
            return '週報'
        if re.search(r'(?i)(產業報告|產業研究|sector report|industry report)', text):
            return '產業研究'
        if re.search(r'(?i)(個股報告|公司研究|equity research|company report|券商評等)', text):
            return '個股研究'
    return '市場情報'


def original_date(row):
    # The Sheet date is often the import date. Use a publication date only if
    # the row explicitly labels one; otherwise preserve the sheet date as fallback.
    for key in ('source_row','story','full_text'):
        v = str(row.get(key) or '')[:700]
        m = re.search(r'(?:報告日期|發布日期|出刊日期|研究日期|Report Date|Published)\s*[:：]?\s*(20\d{2}[-/年]\d{1,2}[-/月]\d{1,2})',v,re.I)
        if m:
            d = parse_date(m.group(1))
            if d: return d.isoformat(), 'publication'
    return row['date'], 'sheet'


def clean_display(value):
    """Presentation-only cleanup. Keep the source Excel and numeric values intact."""
    if isinstance(value, (list, tuple)):
        text = '\n'.join(str(x) for x in value if str(x).strip())
    else:
        text = str(value or '')
        stripped = text.strip()
        # Some AI-produced cells are serialized Python/JSON string arrays.
        if stripped.startswith('[') and stripped.endswith(']'):
            try:
                parsed = json.loads(stripped)
            except (ValueError, TypeError):
                try:
                    parsed = ast.literal_eval(stripped)
                except (ValueError, SyntaxError):
                    parsed = None
            if isinstance(parsed, list) and all(isinstance(x, str) for x in parsed):
                text = '\n'.join(x.strip() for x in parsed if x.strip())
    text = text.replace('\r\n', '\n').replace('\r', '\n').replace('\x0c', '\n')
    if text.strip().lower() in ('null', 'none', 'nan'):
        return ''
    text = re.sub(r'【Raw_Inbox\s+row\d+】|【另一來源】', '', text, flags=re.I)
    text = re.sub(r'(?im)^\s*(?:檔案|原始檔)\s*[:：]\s*[^\n]+\.(?:pdf|docx?|pptx?)\s*$', '', text)
    # Remove complete boilerplate/contact lines only, not adjacent research analysis.
    boiler = re.compile(r'(?i)(?:免責聲明|不構成(?:任何)?投資建議|僅供(?:內部|參考)|請勿外傳|禁止轉載|copyright\s*[©\d]|all rights reserved|important disclosures|analyst certification|研究員(?:聯絡|電話|信箱)|聯絡電話|電子郵件|e-?mail\s*[:：]|傳真\s*[:：]|\bfax\s*[:：])')
    lines = []
    for line in text.split('\n'):
        s = line.strip()
        if not s: lines.append(''); continue
        if re.fullmatch(r'\d{1,3}', s): continue
        if re.fullmatch(r'(?:[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}|(?:tel|phone|fax|email|e-mail)\s*[:：].*)',s,re.I): continue
        if boiler.search(s) and (len(s) < 210 or len(s.split()) < 25): continue
        lines.append(s)
    text = '\n'.join(lines)
    # Chinese punctuation: preserve thousands separators and normal English-only prose.
    def punct(line):
        if not re.search(r'[\u3400-\u9fff]',line): return line
        line = re.sub(r'(?<!\d),(?!\d{3}(?:\D|$))', '，', line)
        line = re.sub(r'(?<=\d),(?!\d{3}(?:\D|$))', '，', line)
        return line.replace(';','；').replace('， ', '，')
    text = '\n'.join(punct(x) for x in text.split('\n'))
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


def display_title(row):
    title = str(row.get('company') or row.get('title') or row.get('name') or '').strip()
    code = str(row.get('ticker') or '').strip()
    multi = len(re.findall(r'(?<!\d)\d{4}\.(?:TW|TWO)(?!\w)', title+' '+code,re.I)) >= 3 or '多檔聚合' in title
    if multi:
        topic = str(row.get('period') or row.get('title') or title)
        topic = re.sub(r'[（(]?多檔聚合[）)]?', '', topic)
        topic = re.sub(r'(?:[;；,，\s]*\d{4}\.(?:TW|TWO))+', '', topic, flags=re.I)
        topic = re.sub(r'\s+', ' ', topic).strip(' -|；,，')
        if not topic or re.fullmatch(r'\d{4,8}',topic): topic = '多股研究整理'
        return topic, '', True
    return title, code, False


def is_us_research(row):
    code = str(row.get('ticker') or '').strip().upper()
    if re.search(r'\.(?:US|NYSE|NASDAQ)$', code):
        return True
    if re.fullmatch(r'[A-Z]{1,5}', code) and code not in ('',):
        return True
    return False


def transform(values, brokers, today):
    if not values or not values[0]:
        raise ValueError('Empty sheet; refuse to overwrite existing data')
    items, seen = [], set()
    invalid = identical = 0
    for sheet_row_number, raw in enumerate(values[1:], 2):
        cells = (list(raw) + [''] * len(COLUMNS))[:len(COLUMNS)]
        row = dict(zip(COLUMNS,cells))
        d = parse_date(row['date'])
        if d is None:
            invalid += 1
            continue
        row['date'] = d.isoformat()
        row['sheet_row_number'] = sheet_row_number
        content = json.dumps({k:row[k] for k in COLUMNS},ensure_ascii=False,sort_keys=True)
        digest = hashlib.sha256(content.encode()).hexdigest()
        if digest in seen:
            identical += 1
            continue
        seen.add(digest)
        row['id'] = 'line-' + digest[:20]
        row['original_type'] = row['type']
        row['category'] = classify(row)
        row['date'], row['date_source'] = original_date(row)
        row['source_kind'] = 'line'
        row['market'] = 'US' if is_us_research(row) else 'TW'
        row['display'] = {k: clean_display(row.get(k)) for k in ('story','revenue','eps','inventory','utilization','guidance','trend','rating_target','numbers','dividend_current','dividend_next','dividend_policy','full_text','full_text_2','full_text_3')}
        row['possible_broker_duplicates'] = broker_candidates(row, brokers)
        row['display_title'], row['display_ticker'], row['is_multi_company'] = display_title(row)
        row['unverified'] = row['original_type'] == '小作文'
        items.append(row)
    items.sort(key=lambda r:(r['date'],r['sheet_row_number']),reverse=True)
    return {'count':len(items),'items':items}, {'input_rows':len(values)-1,
        'kept':len(items),'invalid_dates':invalid,'identical_rows_removed':identical,
        'broker_overlap_candidates':sum(bool(r['possible_broker_duplicates']) for r in items)}


def broker_records(brokers):
    result=[]
    for r in brokers:
        item=dict(r)
        item['source_kind']='broker'
        item['market']='US' if is_us_research(item) else 'TW'
        item['display']={'story':clean_display(item.get('summary') or item.get('title') or '')}
        item['category']='產業研究' if r.get('report_type') == 'sector' else '個股研究'
        item['original_type']='券商報告'
        item['display_title'], item['display_ticker'], item['is_multi_company'] = display_title(item)
        item['company']=r.get('name') or ''
        item['source']=r.get('broker') or ''
        item['date']=str(r.get('group_date') or r.get('date') or '')[:10]
        item['date_source']='broker'
        result.append(item)
    return result


def write_json_atomic(path, obj):
    path.parent.mkdir(parents=True,exist_ok=True)
    content=json.dumps(obj,ensure_ascii=False,separators=(',',':'))
    if path.exists() and path.read_text(encoding='utf-8')==content:
        return False
    tmp=path.with_suffix(path.suffix+'.tmp')
    tmp.write_text(content,encoding='utf-8')
    tmp.replace(path)
    return True


def configured_identity():
    """Read only impersonation target; never print credential contents or tokens."""
    expected = os.getenv('LINE_EXPECTED_SERVICE_ACCOUNT', '').strip()
    path = os.getenv('GOOGLE_APPLICATION_CREDENTIALS')
    actual = None
    if path:
        config = json.loads(Path(path).read_text(encoding='utf-8'))
        url = config.get('service_account_impersonation_url', '')
        match = re.search(r'/serviceAccounts/([^/:]+):', unquote(url))
        actual = match.group(1) if match else config.get('client_email')
    if expected and actual and expected != actual:
        raise RuntimeError('SERVICE_ACCOUNT_MISMATCH: workflow 帳號與預期帳號不同；停止讀取')
    print(json.dumps({'service_account': actual or expected or 'not_verified',
                      'identity_verified_from_auth_config': bool(actual),
                      'spreadsheet_id': SHEET_ID}, ensure_ascii=False))


def sheets_get(endpoint, access_token, params):
    resp = requests.get(endpoint, headers={'Authorization': 'Bearer ' + access_token},
                        params=params, timeout=120)
    if resp.ok:
        return resp.json()
    try:
        detail = resp.json().get('error', {})
    except ValueError:
        detail = {}
    reasons = [x.get('reason') for x in detail.get('errors', []) if isinstance(x, dict)]
    reasons += [x.get('reason') for x in detail.get('details', []) if isinstance(x, dict)]
    # Do not print arbitrary server messages: they can include URLs or request data.
    print('GOOGLE_SHEETS_API_ERROR ' + json.dumps({
        'http_status': resp.status_code, 'google_status': detail.get('status'),
        'reasons': reasons, 'spreadsheet_id': SHEET_ID}, ensure_ascii=False), file=sys.stderr)
    if 'SERVICE_DISABLED' in reasons or 'accessNotConfigured' in reasons:
        hint = 'SHEETS_API_DISABLED: 請在服務帳號所屬專案啟用 Google Sheets API'
    elif 'ACCESS_TOKEN_SCOPE_INSUFFICIENT' in reasons or 'insufficientPermissions' in reasons:
        hint = 'TOKEN_SCOPE_INSUFFICIENT: token 缺少 spreadsheets.readonly scope'
    elif resp.status_code == 403:
        hint = ('SHEET_ACCESS_DENIED: 指定服務帳號無法讀取這個試算表 ID。'
                '請核對作者分享的是同一份原始試算表，且分享名單中的完整帳號一致；'
                '若皆一致，需由作者或 Workspace 管理員檢查檔案存取限制。'
                '你的個人帳號權限不會自動套用到服務帳號。')
    elif resp.status_code == 404:
        hint = 'SHEET_NOT_FOUND_OR_HIDDEN: ID 錯誤、檔案不存在或此帳號無權看見'
    elif resp.status_code == 401:
        hint = 'TOKEN_INVALID: 權杖失效，請重新執行 workflow 取得新權杖'
    else:
        hint = 'SHEETS_REQUEST_FAILED: HTTP ' + str(resp.status_code)
    raise RuntimeError(hint)


def fetch_sheet(access_token):
    if not re.fullmatch(r'[A-Za-z0-9_-]+', SHEET_ID):
        raise ValueError('LINE_SHEET_ID 必須填 /d/ 後面的 ID，不是完整網址')
    configured_identity()
    base = f'https://sheets.googleapis.com/v4/spreadsheets/{SHEET_ID}'
    metadata = sheets_get(base, access_token,
                         {'fields': 'spreadsheetId,sheets.properties(title,sheetId)'})
    titles = [x.get('properties', {}).get('title') for x in metadata.get('sheets', [])]
    if SHEET_TAB not in titles:
        raise RuntimeError('SHEET_TAB_NOT_FOUND: 已有讀取檔案權限，但找不到指定分頁；請確認 LINE_SHEET_TAB')
    print('SHEET_ACCESS_OK: 已通過指定試算表及分頁的讀取檢查')
    a1_range = "'" + SHEET_TAB.replace("'", "''") + "'!A1:W"
    result = sheets_get(base + '/values/' + quote(a1_range, safe=''), access_token,
                        {'valueRenderOption': 'FORMATTED_VALUE'})
    return result.get('values', [])


def main():
    today = date.fromisoformat(os.environ['LINE_SYNC_TODAY']) if os.getenv('LINE_SYNC_TODAY') else datetime.now(ZoneInfo('Asia/Taipei')).date()
    fixture = os.getenv('LINE_SYNC_FIXTURE')
    if fixture:
        values = json.loads(Path(fixture).read_text(encoding='utf-8'))
    else:
        token = os.getenv('ACCESS_TOKEN', '').strip()
        if not token:
            sys.exit('ACCESS_TOKEN missing; no output written')
        values = fetch_sheet(token)
    brokers = load_json(BROKER_FILE).get('items', [])
    data, stats = transform(values, brokers, today)
    print(json.dumps(stats, ensure_ascii=False))
    # Full text publication is explicitly authorized by the owner of this website.
    # Keep original broker reports unchanged; broker cards link back to the legacy renderer.
    merged = broker_records(brokers) + data['items']
    merged.sort(key=lambda r:(str(r.get('date') or ''),str(r.get('id') or '')),reverse=True)
    public={'count':len(merged),'line_count':len(data['items']),
            'broker_count':len(brokers),'items':merged}
    audit={'line_count':len(data['items']),'broker_count':len(brokers),
           'exact_line_duplicates':stats['identical_rows_removed'],
           'broker_overlap_candidates':stats['broker_overlap_candidates'],
           'candidates':[{'sheet_row_number':r['sheet_row_number'],'id':r['id'],
             'matches':r['possible_broker_duplicates']} for r in data['items']
             if r['possible_broker_duplicates']],
           'note':'保守去重：只刪除完全相同的 LINE 行；跨來源疑似重複保留並列入核對，避免誤刪不同報告。'}
    if os.getenv('LINE_SYNC_DRY_RUN') == '1':
        print(json.dumps({'merged':len(merged),'line':len(data['items']),
                          'broker':len(brokers),'audit':len(audit['candidates'])},ensure_ascii=False))
        return
    # Bounded-size immutable month shards. No 50MB monolithic browser request.
    from collections import defaultdict
    shards = defaultdict(list)
    for item in merged:
        key = str(item.get('date') or '')[:7]
        if not re.fullmatch(r'20\d{2}-\d{2}', key):
            key = 'unknown'
        shards[key].append(item)
    folder = ROOT / 'data/research_shards'
    folder.mkdir(parents=True, exist_ok=True)
    manifest = {'version': 2, 'count': len(merged), 'line_count': len(data['items']),
                'broker_count': len(brokers), 'shards': [], 'search_buckets': 64}
    live = set()
    from collections import defaultdict as _dd
    search_index = _dd(lambda: _dd(list))
    meta_rows = []
    # Content-addressed names allow safe caching and atomic manifest switch.
    for key in sorted(shards, reverse=True):
        items = shards[key]
        # Each shard capped at 100 records, preventing unbounded monthly files.
        for part in range(0, len(items), 100):
            batch = items[part:part+100]
            raw = json.dumps({'items':batch}, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
            digest = hashlib.sha256(raw).hexdigest()[:12]
            filename = f'{key}-{part//100:03d}-{digest}.json'
            path = folder / filename
            if not path.exists():
                path.write_bytes(raw)
            live.add(filename)
            for offset, record in enumerate(batch):
                rid = str(record.get('id') or f'{filename}:{offset}')
                metadata = {'id':rid, 'file':filename, 'date':str(record.get('date') or '')[:10],
                            'category': '券商報告' if record.get('source_kind') == 'broker' else record.get('category','市場情報'),
                            'company':record.get('display_title') or record.get('company') or record.get('name') or '',
                            'is_multi_company':bool(record.get('is_multi_company')),
                            'title':record.get('title') or record.get('period') or '',
                            'ticker':record.get('display_ticker') if record.get('is_multi_company') else record.get('ticker') or '',
                            'source':record.get('source') or record.get('broker') or '',
                            'story':clean_display(record.get('story') or record.get('summary') or record.get('title') or ''),
                            'market':record.get('market','TW'), 'source_kind':record.get('source_kind','line')}
                meta_rows.append(metadata)
                fields = ('company','name','ticker','stock_id','source','broker','source_name',
                          'summary','story','full_text','full_text_2','full_text_3',
                          'revenue','eps','inventory','utilization','guidance','trend',
                          'numbers','rating_target','title','industry','sector')
                haystack = ' '.join(clean_display(record.get(k)) for k in fields).casefold()
                haystack = re.sub(r'\s+', ' ', haystack)
                # 2-character grams support Chinese names and mixed Chinese/English phrases.
                grams = set(haystack[i:i+2] for i in range(max(0,len(haystack)-1)))
                for gram in grams:
                    bucket = sum((i+1)*ord(ch) for i,ch in enumerate(gram))%64
                    search_index[bucket][gram].append(len(meta_rows)-1)
            manifest['shards'].append({'file': filename, 'month': key, 'count': len(batch),
                                       'bytes': len(raw)})
    # Lightweight metadata (no full texts) and bucketed inverted index.
    write_json_atomic(ROOT / 'data/research_meta.json', meta_rows)
    search_folder = ROOT / 'data/research_search'
    search_folder.mkdir(parents=True,exist_ok=True)
    for bucket in range(64):
        write_json_atomic(search_folder / f'{bucket:02d}.json', search_index[bucket])
    write_json_atomic(ROOT / 'data/research_manifest.json', manifest)
    write_json_atomic(AUDIT_OUTPUT, audit)
    # Clean old content-addressed shards only after new manifest is ready.
    for path in folder.glob('*.json'):
        if path.name not in live:
            path.unlink()
    # Retire giant legacy exports to avoid ever growing the repository on each run.
    for legacy in (OUTPUT, PUBLIC_OUTPUT):
        if legacy.exists():
            legacy.unlink()
    print(f'RESEARCH_SHARDS_OK count={len(merged)} shards={len(manifest["shards"])} '
          f'max_bytes={max((x["bytes"] for x in manifest["shards"]), default=0)}; no AI/Telegram')



if __name__ == '__main__':
    main()

