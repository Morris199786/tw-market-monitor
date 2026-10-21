"""Poll a dedicated Telegram group and save PDF documents to Google Drive.

Uses an existing Telegram bot token and GitHub OIDC Google access token.
State is persisted in data/telegram_drive_state.json by the workflow.
"""
import json
import os
import sys
import time
from pathlib import Path
from urllib.parse import quote

import requests

BOT_TOKEN = os.environ['TELEGRAM_BOT_TOKEN']
ACCESS_TOKEN = os.environ['ACCESS_TOKEN']
FOLDER_ID = os.environ['DRIVE_FOLDER_ID']
CHAT_ID = os.getenv('TELEGRAM_REPORT_CHAT_ID', '').strip()
CHAT_TITLE = os.getenv('TELEGRAM_REPORT_CHAT_TITLE', '券商報告').strip()
STATE_PATH = Path('data/telegram_drive_state.json')
TG_API = f'https://api.telegram.org/bot{BOT_TOKEN}'
DRIVE_API = 'https://www.googleapis.com/drive/v3/files'
MAX_DOWNLOAD = 20 * 1024 * 1024  # Telegram hosted Bot API getFile download limit


def telegram(method, **params):
    resp = requests.post(f'{TG_API}/{method}', data=params, timeout=45)
    resp.raise_for_status()
    data = resp.json()
    if not data.get('ok'):
        raise RuntimeError(f'Telegram {method} failed: {data.get("description")}')
    return data['result']


def drive_headers():
    return {'Authorization': f'Bearer {ACCESS_TOKEN}'}


def already_uploaded(unique_id):
    # Search Drive metadata instead of relying solely on Git state: safe after a
    # successful upload followed by a failed git push.
    safe_id = unique_id.replace('\\', '\\\\').replace("'", "\\'")
    query = f"'{FOLDER_ID}' in parents and trashed = false and appProperties has {{ key='telegram_unique_id' and value='{safe_id}' }}"
    response = requests.get(DRIVE_API, headers=drive_headers(), params={
        'q': query, 'fields': 'nextPageToken,files(id,name)', 'page_size': 1,
        'supportsAllDrives': 'true', 'includeItemsFromAllDrives': 'true',
    }, timeout=45)
    response.raise_for_status()
    return bool(response.json().get('files'))


def upload_pdf(file_bytes, filename, unique_id):
    from requests_toolbelt.multipart.encoder import MultipartEncoder
    meta = {'name': filename, 'parents': [FOLDER_ID], 'mimeType': 'application/pdf',
            'appProperties': {'telegram_unique_id': unique_id}}
    body = MultipartEncoder(fields={
        'metadata': ('metadata', json.dumps(meta, ensure_ascii=False).encode(), 'application/json; charset=UTF-8'),
        'file': (filename, file_bytes, 'application/pdf'),
    })
    response = requests.post('https://www.googleapis.com/upload/drive/v3/files',
        params={'uploadType': 'multipart', 'fields': 'id,name', 'supportsAllDrives': 'true'},
        headers={**drive_headers(), 'Content-Type': body.content_type},
        data=body, timeout=180)
    response.raise_for_status()
    return response.json()


def main():
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    state = json.loads(STATE_PATH.read_text()) if STATE_PATH.exists() else {}
    offset = int(state.get('next_offset', 0))
    hook = telegram('getWebhookInfo')
    if hook.get('url'):
        raise RuntimeError('This bot has a webhook configured. Polling is disabled; do not delete the webhook without checking the existing receiver.')

    # Telegram keeps pending updates for at most 24 hours. Read in pages, do not
    # use negative offsets or drop_pending_updates.
    count = 0
    while True:
        updates = telegram('getUpdates', offset=offset, limit=100, timeout=0,
                           allowed_updates=json.dumps(['message', 'channel_post']))
        if not updates:
            break
        for update in updates:
            update_id = update['update_id']
            message = update.get('message') or update.get('channel_post') or {}
            chat = message.get('chat', {})
            document = message.get('document') or {}
            chat_id = str(chat.get('id', ''))
            title = chat.get('title', '')
            selected = (chat_id == CHAT_ID) if CHAT_ID else (title == CHAT_TITLE and chat.get('type') in ('group', 'supergroup'))
            if selected and document:
                filename = document.get('file_name', '')
                is_pdf = filename.lower().endswith('.pdf') or document.get('mime_type') == 'application/pdf'
                if is_pdf:
                    if not filename.lower().endswith('.pdf'):
                        filename = (filename or f'telegram_{message.get("message_id", update_id)}') + '.pdf'
                    unique_id = document.get('file_unique_id') or f'{chat_id}-{message.get("message_id", update_id)}'
                    size = int(document.get('file_size', 0))
                    if size > MAX_DOWNLOAD:
                        print(f'SKIP oversized PDF ({size} bytes): {filename}; Telegram Bot API hosted download limit', flush=True)
                    elif already_uploaded(unique_id):
                        print(f'ALREADY UPLOADED: {filename}', flush=True)
                    else:
                        file_info = telegram('getFile', file_id=document['file_id'])
                        file_path = file_info['file_path']
                        url = f'https://api.telegram.org/file/bot{BOT_TOKEN}/{quote(file_path, safe="/")}'
                        download = requests.get(url, timeout=180)
                        download.raise_for_status()
                        if len(download.content) > MAX_DOWNLOAD:
                            print(f'SKIP oversized download: {filename}', flush=True)
                        elif not download.content.startswith(b'%PDF-'):
                            print(f'SKIP non-PDF content: {filename}', flush=True)
                        else:
                            result = upload_pdf(download.content, filename, unique_id)
                            print(f'UPLOADED: {result["name"]} ({result["id"]}) from chat {chat_id}', flush=True)
            offset = update_id + 1
            state['next_offset'] = offset
            STATE_PATH.write_text(json.dumps(state, indent=2) + '\n')
            count += 1
        if len(updates) < 100:
            break
    print(f'Processed {count} Telegram updates; next offset={offset}.', flush=True)


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        # Avoid logging URLs, tokens or authorization headers.
        print(f'Ingest failed: {type(exc).__name__}: {str(exc)[:300]}', file=sys.stderr)
        sys.exit(1)
