"""SEC issuer repurchases: report only directly tagged actual amounts/shares, never authorization estimates."""
import datetime as dt,json
from pathlib import Path
from update_us_insider import get,SEC,DSEC,ROOT
TAGS={"payments":("PaymentsForRepurchaseOfCommonStock","PaymentsForRepurchaseOfEquity"),"shares":("StockRepurchasedDuringPeriodShares",),"price":("StockRepurchasedDuringPeriodAveragePricePaidPerShare",)}
def main():
 cfg=json.loads((ROOT/"watchlist.json").read_text())
 mapping={x["ticker"]:x["cik_str"] for x in get(SEC+"/files/company_tickers.json").json().values()}
 start=(dt.date.today()-dt.timedelta(days=730)).isoformat()
 coverage={}; rows=[]
 for ticker in cfg["tickers"]:
  try:
   cik=mapping[ticker]; resp=get(f"{DSEC}/api/xbrl/companyfacts/CIK{cik:010d}.json")
   if resp is None:coverage[ticker]="no_companyfacts";continue
   facts=resp.json()["facts"].get("us-gaap",{})
   found={}
   for kind,tags in TAGS.items():
    for tag in tags:
     units=facts.get(tag,{}).get("units",{})
     unit={"payments":"USD","shares":"shares","price":"USD/shares"}[kind]
     for x in units.get(unit,[]):
      if x.get("form") not in ("10-K","10-Q","10-K/A","10-Q/A") or x.get("end","")<start or not x.get("start") or not x.get("filed") or not x.get("accn"):continue
      key=(kind,x["start"],x["end"])
      prior=found.get(key)
      if prior and (prior["filed"],-tags.index(prior["tag"])) >= (x["filed"],-tags.index(tag)):continue
      found[key]=dict(ticker=ticker,kind=kind,tag=tag,unit=unit,start=x["start"],end=x["end"],filed=x["filed"],value=x["val"],url=f"{SEC}/Archives/edgar/data/{cik}/{x['accn'].replace('-','')}/")
   rows.extend(found.values());coverage[ticker]="tagged" if found else "no_supported_tags"
  except Exception as e:coverage[ticker]="failed";print(ticker,str(e),flush=True)
  print(ticker,coverage[ticker],flush=True)
 if not rows or "failed" in coverage.values():raise RuntimeError("Incomplete issuer facts; preserve prior data")
 payload=dict(updated_at=dt.datetime.now(dt.timezone.utc).isoformat(),coverage=coverage,rows=rows,note="原始 XBRL 期間數據，季度與累計期間不可加總；未找到標籤不代表沒有回購。未包含回購授權及剩餘額度。")
 p=ROOT/"buybacks.tmp";p.write_text(json.dumps(payload,ensure_ascii=False,allow_nan=False));p.replace(ROOT/"buybacks.json")
if __name__=="__main__":main()
