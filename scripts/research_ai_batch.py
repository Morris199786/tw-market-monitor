#!/usr/bin/env python3
"""LINE research AI extraction v2: full A-W evidence, one paid attempt per row.

Drop into scripts/research_ai_batch.py. Existing cache successes are never retried.
"""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / 'data/research_ai_cache.json'
AUDIT = ROOT / 'data/research_ai_batch_history.json'
FIELD_NAMES = {
    'date':'A 資料日期', 'type':'B 類型', 'source':'C 來源',
    'industry':'D 產業', 'company':'E 公司', 'ticker':'F 代號',
    'period':'G 期間/事件', 'story':'H 一句話故事',
    'revenue':'I 營收(YoY/QoQ)', 'eps':'J EPS/獲利',
    'inventory':'K 庫存/出貨', 'utilization':'L 產能利用率/稼動率',
    'guidance':'M 展望Guidance', 'trend':'N 產業趨勢/題材',
    'rating_target':'O 評等/目標價', 'numbers':'P 關鍵數字摘要',
    'dividend_current':'Q 現金股利預估(今年)',
    'dividend_next':'R 現金股利預估(明年)',
    'dividend_policy':'S 股利政策', 'source_row':'T 原文rowIndex',
    'full_text':'U 原文全文', 'full_text_2':'V 原文全文2',
    'full_text_3':'W 原文全文3',
}
RAW_KEYS = ('full_text', 'full_text_2', 'full_text_3')
SCHEMA = 'research-full-article-v2'
TARGET_REPROCESS_IDS = {'line-eb38fe730115b004ab61', 'line-d254637831a810ab2161', 'line-989d0430b6a71dde3aac'}
TRIAL_SUFFIX = '::gpt-5.6-luna-full-article-v2'


def load(path, default):
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else default


def write(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def checkpoint(cache):
    """Durably save each attempt before a paid call; fail closed if remote rejects it.

    A workflow may have uncommitted sync outputs. Commit only the ledger, then
    rebase with autostash to handle an independently advanced main branch.
    """
    write(CACHE, cache)
    if os.getenv('RESEARCH_AI_REMOTE_CHECKPOINT') != '1':
        return

    def git(*args):
        return subprocess.run(['git', *args], cwd=ROOT, capture_output=True, text=True)

    def checked(args, label):
        result = git(*args)
        if result.returncode:
            details = (result.stderr or result.stdout or '').strip()[-1500:]
            raise RuntimeError(f'{label}: {details}; refusing paid call')
        return result

    checked(('add', '--', 'data/research_ai_cache.json'), 'Cannot stage attempt ledger')
    diff = git('diff', '--cached', '--quiet')
    if diff.returncode == 0:
        return
    if diff.returncode != 1:
        raise RuntimeError('Cannot inspect staged attempt ledger; refusing paid call')
    checked(('commit', '-m', 'Checkpoint LINE research AI attempt'), 'Cannot commit attempt ledger')

    import time
    for attempt in range(4):
        # Preserve unstaged research sync files while incorporating concurrent
        # commits. Never send a paid request until this ledger reaches main.
        fetched = git('fetch', 'origin', 'main')
        if fetched.returncode:
            details = (fetched.stderr or fetched.stdout or '').strip()[-1000:]
            raise RuntimeError(f'Cannot fetch main: {details}; refusing paid call')
        rebased = git('-c', 'rebase.autoStash=true', 'rebase', 'origin/main')
        if rebased.returncode:
            details = (rebased.stderr or rebased.stdout or '').strip()[-1000:]
            raise RuntimeError(f'Cannot rebase checkpoint: {details}; refusing paid call')
        pushed = git('push', 'origin', 'HEAD:main')
        if pushed.returncode == 0:
            return
        if attempt < 3:
            time.sleep(2 * (attempt + 1))
    details = (pushed.stderr or pushed.stdout or '').strip()[-1500:]
    raise RuntimeError(f'Cannot push attempt ledger after 4 attempts: {details}; refusing paid call')


def allowed_type(value):
    import unicodedata
    value = unicodedata.normalize('NFKC', str(value or '')).strip().casefold()
    return re.sub(r'\s+', ' ', value) in ('call memo', '法說會')


def source_fields(row):
    """Send every nonempty A-W column, retaining the original field labels."""
    return {label: str(row.get(key) or '') for key, label in FIELD_NAMES.items()
            if str(row.get(key) or '').strip()}


def content(row):
    return json.dumps(source_fields(row), ensure_ascii=False, indent=2)


def route(row):
    if row.get('market') == 'US':
        return 'python'
    if allowed_type(row.get('original_type') or row.get('type')):
        return 'required'
    return row.get('api_route') or 'none'


SYSTEM_PROMPT = '''你是專業台股產業研究分析師。完整閱讀 Excel A–W 原文，直接產生可刊登在網站的繁體中文研究整理。所有文章的取捨、章節、文字深度、數字比較與是否使用表格，均由你自主決定；Python 不負責寫作、組表、比對原文或篩選內容。

輸出唯一 JSON 物件：
{"title":"文章標題","summary":["適合首頁閱讀的精簡重點"],"blocks":[{"type":"heading|paragraph|bullets|table|quote|chart","text":"heading/paragraph/quote 的文字","items":["bullets 條目"],"columns":["table 欄名"],"rows":[["table 儲存格"]]}]}

summary 僅供首頁卡片，blocks 必須是獨立完整的 AI 研究全文，不可只重複 summary。按照原文資訊量完整整理背景、營運數據、業務驅動、比較、展望、風險及重要問答；文章短則精簡，長則深入，不得硬湊固定章節或固定表格。數字多且適合比較時主動設計表格；只有敘事時以段落呈現；可以交錯使用表格與文字。表格欄位與列數由你自行決定，絕不固定。

所有視覺化也由你自主選擇：除了 table，必要時可使用 chart 區塊，格式為 {"type":"chart","chart_type":"bar|line|donut","title":"圖表標題","labels":["項目"],"values":[數值],"unit":"單位","note":"資料期間與性質"}。只有數值可比且有明確同單位時才使用圖表；不要虛構數字，也不要把預估與實績混成同一口徑。對於缺少日期、期間或資料無法判定的欄位，不要輸出 unknown，改以文字說明或省略不重要的欄位。數字和單位在同一個儲存格只寫一次。忠於來源，不得虛構。清楚區分公司指引、券商估計、歷史實績及推論；保留期間、單位、約數、範圍和重要條件。若原文沒有的資料，不要補造。避免冗長重複、空泛總結。不要輸出 markdown，只輸出合法 JSON。'''


def parse(text, model):
    # GPT-5 family: Responses API, no unsupported temperature/JSON-mode settings.
    payload = {
        'model': model,
        'instructions': SYSTEM_PROMPT + '\n僅輸出合法 JSON object，不要 markdown。',
        'input': text,
    }
    request = urllib.request.Request(
        'https://api.openai.com/v1/responses',
        data=json.dumps(payload, ensure_ascii=False).encode('utf-8'),
        headers={'Authorization': 'Bearer ' + os.environ['OPENAI_API_KEY'],
                 'Content-Type': 'application/json'},
    )
    with urllib.request.urlopen(request, timeout=300) as response:
        data = json.load(response)
    parts = []
    for item in data.get('output', []):
        if item.get('type') == 'message':
            for c in item.get('content', []):
                if c.get('type') == 'output_text':
                    parts.append(c.get('text', ''))
    body = ''.join(parts).strip()
    if body.startswith('```'):
        body = re.sub(r'^```(?:json)?\s*|\s*```$', '', body).strip()
    if not body:
        raise ValueError('Responses API returned no output_text')
    return json.loads(body), data.get('usage', {})


def audit(result, row):
    """Only verify the JSON can be displayed; editorial judgment belongs to AI."""
    if not isinstance(result, dict) or not isinstance(result.get('blocks'), list) or not result['blocks']:
        return {'status':'needs_review','issues':['AI 輸出缺少 blocks 陣列']}
    allowed = {'heading','paragraph','bullets','table','quote','chart'}
    for block in result['blocks']:
        if not isinstance(block, dict) or block.get('type') not in allowed:
            return {'status':'needs_review','issues':['AI 區塊格式無法顯示']}
    for block in result['blocks']:
        if block.get('type') == 'chart':
            labels, values = block.get('labels'), block.get('values')
            if (block.get('chart_type') not in ('bar','line','donut') or
                not isinstance(labels,list) or not isinstance(values,list) or
                not labels or len(labels)!=len(values) or
                any(not isinstance(v,(int,float)) or isinstance(v,bool) for v in values)):
                return {'status':'needs_review','issues':['AI 圖表資料格式不完整']}
    return {'status':'passed','issues':[],'blocks':len(result['blocks'])}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--limit', type=int, default=10)
    parser.add_argument('--category', choices=['all','morning','meeting','industry'], default='all')
    parser.add_argument('--mode', choices=['pending','failed','rerun_three'], default='pending')
    parser.add_argument('--model', default=os.getenv('RESEARCH_AI_MODEL', 'gpt-5.6-luna'))
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    if not 1 <= args.limit <= 200:
        sys.exit('limit must be 1..200')
    cache = load(CACHE, {})
    history = load(AUDIT, [])
    manifest = load(ROOT / 'data/research_manifest.json', {})
    if not manifest.get('shards'):
        sys.exit('research_manifest.json missing or empty; sync first')
    entries, seen = [], set()
    stats = {'shard_rows':0,'line_rows':0,'required':0,'duplicate_text':0,
             'cached':0,'eligible':0,'by_category':{},'by_route':{},
             'missing_category':0,'missing_api_route':0}
    for shard in manifest['shards']:
        path = ROOT / 'data/research_shards' / shard['file']
        for row in load(path, {}).get('items', []):
            stats['shard_rows'] += 1
            if row.get('source_kind') != 'line' or not allowed_type(row.get('original_type') or row.get('type')):
                continue
            if row.get('market') == 'US':
                continue
            stats['line_rows'] += 1
            cat = row.get('category') or '(missing)'
            stats['by_category'][cat] = stats['by_category'].get(cat, 0) + 1
            rt = route(row)
            stats['by_route'][rt] = stats['by_route'].get(rt, 0) + 1
            if not row.get('category'): stats['missing_category'] += 1
            if not row.get('api_route'): stats['missing_api_route'] += 1
            if rt != 'required': continue
            stats['required'] += 1
            if args.category == 'morning' and cat != '早報': continue
            if args.category == 'meeting' and cat != '法說／訪談': continue
            if args.category == 'industry' and cat != '產業研究': continue
            raw = content(row)
            if not raw.strip(): continue
            fp = hashlib.sha256(raw.encode('utf-8')).hexdigest()
            if fp in seen:
                stats['duplicate_text'] += 1
                continue
            seen.add(fp)
            old = cache.get(row['id'])
            if args.mode == 'rerun_three' and row['id'] not in TARGET_REPROCESS_IDS:
                continue
            if args.mode == 'rerun_three' and (cache.get(row['id'] + TRIAL_SUFFIX) is not None):
                stats['cached'] += 1
                continue
            if args.mode == 'pending' and old is not None:
                stats['cached'] += 1
                continue
            if args.mode == 'failed' and (not old or old.get('status') not in ('failed','needs_review')):
                continue
            entries.append((row, raw, fp))
    entries.sort(key=lambda x: (x[0].get('date',''),x[0].get('id','')), reverse=True)
    stats['eligible'] = len(entries)
    print('BATCH_DIAGNOSTICS ' + json.dumps(stats, ensure_ascii=False, sort_keys=True))
    selected = entries[:args.limit]
    if args.mode == 'rerun_three' and args.model != 'gpt-5.6-luna':
        sys.exit('rerun_three requires gpt-5.6-luna')
    if args.dry_run:
        print('DRY_RUN_NO_API ' + json.dumps([
            {'id':r['id'],'category':r.get('category'),'source':r.get('source'),
             'date':r.get('date'),'title':str(r.get('story') or '')[:90]}
            for r,_,_ in selected], ensure_ascii=False))
        return
    if stats['missing_category'] or stats['missing_api_route']:
        sys.exit('RESEARCH_SYNC_REQUIRED: run LINE research sync before paid batch')
    if selected and not os.getenv('OPENAI_API_KEY'):
        sys.exit('OPENAI_API_KEY missing; no calls made')
    run = {'at':datetime.datetime.now(datetime.timezone.utc).isoformat(),
           'category':args.category,'mode':args.mode,'limit':args.limit,
           'model':args.model,'results':[]}
    for row, raw, fp in selected:
        rid = row['id']
        trial = args.mode == 'rerun_three'
        key = rid + TRIAL_SUFFIX if trial else rid
        # A trial has a separate immutable claim, leaving the old result untouched.
        cache[key] = {'status':'attempted','fingerprint':fp,
                      'category':row.get('category'),'model':args.model,'at':run['at'],
                      'original_id':rid if trial else None}
        checkpoint(cache)
        try:
            result, usage = parse(raw, args.model)
            check = audit(result, row)
            status = 'success' if check['status'] == 'passed' else 'needs_review'
            cache[key].update({'status':status,'schema':SCHEMA,'result':result,
                               'audit':check,'usage':usage})
            # Promote only fully verified results; never overwrite old results on errors.
            # Keep the original version in the new record for audit and rollback.
            if trial and status == 'success':
                promoted = dict(cache[key])
                promoted['previous_version'] = cache.get(rid)
                cache[rid] = promoted
            run['results'].append({'id':rid,'status':status,'audit':check,'usage':usage,
                                   'promoted':trial and status == 'success'})
        except Exception as exc:
            cache[key].update({'status':'failed','error':str(exc)[:300]})
            run['results'].append({'id':rid,'status':'failed','error':str(exc)[:300]})
        checkpoint(cache)
        print(f"{rid}: {cache[key]['status']}" + (' (trial)' if trial else ''))
    history.append(run)
    write(AUDIT, history)
    print(json.dumps({'processed':len(selected),
                      'status_counts':{s:sum(x['status']==s for x in run['results'])
                                       for s in ('success','needs_review','failed')}},
                     ensure_ascii=False))

if __name__ == '__main__':
    main()
