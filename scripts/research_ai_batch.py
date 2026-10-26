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
SCHEMA = 'research-batch-v2'
TARGET_REPROCESS_IDS = {'line-eb38fe730115b004ab61', 'line-d254637831a810ab2161', 'line-989d0430b6a71dde3aac'}
TRIAL_SUFFIX = '::gpt-5.6-luna-trial-v1'


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


SYSTEM_PROMPT = '''你是台灣上市櫃法說會及 call memo 的研究資料整理員。你會收到 Excel A～W 各欄位，欄位名稱和原文均為證據。
任務是為長期可視覺化追蹤建立完整的研究資料，而不只是摘要。
請完整掃描所有欄位：I、J、P 等已整理數字非常重要，U～W 原文用來補充與核對。不得只讀原文，也不得因原文缺失就丟棄其他欄位的資料。
僅擷取來源確實支持的事實；絕對不要補造數字、日期、券商或公司。
以繁體中文輸出 JSON object，包含 title、summary (字串陣列)、companies (陣列)。
每家公司可有 name、ticker、key_points、financials、guidance、operating_metrics、valuations、risks、unstructured_notes。
financials、guidance、operating_metrics、valuations 均為自由長度陣列，不要求任何欄位必填。每個數字物件盡量提供：
metric(指標名稱不限)、period(例 3Q26、1H26、2027E)、value(原文數字字串)、unit、actual_or_estimate(actual/estimate/guidance/unknown)、source_type(company/broker/unknown)、provider(來源機構若可辨)、evidence(來源中的原文連續短句)、source_column(例如 I、J、P、U)、qualifier(exact/range/at_least/at_most/approximate/qualitative)。
有區間則保留原區間；年度、季度、累計、半年不可混用；公司指引、券商預估、實績必須分開；多家公司、多券商分別標註。
強制期間：前三季/1~9月=9MYY、上半年/1~6月=1HYY，絕不能寫成Q3/Q2單季。
來源為券商財報前瞻且句子含「我們預估」「我們預期」「我們認為」時，一律是券商 estimate，不得當成公司 actual。公司已公布的歷史營收/財報實績才能標 actual。
「約」「接近」「多元」「超過」「略低」不得標 exact，須分別保留 approximate/at_least/at_most。
evidence 必須從某個 Excel 欄位原封不動複製一段連續文字，不得自行改寫或拼接；source_column 必須是實際包含該 evidence 的欄位。
對無法確認期間、公司歸屬或數值性質的資訊，保留在 unstructured_notes，絕不可硬猜。
目標價或評等只有原文明確寫出且來源歸屬清楚時才填入 valuations；call memo 不要求有目標價。
不要求完整三表；任何已確認的現金流、負債比、CAPEX、訂單、稼動率、產品占比等都應保留。
如 Excel 不同欄位有衝突，分別保留並於 notes 說明，不要自行裁決。'''


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
    issues = []
    count = 0
    if not isinstance(result, dict) or not isinstance(result.get('companies'), list):
        return {'status':'needs_review','financial_count':0,'issues':['companies 格式不正確']}
    fields = source_fields(row)
    for company in result['companies']:
        if not isinstance(company, dict):
            issues.append('公司格式不正確')
            continue
        for section in ('financials', 'guidance', 'operating_metrics', 'valuations'):
            facts = company.get(section) or []
            if not isinstance(facts, list):
                issues.append(f'{section} 格式不正確')
                continue
            for fact in facts:
                count += 1
                if not isinstance(fact, dict):
                    issues.append(f'{section} 項目非物件')
                    continue
                evidence = str(fact.get('evidence') or '').strip()
                col = str(fact.get('source_column') or '').strip().upper()
                matched = [v for k, v in fields.items() if k.startswith(col + ' ')] if col else []
                if not evidence or not any(evidence in v for v in fields.values()):
                    issues.append(f"{company.get('name','?')} {fact.get('metric','?')}: 證據不在 Excel A-W")
                elif col and (not matched or not any(evidence in v for v in matched)):
                    issues.append(f"{company.get('name','?')} {fact.get('metric','?')}: 來源欄位不吻合")
                if not str(fact.get('metric') or '').strip():
                    issues.append('指標名稱缺失')
                if not str(fact.get('value') or '').strip() and section != 'guidance':
                    issues.append('數值缺失')
                # Missing periods or qualitative guidance should be reviewed, not rejected.
                if not fact.get('period'):
                    issues.append(f"{company.get('name','?')} {fact.get('metric','?')}: 期間不明")
                if re.search(r'前三季|前3季|1\s*[~～至-]\s*9\s*月', evidence) and re.search(r'^[34]Q', str(fact.get('period') or ''), re.I):
                    issues.append(f"{company.get('name','?')} {fact.get('metric','?')}: 累計期間誤作單季")
                if str(fact.get('qualifier') or '') == 'exact' and re.search(r'約|接近|多元|多億|超過|略低|左右', evidence):
                    issues.append(f"{company.get('name','?')} {fact.get('metric','?')}: 約數誤標 exact")
                if str(fact.get('actual_or_estimate') or '') == 'actual' and re.search(r'我們預估|我們預期|預估|預期', evidence) and str(fact.get('source_type') or '') == 'broker':
                    issues.append(f"{company.get('name','?')} {fact.get('metric','?')}: 券商預估誤標實績")
    return {'status':'needs_review' if issues else 'passed',
            'financial_count':count,'issues':issues[:60]}


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
