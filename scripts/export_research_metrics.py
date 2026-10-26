#!/usr/bin/env python3
"""Publish AI-authored LINE research JSON verbatim. No Python research parsing.

The separate research_metrics.json is deliberately not rewritten here.
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TRIAL_V2 = '::gpt-5.6-luna-full-article-v2'
TRIAL_V1 = '::gpt-5.6-luna-trial-v1'


def load(path, default):
    return json.loads(path.read_text(encoding='utf-8')) if path.is_file() else default


def main():
    manifest = load(ROOT / 'data/research_manifest.json', {})
    if not manifest.get('shards'):
        raise RuntimeError('Research manifest missing; refusing empty publish')
    cache = load(ROOT / 'data/research_ai_cache.json', {})
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
            if not rid or row.get('source_kind') != 'line':
                continue
            typ = str(row.get('original_type') or row.get('type') or '').strip().casefold()
            if typ not in ('call memo','法說會'):
                continue
            # V2 rerun takes precedence. Preserve old paid model output when no V2 exists.
            for key in (rid + TRIAL_V2, rid, rid + TRIAL_V1):
                rec = cache.get(key)
                if not isinstance(rec, dict) or rec.get('status') != 'success':
                    continue
                result = rec.get('result')
                if isinstance(result, dict) and (isinstance(result.get('blocks'), list) or isinstance(result.get('companies'), list)):
                    out[rid] = {'model':rec.get('model'), 'content':result}
                    break
    dest = ROOT / 'data/research_ai_render.json'
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps({'schema':'research-ai-direct-v2','items':out}, ensure_ascii=False, separators=(',',':'))+'\n', encoding='utf-8')
    print('AI_DIRECT_PUBLISHED',len(out))

if __name__ == '__main__':
    main()
