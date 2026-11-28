"""Separate verified issuer common-share program evidence from search candidates.
Never treat a missing table/cell as zero or infer currency/scale.
"""
import re, datetime as dt, calendar
from collections import defaultdict
NEG=re.compile(r"\b(?:debt|bonds?|debentures?|convertible|senior notes?|exchangeable notes?|preferred (?:stock|shares)|subsidiar(?:y|ies)|tax withholding|withheld|employee|equity awards?|stock options?|restricted stock units?|redemption|noncontrolling)\b",re.I)
OWN=re.compile(r"\b(?:our|its|the company.s|company.s)\s+(?:outstanding\s+)?(?:class [a-z]\s+)?(?:common stock|common shares|ordinary shares|own shares)\b",re.I)
PROGRAM=re.compile(r"\b(?:share|stock|common stock|ordinary share) repurchase (?:program|plan|authorization)s?\b",re.I)
ZERO=re.compile(r"\b(?:no shares (?:of (?:our|its|the company.s) (?:common stock|ordinary shares) )?were repurchased|(?:we|the company) did not repurchase any (?:shares(?: of (?:our|its) common stock)?|of its common stock|of our common stock))\b",re.I)
DATE=r"(?:January|February|March|April|May|June|July|August|September|October|November|December) \d{1,2}, \d{4}"
def date(s):
 try:return dt.datetime.strptime(s,"%B %d, %Y").date().isoformat()
 except ValueError:return None
def amount(s,scale):
 return int(round(float(s.replace(",",""))*{"million":1e6,"billion":1e9,"thousand":1e3}[scale.lower()]))
def num(s):
 s=s.strip().replace(",","")
 return int(s) if re.fullmatch(r"\d+",s) else None
def classify(doc):
 good=[]; rejected=[]
 for p in doc.get("passages",[]):
  # Keep whole paragraph as context; reject mixed-security paragraphs rather than guess.
  if NEG.search(p):rejected.append(p);continue
  if (OWN.search(p) or PROGRAM.search(p)) and re.search(r"repurchas",p,re.I):good.append(p)
  else:rejected.append(p)
 return good,rejected
def verified(ticker,docs):
 rows=[]; plans=[]; candidates=[]; rejected=0
 for doc in docs:
  good,bad=classify(doc);rejected+=len(bad)
  period=doc.get("period");form=doc.get("form","")
  base=dict(ticker=ticker,filed=doc["filed"],url=doc["url"],source="sec_filing_text")
  for p in good:
   # Explicit zero tied to exact stated reporting period, not authorization date.
   m=re.search(r"\b(?:quarter|three months|fiscal year|year) ended ("+DATE+r")",p,re.I)
   if m and ZERO.search(p) and form in ("10-Q","10-K","20-F","40-F","10-Q/A","10-K/A") and date(m[1])==period:
    scope="quarter" if re.search(r"quarter ended|three months ended",m[0],re.I) else "annual"
    rows.append(dict(base,kind="shares",value=0,unit="shares",end=period,period_scope=scope,evidence=p))
   # A dollar-denominated common-stock authorization with explicit scale.
   m=re.search(r"(?:authorized|approved).{0,150}?(?:up to|aggregate purchase price of)\s+\$\s*([\d,.]+)\s*(million|billion|thousand)\b",p,re.I)
   if m and OWN.search(p) and re.search(r"board of directors",p,re.I):
    event=re.search(r"\bOn ("+DATE+r")",p,re.I)
    plans.append(dict(base,kind="authorization_candidate",value=amount(m[1],m[2]),unit="USD",event_date=date(event[1]) if event else None,evidence=p))
   candidates.append(dict(base,period=period,evidence=p))
  # Tables remain candidates unless security and units are independently established.
  # Never count column (a) as program shares; preserve original table for review.
 return dict(explicit_zero=rows,authorization_candidates=plans,common_candidates=candidates,rejected_passages=rejected,table_candidates=sum(len(x.get("tables",[])) for x in docs))
def audit_payload(d):
 result={t:verified(t,d.get("filing_evidence",{}).get(t,[])) for t in d["coverage"]}
 return dict(issuers=result,summary=dict(issuers=len(result),explicit_zero_issuers=sum(bool(x["explicit_zero"]) for x in result.values()),authorization_candidate_issuers=sum(bool(x["authorization_candidates"]) for x in result.values()),rejected_passages=sum(x["rejected_passages"] for x in result.values())))
