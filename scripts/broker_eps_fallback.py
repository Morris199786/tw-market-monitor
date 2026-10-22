#!/usr/bin/env python3
"""Conservative local EPS fallback. No network, OpenAI, PDF downloads or retries.

Reads the text already stored by reports-drive in report_inbox.json. Only accepts
explicit broker forecast labels on the same line; ambiguous lines go to review.
"""
from __future__ import annotations
import re
from collections import defaultdict

PERIOD = re.compile(r'(?<!\d)(20\d{2})\s*[-/年 ]\s*Q\s*([1-4])\s*([EFPe f p]?)\b', re.I)
EPS = re.compile(r'(?<![a-z])(?:basic\s+)?EPS|每股(?:稅後)?盈餘|每股盈餘', re.I)
NUMBER = re.compile(r'(?<![\d.])[-+]?\d{1,2}(?:\.\d{1,4})?(?![\d.])')
FORWARD = re.compile(r'預估|預測|預期|forecast|estimate|估計|預計|\bEPS\s*E\b', re.I)
EXCLUDE = re.compile(r'consensus|visible\s*alpha|市場共識|市場預期|actual|實際|已公布|已公告|歷史|reported', re.I)

def extract(text: str):
    """Return (safe rows, review evidence). Fail closed on table ambiguity."""
    candidates = defaultdict(set)
    review = []
    for n, line in enumerate((text or '').splitlines(), 1):
        if not EPS.search(line):
            continue
        periods = list(PERIOD.finditer(line))
        if not periods:
            continue
        if EXCLUDE.search(line):
            review.append({'line': n, 'reason': 'consensus_or_actual', 'text': line[:220]})
            continue
        if len(periods) != 1:
            review.append({'line': n, 'reason': 'multi_period_table', 'text': line[:220]})
            continue
        match = periods[0]
        if not (match[3].upper() in ('E', 'F', 'P') or FORWARD.search(line)):
            review.append({'line': n, 'reason': 'forecast_not_explicit', 'text': line[:220]})
            continue
        # Require an explicit separator between period and value, and only one
        # numeric token AFTER the period. Avoid accidentally reading a year.
        suffix = line[match.end():].strip(' :：=\t')
        numbers = NUMBER.findall(suffix)
        if len(numbers) != 1:
            review.append({'line': n, 'reason': 'ambiguous_numeric_columns', 'text': line[:220]})
            continue
        value = float(numbers[0])
        if not -100 <= value <= 100:
            continue
        candidates[f'{match[1]}-Q{match[2]}'].add(value)
    safe = [{'period': p, 'eps': next(iter(values)), 'source': 'python_fallback'}
            for p, values in sorted(candidates.items()) if len(values) == 1]
    for p, values in candidates.items():
        if len(values) > 1:
            review.append({'period': p, 'reason': 'conflicting_forecasts', 'values': sorted(values)})
    return safe, review
