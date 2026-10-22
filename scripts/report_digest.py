"""One Telegram notification per category; no AI calls or automatic retries."""
import json
import math
import requests


def send_digest(token, chat_id, title, entries, url):
    if not token or not chat_id or not entries:
        return False
    text = title + '\n\n' + '\n\n'.join(entries)
    data = {'chat_id': chat_id, 'reply_markup': json.dumps({'inline_keyboard': [[{'text': '查看完整內容', 'url': url}]]}, ensure_ascii=False)}
    # UTF-16 length is conservative for Telegram, including emoji.
    try:
        if len(text.encode('utf-16-le')) // 2 <= 4000:
            data.update(text=text, disable_web_page_preview=True)
            response = requests.post(f'https://api.telegram.org/bot{token}/sendMessage', data=data, timeout=30)
        else:
            data['caption'] = f'{title}\n共 {len(entries)} 筆，完整清單請開啟附件'
            response = requests.post(f'https://api.telegram.org/bot{token}/sendDocument', data=data,
                files={'document': ('digest.txt', text.encode('utf-8-sig'), 'text/plain')}, timeout=30)
        response.raise_for_status()
        return bool(response.json().get('ok'))
    except Exception as exc:
        # Never log request URLs: they contain the bot token.
        print('Telegram digest failed:', type(exc).__name__)
        return False


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

