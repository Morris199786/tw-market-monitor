"""Shared, non-truncating broker report presentation; no network calls."""
import math
import re


def upside_text(report):
    value = report.get('implied_upside_pct')
    if value is None or not report.get('upside_basis'):
        return ''
    try:
        value = float(value)
        if not math.isfinite(value):
            return ''
    except (TypeError, ValueError):
        return ''
    label = '隱含漲幅' if value >= 0 else '隱含跌幅'
    return f'（{label} {value:+.1f}%，報告基準）'


def complete_reason(report):
    candidates = [report.get('push_reason'), *(report.get('summary') or []),
                  *(report.get('key_points') or [])]
    headlines = report.get('recommendation_headlines') or []
    for candidate in candidates:
        if not isinstance(candidate, str) or candidate in headlines:
            continue
        text = re.sub(r'\s+', ' ', candidate).strip()
        if not text or text.endswith(('…', '...')):
            continue
        # Skip generated price-only headlines, not causal investment conclusions.
        if '｜' in text and '目標價' in text:
            continue
        if len(text) < 12:
            continue
        # Keep the whole sentence, including dependent clauses and qualifications.
        return text
    return ''


def enrich_upside(report, text):
    """Use an unambiguous cover close, never today's quote or an EPS value."""
    for key in ('implied_upside_pct', 'upside_basis', 'reference_close'):
        report.pop(key, None)
    if report.get('report_type') != 'company' or not report.get('target_price_new'):
        return
    cover = text.split('\f')[0][:5000]
    matches = list(re.finditer(
        r'(?:收盤價|Closing price|Close price)\s*(?:\([^\n)]*\)|（[^\n）]*）)?\s*[:：]?\s*(?:NT\$|TWD|NTD)?\s*(\d[\d,]*(?:\.\d+)?)',
        cover, re.I))
    values = {float(m.group(1).replace(',', '')) for m in matches}
    if not values:
        percentages = list(re.finditer(
            r'(?:隱含漲幅|上漲空間|潛在漲幅|Upside(?:/downside)?)\s*(?:\(%\)|（%）)?\s*[:：]?\s*([+-]?\d+(?:\.\d+)?)\s*%', cover, re.I))
        nums = {float(m.group(1)) for m in percentages}
        if len(nums) == 1:
            report['implied_upside_pct'] = next(iter(nums))
            report['upside_basis'] = {'kind': 'report_stated', 'report_date': report.get('date'),
                                      'evidence': percentages[0].group(0)}
        return
    if len(values) != 1 or next(iter(values)) <= 0:
        return
    close = next(iter(values))
    report['reference_close'] = close
    report['implied_upside_pct'] = (float(report['target_price_new']) / close - 1) * 100
    report['upside_basis'] = {'kind': 'report_close', 'report_date': report.get('date'),
                              'evidence': matches[0].group(0)}
