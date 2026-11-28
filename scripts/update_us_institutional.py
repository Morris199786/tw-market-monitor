"""SEC quarterly 13F holdings; match explicitly configured CUSIPs only, never infer from issuer names."""
import datetime as dt, json, io, zipfile, csv, re
from urllib.parse import urljoin
from collections import defaultdict
from update_us_insider import get,SEC,ROOT
import requests,time
def quarters(now):
 y,q=now.year,(now.month-1)//3+1
 for _ in range(4):
  yield y,q
  q-=1
  if q==0:y-=1;q=4
def table(z,name):
 f=next((x for x in z.namelist() if x.rsplit("/",1)[-1].upper()==name.upper()),None)
 if not f:raise ValueError("Missing "+name)
 return csv.DictReader(io.TextIOWrapper(z.open(f),encoding="utf-8-sig"),delimiter="\t")
def main():
 cfg=json.loads((ROOT/"institutional_watchlist.json").read_text())
 cusips={x["cusip"]:x["ticker"] for x in cfg["securities"]}
 if not cusips:raise RuntimeError("No verified CUSIP mappings")
 now=dt.date.today(); filings={}; positions=defaultdict(int); sources=[]
 page=get(SEC+"/data-research/sec-markets-data/form-13f-data-sets").text
 links=list(dict.fromkeys(urljoin(SEC,x) for x in re.findall(r'href=["\']([^"\']+\.zip)["\']',page,re.I) if "13f" in x.lower()))
 def archive_end(url):
  m=re.search(r'-(\d{2}[a-z]{3}\d{4})_form13f\.zip
  r=get(url)
  if r is None:raise RuntimeError("Missing advertised dataset "+url)
  z=zipfile.ZipFile(io.BytesIO(r.content));sources.append(url)
  for x in table(z,"SUBMISSION.tsv"):
   if x.get("SUBMISSIONTYPE") not in ("13F-HR","13F-HR/A"):continue
   acc=x.get("ACCESSION_NUMBER");filings[acc]=dict(cik=x.get("CIK"),period=x.get("PERIODOFREPORT"),filed=x.get("FILING_DATE"),form=x.get("SUBMISSIONTYPE"))
  for x in table(z,"INFOTABLE.tsv"):
   acc=x.get("ACCESSION_NUMBER");cusip=x.get("CUSIP","").strip().upper()
   if cusip not in cusips or acc not in filings or x.get("PUTCALL") or x.get("SSHPRNAMTTYPE")!="SH":continue
   try:positions[(acc,cusip)]+=int(float(x["SSHPRNAMT"]))
   except (ValueError,KeyError):continue
 if len(sources)<2 or not positions:raise RuntimeError("No matched official holdings; preserve prior output")
 # Do not infer new/closed positions from missing submissions. Amendments require reconciliation.
 def iso(s):
  for fmt in ("%d-%b-%Y","%Y-%m-%d","%m/%d/%Y"):
   try:return dt.datetime.strptime(s or "",fmt).date().isoformat()
   except ValueError:pass
  return None
 amendments=set(); latest={}
 for acc,f in filings.items():
  p=iso(f["period"]);d=iso(f["filed"])
  if not p or not d or not f["cik"] or p<cutoff or p>now.isoformat():continue
  k=(f["cik"],p)
  if f["form"].endswith("/A"):amendments.add(k);continue
  if k not in latest or d>latest[k][0]:latest[k]=(d,acc)
 by=defaultdict(dict)
 for (cik,p),(d,acc) in latest.items():
  if (cik,p) in amendments:continue
  for cusip,ticker in cusips.items():
   n=positions.get((acc,cusip))
   if n is not None:by[(ticker,cik)][p]=(n,d,acc)
 rows=[]
 for (ticker,cik),hist in by.items():
  dates=sorted(hist)
  for p in dates:
   n,d,acc=hist[p];prev=[x for x in dates if 80<=(dt.date.fromisoformat(p)-dt.date.fromisoformat(x)).days<=100]
   if not prev:continue
   old=hist[prev[-1]][0]
   rows.append(dict(ticker=ticker,cik=cik,period=p,previous_period=prev[-1],filed=d,shares=n,previous_shares=old,change=n-old,accession=acc,url=f"{SEC}/Archives/edgar/data/{int(cik)}/{acc.replace('-','')}/"))
 latest_expected=(dt.date(now.year,((now.month-1)//3)*3+1,1)-dt.timedelta(days=1))
 if now<latest_expected+dt.timedelta(days=45):
  latest_expected=dt.date(latest_expected.year,((latest_expected.month-1)//3)*3+1,1)-dt.timedelta(days=1)
 if not rows:raise RuntimeError('No comparable consecutive-quarter positions')
 payload=dict(updated_at=dt.datetime.now(dt.timezone.utc).isoformat(),sources=sources,rows=rows,coverage=sorted(set(cusips.values())),expected_period=latest_expected.isoformat(),latest_period=max(x["period"] for x in rows),missing_expected_period=max(x["period"] for x in rows)<latest_expected.isoformat(),note="僅比較同一申報機構連續兩季均有明確持股的普通股資料；未納入選擇權、修正申報、新建倉或清倉推論。13F 為季末持股，不是即時交易。")
 p=ROOT/"institutional.tmp";p.write_text(json.dumps(payload,ensure_ascii=False,allow_nan=False));p.replace(ROOT/"institutional.json")
if __name__=="__main__":main()
,url,re.I)
  if m:
   try:return dt.datetime.strptime(m.group(1),"%d%b%Y").date()
   except ValueError:pass
  return dt.date.min
 links=sorted((u for u in links if archive_end(u)>dt.date.min),key=archive_end,reverse=True)
 if len(links)<4:raise RuntimeError("Cannot identify four recent SEC archive periods")
 cutoff=(now-dt.timedelta(days=460)).isoformat()
 for url in links[:5]:
  r=get(url)
  if r is None:raise RuntimeError("Missing advertised dataset "+url)
  z=zipfile.ZipFile(io.BytesIO(r.content));sources.append(url)
  for x in table(z,"SUBMISSION.tsv"):
   if x.get("SUBMISSIONTYPE") not in ("13F-HR","13F-HR/A"):continue
   acc=x.get("ACCESSION_NUMBER");filings[acc]=dict(cik=x.get("CIK"),period=x.get("PERIODOFREPORT"),filed=x.get("FILING_DATE"),form=x.get("SUBMISSIONTYPE"))
  for x in table(z,"INFOTABLE.tsv"):
   acc=x.get("ACCESSION_NUMBER");cusip=x.get("CUSIP","").strip().upper()
   if cusip not in cusips or acc not in filings or x.get("PUTCALL") or x.get("SSHPRNAMTTYPE")!="SH":continue
   try:positions[(acc,cusip)]+=int(float(x["SSHPRNAMT"]))
   except (ValueError,KeyError):continue
 if len(sources)<2 or not positions:raise RuntimeError("No matched official holdings; preserve prior output")
 # Do not infer new/closed positions from missing submissions. Amendments require reconciliation.
 def iso(s):
  for fmt in ("%d-%b-%Y","%Y-%m-%d","%m/%d/%Y"):
   try:return dt.datetime.strptime(s or "",fmt).date().isoformat()
   except ValueError:pass
  return None
 amendments=set(); latest={}
 for acc,f in filings.items():
  p=iso(f["period"]);d=iso(f["filed"])
  if not p or not d or not f["cik"]:continue
  k=(f["cik"],p)
  if f["form"].endswith("/A"):amendments.add(k);continue
  if k not in latest or d>latest[k][0]:latest[k]=(d,acc)
 by=defaultdict(dict)
 for (cik,p),(d,acc) in latest.items():
  if (cik,p) in amendments:continue
  for cusip,ticker in cusips.items():
   n=positions.get((acc,cusip))
   if n is not None:by[(ticker,cik)][p]=(n,d,acc)
 rows=[]
 for (ticker,cik),hist in by.items():
  dates=sorted(hist)
  for p in dates:
   n,d,acc=hist[p];prev=[x for x in dates if 80<=(dt.date.fromisoformat(p)-dt.date.fromisoformat(x)).days<=100]
   if not prev:continue
   old=hist[prev[-1]][0]
   rows.append(dict(ticker=ticker,cik=cik,period=p,previous_period=prev[-1],filed=d,shares=n,previous_shares=old,change=n-old,accession=acc,url=f"{SEC}/Archives/edgar/data/{int(cik)}/{acc.replace('-','')}/"))
 if not rows:raise RuntimeError('No comparable consecutive-quarter positions')
 payload=dict(updated_at=dt.datetime.now(dt.timezone.utc).isoformat(),sources=sources,rows=rows,coverage=list(cusips.values()),note="僅比較同一申報機構連續兩季均有明確持股的普通股資料；未納入選擇權、修正申報、新建倉或清倉推論。13F 為季末持股，不是即時交易。")
 p=ROOT/"institutional.tmp";p.write_text(json.dumps(payload,ensure_ascii=False,allow_nan=False));p.replace(ROOT/"institutional.json")
if __name__=="__main__":main()
