"""SEC issuer repurchases: report only directly tagged actual amounts/shares, never authorization estimates."""
import datetime as dt,json,re
from pathlib import Path
from update_us_insider import get,SEC,DSEC,ROOT
TAGS={
 "payments":("PaymentsForRepurchaseOfCommonStock","PaymentsForRepurchaseOfEquity","PaymentsForRepurchaseOfOrdinaryShares","PaymentsForRepurchaseOfOwnShares","PurchaseOfTreasuryShares","PaymentsToAcquireOrRedeemEntitysShares"),
 "shares":("StockRepurchasedDuringPeriodShares","NumberOfSharesRepurchased","NumberOfOwnSharesRepurchased"),
 "price":("StockRepurchasedDuringPeriodAveragePricePaidPerShare",),
}
FORMS={"10-K","10-Q","10-K/A","10-Q/A","20-F","20-F/A","40-F","40-F/A","6-K","6-K/A"}
def extract(facts,ticker,cik,start):
 found={}
 for taxonomy in ("us-gaap","ifrs-full"):
  for kind,tags in TAGS.items():
   for tag in tags:
    for unit,items in facts.get(taxonomy,{}).get(tag,{}).get("units",{}).items():
     if not (unit=="shares" if kind=="shares" else bool(re.fullmatch(r"[A-Z]{3}",unit)) if kind=="payments" else bool(re.fullmatch(r"[A-Z]{3}/shares",unit))):continue
     for x in items:
      if x.get("form") not in FORMS or x.get("end","")<start or not x.get("start") or not x.get("filed") or not x.get("accn"):continue
      v=x.get("val")
      if not isinstance(v,(int,float)) or v<0:continue
      key=(kind,x["start"],x["end"],unit)
      prior=found.get(key)
      if prior and (prior["filed"],-tags.index(prior["tag"])) >= (x["filed"],-tags.index(tag)):continue
      found[key]=dict(ticker=ticker,kind=kind,tag=tag,taxonomy=taxonomy,unit=unit,start=x["start"],end=x["end"],filed=x["filed"],value=v,url=f"{SEC}/Archives/edgar/data/{cik}/{x['accn'].replace('-','')}/")
 return list(found.values())
def main():
 cfg=json.loads((ROOT/"watchlist.json").read_text())
 mapping={x["ticker"]:x["cik_str"] for x in get(SEC+"/files/company_tickers.json").json().values()}
 start=(dt.date.today()-dt.timedelta(days=730)).isoformat()
 coverage={}; rows=[]; evidence={}; audit={}
 from us_buyback_filing import scan
 prior_path=ROOT/"buybacks.json"
 prior=json.loads(prior_path.read_text()) if prior_path.exists() else {}
 scan_start=(dt.date.today()-dt.timedelta(days=460)).isoformat()
 for ticker in cfg["tickers"]:
  try:
   cik=mapping[ticker]; resp=get(f"{DSEC}/api/xbrl/companyfacts/CIK{cik:010d}.json")
   if resp is None:coverage[ticker]="no_companyfacts";continue
   found=extract(resp.json()["facts"],ticker,cik,start)
   rows.extend(found);coverage[ticker]="tagged" if found else "no_supported_tags"
  except Exception as e:coverage[ticker]="failed";print(ticker,str(e),flush=True)
  try:
   evidence[ticker]=scan(get,SEC,DSEC,mapping[ticker],scan_start)
   audit[ticker]="evidence_found" if evidence[ticker] else "no_matching_passage"
  except Exception as e:
   audit[ticker]="scan_failed";evidence[ticker]=prior.get("filing_evidence",{}).get(ticker,[]);print(ticker,"filing scan:",str(e),flush=True)
  print(ticker,coverage[ticker],audit[ticker],flush=True)
 if not rows or "failed" in coverage.values():raise RuntimeError("Incomplete issuer facts; preserve prior data")
 payload=dict(updated_at=dt.datetime.now(dt.timezone.utc).isoformat(),coverage=coverage,rows=rows,filing_evidence=evidence,filing_audit=audit,note="SEC US GAAP / IFRS 原始期間資料，保留原始幣別；未找到標籤不代表沒有回購。未包含回購授權及剩餘額度。")
 p=ROOT/"buybacks.tmp";p.write_text(json.dumps(payload,ensure_ascii=False,allow_nan=False));p.replace(ROOT/"buybacks.json")
if __name__=="__main__":main()
