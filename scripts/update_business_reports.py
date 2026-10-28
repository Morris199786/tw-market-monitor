"""業務報告：從 Drive 同步 PDF 索引；從 PDF 首頁擷取報告日期，不使用 AI。"""
import io
import json
import os
import re
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path

import fitz  # PyMuPDF

FOLDER = '1CLtRfuqr9uC_Sak0VSgYdlhogzG8K2ma'
API = 'https://www.googleapis.com/drive/v3/files'
OUTPUT = Path('data/business_reports.json')
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
        d = parse_dates(line)
        if d:
            return d[0], 'pdf'
    # PDF 若沒有可辨識日期，退回檔名；最後才使用 Drive 建立日。
    d = parse_dates(filename)
    if d:
        return d[-1], 'filename'
    return created[:10], 'drive_created'

def identity(filename):
    stem = re.sub(r'\.pdf$', '', filename, flags=re.I)
    broker = next((b for b in BROKERS if stem.startswith(b)), '')
    # 僅 4 碼台股代號；避免把 2026 年份誤認為股票。
    code = re.search(r'(?<!\d)([1-9]\d{3})(?!\d)', stem)
    ticker = code.group(1) if code and not 2000 <= int(code.group(1)) <= 2099 else ''
    company = ''
    if ticker:
        tail = stem[code.end():].lstrip(' -_()（）')
        match = re.match(r'([\u4e00-\u9fffA-Za-z][\u4e00-\u9fffA-Za-z\-KY]*)', tail)
        if match and match.group(1) not in ('takeaway',):
            company = match.group(1)
        if not company:
            before = stem[:code.start()].rstrip(' -_()（）')
            before = before[len(broker):].strip(' -_()（）') if broker else before
            match = re.search(r'([\u4e00-\u9fff]{2,8})$', before)
            if match:
                company = match.group(1)
    return ticker, company, broker

def main():
    old = {}
    if OUTPUT.exists():
        try:
            old = {str(x['id']): x for x in json.loads(OUTPUT.read_text(encoding='utf-8')).get('items', [])}
        except (ValueError, KeyError, TypeError):
            pass
    rows = []
    count_pdf = count_cached = count_fallback = 0
    for f in list_files():
        fid = f['id']
        name = f['name']
        previous = old.get(fid, {})
        modified = f.get('modifiedTime', '')
        ticker, company, broker = identity(name)
        if previous.get('modified_time') == modified and previous.get('filename') == name and previous.get('date_source'):
            dt = previous['date']
            source = previous['date_source']
            count_cached += 1
        else:
            try:
                pdf_text = extract_pdf_text(fid)
                dt, source = report_date(pdf_text, name, f.get('createdTime', ''))
            except Exception as exc:
                print(f'WARNING: PDF {name}: {exc}; fallback to filename/Drive date')
                dt, source = report_date('', name, f.get('createdTime', ''))
            if source == 'pdf':
                count_pdf += 1
            else:
                count_fallback += 1
        rows.append({'id': fid, 'filename': name, 'title': re.sub(r'\.pdf$', '', name, flags=re.I),
                     'date': dt, 'date_source': source, 'ticker': ticker, 'company': company,
                     'broker': broker, 'modified_time': modified,
                     'url': f'https://drive.google.com/file/d/{fid}/view',
                     'preview_url': f'https://drive.google.com/file/d/{fid}/preview'})
    rows.sort(key=lambda r: (r['date'], r['filename']), reverse=True)
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps({'items': rows}, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f'Indexed {len(rows)} PDFs; PDF date={count_pdf}, cached={count_cached}, filename/Drive fallback={count_fallback}. No AI API.')
    for row in rows:
        print(f"{row['date']} [{row['date_source']}] {row['broker']} {row['ticker']} {row['company']} | {row['filename']}")

if __name__ == '__main__':
    main()
