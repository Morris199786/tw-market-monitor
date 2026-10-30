"""業務報告：從 Drive 同步 PDF 索引；採 Drive 建檔日（台灣時間）歸類，不使用 AI。"""
import io
import json
import os
import re
import urllib.parse
import urllib.request
from datetime import date, datetime
from zoneinfo import ZoneInfo
from pathlib import Path

import fitz  # PyMuPDF

FOLDER = '1CLtRfuqr9uC_Sak0VSgYdlhogzG8K2ma'
API = 'https://www.googleapis.com/drive/v3/files'
OUTPUT = Path('data/business_reports.json')
PARSER_VERSION = 'business-v4-20261030'
TOKEN = os.environ.get('ACCESS_TOKEN', '')

BROKERS = ('華南投顧', '康和投顧', '凱基', '元大', '永豐', '群益', '富邦', '國泰', '統一', '元富', '第一金', '兆豐', '台新', '中信', '摩根士丹利', '高盛', '瑞銀', '花旗', '大和', '野村', '美銀', '麥格理', '國票', '合庫', '玉山', '華南', '康和')

def request(url):
    req = urllib.request.Request(url, headers={'Authorization': 'Bearer ' + TOKEN})
    with urllib.request.urlopen(req, timeout=120) as response:
        return response.read()

def list_files():
    page = None
    while True:
        params = {'q': f"'{FOLDER}' in parents and trashed = false and mimeType = 'application/pdf'",
                  'fields': 'nextPageToken,files(id,name,createdTime,modifiedTime,description,webViewLink)',
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
 'VRT':'Vertiv','FLEX':'Flex','VFC':'VF Corporation'}

def company_catalog():
    names = dict(COMPANIES)
    path = Path('data/stock_detail.json')
    if path.exists():
        data = json.loads(path.read_text(encoding='utf-8'))
        for code, row in data.get('stocks', {}).items():
            if isinstance(row, dict) and row.get('name'):
                names[str(code)] = row['name']
    return names

def identity(filename):
    stem = re.sub(r'\.pdf$', '', filename, flags=re.I)
    broker = next((b for b in BROKERS + ('福邦',) if b in stem), '')
    if stem.startswith('JPM_'):
        broker = 'J.P. Morgan'
    names = company_catalog()
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

def main():
    old = {}
    if OUTPUT.exists():
        try:
            old = {str(x['id']): x for x in json.loads(OUTPUT.read_text(encoding='utf-8')).get('items', [])}
        except (ValueError, KeyError, TypeError):
            pass
    rows = []
    excluded = 0
    for f in list_files():
        fid, name = f['id'], f['name']
        if '邀請' in name:
            excluded += 1
            continue
        previous = old.get(fid, {})
        ticker, company, broker = identity(name)
        created = f.get('createdTime', '')
        dt = drive_date(created)  # Fail rather than silently write an incorrect date.
        row = {'id': fid, 'filename': name, 'title': re.sub(r'\.pdf$', '', name, flags=re.I),
               'date': dt, 'date_source': 'drive_created', 'created_time': created,
               'parser_version': PARSER_VERSION, 'ticker': ticker, 'company': company,
               'broker': broker, 'modified_time': f.get('modifiedTime', ''),
               'url': f'https://drive.google.com/file/d/{fid}/view',
               'preview_url': f'https://drive.google.com/file/d/{fid}/preview'}
        # Preserve previously extracted report dates separately from the grouping date.
        if previous.get('report_date'):
            row['report_date'] = previous['report_date']
        elif previous.get('date_source') in ('pdf', 'filename'):
            row['report_date'] = previous.get('date', '')
        rows.append(row)
    rows.sort(key=lambda r: (r['date'], r['filename']), reverse=True)
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps({'items': rows}, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f'Indexed {len(rows)} PDFs; excluded invitations={excluded}. Grouped by Drive createdTime (Asia/Taipei). No AI API.')
    for row in rows:
        print(f"{row['date']} [{row['date_source']}] {row['broker']} {row['ticker']} {row['company']} | {row['filename']}")

if __name__ == '__main__':
    main()

