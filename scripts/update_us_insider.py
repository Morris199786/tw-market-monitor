"""SEC Form 4 purchase collector. No AI, no paid API. Run from repo root."""
import gzip, argparse, datetime as dt, json, os, pathlib, re, time, xml.etree.ElementTree as ET
from collections import defaultdict
from statistics import mean, median
from urllib.parse import quote
import requests

ROOT=pathlib.Path("data/us_insider")
SEC="https://www.sec.gov"
DSEC="https://data.sec.gov"
SESSION=requests.Session()
UA=os.environ.get("SEC_USER_AGENT","").strip()
def get(url,sec=True):
    if sec and not UA: raise RuntimeError("Set SEC_USER_AGENT to a real organization and contact email")
    for i in range(4):
        if sec: time.sleep(.24)
        try:
            r=SESSION.get(url,headers={"User-Agent":UA if sec else "Mozilla/5.0","Accept":"*/*"},timeout=45)
            if r.status_code==404: return None
            r.raise_for_status()
            return r
        except requests.RequestException:
            if i==3: raise
            time.sleep(2**i)
def val(node,path):
    return (node.findtext(path) or "").strip()
def truth(s):return s.lower() in ("1","true")
def positive(s):
    try:
        n=float(s)
        return n if 0<n<float("inf") else None
    except (ValueError,TypeError):return None
def filing_rows(blob,ticker,accession,filed,url):
    root=ET.fromstring(blob)
    if root.tag.split("}")[-1]!="ownershipDocument":raise ValueError("Not ownership XML")
    for e in root.iter():e.tag=e.tag.split("}")[-1]
    owners=[]
    for o in root.findall("reportingOwner"):
        rel=o.find("reportingOwnerRelationship")
        title=val(rel,"officerTitle") if rel is not None else ""
        roles=[]
        if rel is not None:
            if truth(val(rel,"isDirector")):roles.append("董事")
            if truth(val(rel,"isOfficer")):roles.append("高階主管 "+title)
            if truth(val(rel,"isTenPercentOwner")):roles.append("大股東")
        owners.append((val(o,"reportingOwnerId/rptOwnerCik"),val(o,"reportingOwnerId/rptOwnerName")," / ".join(roles)))
    if not owners:raise ValueError("Missing reporting owner")
    owner_id="|".join(sorted(x[0] for x in owners))
    owner=" / ".join(x[1] for x in owners)
    role=" / ".join(dict.fromkeys(x[2] for x in owners))
    rows=[]
    footnote_map={f.get("id"):f.text or "" for f in root.findall("footnotes/footnote")}
    for i,t in enumerate(root.findall("nonDerivativeTable/nonDerivativeTransaction")):
        code=val(t,"transactionCoding/transactionCode"); side=val(t,"transactionAmounts/transactionAcquiredDisposedCode/value")
        if (code,side) not in (("P","A"),("S","D")):continue
        shares=positive(val(t,"transactionAmounts/transactionShares/value"))
        price=positive(val(t,"transactionAmounts/transactionPricePerShare/value"))
        date=val(t,"transactionDate/value")
        security=val(t,"securityTitle/value")
        if not shares or not price or not date:continue
        # Exclude non-common instruments; retain unclassified titles for manual review.
        if re.search(r"preferred|warrant|option|unit|convertible|restricted stock",security,re.I):continue
        rows.append(dict(ticker=ticker,issuer_cik=val(root,"issuer/issuerCik"),accession=accession,row=i,date=date,filed=filed,owner=owner,owner_id=owner_id,owner_ids=[x[0] for x in owners],role=role,shares=shares,price=price,amount=shares*price,ownership=val(t,"ownershipNature/directOrIndirectOwnership/value"),security=security,post_shares=positive(val(t,"postTransactionAmounts/sharesOwnedFollowingTransaction/value")) if val(t,"postTransactionAmounts/sharesOwnedFollowingTransaction/value") not in ("0","0.0") else 0,url=url,amendment=val(root,"documentType")=="4/A",original_date=val(root,"dateOfOriginalSubmission"),joint=len(owners)>1,plan_10b5=truth(val(root,"aff10b5One")),transaction_code=code,side="buy" if code=="P" else "sell",footnotes=[footnote_map[f.get("id")] for f in t.iter("footnoteId") if f.get("id") in footnote_map],filing_footnotes=list(footnote_map.values())))
    return rows
def get_filings(cik,start):
    r=get(f"{DSEC}/submissions/CIK{int(cik):010d}.json")
    if r is None:raise RuntimeError("Missing issuer submissions")
    obj=r.json(); blocks=[obj["filings"]["recent"]]
    for f in obj["filings"].get("files",[]):
        if f["filingTo"]>=start:
            z=get(DSEC+"/submissions/"+f["name"])
            if z is None:raise RuntimeError("Missing historical submissions file")
            blocks.append(z.json())
    seen=set()
    for b in blocks:
        for form,fil,acc,doc in zip(b["form"],b["filingDate"],b["accessionNumber"],b["primaryDocument"]):
            if form not in ("4","4/A") or fil<start or acc in seen:continue
            seen.add(acc);yield form,fil,acc,doc
def download_xml(cik,acc,doc):
    base=f"{SEC}/Archives/edgar/data/{int(cik)}/{acc.replace('-','')}/"
    # primaryDocument may include xsl rendering directory. Fetch raw XML.
    name=doc.rsplit("/",1)[-1]
    if name.lower().endswith(".xml"):
        r=get(base+quote(name))
        if r is not None:return r.content,base+quote(name)
    ix=get(base+"index.json")
    if ix is None:raise RuntimeError("No filing index "+acc)
    for f in ix.json()["directory"]["item"]:
        name=f["name"]
        if not name.lower().endswith(".xml"):continue
        r=get(base+quote(name))
        if r is not None and b"ownershipDocument" in r.content:return r.content,base+quote(name)
    raise RuntimeError("No ownership XML "+acc)
def clean(rows):
    # Preserve distinct rows within one filing; suppress only identical accession/row repeats.
    unique={}
    for x in rows:
        k=(x["ticker"],x["accession"],x["row"],x["owner_id"])
        unique[k]=x
    rows=list(unique.values())
    amend=[x for x in rows if x["amendment"]]
    originals=[x for x in rows if not x["amendment"]]
    # Only reconcile unchanged economic rows with explicit original filing date,
    # exact owner identity, and a unique one-to-one match. Changed economics
    # require document-level review, not an assumed full replacement.
    def economic(x):
        return tuple(x.get(k) for k in ("ticker","issuer_cik","owner_id","date","security","shares","price","post_shares","ownership","side"))
    matched=set();resolved=set()
    for i,a in enumerate(amend):
        if not a.get("original_date"):continue
        candidates=[j for j,o in enumerate(originals) if o["filed"]==a["original_date"] and economic(o)==economic(a)]
        peers=[z for z in amend if z.get("original_date")==a["original_date"] and economic(z)==economic(a)]
        if len(candidates)==1 and len(peers)==1:
            # Retain original transaction publication date and amendment evidence.
            j=candidates[0];o=originals[j]
            if o.get("plan_10b5")!=a.get("plan_10b5") or o.get("footnotes")!=a.get("footnotes"):continue
            matched.add(j);resolved.add(i)
    pending=[a for i,a in enumerate(amend) if i not in resolved]
    def affected(x):
        return any(a["issuer_cik"]==x["issuer_cik"] and set(a["owner_ids"])&set(x["owner_ids"]) and (a["original_date"]==x["filed"] or a["date"]==x["date"]) for a in pending)
    out=[];quarantine=list(pending)
    for j,x in enumerate(originals):
        if affected(x):quarantine.append(x);continue
        if j in matched:x=dict(x,amendment_verified_unchanged=True)
        out.append(x)
    return sorted(out,key=lambda r:(r["filed"],r["accession"],r["row"])),quarantine
def classify(row):
    notes=" ".join(row.get("footnotes",[]))
    security=row.get("security","")
    local=bool(re.search(r"\b\d{4}\.TW\b|\b\d{4}\.TWO\b|\b\d{6}\.KS\b",security,re.I))
    adr=bool(re.search(r"american depositary|\bADR\b|\bADS\b",security,re.I))
    employee=bool(re.search(r"employee stock purchase plan|\bESPP\b|long.term incentive.{0,30}bonus plan",notes,re.I))
    negative_plan=bool(re.search(r"(?:not|outside|without).{0,45}(?:10b5.1|trading plan)",notes,re.I))
    plan=bool(re.search(r"(?:pursuant to|under|effected under|made under|in accordance with).{0,85}10b5.1",notes,re.I)) and not negative_plan
    private=bool(re.search(r"private placement|privately negotiated|private transaction|subscription agreement|registered direct offering|purchase agreement|sale agreement",notes,re.I))
    market=bool(re.search(r"open.market (?:purchase|sale|transaction)|(?:purchased|sold|acquired) (?:shares |stock )?(?:in|on|through) (?:the )?open market",notes,re.I))
    ambiguous=bool((row.get("plan_10b5") and not plan and not negative_plan) or (plan and private) or (market and private))
    category="employee_plan" if employee else "plan_uncertain" if ambiguous else "scheduled_plan" if plan else "private_purchase" if private else "confirmed_market" if market else "discretionary_candidate"
    row["security_class"]="local_common" if local else "adr" if adr else "listed_equity"
    row["purchase_class"]=category
    row["classification_basis"]="transaction_footnote" if employee or plan or private or market else "filing_plan_flag" if ambiguous else "P_or_S_code_only"
    row["price_comparable"]=not local
    row["research_eligible"]=row.get("side","buy")=="buy" and category in ("confirmed_market","discretionary_candidate") and not (local or row.get("joint"))
    return row

def price_history(ticker,start,end):
    # yfinance public market data; unadjusted OHLC plus split events.
    import yfinance as yf
    df=yf.Ticker(ticker).history(start=start,end=end,auto_adjust=False,actions=True)
    result=[]
    for day,r in df.iterrows():
        o,c=positive(r.get("Open")),positive(r.get("Close"))
        if o and c:result.append(dict(date=day.date().isoformat(),open=o,close=c,split=float(r.get("Stock Splits",0) or 0)))
    return result
def calc(rows,prices):
    # Aggregate disclosed events by ticker, owner, filing day; avoid using transaction-date entry.
    grouped=defaultdict(float)
    for r in rows:
        if not r.get("research_eligible",True):continue
        grouped[(r["ticker"],r["owner_id"],r["filed"])]+=r["amount"]
    result=[]
    for threshold in (100000,250000,500000,1000000,2000000,5000000,10000000):
        events=[k for k,v in grouped.items() if v>=threshold]
        for h in (5,10,20,60,120):
            returns=[]
            for ticker,owner,filed in events:
                p=prices.get(ticker,[]);i=next((j for j,x in enumerate(p) if x["date"]>filed),None)
                if i is None or i+h-1>=len(p):continue
                # Yahoo historical OHLC is split-normalized; no second split adjustment.
                returns.append((p[i+h-1]["close"]/p[i]["open"]-1)*100)
            result.append(dict(threshold=threshold,events=len(events),horizon=h,n=len(returns),mean=mean(returns) if returns else None,median=median(returns) if returns else None,win=100*sum(v>0 for v in returns)/len(returns) if returns else None))
    return result
def main():
    parser=argparse.ArgumentParser();parser.add_argument("--days",type=int,default=400);args=parser.parse_args()
    today=dt.datetime.now(dt.timezone.utc).date();start=(today-dt.timedelta(days=max(args.days,400))).isoformat();end=(today+dt.timedelta(days=1)).isoformat()
    config=json.loads((ROOT/"watchlist.json").read_text());tickers=config["tickers"]
    mapping={x["ticker"].upper():x["cik_str"] for x in get(SEC+"/files/company_tickers.json").json().values()}
    raw=[];coverage={};prices={}
    def read_saved(name):
        compressed=ROOT/(name+".gz")
        plain=ROOT/name
        if compressed.exists():
            with gzip.open(compressed,"rt",encoding="utf-8") as f:return json.load(f)
        return json.loads(plain.read_text()) if plain.exists() else {}
    previous=read_saved("latest.json")
    cache_path=ROOT/"filing_cache.json.gz"
    cache=read_saved("filing_cache.json")
    if cache.get("version")!=2:cache={"version":2,"entries":{}}
    entries=cache["entries"]; retained={}; hits=0; downloads=0
    import exchange_calendars as xcals
    import pandas as pd
    cal=xcals.get_calendar("XNYS")
    now=pd.Timestamp.now(tz="UTC")
    sessions=cal.sessions_in_range(pd.Timestamp(start),pd.Timestamp(today))
    expected=max(str(x.date()) for x in sessions if cal.session_close(x)<=now)
    prior_prices=previous.get("prices",{})
    for ticker in tickers:
        cik=mapping.get(ticker)
        if not cik:coverage[ticker]={"status":"unmapped"};continue
        errors=[];count=0;before=len(raw)
        try:
            for form,filed,acc,doc in get_filings(cik,start):
                try:
                    key=ticker+":"+str(cik)+":"+acc
                    entry=entries.get(key)
                    if entry is not None and entry.get("filed")==filed and entry.get("doc")==doc:
                        hits+=1
                    else:
                        blob,url=download_xml(cik,acc,doc)
                        entry={"filed":filed,"doc":doc,"rows":filing_rows(blob,ticker,acc,filed,url)}
                        downloads+=1
                    retained[key]=entry
                    raw.extend(dict(x) for x in entry["rows"]);count+=1
                except Exception as e:errors.append(acc+": "+str(e))
        except Exception as e:errors.append(str(e))
        coverage[ticker]={"status":"partial" if errors else "scanned","filings":count,"errors":errors,"raw_purchase_rows":len(raw)-before}
        print(ticker,coverage[ticker]["status"],count,flush=True)
    rows,quarantine=clean(raw)
    rows=[classify(x) for x in rows if start<=x["date"]<=today.isoformat()]
    for ticker in sorted({x["ticker"] for x in rows}):
        old=prior_prices.get(ticker,[])
        old=[x for x in old if x["date"]<=expected]
        best=old
        errors=[]
        for attempt in range(3):
            try:
                candidate=price_history(ticker,(today-dt.timedelta(days=max(args.days+15,415))).isoformat(),end)
                candidate=[x for x in candidate if x["date"]<=expected]
                if candidate and (not best or candidate[-1]["date"]>=best[-1]["date"]):
                    # Preserve one coherent price series rather than splice incompatible split bases.
                    best=candidate
                if best and best[-1]["date"]==expected:break
            except Exception as e:errors.append(str(e))
            if attempt<2:time.sleep(2**attempt)
        if best:prices[ticker]=best
        coverage[ticker]["price_as_of"]=best[-1]["date"] if best else None
        coverage[ticker]["price_status"]="ok" if best and best[-1]["date"]==expected else "stale" if best else "missing"
        if errors:coverage[ticker]["price_errors"]=errors
    # SEC prices are as-traded; normalize to the latest share basis for chart comparison.
    for r in rows:
        p=prices.get(r["ticker"],[])
        factor=1
        for x in p:
            if r["price_comparable"] and x["date"]>r["date"] and x["split"]>0:factor*=x["split"]
        r["raw_price"]=r["price"];r["raw_shares"]=r["shares"];r["price"]/=factor;r["shares"]*=factor
    n=sum(x["status"]=="scanned" for x in coverage.values())
    if n!=len(tickers):raise RuntimeError(f"Incomplete SEC scan {n}/{len(tickers)}; preserve previous output")
    bad=sorted(t for t in {x["ticker"] for x in rows} if coverage[t]["price_status"]!="ok")
    print(f"SEC cache hits={hits}, downloads={downloads}; expected price date={expected}; stale/missing={bad}",flush=True)
    # Publish SEC records independently of market-data freshness. Never represent stale quotes as current.
    for t in bad:
        coverage[t]["price_status"]="stale" if prices.get(t) else "missing"
    for r in rows:
        r["quote_current"]=coverage[r["ticker"]].get("price_status")=="ok"
    price_note=("；行情未更新至 "+expected+"（"+",".join(bad)+"），報酬率僅截至行情日期" if bad else "")
    payload=dict(updated_at=dt.datetime.now(dt.timezone.utc).isoformat(),as_of=today.isoformat(),start=start,coverage=coverage,coverage_note=f"SEC 掃描完成 {n}/{len(tickers)} 個已列代號；另有 ETF 與待確認代號。修正申報暫隔離 {len(quarantine)} 列；部分缺漏不能視為零。"+price_note,schema_version=2,expected_price_as_of=expected,price_as_of=min((p[-1]["date"] for p in prices.values() if p),default=None),stale_prices=bad,cache_stats={"hits":hits,"downloads":downloads},transactions=[r for r in rows if r.get("side")=="buy"],sales=[r for r in rows if r.get("side")=="sell"],classification_version=2,amendment_verified_unchanged=sum(bool(r.get("amendment_verified_unchanged")) for r in rows),trading_sessions=[str(x.date()) for x in sessions if str(x.date())<=expected],quarantine=quarantine,price_missing=[t for t in bad if t not in prices],prices=prices,backtest=calc(rows,prices),unresolved=config["unresolved"],excluded_etf=config["excluded_etf"])
    def save_compressed(path,obj):
        tmp=path.with_suffix(".tmp")
        with gzip.GzipFile(filename=str(tmp),mode="wb",mtime=0) as f:
            f.write(json.dumps(obj,ensure_ascii=False,allow_nan=False,separators=(",",":")).encode("utf-8"))
        if tmp.stat().st_size>=24*1024*1024:
            raise RuntimeError(f"Compressed file exceeds static asset budget: {path.name}")
        with gzip.open(tmp,"rt",encoding="utf-8") as f:
            assert json.load(f)==obj
        tmp.replace(path)
    save_compressed(cache_path,{"version":2,"entries":retained})
    save_compressed(ROOT/"latest.json.gz",payload)
if __name__=="__main__":main()
