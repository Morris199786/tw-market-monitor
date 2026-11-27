#!/usr/bin/env python3
"""Publish AI-authored LINE research verbatim; repair the reader's cache-to-shard fallback.

No LLM calls, no Python editorial review, no replacement of AI writing.
The one-time UI repair preserves the existing research JS and all broker pages.
"""
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TRIAL_V2 = '::gpt-5.6-luna-full-article-v2'
TRIAL_V1 = '::gpt-5.6-luna-trial-v1'
READER_MARKER = '20261110-AI-SHARD-FALLBACK-V1'


def load(path, default):
    return json.loads(path.read_text(encoding='utf-8')) if path.is_file() else default


def eligible_line(row):
    # Source/market scope only; a successfully parsed report is not filtered by category.
    return bool(row.get('id') and row.get('source_kind') == 'line'
                and str(row.get('market', 'TW')).upper() != 'US')


def successful_results(cache):
    """Index all successful cache versions once; keep existing preference."""
    results = {}
    for key, rec in cache.items():
        if not isinstance(rec, dict) or rec.get('status') != 'success':
            continue
        rid = key.split('::', 1)[0]
        content = rec.get('result')
        if not isinstance(content, dict) or not (content.get('blocks') or content.get('companies')):
            continue
        rank = 0 if key == rid + TRIAL_V2 else 1 if key == rid else 2 if key == rid + TRIAL_V1 else 3
        results.setdefault(rid, []).append((rank, key, rec))
    return {rid: [v[2] for v in sorted(vals, key=lambda v: (v[0], v[1]))]
            for rid, vals in results.items()}


def publish_ai():
    manifest = load(ROOT / 'data/research_manifest.json', {})
    if not manifest.get('shards'):
        raise RuntimeError('Research manifest missing; refusing empty publish')
    cache = load(ROOT / 'data/research_ai_cache.json', {})
    successes = successful_results(cache)
    out = {}
    for shard in manifest['shards']:
        filename = shard.get('file', '')
        if not filename or Path(filename).name != filename:
            raise RuntimeError('Unsafe shard name')
        path = ROOT / 'data/research_shards' / filename
        if not path.is_file():
            raise RuntimeError('Missing shard: ' + filename)
        for row in load(path, {}).get('items', []):
            rid = row.get('id')
            if not eligible_line(row):
                continue
            records = successes.get(rid, [])
            if records:
                rec = records[0]
                out[rid] = {'model': rec.get('model'), 'content': rec['result']}
    # Fail loudly if an indexed success cannot be published from its shard.
    meta = load(ROOT / 'data/research_meta.json', [])
    missing = [str(row['id']) for row in meta if eligible_line(row)
               and (row.get('ai_processed') or row['id'] in successes)
               and row['id'] not in out]
    if missing:
        raise RuntimeError('RESEARCH_EXPORT_MISSING: ' + ','.join(missing))
    dest = ROOT / 'data/research_ai_render.json'
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps({'schema': 'research-ai-direct-v2', 'items': out}, ensure_ascii=False, separators=(',', ':')) + '\n', encoding='utf-8')
    print('AI_DIRECT_PUBLISHED', len(out))


def repair_reader_once():
    """Fix the false 'no AI article' screen when an AI result already exists in the shard.

    This only changes reader fallback, not the renderer, AI data, charts or analysis.
    Workflow's existing commit step stages data; we stage these two UI files only
    when changed, so the same run publishes the frontend fix with the data.
    """
    js_path = ROOT / 'assets/research_merged.js'
    html_path = ROOT / 'index.html'
    if not js_path.is_file() or not html_path.is_file():
        raise RuntimeError('Reader JS/index.html missing; no changes made')
    js = js_path.read_text(encoding='utf-8')
    html = html_path.read_text(encoding='utf-8')
    if READER_MARKER in js:
        print('RESEARCH_READER_FIX_ALREADY_PRESENT')
        return

    original = "  const modelHtml=renderAiDirect(direct[r.id]);"
    replacement = '''  // 20261110-AI-SHARD-FALLBACK-V1
  // The sync job stores the actual AI-authored article in each immutable shard.
  // A missing/stale/oversized global render JSON must not hide this paid article.
  // Never invent or rewrite research content: render only a saved AI result.
  const directHtml=renderAiDirect(direct[r.id]);
  const shardHtml=(r.ai_research && typeof r.ai_research==='object')
    ? renderAiDirect({content:r.ai_research}) : '';
  const modelHtml=shardHtml || directHtml;'''
    if js.count(original) != 1:
        raise RuntimeError('Unexpected reader source version; refusing unverified JS modification')
    js = js.replace(original, replacement, 1)

    # Do not mislabel published AI content as "not processed" if both copies are unavailable.
    missing_original = "  const missing=section('AI 研究整理','<p class=\"rm-ai-paragraph\">這篇尚無 AI 完整研究文章；網站不會使用 Python 或固定表格代替模型撰寫。</p>');"
    missing_replacement = "  const missing=section('AI 研究整理',`<p class=\"rm-ai-paragraph\">${m.ai_processed?'AI 全文資料暫時無法載入，請重新整理頁面。':'這篇尚未完成 AI 解析；可查看下方 Excel 原文。'}</p>`);"
    if js.count(missing_original) != 1:
        raise RuntimeError('Unexpected missing-message logic; refusing unverified JS modification')
    js = js.replace(missing_original, missing_replacement, 1)

    # Expose fetch failure instead of masking it silently as an empty AI mapping.
    fetch_original = "  return aiDirectPromise ||= fetchJSON('./data/research_ai_render.json').then(x=>x.items||{}).catch(()=>({}));"
    fetch_replacement = "  return aiDirectPromise ||= fetchJSON('./data/research_ai_render.json').then(x=>x.items||{}).catch(e=>{console.warn('[research reader] global AI JSON unavailable; use AI embedded in report shard',e);return {};});"
    if js.count(fetch_original) != 1:
        raise RuntimeError('Unexpected global AI reader logic; refusing unverified JS modification')
    js = js.replace(fetch_original, fetch_replacement, 1)

    # Force mobile browsers / Pages CDN to fetch the patched script.
    import re
    pattern = r'(\./assets/research_merged\.js\?v=)[^"\']+'
    matches = re.findall(pattern, html)
    if len(matches) != 1:
        raise RuntimeError('Unexpected index.html research script reference; refusing unverified modification')
    html = re.sub(pattern, r'\g<1>20261110-ai-shard-fallback-v1', html, count=1)

    # Validate syntax externally in CI if Node exists, before updating files.
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        candidate = Path(tmp) / 'research_merged.js'
        candidate.write_text(js, encoding='utf-8')
        try:
            p = subprocess.run(['node', '--check', str(candidate)], capture_output=True, text=True)
        except FileNotFoundError:
            p = None
        if p is not None and p.returncode != 0:
            raise RuntimeError('Patched JavaScript syntax check failed: ' + p.stderr[:600])
    js_path.write_text(js, encoding='utf-8')
    html_path.write_text(html, encoding='utf-8')
    # The original workflow only stages data/. Stage just these verified UI files.
    subprocess.run(['git', 'add', '--', 'assets/research_merged.js', 'index.html'], cwd=ROOT, check=True)
    print('RESEARCH_READER_SHARD_FALLBACK_FIXED_AND_STAGED', READER_MARKER)


def main():
    publish_ai()
    repair_reader_once()

if __name__ == '__main__':
    main()
