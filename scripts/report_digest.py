"""Telegram grouped digests (10 entries by default; compact mode uses character limits).

Used by earnings and ratings notifications. Standard messages preserve one category
and keep their original content, except redundant long Google News RSS URLs.
"""
import json
import math
import re
import requests

TELEGRAM_LIMIT = 3900  # UTF-16 units; below Telegram's 4096 ceiling
GROUP_SIZE = 10


def utf16_len(text):
    return len(text.encode('utf-16-le')) // 2


def readable_entry(entry):
    """Do not dump huge Google News RSS token URLs into Telegram messages."""
    lines = []
    for line in str(entry).splitlines():
        if re.match(r'^https?://news\.google\.com/rss/articles/\S+', line.strip(), re.I):
            # The source name is already shown above; web-button opens research page.
            continue
        # Other URLs, including original MOPS release pages, stay intact.
        lines.append(line)
    return '\n'.join(lines).strip()


def split_text(text, max_units):
    """Last-resort split for a single unusually long report (no content loss)."""
    if max_units < 30:
        raise ValueError('invalid text budget')
    chunks, buf = [], ''
    for line in text.splitlines(keepends=True):
        for ch in line:
            if utf16_len(buf + ch) > max_units:
                chunks.append(buf)
                buf = ch
            else:
                buf += ch
    if buf:
        chunks.append(buf)
    return chunks


def make_batches(title, entries, max_entries=GROUP_SIZE, *, compact=False):
    """Return safe Telegram plain-text messages, respecting both size limits."""
    if max_entries < 1:
        raise ValueError('max_entries must be positive')
    # Broker report instant digests should split only when Telegram size requires it.
    broker_digest = title.startswith("券商報告彙整｜")
    if broker_digest:
        max_entries = max(max_entries, len(entries))
    clean_entries = [readable_entry(x) for x in entries if str(x).strip()]
    batches = []
    current = []
    prefix_budget = utf16_len(title) + 32
    item_budget = TELEGRAM_LIMIT - prefix_budget - 8
    if item_budget < 100:
        raise ValueError('title too long')
    separator = '\n' if compact else '\n\n'
    for item in clean_entries:
        parts = split_text(item, item_budget) if utf16_len(item) > item_budget else [item]
        for part in parts:
            joined = separator.join(current + [part])
            if current and (len(current) >= max_entries or utf16_len(joined) + prefix_budget > TELEGRAM_LIMIT):
                batches.append(current)
                current = []
            current.append(part)
    if current:
        batches.append(current)
    messages = [(title if (compact or broker_digest) and len(batches) == 1 else f'{title}｜第 {i}/{len(batches)} 則')
                + '\n\n' + separator.join(parts)
                for i, parts in enumerate(batches, 1)]
    if any(utf16_len(message) > TELEGRAM_LIMIT for message in messages):
        raise ValueError('Telegram batch exceeds character limit')
    return messages


def send_messages(token, chat_id, title, entries, url, *, on_sent=None, max_entries=GROUP_SIZE, compact=False):
    """Send grouped texts; callback persists each successful group if provided."""
    if not token or not chat_id or not entries:
        return False
    batches = make_batches(title, entries, max_entries=max_entries, compact=compact)
    for i, text in enumerate(batches, 1):
        data = {
            'chat_id': chat_id,
            'text': text,
            'disable_web_page_preview': True,
            'reply_markup': json.dumps({'inline_keyboard': [[{'text': '查看完整內容', 'url': url}]]}, ensure_ascii=False),
        }
        try:
            response = requests.post(f'https://api.telegram.org/bot{token}/sendMessage', data=data, timeout=30)
            response.raise_for_status()
            payload = response.json()
            if payload.get('ok') is not True:
                print('TELEGRAM_BATCH_REJECTED', i, len(batches))
                return False
            if on_sent:
                on_sent(i, len(batches), payload)
            print('TELEGRAM_BATCH_SENT', i, len(batches), 'items', len(entries))
        except Exception as exc:
            print('TELEGRAM_BATCH_FAILED', i, len(batches), type(exc).__name__)
            return False
    return True


def send_digest(token, chat_id, title, entries, url, *, max_entries=GROUP_SIZE, compact=False):
    return send_messages(token, chat_id, title, entries, url, max_entries=max_entries, compact=compact)


def rating_entry(item):
    action = {'upgrade': '上調', 'downgrade': '下調'}.get(item.get('action'), '調整')
    kind = '評等' if item.get('kind') == 'rating' else '目標價'
    def number(value):
        if value is None or value == '':
            return '未提供'
        try:
            return f'{float(value):g}'
        except (ValueError, TypeError):
            return str(value)
    line = f"📌 {item.get('name') or ''} {item.get('ticker') or ''}｜{item.get('broker') or '券商'}｜{action}{kind}"
    line += f"\n目標價 {number(item.get('target_price_old'))} → {number(item.get('target_price_new'))}"
    try:
        pct = float(item.get('potential_upside_pct'))
        if math.isfinite(pct):
            line += f"（潛在{'漲' if pct >= 0 else '跌'}幅 {pct:+.1f}%）"
    except (TypeError, ValueError):
        pass
    if item.get('rating'):
        line += f"｜評等 {item['rating']}"
    return line
