#!/usr/bin/env python3
"""Read-only MOPS t170sb01 discovery probe. Never touches production data.

Pass criteria: actual company code + board-meeting date in a matching response.
HTTP 200 or MOPS business code 200 alone is NOT a pass.
"""
import argparse
import csv
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin
import requests
from bs4 import BeautifulSoup

ROOT = 'https://mops.twse.com.tw'
PAGE = ROOT + '/mops/'
API = ROOT + '/mops/api/t170sb01'
TICKER = re.compile(r'(?<!\d)\d{4}(?!\d)')
DATE = re.compile(r'(?:20\d{2}|1\d{2})\s*[年/.-]\s*(?:0?[1-9]|1[0-2])\s*[月/.-]\s*(?:[0-2]?\d|3[01])')
FIELDS = ('董事會', '召開日期', '財報', '財務報告', '公司代號')


def summarize(response):
    s = response.text
    obj = None
    try: obj = response.json()
    except ValueError: pass
    text = BeautifulSoup(s, 'html.parser').get_text(' ', strip=True)
    if obj is not None:
        text = json.dumps(obj, ensure_ascii=False)
    codes = sorted(set(TICKER.findall(text)))[:25]
    dates = DATE.findall(text)[:25]
    # Data must be tied to the target page, not a generic SPA shell.
    meaningful = bool(codes and dates and any(k in text for k in FIELDS))
    return {'http': response.status_code, 'url': response.url,
            'content_type': response.headers.get('Content-Type', ''),
            'bytes': len(response.content), 'json_code': obj.get('code') if isinstance(obj, dict) else None,
            'company_codes_sample': codes, 'dates_sample': dates,
            'relevant_terms': [k for k in FIELDS if k in text],
            'candidate': meaningful, 'preview': text[:700]}


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--year', default='115')
    p.add_argument('--season', default='3')
    p.add_argument('--out', default='mops_t170sb01_probe_v2')
    p.add_argument('--timeout', type=int, default=14)
    args = p.parse_args()
    out = Path(args.out); out.mkdir(parents=True, exist_ok=True)
    session = requests.Session()
    session.headers.update({'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/130.0.0.0 Safari/537.36',
        'Accept': 'application/json, text/plain, */*', 'Referer': PAGE + '#/web/t170sb01',
        'Origin': ROOT})
    records = []
    def attempt(label, method, url, **kwargs):
        row = {'label': label, 'method': method, 'requested_url': url, 'params': kwargs.get('params'), 'body': kwargs.get('json') or kwargs.get('data')}
        try:
            r = session.request(method, url, timeout=args.timeout, **kwargs)
            row.update(summarize(r))
            if row['candidate']:
                (out / f'candidate_{len(records):02d}.txt').write_text(r.text[:500000], encoding='utf-8')
            print(label, row.get('http'), 'candidate=', row.get('candidate'), 'code=', row.get('json_code'), 'bytes=', row.get('bytes'), flush=True)
            return r
        except requests.RequestException as e:
            row['error'] = str(e)[:400]
            print(label, 'ERROR', row['error'], flush=True)
            return None
        finally:
            records.append(row)
    # Session initialization and dynamic bundle discovery. Never execute JavaScript.
    home = attempt('homepage', 'GET', PAGE)
    if home is not None:
        soup = BeautifulSoup(home.text, 'html.parser')
        scripts = [urljoin(PAGE, t['src']) for t in soup.select('script[src]') if t.get('src')]
        scripts = [s for s in scripts if s.startswith(ROOT)][:12]
        assets = []
        for i, url in enumerate(scripts):
            try:
                r = session.get(url, timeout=args.timeout)
                matches = []
                for m in list(re.finditer(r't170sb01', r.text, re.I))[:8]:
                    matches.append(r.text[max(0, m.start()-350):m.end()+350])
                assets.append({'url': url, 'http': r.status_code, 'bytes': len(r.content), 'matches': matches})
                if matches:
                    print('JS REFERENCE:', url, flush=True)
            except requests.RequestException as e:
                assets.append({'url': url, 'error': str(e)[:250]})
        (out/'js_discovery.json').write_text(json.dumps(assets, ensure_ascii=False, indent=2), encoding='utf-8')
    attempt('page_route', 'GET', ROOT+'/mops/web/t170sb01')
    # Probe several common MOPS parameter conventions; no assumption any is authoritative.
    y, q = args.year, args.season
    bodies = [
        {'year': y, 'season': q, 'TYPEK': 'sii'},
        {'year': y, 'season': q},
        {'year': y, 'season': q, 'type': 'sii'},
        {'year': y, 'quarter': q, 'TYPEK': 'sii'},
        {'year': y, 'season': q, 'typeK': 'sii'},
        {'year': y, 'season': q, 'step': '1', 'firstin': '1', 'TYPEK': 'sii'},
        {'year': str(int(y)+1911), 'season': q, 'TYPEK': 'sii'},
    ]
    for i, body in enumerate(bodies):
        attempt(f'api_post_json_{i}', 'POST', API, json=body)
        attempt(f'api_post_form_{i}', 'POST', API, data=body)
    for i, body in enumerate(bodies[:4]):
        attempt(f'api_get_{i}', 'GET', API, params=body)
    candidates = [x for x in records if x.get('candidate')]
    result = {'checked_at_utc': datetime.now(timezone.utc).isoformat(), 'year_roc': y, 'season': q,
              'candidate_count': len(candidates), 'status': 'CANDIDATE_NEEDS_MANUAL_VALIDATION' if candidates else 'NO_DATA',
              'warning': 'Candidate means ticker/date/keywords present, not yet proof of exact quarter or completeness.',
              'attempts': records}
    (out/'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    with (out/'attempts.csv').open('w', newline='', encoding='utf-8-sig') as f:
        w=csv.writer(f); w.writerow(['label','http','json_code','bytes','candidate','preview'])
        for x in records: w.writerow([x.get('label'),x.get('http'),x.get('json_code'),x.get('bytes'),x.get('candidate'),x.get('preview','')[:180]])
    print('RESULT:', result['status'], 'records:', len(records), flush=True)
    # Strict: no false-green workflows when API returns 406 or SPA placeholder.
    return 0 if candidates else 2

if __name__ == '__main__':
    sys.exit(main())
