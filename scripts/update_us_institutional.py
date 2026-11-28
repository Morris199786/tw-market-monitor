"""SEC quarterly 13F holdings; verified CUSIP/CINS mapping, no issuer-name inference."""
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
 from probe_us_13f_sources import resolve_watchlist, positions as sample_positions
 watch=set(json.loads((ROOT/"watchlist.json").read_text())["tickers"])
 now=dt.date.today(); filings={}; positions=defaultdict(int); sources=[]
 # Use the same resolver that passed the 110/110 acceptance run.
 # The observed filing codes are candidates only; OpenFIGI must verify them.
 sample_base=SEC+"/Archives/edgar/data/1787596/"
 seeds=set(sample_positions(sample_base+"000117266126003632/infotable.xml"))|set(sample_positions(sample_base+"000117266126005103/infotable.xml"))
 cusips=resolve_watchlist(seeds)
 if set(cusips.values())!=watch:raise RuntimeError("Incomplete watchlist identity coverage")
 candidates=set(cusips)
 page=get(SEC+"/data-research/sec-markets-data/form-13f-data-sets").text
 links=list(dict.fromkeys(urljoin(SEC,x) for x in re.findall(r'href=["\']([^"\']+\.zip)["\']',page,re.I) if "13f" in x.lower()))
 def archive_end(url):
  m=re.search(r'-(\d{2}[a-z]{3}\d{4})_form13f\.zip$',url,re.I)
  if m:
   try:return dt.datetime.strptime(m.group(1),"%d%b%Y").date()
   except ValueError:pass
  m=re.search(r'(20\d{2})q([1-4])_form13f\.zip$',url,re.I)
  if m:
   y,q=map(int,m.groups())
   return dt.date(y+int(q==4),q*3%12+1,1)-dt.timedelta(days=1)
  return dt.date.min
 links=sorted((u for u in links if archive_end(u)>dt.date.min),key=archive_end,reverse=True)
 if len(links)<4:raise RuntimeError("Cannot identify recent SEC archives: "+str(links))
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
   if acc not in filings or (x.get("PUTCALL") or "").strip() or x.get("SSHPRNAMTTYPE")!="SH":continue
   if cusip not in candidates:continue
   try:positions[(acc,cusip)]+=int(float(x["SSHPRNAMT"]))
   except (ValueError,KeyError):continue
 if len(sources)<2 or not positions:raise RuntimeError("No matched official holdings; preserve prior output")
 # Bridge the gap between published bulk archives and the current filing index.
 # Use complete submission text (one request per accession), not guessed XML names.
 from xml.etree import ElementTree as ET
 archive_last=archive_end(links[0])
 idx_sources=[]
 bridge_total=0; bridge_ok=0; bridge_failed=[]
 if archive_last<now:
  start=archive_last+dt.timedelta(days=1)
  year,q=start.year,(start.month-1)//3+1
  while (year,q)<=(now.year,(now.month-1)//3+1):
   u=f"{SEC}/Archives/edgar/full-index/{year}/QTR{q}/master.idx"
   r=get(u)
   if r is None:raise RuntimeError("Missing current SEC filing index "+u)
   idx_sources.append(u)
   for line in r.text.splitlines():
    fields=line.split("|")
    if len(fields)!=5 or fields[2] not in ("13F-HR","13F-HR/A") or fields[3]<start.isoformat():continue
    cik,name,form,filed,path=fields
    acc=path.rsplit("/",1)[-1].removesuffix(".txt")
    if acc in filings:continue
    bridge_total+=1
    try:
     raw=get(SEC+"/Archives/"+path)
     if raw is None:raise ValueError("Missing complete filing")
     docs=re.findall(r"<XML>\s*(.*?)\s*</XML>",raw.text,re.I|re.S)
     cover=None;tables=[]
     for doc in docs:
      root=ET.fromstring(doc.strip())
      for e in root.iter():e.tag=e.tag.rsplit("}",1)[-1]
      if root.tag=="edgarSubmission":cover=root
      elif root.tag=="informationTable":tables.append(root)
     if cover is None:raise ValueError("Missing cover")
     period=cover.findtext(".//periodOfReport") or cover.findtext(".//reportCalendarOrQuarter")
     if not period:raise ValueError("Missing reporting period")
     if not tables and form=="13F-HR":raise ValueError("Missing holdings table")
     local=defaultdict(int)
     for root in tables:
      for x in root.findall("infoTable"):
       if (x.findtext("putCall") or "").strip() or x.findtext("shrsOrPrnAmt/sshPrnamtType")!="SH":continue
       c=(x.findtext("cusip") or "").strip().upper()
       if c in candidates:local[c]+=int(x.findtext("shrsOrPrnAmt/sshPrnamt"))
     filings[acc]=dict(cik=cik.zfill(10),period=period,filed=filed,form=form)
     for c,n in local.items():positions[(acc,c)]=n
     bridge_ok+=1
    except Exception as e:
     bridge_failed.append((acc,str(e)[:180]))
    if bridge_total%500==0:print("EDGAR bridge progress:",bridge_ok,"/",bridge_total,"failed:",len(bridge_failed),flush=True)
   q+=1
   if q==5:year+=1;q=1
  print("EDGAR bridge:",bridge_ok,"/",bridge_total,"failed examples:",bridge_failed[:12],flush=True)
  if bridge_failed:raise RuntimeError("Incomplete latest filing bridge; preserve published data")
  sources.extend(idx_sources)
 # Do not infer new/closed positions from missing submissions. Amendments require reconciliation.
 def iso(s):
  for fmt in ("%d-%b-%Y","%Y-%m-%d","%m/%d/%Y","%m-%d-%Y"):
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
   if n is not None:by[(ticker,cik,cusip)][p]=(n,d,acc)
 rows=[]
 for (ticker,cik,cusip),hist in by.items():
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
 actual_coverage=sorted({r["ticker"] for r in rows})
 print("Verified identifiers:",len(set(cusips.values())),"actual historical holdings coverage:",len(actual_coverage),"rows:",len(rows),"latest:",max(r["period"] for r in rows),flush=True)
 payload=dict(updated_at=dt.datetime.now(dt.timezone.utc).isoformat(),sources=sources,rows=rows,coverage=actual_coverage,identifier_coverage=sorted(set(cusips.values())),uncovered_holdings=sorted(watch-set(actual_coverage)),unmapped=sorted(watch-set(cusips.values())),expected_period=latest_expected.isoformat(),latest_period=max(x["period"] for x in rows),missing_expected_period=max(x["period"] for x in rows)<latest_expected.isoformat(),note="僅比較同一申報機構連續兩季均有明確持股的普通股資料；未納入選擇權、修正申報、新建倉或清倉推論。13F 為季末持股，不是即時交易。")
 if payload["missing_expected_period"]:raise RuntimeError("Latest expected quarter absent; preserve published data")
 payload["bridge_filing_count"]=bridge_ok
 if len(actual_coverage)<100:raise RuntimeError("Actual historical holdings coverage below 100; preserve prior file")
 # Publish a tiny index and lossless per-ticker shards. Keep every comparison row.
 from pathlib import Path
 import hashlib
 grouped=defaultdict(list)
 for row in rows:grouped[row["ticker"]].append(row)
 out=ROOT/"institutional_stocks";out.mkdir(exist_ok=True)
 manifest={};summary=defaultdict(list);written=0
 for ticker,stockrows in sorted(grouped.items()):
  if not re.fullmatch(r"[A-Z0-9.\-]+",ticker):raise ValueError("Unsafe ticker")
  blob=json.dumps({"ticker":ticker,"rows":stockrows},ensure_ascii=False,allow_nan=False,separators=(",",":")).encode()
  if len(blob)>20*1024*1024:raise RuntimeError("Ticker shard exceeds deployment limit")
  filename=ticker+".json";tmp=out/(filename+".tmp");tmp.write_bytes(blob);tmp.replace(out/filename)
  manifest[ticker]={"file":"institutional_stocks/"+filename,"count":len(stockrows),"sha256":hashlib.sha256(blob).hexdigest()}
  written+=len(stockrows)
  agg=defaultdict(lambda:dict(up=0,down=0,flat=0,change=0))
  for r in stockrows:
   g=agg[r["period"]];g["up" if r["change"]>0 else "down" if r["change"]<0 else "flat"]+=1;g["change"]+=r["change"]
  for period,g in agg.items():summary[period].append(dict(ticker=ticker,**g))
 assert written==len(rows)
 for file in out.glob("*.json"):
  if file.stem not in manifest:file.unlink()
 payload.pop("rows")
 payload.update(schema_version=2,row_count=written,shards=manifest,summary=dict(summary),rows=[])
 p=ROOT/"institutional.tmp";p.write_text(json.dumps(payload,ensure_ascii=False,allow_nan=False,separators=(",",":")));p.replace(ROOT/"institutional.json")
 print("Published index and shards:",len(manifest),"rows:",written,"uncovered:",payload["uncovered_holdings"],flush=True)
if __name__=="__main__":main()
