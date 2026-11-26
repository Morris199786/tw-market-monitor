#!/usr/bin/env python3
"""Publish a grouped Telegram digest for newly analyzed business reports only."""
import json
import os
from pathlib import Path
import subprocess
import time
from datetime import datetime
from zoneinfo import ZoneInfo

import requests
from report_presentation import complete_reason, upside_text
from update_business_reports_ai import read_items, key, INDEX, OUTPUT, DATA, ROOT
from update_business_reports import write_json

STATE = DATA / 'business_reports_sent.json'
TZ = ZoneInfo('Asia/Taipei')
LIMIT = 3600
ACTIONS = {'upgrade':'上調','downgrade':'下調','initiate':'初評','maintain':'維持'}


def units(s):
    return len(s.encode('utf-16-le')) // 2


def report_key(row):
    return json.dumps(key(row), ensure_ascii=False, separators=(',', ':'))


def eligible(index_rows, results, ledger, day):
    valid = {key(r):r for r in index_rows if r.get('date') == day}
    seen = set(ledger)
    for r in results:
        k = report_key(r)
        if (r.get('status') == 'ready' and r.get('group_date') == day and key(r) in valid and k not in seen):
            seen.add(k)
            yield r, valid[key(r)]


def num(v):
    if v is None or v == '':
        return ''
    try:
        return f'{float(v):g}'
    except (TypeError, ValueError):
        return ''


def report_lines(r, meta):
    company = ' '.join(str(x) for x in (r.get('name') or meta.get('company'), r.get('ticker') or meta.get('ticker')) if x)
    if r.get('report_type') != 'company' or not company:
        company = r.get('title') or meta.get('title') or meta.get('filename') or '研究報告'
    broker = r.get('broker') or meta.get('broker') or '券商'
    labels = [str(broker)]
    rating = ' '.join(x for x in (ACTIONS.get(r.get('action'),''), str(r.get('rating') or '')) if x)
    if rating:
        labels.append(rating)
    old,new = num(r.get('target_price_old')),num(r.get('target_price_new'))
    if new:
        labels.append('目標價 ' + (old+' → ' if old and old != new else '') + new + upside_text(r))
    reason = complete_reason(r)
    # Do not cut a sentence or publish an extremely long AI-generated block.
    if units(reason) > 1800:
        reason = next((v for v in (r.get('summary') or []) if isinstance(v,str) and 12 <= units(v) <= 1800), '')
    return str(company), '• ' + '｜'.join(labels) + ('\n  '+reason if reason else '')


def batches(candidates, day, site):
    grouped = {}
    for r, meta in candidates:
        name, block = report_lines(r, meta)
        grouped.setdefault(name, []).append((report_key(r), block))
    header = '📚 業務報告更新｜' + day.replace('-', '/')
    footer = '\n\n🔗 產業資料庫：' + site
    result = []
    body, keys, last = [], [], None
    def finish():
        if keys:
            result.append((header + f'｜{len(keys)} 份\n\n' + '\n'.join(body) + footer, list(keys)))
    for name, records in grouped.items():
        for k, block in records:
            heading = ('\n' if body else '') + '📌 ' + name
            lines = ([heading] if last != name else []) + [block]
            if keys and units(header + '｜99999 份\n\n' + '\n'.join(body+lines) + footer) > LIMIT:
                finish(); body, keys, last = [], [], None
                lines = ['📌 '+name, block]
            if units(header + '｜1 份\n\n' + '\n'.join(lines) + footer) > LIMIT:
                # Keep a useful report reference rather than chopping a sentence.
                lines = ['📌 業務報告', '• 完整解析請至產業資料庫閱讀。']
            body.extend(lines); keys.append(k); last=name
    finish()
    return result


def git(*args):
    return subprocess.run(['git', *args], cwd=ROOT, check=True, capture_output=True, text=True, timeout=90).stdout.strip()


def publish_state():
    """Durably claim before network I/O. Never overwrite concurrent ledger edits."""
    rel = str(STATE.relative_to(ROOT))
    git('config','user.name','github-actions[bot]')
    git('config','user.email','41898282+github-actions[bot]@users.noreply.github.com')
    git('add',rel)
    if git('diff','--cached','--name-only'):
        git('commit','-m','data: business reports Telegram state')
    for i in range(5):
        git('fetch','origin','main')
        base = git('merge-base','HEAD','origin/main')
        if git('diff','--name-only',base,'origin/main','--',rel):
            raise RuntimeError('Remote business notification state changed')
        try:
            git('rebase','origin/main')
        except subprocess.CalledProcessError:
            subprocess.run(['git','rebase','--abort'],cwd=ROOT,capture_output=True,timeout=90)
            raise
        try:
            git('push','origin','HEAD:main')
            return
        except subprocess.CalledProcessError:
            if i == 4:
                raise
            time.sleep(2)


def send_batches(messages, ledger, save, post, stamp):
    """At-most-once for ambiguous Telegram responses. Explicit rejection is retryable."""
    sent = 0
    for text, keys in messages:
        for k in keys:
            ledger[k] = {'status':'claimed','at':stamp()}
        save(ledger)  # Must be published before sending.
        try:
            resp = post(text)
            data = resp.json()
        except Exception:
            # Unknown if Telegram delivered; keep the durable claim to prevent duplicate.
            print('Telegram delivery uncertain; claim retained, inspect workflow log.')
            break
        if isinstance(data, dict) and data.get('ok') is True and resp.ok:
            for k in keys:
                ledger[k] = {'status':'sent','at':stamp(),'message_id':data.get('result',{}).get('message_id')}
            save(ledger)
            sent += len(keys)
        elif isinstance(data, dict) and data.get('ok') is False:
            # Telegram explicitly rejected the message; safe to retry on next same-day run.
            for k in keys:
                ledger.pop(k,None)
            save(ledger)
            print('Telegram rejected business summary; same-day retry allowed.')
            break
        else:
            print('Telegram response uncertain; claim retained.')
            break
    return sent


def main():
    day = datetime.now(TZ).date().isoformat()
    if not OUTPUT.exists() or not INDEX.exists():
        return
    ledger = json.loads(STATE.read_text(encoding='utf-8'))['reports'] if STATE.exists() else {}
    if not isinstance(ledger,dict):
        raise ValueError('Invalid Telegram ledger')
    candidates = list(eligible(read_items(INDEX),read_items(OUTPUT),ledger,day))
    if not candidates:
        print('No new business report summaries to send.')
        return
    token = os.environ.get('TELEGRAM_BOT_TOKEN','').strip()
    chat = os.environ.get('TELEGRAM_CHAT_ID','').strip()
    if not token or not chat:
        print('Telegram credentials unavailable; no claims created.')
        return
    site = os.environ.get('REPORT_SITE_URL','https://morris199786.github.io/tw-market-monitor/').rstrip('/')+'/?page=reports'
    def save(value):
        write_json(STATE,{'reports':value})
        publish_state()
    def post(text):
        return requests.post('https://api.telegram.org/bot'+token+'/sendMessage',
                             json={'chat_id':chat,'text':text,'disable_web_page_preview':True},timeout=45)
    stamp = lambda: datetime.now(TZ).isoformat(timespec='seconds')
    sent = send_batches(batches(candidates,day,site),ledger,save,post,stamp)
    print('Business report summaries sent:',sent)


if __name__ == '__main__':
    main()
