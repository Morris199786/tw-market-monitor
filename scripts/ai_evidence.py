"""Conservative evidence equivalence with exact source-span recovery.
Only layout, width, numeric-list conjunctions and exact TWD-style unit arithmetic
are normalized. No fuzzy match, omitted words, rounding or semantic rewriting.
"""
import re,unicodedata
from decimal import Decimal
VERSION='evidence-equivalence-v1'
MONEY=re.compile(r'(?<![\d.,])([+-]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?)(億元|千萬元|百萬元|萬元|千元|元)')
MULTIPLIER={'億元':100000000,'千萬元':10000000,'百萬元':1000000,'萬元':10000,'千元':1000,'元':1}
PUNCT={'，':',','、':',','。':'.','；':';','：':':','％':'%','−':'-','–':'-','—':'-','﹣':'-'}

def canonical_span(text):
    chars=[];starts=[];ends=[]
    for i,c in enumerate(text):
        for ch in unicodedata.normalize('NFKC',c):
            if ch.isspace() or ch in ('\u200b','\ufeff'):continue
            chars.append(PUNCT.get(ch,ch));starts.append(i);ends.append(i+1)
    raw=''.join(chars)
    # Parentheses around Latin abbreviations are layout, not accounting losses.
    remove=set()
    for m in re.finditer(r'\([A-Za-z][A-Za-z0-9 /-]{1,30}\)',raw):remove.update((m.start(),m.end()-1))
    if remove:
        kept=[i for i in range(len(raw)) if i not in remove]
        raw=''.join(raw[i] for i in kept);starts=[starts[i] for i in kept];ends=[ends[i] for i in kept]
    chunks=[];ss=[];ee=[];pos=0
    for match in MONEY.finditer(raw):
        a,b=match.span();chunks.append(raw[pos:a]);ss.extend(starts[pos:a]);ee.extend(ends[pos:a])
        value=Decimal(match.group(1).replace(',',''))*MULTIPLIER[match.group(2)]
        token='§'+format(value,'f').rstrip('0').rstrip('.')+'元§' if '.' in format(value,'f') else '§'+format(value,'f')+'元§'
        chunks.append(token);ss.extend([starts[a]]*len(token));ee.extend([ends[b-1]]*len(token));pos=b
    chunks.append(raw[pos:]);ss.extend(starts[pos:]);ee.extend(ends[pos:]);out=''.join(chunks)
    # Equate list separators only between numeric percentage / money values.
    for match in re.finditer(r'(?<=[%元§])(?:及|與|和|、|,)(?=[+\-\d§])',out):
        a=match.start();out=out[:a]+','+out[a+1:]
    return out,ss,ee

def resolve_quote(quote,source):
    if not isinstance(quote,str) or len(quote)<6:return None
    index=source.find(quote)
    if index>=0:return {'quote':quote,'start':index,'end':index+len(quote),'match':'exact'}
    normalized,starts,ends=canonical_span(source);needle,_,_=canonical_span(quote)
    if len(needle)<6:return None
    index=normalized.find(needle)
    if index<0:return None
    a,b=starts[index],ends[index+len(needle)-1]
    literal=source[a:b]
    # Prevent partial-token matches, especially 1元 against 11元 or -1元.
    if canonical_span(literal)[0]!=needle:
        # Include an opening acronym parenthesis discarded by normalization, so
        # the returned literal span remains balanced and independently verifiable.
        if a>0 and source[a-1] in ('(','（'):a-=1;literal=source[a:b]
        if canonical_span(literal)[0]!=needle:return None
    return {'quote':literal,'start':a,'end':b,'match':'equivalent_format_or_exact_unit','ai_quote':quote}


def evidence_facts(text):
    normalized=canonical_span(text)[0]
    values=re.findall(r'§[+-]?\d+(?:\.\d+)?元§|[+-]?\d+(?:\.\d+)?%?',normalized)
    return {v.replace('§+','§').lstrip('+') for v in values}
