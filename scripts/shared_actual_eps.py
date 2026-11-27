"""Conservative explicit quarter-column reader for saved MOPS notices."""
import re
import unicodedata
NUM=r'[+-]?(?:\d+(?:,\d{3})*|\d+)(?:\.\d+)?'
TOKEN=re.compile(r'\(?'+NUM+r'\)?%?')
EPS=re.compile(r'(?:稅後)?每股(?:盈餘|純益|獲利)(?:\s*\((?:元(?:/股)?|虧損|除權後追溯調整|損益)\))*\s*')
def explicit_quarter(detail,period):
    if not re.fullmatch(r'20\d{2}-Q[1-4]',str(period)):return None
    s=unicodedata.normalize('NFKC',str(detail or ''))
    year=int(period[:4])-1911
    q=int(period[-1])
    qtext=f'(?:{q}|{"一二三四"[q-1]})'
    now=rf'{year}\s*年?\s*第?\s*{qtext}\s*季'
    prev=rf'{year-1}\s*年?\s*第?\s*{qtext}\s*季'
    # Separate current/prior-year quarter block. Require both headers before EPS.
    for m in re.finditer(r'(?:單季|最近一季單季)',s):
        chunk=s[m.end():m.end()+1500]
        chunk=re.split(r'最近四季累計|最近四季\(累計\)|科目/單季',chunk,maxsplit=1)[0]
        em=EPS.search(chunk)
        if not em:continue
        head=chunk[:em.start()]
        a=re.search(now,head);b=re.search(prev,head)
        if not a or not b or a.start()>=b.start():continue
        tokens=TOKEN.findall(chunk[em.end():em.end()+100])
        if len(tokens)<2 or tokens[0].endswith('%') or tokens[1].endswith('%'):continue
        if len(tokens)>=3 and not tokens[2].endswith('%') and '增減%' not in head and '增減 %' not in head:continue
        return parse(tokens[0])
    # Combined month/quarter table, with explicit YoY columns and current quarter.
    for m in re.finditer(r'最近一季',s):
        chunk=s[m.start():m.start()+1800]
        em=EPS.search(chunk)
        if not em:continue
        head=chunk[:em.start()]
        a=re.search(now,head)
        if not a or not re.search(r'最近四季|114年第|115年第|116年第',head) or not re.search(r'同期增減|期增減|增減%',head):continue
        if re.search(prev,head):continue
        tokens=TOKEN.findall(chunk[em.end():em.end()+110])
        # Strict percentage signs on both YoY columns, otherwise abstain.
        if len(tokens)>=4 and tokens[1].endswith('%') and tokens[3].endswith('%') and not tokens[2].endswith('%'):
            return parse(tokens[2])
    return None
def parse(v):
    try:return -float(v[1:-1].replace(',','')) if v.startswith('(') and v.endswith(')') else float(v.replace(',',''))
    except ValueError:return None
