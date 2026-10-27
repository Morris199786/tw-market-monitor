"""Notify published LINE AI successes; no AI calls and at-most-once delivery.

A remote claim is saved BEFORE sending. An ambiguous Telegram timeout stays
claimed for manual inspection, rather than risking duplicate notifications.
"""
import argparse
import json
import os
import re
import subprocess
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode

ROOT = Path(__file__).resolve().parents[1]
LEDGER = 'data/research_telegram_delivery.json'
SITE = 'https://tw-market-monitor.pages.dev/'


def read(root, name):
    return json.loads((root / name).read_text(encoding='utf-8'))


def category(row):
    if str(row.get('market', 'TW')).upper() == 'US' or row.get('source_kind') == 'broker':
        return ''
    value = row.get('category', '')
    if value in ('早報', '法說／訪談'):
        return value
    if not value and str(row.get('original_type', '')).lower() in ('法說會', 'call memo'):
        return '法說／訪談'
    return ''


def published(root):
    cache = read(root, 'data/research_ai_cache.json')
    rendered = read(root, 'data/research_ai_render.json').get('items', {})
    result = {}
    for row in read(root, 'data/research_meta.json'):
        rid = str(row.get('id', ''))
        if not rid.startswith('line-') or not category(row):
            continue
        entry = cache.get(rid, {})
        content = rendered.get(rid, {}).get('content', {})
        if entry.get('status') == 'success' and content.get('blocks'):
            result[rid] = row
    return result


def message(row):
    if category(row) == '早報':
        source = re.split(r'[（(]', str(row.get('source') or ''), maxsplit=1)[0].strip()
        name = source or str(row.get('company') or '券商').strip()
        name = re.sub(r'(投資)?早報$', '', name).strip()
        label = name + '早報'
    else:
        label = str(row.get('company') or row.get('title') or '公司未標示').strip() + ' 法說/訪談'
    return f"{row.get('date', '')} {label}"


def link(rid):
    return SITE + '?' + urlencode({'research_id': rid}) + '#reports'


def git(*args):
    return subprocess.run(['git', *args], cwd=ROOT, check=True, capture_output=True, text=True)


def checkpoint(state):
    path = ROOT / LEDGER
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    tmp.replace(path)
    git('add', '--', LEDGER)
    diff = subprocess.run(['git', 'diff', '--cached', '--quiet', '--', LEDGER], cwd=ROOT)
    if diff.returncode == 0:
        return
    if diff.returncode != 1:
        raise RuntimeError('Cannot inspect Telegram ledger changes')
    git('commit', '-m', 'Checkpoint LINE research Telegram delivery', '--', LEDGER)
    for attempt in range(5):
        git('fetch', 'origin', 'main')
        git('rebase', 'origin/main')
        try:
            git('push', 'origin', 'HEAD:main')
            return
        except subprocess.CalledProcessError:
            if attempt == 4:
                raise RuntimeError('Telegram ledger push failed; no further messages will be sent') from None
            time.sleep(3 * (attempt + 1))


def now():
    return datetime.now(timezone.utc).isoformat()


def initialize(rows, save):
    state = {'version': 1, 'initialized_at': now(), 'deliveries': {
        rid: {'status': 'baseline', 'at': now()} for rid in rows
    }}
    save(state)
    return state


def send_telegram(text, url):
    payload = json.dumps({
        'chat_id': os.environ['TELEGRAM_CHAT_ID'], 'text': text,
        'disable_web_page_preview': True,
        'reply_markup': {'inline_keyboard': [[{'text': '閱讀完整報告', 'url': url}]]}
    }).encode()
    req = urllib.request.Request(
        'https://api.telegram.org/bot' + os.environ['TELEGRAM_BOT_TOKEN'] + '/sendMessage',
        data=payload, headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=30) as response:
        result = json.load(response)
    if not result.get('ok'):
        raise RuntimeError('Telegram rejected message')
    return result['result']['message_id']


def deliver(rows, state, save, send):
    for rid, row in rows.items():
        if rid in state['deliveries']:
            continue
        record = {'status': 'claimed', 'at': now(), 'text': message(row), 'url': link(rid)}
        state['deliveries'][rid] = record
        save(state)  # Must be durable on main BEFORE network delivery.
        try:
            mid = send(record['text'], record['url'])
        except Exception as exc:
            # Do not print exception strings: HTTP errors can contain the bot token.
            record.update(status='uncertain', error_type=type(exc).__name__)
            save(state)
            raise RuntimeError('Telegram delivery unconfirmed; claim retained, no automatic resend') from None
        record.update(status='sent', message_id=mid, sent_at=now())
        save(state)
        print('TELEGRAM_SENT', rid)
        time.sleep(1.1)  # Single-chat pacing, without automatic HTTP retries.


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('mode', choices=['init', 'send', 'preview'])
    args = parser.parse_args()
    rows = published(ROOT)
    path = ROOT / LEDGER
    if args.mode == 'preview':
        state = read(ROOT, LEDGER) if path.exists() else {'deliveries': {}}
        for rid, row in rows.items():
            if rid not in state['deliveries']:
                print(message(row), link(rid))
        return
    if not path.exists():
        if args.mode != 'init':
            raise RuntimeError('Missing baseline; run init before processing reports')
        initialize(rows, checkpoint)
        print('TELEGRAM_BASELINE', len(rows))
        return
    state = read(ROOT, LEDGER)
    if state.get('version') != 1 or not isinstance(state.get('deliveries'), dict):
        raise RuntimeError('Invalid Telegram ledger; refusing to send')
    if args.mode == 'init':
        return
    if not os.environ.get('TELEGRAM_BOT_TOKEN') or not os.environ.get('TELEGRAM_CHAT_ID'):
        raise RuntimeError('Telegram secrets missing; no delivery claims created')
    deliver(rows, state, checkpoint, send_telegram)


if __name__ == '__main__':
    main()
