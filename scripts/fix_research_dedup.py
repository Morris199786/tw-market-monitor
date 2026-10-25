#!/usr/bin/env python3
"""Idempotent, offline patch for tw-market-monitor. NEVER calls OpenAI."""
from pathlib import Path
import ast
ROOT = Path(__file__).resolve().parents[1]

def change_once(src, before, after):
    if after in src: return src
    n=src.count(before)
    if n != 1: raise RuntimeError(f'Patch anchor mismatch ({n}): {before[:100]}')
    return src.replace(before,after)

def update(path, fn):
    f=ROOT/path; old=f.read_text(encoding='utf-8'); new=fn(old)
    ast.parse(new,filename=str(f))
    if new != old: f.write_text(new,encoding='utf-8'); print('UPDATED',path)
    else: print('UNCHANGED',path)

EXTRAS = r'''

def excel_document_key(row):
    """Only an explicit document filename + same broker/stock, not vague date."""
    raw='\n'.join(str(row.get(k) or '')[:1500] for k in ('source_row','story','full_text','full_text_2'))
    names=re.findall(r'(?im)(?:原始檔(?:名)?|檔案(?:名稱)?|filename|file name)\s*[:：]\s*([^\n\r|]{3,180}?\.(?:pdf|docx?|pptx?))',raw)
    if not names: return ''
    name=norm(names[0].strip().replace('\\','/').split('/')[-1])
    broker=broker_name(row.get('source'))
    code=','.join(sorted(codes(row))) or norm(row.get('company'))
    return f'{broker}|{code}|{name}' if broker and code and name else ''

def _price(row):
    s='\n'.join(str(row.get(k) or '') for k in ('rating_target','story','numbers'))
    matches=re.findall(r'(?:目標價|target\s*price|\bTP\b)\s*[:：]?\s*(?:\d+(?:\.\d+)?\s*(?:→|->|至|調升至|調降至)\s*)?(\d+(?:\.\d+)?)',s,re.I)
    return float(matches[0]) if matches else None

def _annual_eps(row):
    s='\n'.join(str(row.get(k) or '') for k in ('eps','numbers','story'))
    pairs=re.findall(r'(?<!\d)(20\d{2})\s*(?:年|E|F|預估|預測)?\s*(?:EPS|每股盈餘)?\s*[:：=]?\s*(\d{1,3}\.\d{1,2})(?!\d)',s,re.I)
    pairs+=re.findall(r'(?:EPS|每股盈餘)\s*(?:預估)?\s*(20\d{2})\s*[:：=]?\s*(\d{1,3}\.\d{1,2})(?!\d)',s,re.I)
    return {(int(y),float(v)) for y,v in pairs}

def excel_rating_duplicate(report,rating):
    """Cross-type duplicate only when stock, broker, date, target and annual EPS agree."""
    if report.get('original_type')!='個股報告' or rating.get('original_type')!='券商評等': return False
    a,b=broker_name(report.get('source')),broker_name(rating.get('source'))
    if not a or a!=b: return False
    ca,cb=codes(report),codes(rating)
    if len(ca)!=1 or ca!=cb: return False
    try:
        da=date.fromisoformat(str(report['date'])[:10]); db=date.fromisoformat(str(rating['date'])[:10])
    except (ValueError,KeyError): return False
    if abs((da-db).days)>2: return False
    pa,pb=_price(report),_price(rating)
    if pa is None or pb is None or abs(pa-pb)>.01: return False
    if _annual_eps(report) & _annual_eps(rating): return True
    # Some Sheet rows show '2026/2027 EPS 3.95/3.99' without per-year labels.
    # Require TWO matching decimal EPS figures to avoid accidental merging.
    def eps_values(row):
        raw=str(row.get('eps') or '')
        return {float(v) for v in re.findall(r'(?<!\d)\d{1,2}\.\d{1,2}(?!\d)',raw)}
    return len(eps_values(report) & eps_values(rating))>=2
'''

def dedup(s):
    if 'def excel_document_key(' not in s: s += EXTRAS
    s=change_once(s," '大和':'daiwa','中國信託':'中信','中信投顧':'中信',"," '大和':'daiwa','中國信託':'中信','中信投顧':'中信','中信託':'中信',")
    return s

def ai(s):
    s=change_once(s,'from research_dedup import Matcher, content_key, stable_key, source_ids','from research_dedup import Matcher, content_key, stable_key, source_ids, excel_document_key')
    s=change_once(s,'    seen={}; result=[]','    seen={}; seen_documents={}; result=[]')
    s=change_once(s,"            elif body and body in seen: entry.update(status='excel_duplicate',cache_id=seen[body])", "            elif body and body in seen: entry.update(status='excel_duplicate',cache_id=seen[body])\n            elif (doc := excel_document_key(row)) and doc in seen_documents: entry.update(status='excel_duplicate',cache_id=seen_documents[doc])")
    s=change_once(s,"            else:\n                seen[body]=row['id']", "            else:\n                seen[body]=row['id']\n                if (doc := excel_document_key(row)): seen_documents[doc]=row['id']")
    s=change_once(s,"    lookup={r['id']:r for r in rows}; used=0", "    lookup={r['id']:r for r in rows}; used=0; consecutive_errors=0")
    s=change_once(s,"        src=source_for(row)", "        try: src=source_for(row)\n        except ValueError:\n            item.update(status='needs_review',reason='insufficient_source_text'); continue")
    s=change_once(s,"                'source_ids':sorted(source_ids(row)),'date':row['date'],", "                'source_ids':sorted(source_ids(row)),'document_key':excel_document_key(row),'date':row['date'],")
    s=change_once(s,"    key,body,ids=stable_key(row),content_key(row),source_ids(row)", "    key,body,ids=stable_key(row),content_key(row),source_ids(row)\n    doc=excel_document_key(row)")
    s=change_once(s,"        if e.get('stable_key')==key or (body and e.get('content_key')==body) or (", "        if e.get('stable_key')==key or (body and e.get('content_key')==body) or (doc and e.get('document_key')==doc) or (")
    s=change_once(s,"        if cache[rid]['status']=='unknown':\n            print('Stopped after uncertain API result; no automatic retry')\n            break", "        if cache[rid]['status']=='unknown':\n            consecutive_errors+=1\n            # A validation error is quarantined, NEVER retried. Other errors\n            # and two consecutive failures trigger a fail-closed circuit breaker.\n            if cache[rid]['error_type']!='ValueError' or consecutive_errors>=2:\n                print('Stopped: uncertain or repeated errors; no automatic retry',flush=True)\n                break\n            print('Quarantined validation error; continuing with next NEW report',flush=True)\n        else:\n            consecutive_errors=0")
    return s

def sync(s):
    s=change_once(s,'    from research_dedup import Matcher, content_key\n', '    from research_dedup import Matcher, content_key, excel_document_key, excel_rating_duplicate, codes\n')
    s=change_once(s,'    kept=[]; suppressed=[]; seen_content={}', "    kept=[]; suppressed=[]; seen_content={}; seen_documents={}\n    pdf_by_stock={}\n    for row in data['items']:\n        if row.get('original_type')=='個股報告':\n            for code in codes(row): pdf_by_stock.setdefault(code,[]).append(row)")
    s=change_once(s,"        key=content_key(item)\n", "        if item.get('original_type')=='券商評等':\n            stocks=codes(item)\n            if len(stocks)==1:\n                matches=[pdf for pdf in pdf_by_stock.get(next(iter(stocks)),[]) if excel_rating_duplicate(pdf,item)]\n                if len(matches)==1:\n                    suppressed.append({'excel_id':item['id'],'excel_report_id':matches[0]['id'],'evidence':'same_broker_rating_target_annual_eps'}); continue\n        doc=excel_document_key(item)\n        if doc and doc in seen_documents:\n            suppressed.append({'excel_id':item['id'],'excel_report_id':seen_documents[doc],'evidence':'same_original_document'}); continue\n        key=content_key(item)\n")
    s=change_once(s,"        if key: seen_content[key]=item['id']", "        if key: seen_content[key]=item['id']\n        if doc: seen_documents[doc]=item['id']")
    return s

if __name__=='__main__':
    update('scripts/research_dedup.py',dedup)
    update('scripts/ai_research_backfill.py',ai)
    update('scripts/sync_line_research.py',sync)
    print('PATCH_OK: no API calls, no ledger reset, broker reports remain preferred.')
