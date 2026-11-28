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
 now=dt.date.today(); filings={}; positions=defaultdict(int); market_values=defaultdict(int); sources=[]
 # Use the same resolver that passed the 110/110 acceptance run.
 # The observed filing codes are candidates only; OpenFIGI must verify them.
 sample_base=SEC+"/Archives/edgar/data/1787596/"
 seeds=set(sample_positions(sample_base+"000117266126003632/infotable.xml"))|set(sample_positions(sample_base+"000117266126005103/infotable.xml"))
 cusips=resolve_watchlist(seeds)
 if set(cusips.values())!=watch:raise RuntimeError("Incomplete watchlist identity coverage")
 candidates=set(cusips)
 import os
 snapshot_dir=os.environ.get("SEC_13F_SNAPSHOT_DIR")
 cutoff=(now-dt.timedelta(days=460)).isoformat()
 if not snapshot_dir:
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
   for x in table(z,"COVERPAGE.tsv"):
    acc=x.get("ACCESSION_NUMBER")
    if acc in filings:
     f=filings[acc];f["manager_name"]=(x.get("FILINGMANAGER_NAME") or "").strip()
     f["amendment_type"]=x.get("AMENDMENTTYPE");f["amendment_number"]=x.get("AMENDMENTNO")
     f["report_type"]=x.get("REPORTTYPE")
   for x in table(z,"SUMMARYPAGE.tsv"):
    acc=x.get("ACCESSION_NUMBER")
    if acc in filings:filings[acc]["confidential"]=x.get("ISCONFIDENTIALOMITTED")
   for x in table(z,"INFOTABLE.tsv"):
    acc=x.get("ACCESSION_NUMBER");cusip=x.get("CUSIP","").strip().upper()
    if acc not in filings or (x.get("PUTCALL") or "").strip() or x.get("SSHPRNAMTTYPE")!="SH":continue
    if cusip not in candidates:continue
    try:
     positions[(acc,cusip)]+=int(float(x["SSHPRNAMT"]))
     if x.get("VALUE"):market_values[(acc,cusip)]+=int(float(x["VALUE"]))
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
      try:
       raw=get(SEC+"/Archives/"+path)
       if raw is None:raise ValueError("Missing complete filing")
       docs=re.findall(r"<XML>\s*(.*?)\s*</XML>",raw.text,re.I|re.S)
      except requests.HTTPError as exc:
       # A gateway timeout on a large complete submission can be avoided by
       # reading its officially indexed XML attachments. Never retry a denial.
       if exc.response is None or exc.response.status_code not in (502,503,504):raise
       time.sleep(15)
       base=f"{SEC}/Archives/edgar/data/{int(cik)}/{acc.replace('-','')}/"
       ix=get(base+"index.json")
       if ix is None:raise ValueError("Missing official attachment index")
       docs=[]
       for item in ix.json()["directory"]["item"]:
        name=item["name"]
        if not name.lower().endswith(".xml"):continue
        from urllib.parse import quote
        attachment=get(base+quote(name))
        if attachment is None:raise ValueError("Missing indexed XML attachment")
        docs.append(attachment.text)
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
      local=defaultdict(int); local_values=defaultdict(int)
      for root in tables:
       for x in root.findall("infoTable"):
        if (x.findtext("putCall") or "").strip() or x.findtext("shrsOrPrnAmt/sshPrnamtType")!="SH":continue
        c=(x.findtext("cusip") or "").strip().upper()
        if c in candidates:
         local[c]+=int(x.findtext("shrsOrPrnAmt/sshPrnamt"))
         if x.findtext("value"):local_values[c]+=int(x.findtext("value"))
      filings[acc]=dict(cik=cik.zfill(10),period=period,filed=filed,form=form,manager_name=(cover.findtext(".//filingManager/name") or fields[1]).strip())
      filings[acc].update(amendment_type=cover.findtext(".//amendmentType"),amendment_number=cover.findtext(".//amendmentNo"),report_type=cover.findtext(".//reportType"),confidential=cover.findtext(".//isConfidentialOmitted"))
      for c,n in local.items():positions[(acc,c)]=n
      for c,v in local_values.items():market_values[(acc,c)]=v
      bridge_ok+=1
     except Exception as e:
      bridge_failed.append((acc,str(e)[:180]))
     if bridge_total%500==0:print("EDGAR bridge progress:",bridge_ok,"/",bridge_total,"failed:",len(bridge_failed),flush=True)
    q+=1
    if q==5:year+=1;q=1
   print("EDGAR bridge:",bridge_ok,"/",bridge_total,"failed examples:",bridge_failed[:12],flush=True)
   if bridge_failed:raise RuntimeError("Incomplete latest filing bridge; preserve published data")
   sources.extend(idx_sources)
 else:
  bridge_ok=9804
  sources=["https://github.com/Morris199786/tw-market-monitor/actions/runs/46155113153/artifacts/15270192154"]
 # Do not infer new/closed positions from missing submissions. Amendments require reconciliation.
 def iso(s):
  for fmt in ("%d-%b-%Y","%Y-%m-%d","%m/%d/%Y","%m-%d-%Y"):
   try:return dt.datetime.strptime(s or "",fmt).date().isoformat()
   except ValueError:pass
  return None
 from us_13f_reconcile import reconcile,compare
 from pathlib import Path
 import gzip
 # Retain accession-level source records, including those without watchlist holdings.
 rawdir=ROOT/"institutional_raw";rawdir.mkdir(exist_ok=True)
 grouped_raw=defaultdict(list); entries=defaultdict(list)
 if snapshot_dir:
  for path in sorted(Path(snapshot_dir).glob("20*.json.gz")):
   with gzip.open(path,"rt",encoding="utf-8") as f: es=json.load(f)
   for e in es:
    if set(e["positions"])-candidates:raise RuntimeError("Snapshot identifier mapping changed")
    grouped_raw[e["period"]].append(e);entries[(e["cik"],e["period"])].append(e)
  if len(grouped_raw)!=5 or sum(map(len,grouped_raw.values()))<43000:raise RuntimeError("Incomplete recovered snapshots")
 else:
  raw_by_acc=defaultdict(dict)
  for (acc,c),n in positions.items():raw_by_acc[acc][c]=[n,market_values.get((acc,c))]
  for acc,f in filings.items():
   p=iso(f["period"]);d=iso(f["filed"])
   if not p or not d or not f["cik"] or p<cutoff or p>now.isoformat():continue
   cik=str(f["cik"]).zfill(10)
   safe=str(f.get("report_type") or "").strip().upper()=="13F HOLDINGS REPORT" and str(f.get("confidential") or "").strip().upper() in ("N","NO","FALSE","0")
   e=dict(f,accession=acc,cik=cik,period=p,filed=d,absence_safe=safe,positions=raw_by_acc.get(acc,{}))
   grouped_raw[p].append(e);entries[(cik,p)].append(e)
 # Deterministic compressed snapshots; kept outside the public web data directory by workflow artifact.
 for p,es in grouped_raw.items():
  with gzip.GzipFile(filename=str(rawdir/(p+".json.gz")),mode="wb",mtime=0) as out:
   out.write(json.dumps(es,ensure_ascii=False,separators=(",",":")).encode())
 effective={};audit=defaultdict(int)
 for k,es in entries.items():
  state,status=reconcile(es);audit[status]+=1
  if state is not None:effective[k]=state
 effective_by_period=defaultdict(list)
 for (cik,p),state in effective.items():
  effective_by_period[p].append(dict(cik=cik,period=p,**state))
 for p,es in effective_by_period.items():
  with gzip.GzipFile(filename=str(rawdir/("effective-"+p+".json.gz")),mode="wb",mtime=0) as out:
   out.write(json.dumps(es,ensure_ascii=False,separators=(",",":")).encode())
 from update_us_insider import price_history
 from fractions import Fraction
 split_events={}; price_histories={}
 for ticker in sorted(watch):
  prices=price_history(ticker,cutoff,(now+dt.timedelta(days=1)).isoformat())
  if not prices:raise RuntimeError("Missing corporate action history: "+ticker)
  price_histories[ticker]=prices
  split_events[ticker]=[(x["date"],Fraction(str(x["split"]))) for x in prices if x["split"]>0 and x["split"]!=1]
 rows=[]
 for (cik,p),new in effective.items():
  day=dt.date.fromisoformat(p);qstart=dt.date(day.year,((day.month-1)//3)*3+1,1);prev=(qstart-dt.timedelta(days=1)).isoformat()
  oldstate=effective.get((cik,prev))
  if oldstate is None:continue
  for cusip in oldstate["positions"].keys()|new["positions"].keys():
   pair=compare(oldstate,new,cusip)
   if pair is None:continue
   av,bv,status=pair;raw_old=av[0] if av else 0;n=bv[0] if bv else 0;ticker=cusips[cusip]
   factor=Fraction(1)
   for date,ratio in split_events[ticker]:
    if prev<date<=p:factor*=ratio
   old=round(raw_old*factor);f=new["last"];acc=f["accession"];name=f.get("manager_name") or oldstate["last"].get("manager_name") or ""
   rows.append(dict(ticker=ticker,cik=cik,manager_name=name,period=p,previous_period=prev,filed=f["filed"],shares=n,previous_shares=old,previous_shares_raw=raw_old,split_factor=float(factor),change=n-old,change_pct=(n-old)/old*100 if old else None,position_status=status,accession=acc,reported_value=bv[1] if bv else None,previous_reported_value=av[1] if av else None,url=f"{SEC}/Archives/edgar/data/{int(cik)}/{acc.replace('-','')}/"))
 latest_expected=(dt.date(now.year,((now.month-1)//3)*3+1,1)-dt.timedelta(days=1))
 if now<latest_expected+dt.timedelta(days=45):
  latest_expected=dt.date(latest_expected.year,((latest_expected.month-1)//3)*3+1,1)-dt.timedelta(days=1)
 if not rows:raise RuntimeError('No comparable consecutive-quarter positions')
 actual_coverage=sorted({r["ticker"] for r in rows})
 print("Verified identifiers:",len(set(cusips.values())),"actual historical holdings coverage:",len(actual_coverage),"rows:",len(rows),"latest:",max(r["period"] for r in rows),flush=True)
 payload=dict(updated_at=dt.datetime.now(dt.timezone.utc).isoformat(),sources=sources,rows=rows,coverage=actual_coverage,identifier_coverage=sorted(set(cusips.values())),uncovered_holdings=sorted(watch-set(actual_coverage)),unmapped=sorted(watch-set(cusips.values())),expected_period=latest_expected.isoformat(),latest_period=max(x["period"] for x in rows),missing_expected_period=max(x["period"] for x in rows)<latest_expected.isoformat(),note="比較可核對的相鄰季度普通股公開申報；新申報與不再申報不等於實際從零買入或清倉。無法核對的修正申報、保密或不完整報告不推定零持股；拆股已調整。13F 非即時交易。")
 if payload["missing_expected_period"]:raise RuntimeError("Latest expected quarter absent; preserve published data")
 payload["bridge_filing_count"]=bridge_ok
 payload["reconciliation_audit"]=dict(audit)
 payload["position_status_counts"]={k:sum(r["position_status"]==k for r in rows) for k in ("paired","newly_reported","no_longer_reported")}
 payload["split_adjusted"]=True
 payload["split_events"]={t:[{"date":d,"ratio":float(f)} for d,f in v] for t,v in split_events.items() if v}
 payload["manager_name_coverage"]=sum(bool(r["manager_name"]) for r in rows)
 if payload["manager_name_coverage"]!=len(rows):raise RuntimeError("Missing SEC manager names; preserve published data")
 if set(actual_coverage)!=watch:raise RuntimeError("Actual historical holdings coverage below 100; preserve prior file")
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
  agg=defaultdict(lambda:dict(up=0,down=0,flat=0,change=0,previous_shares=0,shares=0,increase_shares=0,decrease_shares=0))
  for r in stockrows:
   g=agg[r["period"]];g["up" if r["change"]>0 else "down" if r["change"]<0 else "flat"]+=1;g["change"]+=r["change"];g["previous_shares"]+=r["previous_shares"];g["shares"]+=r["shares"];g["increase_shares"]+=max(0,r["change"]);g["decrease_shares"]+=max(0,-r["change"])
  for period,g in agg.items():
   # Market close on the last trading day of the reporting quarter.
   # Yahoo close is split-normalized; reverse subsequent splits to the quarter basis.
   from statistics import median
   hist=[v for v in price_histories[ticker] if v["date"]<=period]
   price=None;price_date=None
   if hist and (dt.date.fromisoformat(period)-dt.date.fromisoformat(hist[-1]["date"])).days<=7:
    price_date=hist[-1]["date"]
    factor=Fraction(1)
    for date,ratio in split_events[ticker]:
     if date>price_date:factor*=ratio
    price=round(hist[-1]["close"]*float(factor),4)
   ratios=[r["reported_value"]/r["shares"] for r in stockrows if r["period"]==period and r["shares"]>=100 and r.get("reported_value") and r["reported_value"]>0]
   g["quarter_price"]=price
   g["quarter_price_date"]=price_date
   g["quarter_price_source"]="Yahoo Finance quarter-end close, restored to historical share basis" if price is not None else None
   g["sec_implied_price_median"]=median(ratios) if ratios else None
   g["estimated_change_usd"]=g["change"]*price if price is not None else None
   g["change_pct"]=100*g["change"]/g["previous_shares"] if g["previous_shares"] else None
   summary[period].append(dict(ticker=ticker,**g))
 assert written==len(rows)
 for file in out.glob("*.json"):
  if file.stem not in manifest:file.unlink()
 payload.pop("rows")
 payload.update(schema_version=2,row_count=written,shards=manifest,summary=dict(summary),rows=[])
 p=ROOT/"institutional.tmp";p.write_text(json.dumps(payload,ensure_ascii=False,allow_nan=False,separators=(",",":")));p.replace(ROOT/"institutional.json")
 print("Published index and shards:",len(manifest),"rows:",written,"uncovered:",payload["uncovered_holdings"],flush=True)
if __name__=="__main__":main()
