"""業務報告：從 Drive 同步 PDF 索引；優先使用 Gmail 收件日期，不使用 AI。"""
import io
import hashlib
import time
import tempfile
import urllib.error
import json
import os
import re
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo
from pathlib import Path
from functools import lru_cache

import fitz  # PyMuPDF

FOLDER = '1CLtRfuqr9uC_Sak0VSgYdlhogzG8K2ma'
API = 'https://www.googleapis.com/drive/v3/files'
OUTPUT = Path('data/business_reports.json')
TEXT_ROOT = Path(tempfile.mkdtemp(prefix='business-pdf-text-'))
TEXT_SERVICE = os.environ.get('BUSINESS_TEXT_SERVICE_URL', '').rstrip('/')
TEXT_PASSWORD = os.environ.get('MARKET_ASSISTANT_ADMIN_PASSWORD', '')
TEXT_VERSION = 'pdf-text-v1'
MAX_PDF_BYTES = 40 * 1024 * 1024
MAX_PAGES = 300
MAX_CHARACTERS = 500_000

PARSER_VERSION = 'business-v6-company-registry-20261110'
TOKEN = os.environ.get('ACCESS_TOKEN', '')

BROKERS = ('華南投顧', '康和投顧', '凱基', '元大', '永豐', '群益', '富邦', '國泰', '統一', '元富', '第一金', '兆豐', '台新', '中信', '摩根士丹利', '高盛', '瑞銀', '花旗', '大和', '野村', '美銀', '麥格理', '國票', '合庫', '玉山', '華南', '康和')

def request(url, max_bytes=None):
    req = urllib.request.Request(url, headers={'Authorization': 'Bearer ' + TOKEN})
    with urllib.request.urlopen(req, timeout=120) as response:
        if max_bytes and int(response.headers.get('Content-Length', 0)) > max_bytes:
            raise ValueError('PDF exceeds download limit')
        data = response.read(max_bytes + 1) if max_bytes else response.read()
        if max_bytes and len(data) > max_bytes:
            raise ValueError('PDF exceeds download limit')
        return data

def list_files():
    page = None
    while True:
        params = {'q': f"'{FOLDER}' in parents and trashed = false and mimeType = 'application/pdf'",
                  'fields': 'nextPageToken,files(id,name,createdTime,modifiedTime,description,webViewLink,size,md5Checksum)',
                  'pageSize': 1000}
        if page:
            params['pageToken'] = page
        data = json.loads(request(API + '?' + urllib.parse.urlencode(params)))
        yield from data.get('files', [])
        page = data.get('nextPageToken')
        if not page:
            break

def valid(y, m, d):
    try:
        v = date(int(y), int(m), int(d))
        return v.isoformat() if 2010 <= v.year <= 2100 else ''
    except ValueError:
        return ''

def parse_dates(text):
    """依出現順序回傳合法日期，含西元及民國年。"""
    found = []
    patterns = (
        r'(?<!\d)(20\d{2})\s*[-./年_]\s*(\d{1,2})\s*[-./月_]\s*(\d{1,2})\s*日?(?!\d)',
        r'(?<!\d)(20\d{2})(\d{2})(\d{2})(?!\d)',
        r'(?<!\d)(1\d{2})\s*[-./年_]\s*(\d{1,2})\s*[-./月_]\s*(\d{1,2})\s*日?(?!\d)',
        r'(?<!\d)(1\d{2})(\d{2})(\d{2})(?!\d)',
        r'(?<!\d)(\d{2})\s*[-./年_]\s*(\d{1,2})\s*[-./月_]\s*(\d{1,2})\s*日?(?!\d)',
        r'(?<!\d)(\d{2})(\d{2})(\d{2})(?!\d)',
    )
    matches = []
    for idx, pat in enumerate(patterns):
        for m in re.finditer(pat, text):
            y, mo, d = m.groups()
            year = int(y) + (1911 if idx in (2, 3) else 2000 if idx in (4, 5) else 0)
            value = valid(year, mo, d)
            if value:
                matches.append((m.start(), value))
    for _, value in sorted(matches):
        if value not in found:
            found.append(value)
    return found

def extract_pdf_text(file_id):
    raw = request(API + '/' + urllib.parse.quote(file_id, safe='') + '?alt=media')
    if not raw.startswith(b'%PDF-'):
        raise ValueError('下載內容不是 PDF')
    with fitz.open(stream=raw, filetype='pdf') as doc:
        return '\n'.join(doc[i].get_text(sort=True) for i in range(min(2, len(doc))))

def report_date(pdf_text, filename, created):
    # 首頁日期優先；避免抓到報告正文的歷史年份：先尋找「報告日期」附近的日期。
    top = pdf_text[:3500]
    for line in top.splitlines()[:65]:
        if re.search(r'報告日期|出刊日期|研究日期|發布日期|發行日期|Report Date|Publication Date|Date\s*:', line, re.I):
            d = parse_dates(line)
            if d:
                return d[0], 'pdf'
    # 常見報告頁首只有日期，限制在前 20 行，並避免季度預估表的日期。
    for line in top.splitlines()[:20]:
        if re.search(r'預估|forecast|estimate|FY\d|營收|EPS', line, re.I):
            continue
        d = [v for v in parse_dates(line) if 2020 <= int(v[:4]) <= date.today().year + 1 and not re.fullmatch(r'\s*[1-9]\d{5}\s*', line)]
        if d:
            return d[0], 'pdf'
    # PDF 若沒有可辨識日期，退回檔名；最後才使用 Drive 建立日。
    # 檔名中的 300124 等六位數可能是股票代號，不能視為 2030/01/24。
    stem = re.sub(r'\.pdf$', '', filename, flags=re.I)
    d = []
    for m in re.finditer(r'(?<!\d)(?:20\d{6}|1\d{6}|\d{6})(?!\d)', stem):
        raw = m.group()
        if len(raw) == 6 and raw[:2] not in ('25', '26', '27'):
            continue
        for candidate in parse_dates(raw):
            if 2020 <= int(candidate[:4]) <= date.today().year + 1:
                d.append(candidate)
    if d:
        return d[-1], 'filename'
    return created[:10], 'drive_created'

# Fallbacks for filename-only reports; the repository stock catalog extends this map.
COMPANIES = {'2379':'瑞昱','6274':'台燿','3711':'日月光投控','2308':'台達電',
 '1590':'亞德客-KY','8058':'耐特','2303':'聯電','2383':'台光電','7769':'鴻勁',
 '5289':'宜鼎','3037':'欣興','6510':'精測','3081':'聯亞','3105':'穩懋',
 'VRT':'Vertiv','FLEX':'Flex','VFC':'VF Corporation',
 '4438':'廣越','9921':'巨大','8464':'億豐'}

@lru_cache(maxsize=1)
def company_catalog():
    """Resolve all TW stock names from the canonical registry; never infer names from numbers."""
    names = dict(COMPANIES)
    for path in (Path('data/stock_detail.json'), Path('data/report_company_registry.json')):
        if not path.is_file():
            continue
        try:
            data = json.loads(path.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            continue
        stocks = data.get('stocks', {}) if isinstance(data, dict) else {}
        if isinstance(stocks, dict):
            for code, row in stocks.items():
                if isinstance(row, dict) and row.get('name'):
                    names[str(code)] = str(row['name']).strip()
        if path.name == 'report_company_registry.json' and isinstance(data, dict):
            for code, row in data.items():
                if re.fullmatch(r'\d{4,6}', str(code)) and isinstance(row, dict) and row.get('name'):
                    names[str(code)] = str(row['name']).strip()
    return names

YUANTA_TW = re.compile(r'(?<!\w)([1-9]\d{3})\s+TT\s*[-–—]\s*Yuanta\b', re.I)
YUANTA_NAMES = {'2059':'川湖','2395':'研華','6488':'環球晶','4991':'環宇-KY',
                '6805':'富世達','6526':'達發','2454':'聯發科','2301':'光寶科',
                '3443':'創意','2002':'中鋼'}

KGI_FILE = re.compile(r'^(daily[ _-]+story|takeaway)_([0-9]{4}|[A-Z]{1,5})_20\d\d_\d\d_\d\d_[CE](?:_(TW|US))?\.pdf$', re.I)
KGI_NAMES = {'7953':'峻佳裝修','3704':'合勤控','2467':'志聖','6269':'台郡',
             '6515':'穎崴','3533':'嘉澤','3189':'景碩', **YUANTA_NAMES}
KGI_US = {'AAPL':'蘋果 Apple','SNDK':'晟碟 SanDisk','INTC':'英特爾 Intel',
          'VRT':'維諦 Vertiv','FLEX':'偉創力 Flex','VFC':'威富 VF Corporation'}

def identity(filename):
    stem = re.sub(r'\.pdf$', '', filename, flags=re.I)
    broker = next((b for b in BROKERS + ('福邦',) if b in stem), '')
    if stem.startswith('JPM_'):
        broker = 'J.P. Morgan'
    names = company_catalog()
    kgi = KGI_FILE.fullmatch(filename)
    if kgi:
        code = kgi[2].upper()
        if code.isdigit() and (kgi[3] or 'TW').upper() == 'TW':
            return code, names.get(code) or KGI_NAMES.get(code, ''), '凱基投顧'
        if code.isalpha() and (kgi[3] or '').upper() == 'US':
            return code, KGI_US.get(code, names.get(code, code)), '凱基投顧'
    yuanta = YUANTA_TW.search(stem)
    if yuanta:
        code = yuanta.group(1)
        name = names.get(code, '')
        if not re.search(r'[\u3400-\u9fff]', name):
            name = YUANTA_NAMES.get(code) or re.sub(r'\s*\(ID\)\s*$', '', stem[:yuanta.start()].strip(), flags=re.I)
        return code, name, '元大投顧'
    # Remove dates before looking for codes (a year must not hide a later ticker).
    clean = re.sub(r'(?<!\d)20\d{2}[_/.-]\d{1,2}[_/.-]\d{1,2}(?!\d)', '', stem)
    pairs = []
    for m in re.finditer(r'(?<!\d)([1-9]\d{3})(?!\d)', clean):
        code = m.group(1)
        if 2000 <= int(code) <= 2099:
            continue
        name = names.get(code, '')
        if not name:
            tail = clean[m.end():].lstrip(' -_()（）')
            after = re.match(r'([\u4e00-\u9fff]+(?:-KY)?)', tail)
            before = re.search(r'([\u4e00-\u9fff]+(?:-KY)?)\s*[(（]?$', clean[:m.start()])
            name = after.group(1) if after else before.group(1) if before else ''
        pairs.append((code, name))
    # China codes are six digits and carry an explicit company name.
    cn = re.match(r'(\d{6})_([\u4e00-\u9fff]+)_', stem)
    us = re.search(r'daily story_([A-Z]+)_', stem)
    named = re.match(r'(.+?)\s*[(（]([A-Z]+)(?: US)?\s*[)）]', stem)
    if cn:
        pairs = [(cn.group(1), cn.group(2))]
    elif us:
        pairs = [(us.group(1), names.get(us.group(1), us.group(1)))]
    elif named:
        name = re.sub(r'^美股點評\d+-', '', named.group(1)).strip()
        pairs = [(named.group(2), name)]
    elif stem.startswith(('WuXi AppTec_', 'Fosun Pharma_')):
        pairs = [('', stem.split('_')[0])]
    elif stem.startswith('JPM_'):
        for token, name in [('Seagate','Seagate'), ('Guidewire_Software','Guidewire Software'),
                            ('Block_Inc','Block Inc.'), ('American_Tower','American Tower')]:
            if stem.startswith('JPM_' + token + '_'):
                pairs = [('', name)]
                break
    elif 'Bloom Eenergy' in stem:
        pairs = [('', 'Bloom Energy')]
    return ('、'.join(dict.fromkeys(c for c,n in pairs if c)),
            '、'.join(dict.fromkeys(n for c,n in pairs if n)), broker)

def drive_date(created):
    # Never substitute the PDF date or modification time for the received-file date.
    value = datetime.fromisoformat(created.replace('Z', '+00:00'))
    if value.tzinfo is None:
        raise ValueError('Drive createdTime must include timezone')
    return value.astimezone(ZoneInfo('Asia/Taipei')).date().isoformat()

def gmail_date_from_description(description):
    """從 Drive 描述欄讀取 Apps Script 寫入的 Gmail 原始收件日期。"""
    match = re.search(r'^gmail_received_date=(\d{4}-\d{2}-\d{2})\s*$',
                      str(description or ''), flags=re.M)
    if not match:
        return None
    try:
        value = date.fromisoformat(match.group(1))
    except ValueError:
        return None
    return value.isoformat() if 2020 <= value.year <= date.today().year + 1 else None

def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(value, ensure_ascii=False, indent=2) + '\n'
    if path.exists() and path.read_text(encoding='utf-8') == text:
        return
    temp = path.with_suffix('.tmp')
    temp.write_text(text, encoding='utf-8')
    temp.replace(path)


def fingerprint(file):
    return file.get('md5Checksum') or file.get('modifiedTime', '')


def extract_document(file):
    raw = request(API + '/' + urllib.parse.quote(file['id'], safe='') + '?alt=media',
                  max_bytes=MAX_PDF_BYTES)
    if not raw.startswith(b'%PDF-'):
        raise ValueError('Download is not a PDF')
    chunks, empty, chars, truncated = [], [], 0, False
    with fitz.open(stream=raw, filetype='pdf') as doc:
        if doc.needs_pass:
            raise ValueError('PDF requires password')
        pages = len(doc)
        if not pages:
            raise ValueError('PDF has no pages')
        extracted_pages = 0
        for i in range(min(pages, MAX_PAGES)):
            page_text = doc[i].get_text(sort=True).replace('\x00', '').strip()
            extracted_pages += 1
            if not page_text:
                empty.append(i + 1)
            section = f'[第{i + 1}頁]\n{page_text}'
            remaining = MAX_CHARACTERS - chars - (2 if chunks else 0)
            if remaining <= 0:
                truncated = True
                break
            if len(section) > remaining:
                chunks.append(section[:remaining])
                truncated = True
                break
            chunks.append(section)
            chars += len(section) + (2 if len(chunks) > 1 else 0)
        truncated = truncated or extracted_pages < pages
    has_text = any(len(x.split('\n', 1)[-1].strip()) for x in chunks)
    text = '\n\n'.join(chunks) if has_text else ''
    return dict(id=file['id'], source_fingerprint=fingerprint(file),
                modified_time=file.get('modifiedTime', ''), extractor_version=TEXT_VERSION,
                extracted_at=datetime.now(ZoneInfo('Asia/Taipei')).isoformat(timespec='seconds'),
                pdf_sha256=hashlib.sha256(raw).hexdigest(), page_count=pages,
                extracted_pages=extracted_pages, empty_pages=empty, truncated=truncated,
                status=('partial' if empty or truncated else 'ready') if has_text else 'needs_ocr',
                full_text=text, characters=len(text))


def private_store(name, content=None):
    if not TEXT_SERVICE.startswith('https://') or len(TEXT_PASSWORD) < 20:
        raise ValueError('Private PDF store URL and admin secret are required')
    url = TEXT_SERVICE + '/admin/pdf-text?' + urllib.parse.urlencode({'file': name})
    req = urllib.request.Request(url, data=content.encode('utf-8') if content is not None else None,
          method='PUT' if content is not None else 'GET',
          headers={'Authorization': 'Bearer ' + TEXT_PASSWORD, 'Content-Type': 'application/json',
                   'User-Agent': 'tw-market-pdf-text-sync'})
    try:
        with urllib.request.urlopen(req, timeout=90) as response:
            return response.read().decode('utf-8')
    except urllib.error.HTTPError as exc:
        if exc.code == 404 and content is None:
            return None
        raise RuntimeError(f'Private PDF store HTTP {exc.code}') from None


def load_text_cache():
    raw = private_store('index.json')
    if raw is None:
        return {}, {}
    manifest = json.loads(raw)
    records = {}
    write_json(TEXT_ROOT / 'index.json', manifest)
    for name in manifest.get('shards', []):
        if not re.fullmatch(r'[a-f0-9]{64}\.json', name):
            raise ValueError('Invalid text shard name')
        raw = private_store('shards/' + name)
        if raw is None:
            raise ValueError('Private text cache is temporarily incomplete; retry later')
        (TEXT_ROOT / 'shards').mkdir(parents=True, exist_ok=True)
        (TEXT_ROOT / 'shards' / name).write_text(raw, encoding='utf-8')
        records.update({r['id']: r for r in json.loads(raw).get('items', [])})
    return manifest.get('documents', {}), records

def sync_texts(rows, files):
    previous, records = load_text_cache()
    documents = {}
    now = datetime.now(ZoneInfo('Asia/Taipei'))
    # First run backfills newest reports; subsequent runs prioritize newly arrived PDFs.
    max_files = max(1, int(os.environ.get('BUSINESS_TEXT_MAX_FILES', '100')))
    deadline = time.monotonic() + int(os.environ.get('BUSINESS_TEXT_MAX_SECONDS', '900'))
    attempts = 0
    for row in rows:
        fid = row['id']
        source = files[fid]
        old = previous.get(fid, {})
        record = records.get(fid)
        current = bool(record and record.get('source_fingerprint') == fingerprint(source)
                       and record.get('extractor_version') == TEXT_VERSION)
        meta = {k: v for k, v in old.items() if k != 'file'}
        retry = not old.get('retry_after') or now.isoformat() >= old['retry_after']
        if not current and retry and attempts < max_files and time.monotonic() < deadline:
            attempts += 1
            try:
                if int(source.get('size') or 0) > MAX_PDF_BYTES:
                    raise ValueError('PDF exceeds download limit')
                record = extract_document(source)
                records[fid] = record
                current = True
                meta = {}
            except Exception as exc:
                # Never log OAuth tokens, HTTP response bodies or PDF text.
                meta = {'status': 'error', 'error': type(exc).__name__,
                        'retry_after': (now + timedelta(hours=1)).isoformat()}
                print(f'::warning::PDF text extraction failed for {fid} ({type(exc).__name__}); index retained')
        if current:
            meta = {k: record[k] for k in ('status', 'page_count', 'extracted_pages',
                    'empty_pages', 'truncated', 'characters', 'extracted_at', 'source_fingerprint')}
        else:
            # Do not serve stale text after a Drive PDF was replaced.
            if meta.get('status') != 'error':
                meta['status'] = 'pending'
            meta['characters'] = 0
        documents[fid] = meta
        row.update(text_status=meta['status'], has_original_text=current and bool(record.get('full_text')),
                   text_characters=meta.get('characters', 0))
    # Immutable content-addressed shards prevent partial publication from changing old text.
    shards, chunk, size = [], [], 0
    def flush():
        nonlocal chunk, size
        if not chunk:
            return
        content = json.dumps({'items': chunk}, ensure_ascii=False, sort_keys=True) + '\n'
        name = hashlib.sha256(content.encode()).hexdigest() + '.json'
        path = TEXT_ROOT / 'shards' / name
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            private_store('shards/' + name, content)
            path.write_text(content, encoding='utf-8')
        shards.append(name)
        for value in chunk:
            documents[value['id']]['file'] = 'business_report_text/shards/' + name
        chunk, size = [], 0
    for fid in sorted(documents):
        value = records.get(fid)
        if not value or not documents[fid].get('characters'):
            continue
        length = len(value['full_text'])
        if chunk and size + length > 500_000:
            flush()
        chunk.append(value)
        size += length
    flush()
    # Preserve terminal no-text records as well, so scanned PDFs are not downloaded every run.
    terminal = [records[fid] for fid in sorted(documents)
                if fid in records and documents[fid].get('status') == 'needs_ocr']
    for value in terminal:
        chunk.append(value)
        if len(chunk) >= 100:
            flush()
    flush()
    payload = {'schema_version': 1, 'extractor_version': TEXT_VERSION,
               'documents': documents, 'shards': shards}
    old_payload = None
    index_path = TEXT_ROOT / 'index.json'
    if index_path.exists():
        old_payload = json.loads(index_path.read_text(encoding='utf-8'))
        old_payload.pop('updated_at', None)
    if payload != old_payload:
        updated = {**payload, 'updated_at': now.isoformat(timespec='seconds')}
        private_store('index.json', json.dumps(updated, ensure_ascii=False))
        write_json(index_path, updated)
    counts = {}
    for value in documents.values():
        counts[value['status']] = counts.get(value['status'], 0) + 1
    print(f'PDF text: attempted={attempts}, status={counts}; no AI API calls')

def main():
    old = {}
    if OUTPUT.exists():
        try:
            old = {str(x['id']): x for x in json.loads(OUTPUT.read_text(encoding='utf-8')).get('items', [])}
        except (ValueError, KeyError, TypeError):
            pass
    rows = []
    excluded = 0
    drive_files = list(list_files())
    for f in drive_files:
        fid, name = f['id'], f['name']
        if '邀請' in name:
            excluded += 1
            continue
        previous = old.get(fid, {})
        ticker, company, broker = identity(name)
        created = f.get('createdTime', '')
        gmail_date = gmail_date_from_description(f.get('description', ''))
        dt = gmail_date or drive_date(created)
        source = 'gmail_received' if gmail_date else 'drive_created'
        row = {'id': fid, 'filename': name, 'title': (f'{company}（{ticker}）｜個股研究' if YUANTA_TW.search(name) else re.sub(r'\.pdf$', '', name, flags=re.I)),
               'date': dt, 'date_source': source, 'created_time': created,
               'parser_version': PARSER_VERSION, 'ticker': ticker, 'company': company,
               'broker': broker, 'modified_time': f.get('modifiedTime', ''),
               'source_fingerprint': fingerprint(f),
               'url': f'https://drive.google.com/file/d/{fid}/view',
               'preview_url': f'https://drive.google.com/file/d/{fid}/preview'}
        if broker == '凱基投顧' and KGI_FILE.fullmatch(name):
            category = '重點整理' if name.lower().startswith('takeaway') else '個股研究'
            label = f'{company}（{ticker}）' if company and company != ticker else ticker
            row['title'] = f'{label}｜{category}'
        # Preserve previously extracted report dates separately from the grouping date.
        if previous.get('report_date'):
            row['report_date'] = previous['report_date']
        elif previous.get('date_source') in ('pdf', 'filename'):
            row['report_date'] = previous.get('date', '')
        rows.append(row)
    rows.sort(key=lambda r: (r['date'], r['filename']), reverse=True)
    text_error = None
    try:
        sync_texts(rows, {f['id']: f for f in drive_files})
    except Exception as exc:
        text_error = type(exc).__name__
        print(f'::warning::Private PDF text sync unavailable ({text_error}); original PDF index will still publish')
        for row in rows:
            previous = old.get(row['id'], {})
            if previous.get('modified_time') == row.get('modified_time'):
                for key in ('text_status', 'has_original_text', 'text_characters'):
                    if key in previous:
                        row[key] = previous[key]

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps({'items': rows}, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f'Indexed {len(rows)} PDFs; excluded invitations={excluded}. Grouped by Gmail received date when available, otherwise Drive createdTime. No AI API.')
    for row in rows:
        print(f"{row['date']} [{row['date_source']}] {row['broker']} {row['ticker']} {row['company']} | {row['filename']}")
    if text_error:
        raise SystemExit('PDF index updated; private text sync failed. Check Worker deployment and admin secret, then rerun.')

if __name__ == '__main__':
    main()



