#!/usr/bin/env python3
"""Isolated, read-only browser diagnostic for MOPS t170sb01.

Uses the public website's own frontend requests, rather than guessing private API
parameters. Never writes production JSON or sends notifications.
"""
import argparse
import asyncio
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse
from playwright.async_api import async_playwright

URL = 'https://mops.twse.com.tw/mops/#/web/t170sb01'
TICKER = re.compile(r'(?<!\d)\d{4}(?!\d)')
DATE = re.compile(r'(?:20\d{2}|1\d{2})\s*[年/.-]\s*(?:0?[1-9]|1[0-2])\s*[月/.-]\s*(?:[0-2]?\d|3[01])')


def evidence(text):
    # Require rows with BOTH a ticker and a plausible date. Avoid matching the
    # generic application shell, scripts, or unrelated timestamps.
    rows = [re.sub(r'\s+', ' ', s).strip() for s in text.splitlines()]
    matches = [s[:350] for s in rows if TICKER.search(s) and DATE.search(s)
               and ('董事' in s or '財報' in s or '召開' in s or len(s) < 220)]
    return matches[:40]


async def main():
    p = argparse.ArgumentParser()
    p.add_argument('--year', default='115')
    p.add_argument('--season', default='3')
    p.add_argument('--out', default='mops_t170sb01_probe')
    a = p.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    events = []
    captures = []
    js_hits = []
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True, args=['--no-sandbox'])
        context = await browser.new_context(locale='zh-TW', timezone_id='Asia/Taipei', viewport={'width': 1440, 'height': 1100})
        page = await context.new_page()
        async def capture_response(resp):
            url = resp.url
            if not urlparse(url).netloc.endswith('twse.com.tw'):
                return
            item = {'url': url[:450], 'status': resp.status, 'method': resp.request.method,
                    'content_type': resp.headers.get('content-type', '')}
            try:
                if '/api/' in url or 't170sb01' in url.lower():
                    req = resp.request
                    item['request_body'] = (req.post_data or '')[:1000]
                    body = await resp.text()
                    item['preview'] = body[:1800]
                    item['rows'] = evidence(body)
                    captures.append(item)
                elif url.lower().split('?')[0].endswith('.js'):
                    body = await resp.text()
                    for m in list(re.finditer(r't170sb01', body, re.I))[:12]:
                        js_hits.append({'url': url, 'context': body[max(0,m.start()-600):m.end()+700]})
            except Exception as exc:
                item['error'] = str(exc)[:200]
            events.append(item)
        tasks = []
        page.on('response', lambda r: tasks.append(asyncio.create_task(capture_response(r))))
        page.on('console', lambda msg: events.append({'console': msg.type, 'text': msg.text[:400]}) if msg.type == 'error' else None)
        try:
            await page.goto(URL, wait_until='domcontentloaded', timeout=45000)
            await page.wait_for_timeout(7000)
            # Capture form controls so the next test can use the actual site UI.
            controls = await page.locator('input,select,button,[role=combobox]').evaluate_all(
                "els => els.slice(0,100).map(e=>({tag:e.tagName,type:e.type||'',name:e.name||'',placeholder:e.placeholder||'',text:(e.innerText||'').slice(0,100),html:e.outerHTML.slice(0,450)}))")
            (out/'controls.json').write_text(json.dumps(controls, ensure_ascii=False, indent=2), encoding='utf-8')
            # Prefer interacting with visible year/quarter fields; avoid guessing
            # button labels or submitting unrelated forms.
            for select in await page.locator('select').all():
                try:
                    opts = await select.locator('option').all_text_contents()
                    val = await select.get_attribute('name') or ''
                    if any(a.year in s or '2026' in s for s in opts) and ('year' in val.lower() or len(opts) > 3):
                        for opt in await select.locator('option').all():
                            v = await opt.get_attribute('value') or ''
                            t = (await opt.inner_text()).strip()
                            if v == a.year or a.year in t or '2026' in t:
                                await select.select_option(value=v)
                                break
                except Exception:
                    pass
            await page.wait_for_timeout(2000)
            text = await page.locator('body').inner_text(timeout=15000)
            (out/'visible_page.txt').write_text(text[:60000], encoding='utf-8')
            await page.screenshot(path=str(out/'page.png'), full_page=True, timeout=20000)
            events.append({'page_title': await page.title(), 'final_url': page.url, 'visible_rows': evidence(text)})
        except Exception as exc:
            events.append({'browser_error': str(exc)[:800]})
        await page.wait_for_timeout(3000)
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        await browser.close()
    (out/'network.json').write_text(json.dumps(captures, ensure_ascii=False, indent=2), encoding='utf-8')
    (out/'js_references.json').write_text(json.dumps(js_hits[:30], ensure_ascii=False, indent=2), encoding='utf-8')
    (out/'events.json').write_text(json.dumps(events[-250:], ensure_ascii=False, indent=2), encoding='utf-8')
    visible = [row for e in events for row in e.get('visible_rows', [])]
    api_rows = [row for e in captures for row in e.get('rows', [])]
    result = {'checked_at_utc': datetime.now(timezone.utc).isoformat(), 'target': URL,
              'year': a.year, 'quarter': a.season, 'visible_matching_rows': visible[:20],
              'api_matching_rows': api_rows[:20], 'api_calls': len(captures),
              'js_references': len(js_hits), 'verified': bool(visible or api_rows),
              'note': 'Rows are candidates; inspect company, date, period before production integration.'}
    (out/'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result['verified'] else 2

if __name__ == '__main__':
    sys.exit(asyncio.run(main()))
