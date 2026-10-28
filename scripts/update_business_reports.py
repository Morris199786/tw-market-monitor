"""Read-only Drive metadata sync for 業務報告; never calls an AI API."""
import json, os, re, urllib.parse, urllib.request
from pathlib import Path

FOLDER = '1CLtRfuqr9uC_Sak0VSgYdlhogzG8K2ma'
TOKEN = os.environ['ACCESS_TOKEN']
API = 'https://www.googleapis.com/drive/v3/files'

def list_files():
    token = None
    while True:
        args = {'q': f"'{FOLDER}' in parents and trashed = false and mimeType = 'application/pdf'",
                'fields': 'nextPageToken,files(id,name,createdTime,modifiedTime,webViewLink,description)',
                'pageSize': '1000', 'orderBy': 'createdTime desc'}
        if token: args['pageToken'] = token
        req = urllib.request.Request(API+'?'+urllib.parse.urlencode(args),headers={'Authorization':'Bearer '+TOKEN})
        with urllib.request.urlopen(req,timeout=90) as resp: data=json.load(resp)
        yield from data.get('files',[])
        token=data.get('nextPageToken')
        if not token: break

def extract(r):
    name=r['name']; id=r['id']; description=r.get('description','')
    match=re.search(r'(?<!\d)(\d{4})(?:\s*(?:\.TW|\.TWO|\s*TT|\s*TW))?(?!\d)',name+' '+description,re.I)
    ticker=match.group(1) if match else ''
    date_match=re.search(r'(20\d{2})[-_./]?([01]\d)[-_./]?([0-3]\d)',name)
    date='-'.join(date_match.groups()) if date_match else r.get('createdTime','')[:10]
    return {'id':id,'filename':name,'title':re.sub(r'\.pdf$','',name,flags=re.I),
            'date':date,'ticker':ticker,'company':'','broker':'',
            'url':f'https://drive.google.com/file/d/{id}/view',
            'preview_url':f'https://drive.google.com/file/d/{id}/preview'}

rows=[extract(x) for x in list_files()]
rows.sort(key=lambda r:(r['date'],r['filename']),reverse=True)
p=Path('data/business_reports.json');p.parent.mkdir(parents=True,exist_ok=True)
p.write_text(json.dumps({'items':rows},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(f'Indexed {len(rows)} business PDFs into {p}; no PDF content and no AI API processed.')
