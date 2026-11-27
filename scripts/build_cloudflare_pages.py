#!/usr/bin/env python3
"""Prepare Cloudflare Pages assets without changing the tracked source data."""
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / '.pages-output'
LIMIT = 25 * 1024 * 1024
CHUNK = 8 * 1024 * 1024
# The broker inbox is a processing ledger, not a website data source.
BACKEND_ONLY = {'data/report_inbox.json'}
TOP = {'assets', 'data', 'config', 'research'}

def write(path, obj):
    path.write_text(json.dumps(obj, ensure_ascii=False, separators=(',', ':'), allow_nan=False), encoding='utf-8')

def main():
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir()
    for src in ROOT.iterdir():
        if src.is_dir() and src.name in TOP:
            shutil.copytree(src, OUT / src.name, ignore=shutil.ignore_patterns('__pycache__', '.git', 'node_modules'))
        elif src.is_file() and (src.suffix in {'.html','.js','.css','.json','.csv','.svg','.png','.ico','.webmanifest','.txt'} or src.name in {'_headers','_redirects','_routes.json'}):
            shutil.copy2(src, OUT / src.name)
    for name in BACKEND_ONLY:
        (OUT / name).unlink(missing_ok=True)
    # Byte splitting preserves the complete ledger (all fields, all history),
    # including future schema changes, without splitting UTF-8 incorrectly.
    source = OUT / 'data/ai_portfolio.json'
    if source.exists():
        raw = source.read_bytes()
        json.loads(raw)
        if len(raw) > CHUNK:
            folder = source.parent / 'ai_portfolio_parts'
            if folder.exists():
                shutil.rmtree(folder)
            folder.mkdir()
            parts = []
            for i, offset in enumerate(range(0, len(raw), CHUNK)):
                part = folder / f'{i:05d}.bin'
                part.write_bytes(raw[offset:offset+CHUNK])
                parts.append('ai_portfolio_parts/' + part.name)
            write(source, {'format':'portfolio-byte-parts-v1','parts':parts,'bytes':len(raw)})
            assert b''.join((source.parent / p).read_bytes() for p in parts) == raw
            print(f'Portfolio: {len(raw):,} bytes split into {len(parts)} lossless parts')
    oversized = [(p.relative_to(OUT),p.stat().st_size) for p in OUT.rglob('*') if p.is_file() and p.stat().st_size > LIMIT]
    if oversized:
        raise SystemExit('Pages asset size limit exceeded: ' + ', '.join(f'{p}: {n:,}' for p,n in oversized))
    print('Pages asset validation passed')

if __name__ == '__main__':
    main()
