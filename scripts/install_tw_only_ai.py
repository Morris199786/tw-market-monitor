#!/usr/bin/env python3
"""Idempotent patch: exclude US and ambiguous foreign equities BEFORE API planning."""
from pathlib import Path
import ast
p=Path(__file__).resolve().parents[1]/'scripts/ai_research_backfill.py'
s=p.read_text(encoding='utf-8')
marker='# TW_ONLY_AI_GUARD_V1'
if marker in s:
    print('[TW_ONLY] Already installed; no changes')
    raise SystemExit(0)
needle='def make_plan(rows,brokers,inbox,cache,today):'
assert s.count(needle)==1, 'Unexpected upstream code; refuse to patch'
guard='''# TW_ONLY_AI_GUARD_V1
# Fail closed for unknown stock markets: never spend API on a possible US report.
import re

def tw_only_reason(row):
    ticker=str(row.get('ticker') or '').strip().upper()
    market=str(row.get('market') or '').strip().upper()
    company=str(row.get('company') or '').strip()
    if market == 'US': return 'us_market'
    if re.search(r'\\.(?:US|NYSE|NASDAQ)$', ticker): return 'us_exchange_suffix'
    if re.fullmatch(r'[A-Z]{1,5}', ticker): return 'us_equity_ticker'
    if ticker and not re.fullmatch(r'(?:[0-9]{4,6})(?:\\.(?:TW|TWO))?', ticker):
        return 'unverified_foreign_ticker'
    # A company without a Taiwan ticker cannot be verified as a Taiwan stock.
    # Industry reports with no single-stock ticker are permitted only when the
    # subject is explicitly Taiwan-related and contains no US stock symbols.
    if not ticker:
        if row.get('original_type') == '個股報告': return 'missing_tw_ticker'
        if row.get('original_type') == '產業報告':
            if re.search(r'(?i)\\b(?:NASDAQ|NYSE|US STOCK|U\\.S\\. EQUITY)\\b',
                         ' '.join(str(row.get(k) or '')[:400] for k in ('company','industry','story'))):
                return 'us_industry_report'
            # No stock ticker: only allow reports with an explicit Taiwan indicator.
            context=' '.join(str(row.get(k) or '')[:400] for k in ('company','industry','story'))
            if not re.search(r'台灣|台股|臺灣|台廠|TWSE|TPEX|上市|上櫃|TPCA',context,re.I):
                return 'unverified_industry_market'
    return ''

'''
s=s.replace(needle,guard+needle)
needle2="        decision=matcher.decide(row)"
assert s.count(needle2)==1
s=s.replace(needle2,"        us_reason=tw_only_reason(row)\n        if us_reason:\n            result.append({'id':row['id'],'date':row['date'],'company':row.get('company',''),\n                           'source':row.get('source',''),'status':'excluded_us',\n                           'reason':us_reason})\n            continue\n"+needle2)
needle3="        row=lookup[item['id']]; rid=row['id']; status=item['status']"
assert s.count(needle3)==1
s=s.replace(needle3,needle3+"\n        if tw_only_reason(row):\n            print(f'[TW_ONLY][SKIP] {rid} {row.get(\"company\",\"\")} reason={tw_only_reason(row)}',flush=True)\n            continue")
# no changes to API checkpoint or existing ledger
ast.parse(s)
p.write_text(s,encoding='utf-8')
print('[TW_ONLY] Patched AI planning and execution; existing cache untouched')
