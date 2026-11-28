"""Read-only source acceptance probe; does not publish holdings or identifiers."""
import io, re, json, time, datetime as dt
import xml.etree.ElementTree as ET
from collections import defaultdict
from pypdf import PdfReader
from update_us_insider import get, SEC, ROOT
import requests

def local(root):
    for e in root.iter(): e.tag=e.tag.rsplit("}",1)[-1]
    return root

def positions(url):
    r=get(url)
    if r is None: raise RuntimeError("Missing XML: "+url)
    root=local(ET.fromstring(r.content))
    assert root.tag=="informationTable",root.tag
    out=defaultdict(int)
    for x in root.findall("infoTable"):
        if (x.findtext("putCall") or "").strip():continue
        if x.findtext("shrsOrPrnAmt/sshPrnamtType")!="SH":continue
        c=x.findtext("cusip")
        n=int(x.findtext("shrsOrPrnAmt/sshPrnamt"))
        out[c]+=n
    return out

def main():
    base=SEC+"/Archives/edgar/data/1787596/"
    a=positions(base+"000117266126003632/infotable.xml")
    b=positions(base+"000117266126005103/infotable.xml")
    assert b["67066G104"]==61762 and b["595112103"]==3309
    assert a["67066G104"]==70860 and a["595112103"]==2325
    print("XML and option exclusion verified; two-quarter sample:",len(a),len(b),flush=True)
    idx=get(SEC+"/Archives/edgar/full-index/2026/QTR4/master.idx")
    records=[l.split("|") for l in idx.text.splitlines() if "|13F-HR|" in l or "|13F-HR/A|" in l]
    assert records and any("1787596"==r[0] and r[3]=="2026-11-16" for r in records)
    print("EDGAR latest-quarter index records:",len(records),flush=True)
    pdf=get(SEC+"/files/investment/13flist2026q3.pdf")
    assert pdf is not None and pdf.content.startswith(b"%PDF")
    reader=PdfReader(io.BytesIO(pdf.content))
    watch=set(json.loads((ROOT/"watchlist.json").read_text())["tickers"])
    names={x["ticker"]:x["title"] for x in get(SEC+"/files/company_tickers.json").json().values() if x["ticker"] in watch}
    def norm(n):return re.sub(r"[^A-Z0-9]","",n.upper())
    def tokens(n):
        return set(re.findall(r"[A-Z0-9]+",n.upper()))-{"INC","CORP","CORPORATION","LTD","LIMITED","PLC","THE","CO","COMPANY","HOLDINGS","HLDGS","GROUP","NV","SA","AG","DE","CL","A","B","COM"}
    nt={t:tokens(n) for t,n in names.items()}
    candidates=set(a)|set(b)
    # Name similarity only narrows search; never establishes identity.
    rows=0
    for page in reader.pages:
        for line in (page.extract_text(extraction_mode="layout") or "").splitlines():
            m=re.match(r"^\s*([A-Z0-9]{6})\s+([A-Z0-9]{2})\s+([A-Z0-9])\s+(.+)",line)
            if not m:continue
            rows+=1
            c="".join(m.group(i) for i in (1,2,3))
            n=re.split(r"\s{2,}",m.group(4).strip())[0]
            q=tokens(n)
            if any(q and v and (q<=v or v<=q or len(q&v)>=2) for v in nt.values()):candidates.add(c)
    assert rows>1000,("PDF row count",rows)
    print("PDF pages/rows/candidates:",len(reader.pages),rows,len(candidates),flush=True)
    found=defaultdict(set); errors=0
    cs=sorted(candidates)
    for i in range(0,len(cs),10):
        batch=cs[i:i+10]
        req=[{"idType":"ID_CUSIP","idValue":c,"exchCode":"US","marketSecDes":"Equity"} for c in batch]
        for retry in range(3):
            r=requests.post("https://api.openfigi.com/v3/mapping",json=req,timeout=45)
            if r.status_code!=429:break
            time.sleep(65)
        r.raise_for_status()
        items=r.json()
        assert len(items)==len(batch)
        for c,item in zip(batch,items):
            matches={x["ticker"] for x in item.get("data",[]) if x.get("ticker") in watch and x.get("securityType2") in ("Common Stock","Depositary Receipt")}
            if len(matches)==1:found[next(iter(matches))].add(c)
        time.sleep(2.6)
    print("OpenFIGI verified tickers:",sorted(found),flush=True)
    print("Unmapped:",sorted(watch-set(found)),flush=True)
    print("Coverage:",len(found),"/",len(watch),flush=True)
    assert {"NVDA","AMD","MU","MSFT","AMZN"}<=set(found),"Core mapping failed"
    assert len(found)>=100,"Coverage below acceptance threshold; do not publish"
if __name__=="__main__":main()
