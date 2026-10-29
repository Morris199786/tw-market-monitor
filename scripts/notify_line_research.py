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
    from meeting_identity import event_index, event_key
    rows = read(root, 'data/research_meta.json')
    events = event_index(root, cache, rows)
    ledger = read(root, LEDGER) if (root / LEDGER).exists() else {'deliveries': {}}
    known = {cache[rid].get('meeting_event_key') for rid in ledger['deliveries'] if rid in cache and isinstance(cache[rid], dict)}
    delivered_meetings = {event_key(r) for r in rows if str(r.get('id')) in ledger['deliveries'] and event_key(r)}
    result = {}
    for row in rows:
        key = event_key(row)
        if key and (key in known or any(__import__('meeting_identity')._same_event(key, k) for k in delivered_meetings)):
            continue
        rid = str(row.get('id', ''))
        if not rid.startswith('line-') or not category(row):
            continue
        entry = cache.get(rid, {})
        content = rendered.get(rid, {}).get('content', {})
        if entry.get('status') == 'success' and content.get('blocks'):
            result[rid] = dict(row, telegram_summary=content.get("summary", []))
            if key:
                known.add(key)
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


def compact(value, limit):
    text = re.sub(r'\s+', ' ', str(value or '')).strip()
    return text if len(text) <= limit else text[:limit - 1] + '…'


def digest_entry(rid, row, number):
    summary = row.get('telegram_summary', [])
    if isinstance(summary, list):
        summary = next((x for x in summary if isinstance(x, str) and x.strip()), '')
    if not isinstance(summary, str):
        summary = ''
    name = compact(row.get('company') or row.get('title') or '公司未標示', 100)
    date = compact(row.get('date'), 20)
    text = f"{number}. {name}｜{date}"
    if summary:
        text += '\n重點：' + compact(summary, 200)
    return text + '\n閱讀完整報告：' + link(rid)


def batches(rows, state):
    pending = [(rid, row) for rid, row in rows.items() if rid not in state['deliveries']]
    meetings = [(rid, row) for rid, row in pending if category(row) == '法說／訪談']
    chunks, current = [], []
    for rid, row in meetings:
        entry = digest_entry(rid, row, len(current) + 1)
        # Conservative UTF-16 budget leaves room for the heading and emoji.
        if current and len(('\n\n'.join(x[1] for x in current) + '\n\n' + entry).encode('utf-16-le')) // 2 > 3600:
            chunks.append(current)
            current = []
            entry = digest_entry(rid, row, 1)
        current.append((rid, entry))
    if current:
        chunks.append(current)
    for i, chunk in enumerate(chunks, 1):
        heading = f'📊 法說／訪談彙整｜新增 {len(meetings)} 篇'
        if len(chunks) > 1:
            heading += f'（{i}/{len(chunks)}）'
        yield [x[0] for x in chunk], heading + '\n\n' + '\n\n'.join(x[1] for x in chunk), SITE + '#reports'
    # Preserve existing morning-report delivery behavior.
    for rid, row in pending:
        if category(row) != '法說／訪談':
            yield [rid], message(row), link(rid)


def deliver(rows, state, save, send):
    for ids, text, url in batches(rows, state):
        for rid in ids:
            state['deliveries'][rid] = {
                'status': 'claimed', 'at': now(), 'text': text,
                'url': link(rid), 'batch_ids': ids,
            }
        save(state)  # Claim every member durably BEFORE sending this digest.
        try:
            mid = send(text, url)
        except Exception as exc:
            for rid in ids:
                state['deliveries'][rid].update(status='uncertain', error_type=type(exc).__name__)
            save(state)
            raise RuntimeError('Telegram delivery unconfirmed; claim retained, no automatic resend') from None
        for rid in ids:
            state['deliveries'][rid].update(status='sent', message_id=mid, sent_at=now())
        save(state)
        print('TELEGRAM_SENT', ','.join(ids))
        time.sleep(1.1)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('mode', choices=['init', 'send', 'preview'])
    args = parser.parse_args()
    rows = published(ROOT)
    path = ROOT / LEDGER
    if args.mode == 'preview':
        state = read(ROOT, LEDGER) if path.exists() else {'deliveries': {}}
        for ids, text, url in batches(rows, state):
            print(text, url)
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


