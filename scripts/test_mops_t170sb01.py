#!/usr/bin/env python3
"""Isolated MOPS t170sb01 UI test; no production writes.

Fixes #2 diagnostic: the old test NEVER filled #year, NEVER selected
#season and NEVER clicked #searchBtn. Merely loading the form cannot
issue the data request. This test submits both markets through the UI.
"""
import argparse
import asyncio
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from playwright.async_api import async_playwright

URL = 'https://mops.twse.com.tw/mops/#/web/t170sb01'
TICKER = re.compile(r'(?<!\d)\d{4}(?!\d)')
DATE = re.compile(r'(?:20\d{2}|1\d{2})\s*[年/.-]\s*(?:0?[1-9]|1[0-2])\s*[月/.-]\s*(?:[0-2]?\d|3[01])')


def normalize_season(value):
    """The actual MOPS select values are 01/02/03/04, not 1/2/3/4."""
    s = str(value).strip()
    if s not in ('1','2','3','4','01','02','03','04'):
        raise ValueError('season must be 1..4')
    return str(int(s)).zfill(2)


def candidate_rows(text):
    return [re.sub(r'\s+', ' ', line).strip()[:400] for line in text.splitlines()
            if TICKER.search(line) and DATE.search(line)][:50]


async def run(args):
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    season = normalize_season(args.season)
    requests = []
    results = []
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True, args=['--no-sandbox'])
        context = await browser.new_context(locale='zh-TW', timezone_id='Asia/Taipei', viewport={'width':1440,'height':1100})
        page = await context.new_page()
        tasks = []
        async def capture(response):
            if 'mops.twse.com.tw/mops/api/' not in response.url:
                return
            item = {'url':response.url,'status':response.status,'method':response.request.method,
                    'request_body':(response.request.post_data or '')[:3000]}
            try:
                body = await response.text()
                item['response_preview'] = body[:5000]
                item['candidate_rows'] = candidate_rows(body)
            except Exception as exc:
                item['error'] = str(exc)[:300]
            requests.append(item)
        page.on('response', lambda r: tasks.append(asyncio.create_task(capture(r))))
        try:
            await page.goto(URL, wait_until='domcontentloaded', timeout=45000)
            await page.locator('#year').wait_for(state='visible',timeout=20000)
            for market in ('sii','otc'):
                await page.locator('#TYPEK').select_option(market)
                await page.locator('#year').fill(str(args.year))
                await page.locator('#season').select_option(season)
                await page.locator('#sortType').select_option('1')
                before = len(requests)
                await page.locator('#searchBtn').click()
                await page.wait_for_timeout(7000)
                text = await page.locator('body').inner_text()
                await page.screenshot(path=str(out/f'{market}.png'),full_page=True)
                (out/f'{market}.txt').write_text(text,encoding='utf-8')
                results.append({'market':market,'year':str(args.year),'season':season,
                                'rows':candidate_rows(text),
                                'no_data':'查無相符資料' in text,
                                'page_text_preview':text[-3000:],
                                'api_calls_after_click':len(requests)-before})
                # Results screen may hide the form; return to search form before next market.
                if market == 'sii':
                    btn = page.get_by_role('button',name='修改條件')
                    if await btn.count() and await btn.first.is_visible():
                        await btn.first.click()
                    await page.locator('#TYPEK').wait_for(state='visible',timeout=10000)
        except Exception as exc:
            results.append({'fatal_error':repr(exc)})
        if tasks:
            await asyncio.gather(*tasks,return_exceptions=True)
        await browser.close()
    (out/'network.json').write_text(json.dumps(requests,ensure_ascii=False,indent=2),encoding='utf-8')
    (out/'markets.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
    verified = any(r.get('rows') for r in results)
    summary = {'checked_at_utc':datetime.now(timezone.utc).isoformat(),'year':str(args.year),
               'season':season,'markets':results,'api_calls':len(requests),'verified':verified,
               'note':'Verification requires real company code + date rows; no production changes.'}
    (out/'result.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'verified':verified,'api_calls':len(requests),
                      'market_summary':[{'market':r.get('market'),'rows':len(r.get('rows',[])),
                                         'api_calls_after_click':r.get('api_calls_after_click'),
                                         'error':r.get('fatal_error')} for r in results]},ensure_ascii=False,indent=2))
    return 0 if verified else 2


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--year',default='115')
    parser.add_argument('--season',default='3')
    parser.add_argument('--out',default='mops_t170sb01_probe')
    args=parser.parse_args()
    return asyncio.run(run(args))

if __name__=='__main__':
    sys.exit(main())
