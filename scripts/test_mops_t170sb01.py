#!/usr/bin/env python3
"""Isolated MOPS t170sb01 endpoint probe. No production files, APIs or Telegram."""
import argparse
import csv
import io
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

BASES = ('https://mops.twse.com.tw', 'https://mopsov.twse.com.tw')
PATHS = ('/mops/web/ajax_t170sb01', '/mops/web/t170sb01', '/mops/api/t170sb01')
DATE = re.compile(r'(?:20\d{2}|1\d{2})[年/.-]\s*\d{1,2}[月/.-]\s*\d{1,2}')
KEYWORDS = ('董事會', '財務報告', '預計召開', '公司代號', '召開日期', '財報')


def parse_response(content, content_type):
    soup = BeautifulSoup(content, 'html.parser')
    tables = []
    for table in soup.find_all('table'):
        rows = []
        for tr in table.find_all('tr'):
            cells = [c.get_text(' ', strip=True) for c in tr.find_all(['th', 'td'])]
            if cells:
                rows.append(cells)
        if rows:
            tables.append(rows)
    text = soup.get_text(' ', strip=True)
    valid = any(k in text for k in KEYWORDS) and bool(tables)
    # Never treat HTTP 200 SPA shell, captcha, or error page as valid data.
    return {'table_count': len(tables), 'table_row_counts': [len(t) for t in tables],
            'date_matches': DATE.findall(text)[:15], 'has_relevant_table': valid,
            'text_preview': text[:650], 'tables': tables}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', default='mops_t170sb01_probe')
    ap.add_argument('--year', default='115', help='ROC year')
    ap.add_argument('--season', default='3')
    ap.add_argument('--timeout', type=int, default=18)
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    sess = requests.Session()
    sess.headers.update({'User-Agent': 'Mozilla/5.0 (compatible; MOPS-calendar-diagnostic/1.0)',
                         'Referer': 'https://mops.twse.com.tw/mops/#/web/t170sb01',
                         'Accept': 'text/html,application/json,*/*'})
    attempts = []
    payloads = [
        {'encodeURIComponent': '1', 'step': '1', 'firstin': '1', 'TYPEK': 'sii', 'year': args.year, 'season': args.season},
        {'TYPEK': 'sii', 'year': args.year, 'season': args.season},
        {'year': args.year, 'season': args.season},
    ]
    for base in BASES:
        for path in PATHS:
            for method in ('GET', 'POST'):
                for idx, payload in enumerate(payloads if method == 'POST' else ({},)):
                    url = base + path
                    item = {'url': url, 'method': method, 'payload': payload, 'attempt': idx}
                    try:
                        r = sess.request(method, url, data=payload if method == 'POST' else None,
                                         timeout=args.timeout, allow_redirects=True)
                        item.update(status=r.status_code, final_url=r.url,
                                    content_type=r.headers.get('Content-Type', ''),
                                    bytes=len(r.content))
                        parsed = parse_response(r.text, item['content_type'])
                        item.update({k: v for k, v in parsed.items() if k != 'tables'})
                        if parsed['has_relevant_table']:
                            stem = f'candidate_{len(attempts):02d}'
                            (out / (stem + '.html')).write_text(r.text, encoding='utf-8')
                            with (out / (stem + '.csv')).open('w', newline='', encoding='utf-8-sig') as f:
                                w = csv.writer(f)
                                for i, table in enumerate(parsed['tables']):
                                    w.writerow([f'TABLE {i + 1}'])
                                    w.writerows(table)
                        print(f"{r.status_code} {method} {url} rows={item['table_row_counts']} relevant={item['has_relevant_table']}")
                    except requests.RequestException as e:
                        item['error'] = str(e)[:350]
                        print(f'ERROR {method} {url}: {item["error"]}')
                    attempts.append(item)
    result = {'checked_at_utc': datetime.now(timezone.utc).isoformat(),
              'target': 'MOPS t170sb01', 'year_roc': args.year, 'season': args.season,
              'verified': any(x.get('has_relevant_table') for x in attempts),
              'note': 'A matching HTML table is a candidate, not proof of correct period or complete coverage. Check CSV and compare MOPS manually.',
              'attempts': attempts}
    (out / 'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print('RESULT:', 'CANDIDATE FOUND - inspect CSV' if result['verified'] else 'NO VERIFIED TABLE; inspect result.json')
    print('Saved:', out / 'result.json')
    # Diagnostic only; never fail workflow solely because site blocks automated access.


if __name__ == '__main__':
    main()
