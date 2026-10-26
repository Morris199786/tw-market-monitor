"""LINE research: evidence-preserving Python cleanup and conservative API routing.
No paid calls. Raw source and existing summaries are never overwritten.
"""
import re

RAW = ('full_text', 'full_text_2', 'full_text_3')
FIELDS = ('story', 'revenue', 'eps', 'inventory', 'utilization', 'guidance', 'trend', 'rating_target', 'numbers')
TOPICS = {
    'revenue': r'營收|營業收入|revenue|sales',
    'eps': r'(?<![A-Za-z])EPS(?![A-Za-z])|每股(?:稅後)?盈餘',
    'gross_margin': r'毛利率|gross margin|GPM',
    'outlook': r'展望|財測|預期|預估|預計|guidance|outlook',
    'capacity': r'產能|稼動率|擴產|utilization',
    'orders': r'訂單|在手訂單|接單|backlog',
    'growth': r'YoY|QoQ|年增|季增|年減|季減',
}
EXTRACT = {
    'revenue': TOPICS['revenue'],
    'eps': TOPICS['eps'],
    'inventory': r'庫存|存貨|inventory',
    'utilization': TOPICS['capacity'],
    'guidance': TOPICS['outlook'],
    'rating_target': r'目標價|評等|買進|中立|target price|overweight',
}
NUMBER = re.compile(r'(?<![\w])[-+]?\d[\d,]*(?:\.\d+)?\s*(?:%|％|億|兆|元|倍|萬|美元|USD)(?![\w])', re.I)
SENTENCE = re.compile(r'(?<=[。；;\n])|(?=\n)')


def source(row):
    return '\n'.join(str(row.get(k) or '') for k in RAW)


def normalize_display(value):
    """Formatting only: keep every number, word, original sentence and section."""
    if isinstance(value, list):
        value = '\n\n'.join(str(v) for v in value if v)
    s = str(value or '').replace('\r\n', '\n').replace('\r', '\n').replace('\x0c', '\n')
    s = re.sub(r'[\t ]+\n', '\n', s)
    s = re.sub(r'\n[ \t]*\n(?:[ \t]*\n)+', '\n\n', s)
    # Add line breaks only at explicit section markers, never split decimals or figures.
    s = re.sub(r'(?<!\n)(?<!\S)(?=(?:【[^\n】]{2,28}】|(?:一|二|三|四|五|六)[、．]))', '', s)
    return s.strip()


def excerpts(text, pattern, limit=5):
    found = []
    for chunk in SENTENCE.split(text):
        chunk = re.sub(r'\s+', ' ', chunk).strip(' 。；;')
        if 8 <= len(chunk) <= 420 and re.search(pattern, chunk, re.I) and NUMBER.search(chunk) and chunk not in found:
            found.append(chunk)
            if len(found) >= limit:
                break
    return found


def enrich(row):
    """Add traceable excerpts to empty fields, never substitute for editorial QA."""
    out = dict(row)
    raw = source(row)
    if not raw.strip():
        return out
    for field, pattern in EXTRACT.items():
        if not str(out.get(field) or '').strip():
            matches = excerpts(raw, pattern, 5)
            if matches:
                out[field] = '；'.join(matches)
    if not str(out.get('numbers') or '').strip():
        parts = [str(out.get(k) or '') for k in ('revenue', 'eps', 'utilization') if out.get(k)]
        if parts:
            out['numbers'] = '；'.join(parts)
    return out


def quality(row):
    """Exemption must be demonstrably safe; uncertainty goes to AI, not Python."""
    raw = source(row).strip()
    summary = str(row.get('story') or '').strip()
    company = str(row.get('company') or '').strip()
    ticker = str(row.get('ticker') or '').strip()
    issues = []
    if not raw: issues.append('no_verifiable_original')
    if len(summary) < 200: issues.append('summary_too_short_to_verify')
    if len(raw) > 4000: issues.append('long_document_requires_comprehension')
    if raw and len(raw) > max(1200, len(summary) * 2.5): issues.append('summary_coverage_uncertain')
    if '\ufffd' in raw or re.search(r'(?m)^.{240,}$', raw): issues.append('layout_or_encoding_problem')
    if re.search(r'(?m)^\s*(?:\|.*\|.*\||[-+]{4,}|={4,}|_{4,})', raw): issues.append('complex_table')
    if re.search(r'(?m)^\s*(?:\(?\d{4}\)?[.．、)）]|[A-Z]{2,6}\s*[:：])', raw): issues.append('potential_multiple_companies')
    if not company or not re.search(r'\d{4}', ticker + ' ' + company): issues.append('company_identity_unverified')
    if company and len(company) >= 2 and company not in (raw + ' ' + summary): issues.append('company_not_found_in_text')
    if re.search(r'(?<!\d)4541(?!\d)', ticker + ' ' + company): issues.append('4541_requires_editorial_review')
    for name, pattern in TOPICS.items():
        if re.search(pattern, raw, re.I) and not re.search(pattern, summary, re.I):
            issues.append('summary_missing_' + name)
    raw_numbers = {re.sub(r'\s+', '', n).replace(',', '') for n in NUMBER.findall(raw)}
    sum_numbers = {re.sub(r'\s+', '', n).replace(',', '') for n in NUMBER.findall(summary)}
    if len(raw_numbers) >= 3 and len(raw_numbers - sum_numbers) > max(1, len(raw_numbers) // 5):
        issues.append('important_numbers_not_in_summary')
    # Preserve existing hand-written full summaries, but do not assume an
    # automatically populated EPS/revenue field proves the story is complete.
    return {'requires_ai': bool(issues), 'issues': issues,
            'source_number_count': len(raw_numbers), 'summary_number_count': len(sum_numbers),
            'filled_fields': [k for k in FIELDS if str(row.get(k) or '').strip()]}


def decide_route(row):
    market = row.get('market') or 'TW'
    category = row.get('category') or ''
    if market == 'US': return 'python'  # Explicit user requirement.
    if category == '早報': return 'required'
    if category in ('市場情報',): return 'python'  # Explicit user requirement.
    if category in ('法說／訪談', '產業研究'):
        # Even if source is empty, AI may still organize the supplied story;
        # the batch itself skips truly empty content.
        return 'required' if quality(row)['requires_ai'] else 'python'
    return 'python'
