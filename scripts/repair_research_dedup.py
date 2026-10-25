#!/usr/bin/env python3
"""One-time source patch for tw-market-monitor. Run at repository root."""
from pathlib import Path
import ast

sync=Path('scripts/sync_line_research.py')
ai=Path('scripts/ai_research_backfill.py')
if not sync.exists() or not ai.exists():
    raise SystemExit('請在 tw-market-monitor repo 根目錄執行')
s=sync.read_text(encoding='utf-8')
a=ai.read_text(encoding='utf-8')

start=s.index('def is_same_broker_report(')
end=s.index('\ndef attach_ai(',start)
replacement='''def broker_overlap_evidence(row, broker):
    """Date ±2 days only discovers candidates; independent textual evidence confirms duplicates."""
    a=parse_date(row.get('date')); b=parse_date(broker.get('group_date') or broker.get('date'))
    if not a or not b or abs((a-b).days)>2:
        return {'status':'outside_window','date_gap':None}
    gap=(a-b).days
    ra=ticker(row.get('ticker')); rb=ticker(broker.get('ticker') or broker.get('stock_id'))
    if ra and rb and ra!=rb: return {'status':'different_stock','date_gap':gap}
    company_a=normalize(row.get('company')); company_b=normalize(broker.get('name'))
    if not (ra and rb) and (not company_a or company_a!=company_b):
        return {'status':'different_stock','date_gap':gap}
    sa=broker_key(row.get('source')); sb=broker_key(broker.get('broker'))
    if not sa or not sb or not (sa==sb or (len(sa)>=3 and len(sb)>=3 and (sa in sb or sb in sa))):
        return {'status':'different_broker','date_gap':gap}
    # 'period' is not reliably a title: never use it alone to confirm duplication.
    original=normalize(' '.join(str(row.get(k) or '') for k in
        ('story','revenue','eps','guidance','trend','rating_target','numbers','full_text','full_text_2','full_text_3')))
    old=normalize(' '.join(str(broker.get(k) or '') for k in
        ('title','summary','highlights','content','full_text')))
    title=normalize(broker.get('title'))
    # Compare informative overlapping substrings, not company names or dates.
    substantial = len(original)>=160 and len(old)>=160
    direct = substantial and (old[:130] in original or original[:130] in old)
    # Broker summary may be a short extract from a longer LINE report.
    snippets=[old[i:i+65] for i in range(0,max(0,len(old)-64),65)]
    matches=sum(bool(x in original) for x in snippets[:12])
    overlap=substantial and matches>=2
    # Exact substantial title found in LINE text is additional evidence only.
    title_hit=len(title)>=22 and title in original and (direct or overlap)
    if direct or overlap or title_hit:
        return {'status':'confirmed_duplicate','date_gap':gap,'evidence':'content_overlap'}
    return {'status':'needs_review','date_gap':gap,'evidence':'same_stock_broker_near_date'}


def is_same_broker_report(row, broker):
    if row.get('original_type') not in ('個股報告','產業報告','券商評等'):
        return False
    return broker_overlap_evidence(row,broker)['status']=='confirmed_duplicate'

'''
s=s[:start]+replacement+s[end:]
# Candidate audit should include the same ±2 window and explicit evidence.
s=s.replace('abs((day-report_day).days) > 3','abs((day-report_day).days) > 2')
s=s.replace("'status': 'needs_review'})", "'status': broker_overlap_evidence(row,report)['status'],\n                        'date_gap': (day-report_day).days})")
# Audit should not expose a definitive suppression when the report is merely near in date.

needle="    targets=[]\n    for row in history:"
if needle not in a: raise SystemExit('AI 程式版本不同：找不到 targets 區段，未修改檔案')
a=a.replace(needle,"    targets=[]\n    audit=Counter()\n    review=[]\n    confirmed=[]\n    for row in history:")
a=a.replace("        if row['original_type'] not in ('個股報告','產業報告') or not day or not START<=day<=END: continue", "        if row['original_type'] not in ('個股報告','產業報告') or not day or not START<=day<=END: continue\n        audit['in_scope']+=1")
a=a.replace("        if row['id'] in cache: continue", "        if row['id'] in cache:\n            audit['already_cached']+=1\n            continue")
a=a.replace("            print(f'AMBIGUOUS: {row[\"id\"]}; manual review, no API')", "            audit['ambiguous_key']+=1\n            review.append({'id':row['id'],'reason':'ambiguous_key','date':row['date'],'company':row.get('company'),'broker':row.get('source')})\n            print(f'AMBIGUOUS: {row[\"id\"]}; manual review, no API')")
a=a.replace("            cache[row['id']]=dict(cache[index[key][0]],stable_key=key)", "            audit['stable_key_cached']+=1\n            cache[row['id']]=dict(cache[index[key][0]],stable_key=key)")
a=a.replace("            index[key]=[row['id']]\n            continue\n        targets.append((row,key))", "            index[key]=[row['id']]\n            audit['confirmed_broker_duplicate']+=1\n            confirmed.append({'id':row['id'],'broker_report_id':matches[0].get('id'),'date':row['date']})\n            continue\n        # Same stock, same broker, ±2 days but insufficient content evidence: do NOT charge API.\n        from sync_line_research import broker_overlap_evidence\n        uncertain=[b for b in brokers if broker_overlap_evidence(row,b)['status']=='needs_review']\n        if uncertain:\n            audit['broker_needs_review']+=1\n            review.append({'id':row['id'],'reason':'broker_needs_review','date':row['date'],\n                           'company':row.get('company'),'broker':row.get('source'),\n                           'broker_report_ids':[b.get('id') for b in uncertain]})\n            continue\n        targets.append((row,key))")
a=a.replace("    print(f'Eligible unprocessed reports: {len(targets)}')", "    audit['eligible_api']=len(targets)\n    print('AI_BACKFILL_AUDIT '+json.dumps(dict(audit),ensure_ascii=False,sort_keys=True))\n    print('AI_BACKFILL_REVIEW '+json.dumps(review,ensure_ascii=False))\n    print('AI_BACKFILL_CONFIRMED_DUPLICATES '+json.dumps(confirmed,ensure_ascii=False))\n    print('AI_BACKFILL_TARGETS '+json.dumps([{'id':r['id'],'date':r['date'],\n        'company':r.get('company'),'broker':r.get('source'),'type':r['original_type']} for r,_ in targets],ensure_ascii=False))\n    print(f'Eligible unprocessed reports: {len(targets)}')")
# Validate before writing.
ast.parse(s);ast.parse(a)
sync.write_text(s,encoding='utf-8');ai.write_text(a,encoding='utf-8')
print('PATCH_OK: updated scripts/sync_line_research.py and scripts/ai_research_backfill.py')
print('Next run GitHub Action mode=check. No API calls in check mode.')
