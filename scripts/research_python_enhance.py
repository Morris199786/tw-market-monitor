"""Conservative, zero-API research enrichment and routing.
Never invents metrics or replaces original fields. Python 3.10+.
"""
import re

FIELDS = ('story','revenue','eps','inventory','utilization','guidance','trend','rating_target','numbers')
RAW = ('full_text','full_text_2','full_text_3')
METRICS = {
    'revenue': re.compile(r'(?:營收|營業收入|sales|revenue)',re.I),
    'eps': re.compile(r'(?<![A-Za-z])EPS(?![A-Za-z])|每股(?:稅後)?盈餘',re.I),
    'utilization': re.compile(r'稼動率|產能利用率|utilization',re.I),
    'inventory': re.compile(r'庫存|存貨|inventory',re.I),
    'guidance': re.compile(r'展望|財測|預期|預估|預計|明年|202[6-9]|guidance|outlook',re.I),
    'rating_target': re.compile(r'目標價|評等|買進|中立|target price|overweight',re.I),
}
VALUE = re.compile(r'(?:[-+]?\d[\d,]*(?:\.\d+)?\s*(?:%|％|元|億|兆|百萬|千萬|倍|美元|USD)|(?:Q[1-4]|[1-4]Q)\s*\d{2,4})',re.I)
ESTIMATE = re.compile(r'預估|預期|預測|估計|預計|目標|財測|guidance|forecast|estimate|\d{2,4}F\b|\d{2,4}E\b',re.I)
ACTUAL = re.compile(r'實際|公告|已公布|已達|達成|結算|reported|actual',re.I)
COMPANY_SPLIT = re.compile(r'(?m)^\s*(?:[（(]?\d{4}[）)]?\s+|(?:公司|個股)\s*[:：])')

def source(row):
    return '\n'.join(str(row.get(k) or '') for k in RAW)

def excerpts(text, pattern, limit=5):
    """Extract short evidence-bearing sentences; avoid duplicating existing text."""
    chunks=re.split(r'(?<=[。；;\n])|(?=\n)',text)
    found=[]
    for c in chunks:
        c=re.sub(r'\s+',' ',c).strip(' 。；;')
        if 8<=len(c)<=360 and pattern.search(c) and VALUE.search(c) and c not in found:
            found.append(c)
            if len(found)>=limit:break
    return found

def enrich(row):
    """Fill empty fields with source-exact excerpts only; no inference or paid API."""
    raw=source(row)
    out=dict(row)
    if not raw.strip():return out
    for field,pattern in METRICS.items():
        if not str(out.get(field) or '').strip():
            matches=excerpts(raw,pattern,3)
            if matches:out[field]='；'.join(matches)[:1000]
    if not str(out.get('numbers') or '').strip():
        nums=[]
        for k in ('revenue','eps','utilization'):
            v=str(out.get(k) or '').strip()
            if v:nums.append(v[:220])
        if nums:out['numbers']='；'.join(nums)[:700]
    return out

def quality(row):
    """Heuristic QA; missing optional financial metrics never forces API."""
    raw=source(row)
    story=str(row.get('story') or '').strip()
    filled=[k for k in FIELDS if str(row.get(k) or '').strip()]
    issues=[]
    if not story and len(raw)>400:issues.append('missing_summary')
    if raw.count('\ufffd')>3:issues.append('garbled_source')
    if len(raw)>16000 and len(story)<90:issues.append('long_unstructured_source')
    if len(raw)>5000 and not story and COMPANY_SPLIT.search(raw):issues.append('multi_company_unstructured')
    return {'filled_fields':filled,'issues':issues,'requires_ai':bool(issues)}

def decide_route(row):
    category=row.get('category') or ''
    market=row.get('market') or 'TW'
    if market=='US':return 'python'
    if category=='早報':return 'required'
    if category not in ('法說／訪談','產業研究'):return 'python'
    if not source(row).strip():return 'python'
    return 'required' if quality(row)['requires_ai'] else 'python'
