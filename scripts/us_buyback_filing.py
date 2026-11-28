"""Conservative SEC filing evidence extraction; no AI or inferred zeroes."""
import re, datetime as dt
from bs4 import BeautifulSoup
from urllib.parse import quote

PERIODIC={"10-K","10-Q","20-F","40-F"}
EVENTS={"8-K","6-K"}
def norm(s):return " ".join(s.replace("\xa0"," ").split())
def number(s):
 s=norm(s).replace(",","").replace("$","").strip()
 if not re.fullmatch(r"\d+(?:\.\d+)?",s):return None
 return float(s) if "." in s else int(s)

def extract_html(html):
 soup=BeautifulSoup(html,"html.parser")
 tables=[]; evidence=[]
 for t in soup.find_all("table"):
  if t.find("table"):continue
  txt=norm(t.get_text(" ",strip=True))
  if not re.search(r"(?:shares|stock|securities).{0,65}(?:purchased|repurchased)|(?:purchased|repurchased).{0,65}(?:shares|stock|securities)",txt,re.I):continue
  if not re.search(r"average price paid|publicly announced|maximum (?:number|dollar)|remaining.*(?:authorization|repurchase)",txt,re.I):continue
  grid=[]
  for tr in t.find_all("tr"):
   cells=[norm(x.get_text(" ",strip=True)) for x in tr.find_all(["th","td"],recursive=False)]
   if any(cells):grid.append(cells)
  if grid:tables.append(grid)
 for el in soup.find_all(["p","div"]):
  if el.find(["p","div","table"]):continue
  txt=norm(el.get_text(" ",strip=True))
  if len(txt)<25 or len(txt)>2200:continue
  if not re.search(r"repurchas|buyback|buy.back|purchase of equity securities|purchase of own shares|treasury shares",txt,re.I):continue
  if re.search(r"authoriz|remaining|expir|did not (?:repurchase|purchase)|no (?:shares|stock|purchases|repurchases)|not repurchase any|repurchased.{0,100}(?:million|billion|shares)|not applicable|treasury shares|purchase of equity securities",txt,re.I):
   evidence.append(txt)
 return {"tables":tables,"passages":list(dict.fromkeys(evidence))}

def scan(get,SEC,DSEC,cik,start):
 r=get(f"{DSEC}/submissions/CIK{int(cik):010d}.json")
 if r is None:raise RuntimeError("missing submissions")
 b=r.json()["filings"]["recent"];out=[]
 for form,filed,acc,doc,period in zip(b["form"],b["filingDate"],b["accessionNumber"],b["primaryDocument"],b["reportDate"]):
  if filed<start or form.removesuffix("/A") not in PERIODIC|EVENTS:continue
  base=f"{SEC}/Archives/edgar/data/{int(cik)}/{acc.replace('-','')}/"
  url=base+quote(doc,safe="/")
  f=get(url)
  if f is None:raise RuntimeError("missing "+url)
  parsed=extract_html(f.text)
  # 8-K and 6-K often disclose the decision in an attached press release.
  if form.removesuffix("/A") in EVENTS:
   soup=BeautifulSoup(f.text,"html.parser")
   from urllib.parse import urljoin,urlparse
   links=set()
   for a in soup.find_all("a",href=True):
    label=norm(a.get_text(" ",strip=True))
    if re.search(r"^(?:exhibit\s*)?99(?:\.\d+)?\b|press release",label,re.I):
     link=urljoin(url,a["href"])
     if link.startswith(base) and urlparse(link).path.lower().endswith((".htm",".html")):links.add(link)
   for link in sorted(links):
    docr=get(link)
    if docr is None:raise RuntimeError("missing "+link)
    ev=extract_html(docr.text)
    if ev["tables"] or ev["passages"]:out.append(dict(form=form,filed=filed,period=period,url=link,**ev))
  if parsed["tables"] or parsed["passages"]:out.append(dict(form=form,filed=filed,period=period,url=url,**parsed))
 return out
