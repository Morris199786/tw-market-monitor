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
    # SEC documents column 10 as the option indicator, NOT an option row.
    # The actual instrument class appears in columns 41-67.
    official=get(SEC+"/rules-regulations/staff-guidance/official-list-section-13f-securities").text
    from urllib.parse import urljoin
    links=[urljoin(SEC,x) for x in re.findall(r"""href=["']([^"']+\.txt)["']""",official,re.I) if "13flist" in x.lower()]
    links=list(dict.fromkeys([SEC+"/files/investment/13flist2026q3-txt.txt"]+links))
    records=[]
    def acceptable(desc,status):
        return "*D*" not in status and not re.match(r"^(CALL|PUT|RIGHT|UNIT|\*W|WARRANT|NOTE|BOND|DBCV|PFD)\b",desc.strip(),re.I)
    for u in links:
        r=get(u)
        if r is None:continue
        temp=[]
        for line in r.text.splitlines():
            if len(line)<67 or not re.fullmatch(r"[A-Z0-9]{9}",line[:9]) or line[9] not in " *":continue
            if acceptable(line[40:67],line[67:70]):temp.append((line[:9],line[10:40].strip()))
        if len(temp)>1000:
            records=temp
            print("Fixed width TXT source:",u,"eligible rows:",len(records),flush=True)
            break
    # Also parse current PDF, accepting optional star after the check digit.
    # Preserve historical TXT candidates, since symbols can change class.
    pdf_rows=0
    for page in reader.pages:
        for line in (page.extract_text(extraction_mode="layout") or "").splitlines():
            m=re.match(r"^\s*([A-Z0-9]{6})\s*([A-Z0-9]{2})\s*([A-Z0-9])\s*\*?\s+(.+)",line)
            if not m:continue
            c="".join(m.group(i) for i in (1,2,3))
            fields=re.split(r"\s{2,}",m.group(4).strip())
            if len(fields)<2:continue
            if acceptable(fields[1]," ".join(fields[2:])):
                records.append((c,fields[0]));pdf_rows+=1
    records=list(set(records))
    assert len(records)>1000
    print("PDF eligible rows:",pdf_rows,"total distinct candidates before filter:",len(records),flush=True)
    # Independently sourced SEC filing controls: do not query them as seeds.
    controls={"AAPL":"037833100","INTC":"458140100","NVDA":"67066G104","AMD":"007903107","MU":"595112103","MSFT":"594918104"}
    print("Control codes present in parsed source:",{t:any(c==v for c,n in records) for t,v in controls.items()},flush=True)
    for c,n in records:
        q=tokens(n)
        if any(q and v and (q<=v or v<=q or len(q&v)>=2) for v in nt.values()):candidates.add(c)
    print("Initial candidates:",len(candidates),flush=True)
    # Independently query each exact US ticker using OpenFIGI's ticker mapping.
    # FIGI itself does not return CUSIP; use returned issuer names to improve
    # PDF candidate selection and verify candidates by CUSIP in a second pass.
    def mapping(jobs):
        for retry in range(4):
            r=requests.post("https://api.openfigi.com/v3/mapping",json=jobs,timeout=45)
            if r.status_code!=429:break
            time.sleep(65)
        r.raise_for_status()
        result=r.json()
        assert len(result)==len(jobs)
        time.sleep(2.6)
        return result
    issuer_aliases={}
    ticker_figis=defaultdict(set)
    allowed={"Common Stock","Depositary Receipt","REIT","ETP","ETN","Closed-End Fund"}
    for i in range(0,len(watch),10):
        batch=sorted(watch)[i:i+10]
        items=mapping([{"idType":"TICKER","idValue":t,"exchCode":"US","marketSecDes":"Equity"} for t in batch])
        for t,item in zip(batch,items):
            match=[x for x in item.get("data",[]) if x.get("ticker")==t and x.get("securityType2") in allowed]
            issuer_aliases[t]={norm(x.get("name","")) for x in match if x.get("name")}
            ticker_figis[t].update(x[k] for x in match for k in ("figi","shareClassFIGI","compositeFIGI") if x.get(k))
    print("Exact ticker lookup results:",sum(bool(x) for x in issuer_aliases.values()),"/",len(watch),flush=True)
    # Search only relevant securities; use normalized name prefixes and
    # OpenFIGI issuer aliases as candidate hints, not identity proof.
    prefixes={n for t in watch for n in ({norm(names.get(t,""))}|issuer_aliases.get(t,set())) if len(n)>=4}
    for c,issuer in records:
        n=norm(issuer)
        if len(n)>=4 and any(n.startswith(p) or p.startswith(n) or (min(len(n),len(p))>=8 and n[:8]==p[:8]) for p in prefixes):candidates.add(c)
    print("Control codes selected:",{t:c in candidates for t,c in controls.items()},flush=True)
    assert all(c in candidates for c in controls.values()),"Known ordinary share missing from candidate parser"
    print("Expanded candidates:",len(candidates),flush=True)
    found=defaultdict(set); type_counts=defaultdict(int)
    cs=sorted(candidates)
    for i in range(0,len(cs),10):
        batch=cs[i:i+10]
        items=mapping([{"idType":"ID_CUSIP","idValue":c,"exchCode":"US","marketSecDes":"Equity"} for c in batch])
        for c,item in zip(batch,items):
            matches=set()
            for x in item.get("data",[]):
                if x.get("ticker") in watch:
                    type_counts[str((x.get("securityType"),x.get("securityType2")))]+=1
                    if x.get("securityType2") in allowed or x.get("securityType") in ("Common Stock","ADR","Depositary Receipt","NY Reg Shrs","REIT"):
                        matches.add(x["ticker"])
            if len(matches)==1:found[next(iter(matches))].add(c)
    # Foreign securities often have non-US identifiers. Compare FIGI identities
    # without assuming the country prefix or requiring a US exchange on lookup.
    missing=watch-set(found)
    hints={"ASML":["ASML"],"CRDO":["CREDO"],"FLEX":["FLEX"],"FN":["FABRINET"],"GFS":["GLOBALFOUNDRIES"],"ICHR":["ICHOR"],"NBIS":["NEBIUS"],"NXPI":["NXP"],"STX":["SEAGATE"],"TEL":["TE CONNECTIVITY"],"TSEM":["TOWER SEMICONDUCTOR","TOWER SEMICOND"]}
    extra=set()
    for c,n in records:
        if any(any(norm(n).startswith(norm(h)) for h in hints.get(t,[])) for t in missing):extra.add(c)
    # Actual filing sample supplies additional independently observed codes.
    extra.update(set(a)|set(b))
    print("Foreign-security fallback candidates:",len(extra),flush=True)
    cs=sorted(extra)
    for i in range(0,len(cs),10):
        batch=cs[i:i+10]
        items=mapping([{"idType":"ID_CUSIP","idValue":c,"marketSecDes":"Equity"} for c in batch])
        for c,item in zip(batch,items):
            matches=set()
            for x in item.get("data",[]):
                if x.get("securityType2") not in allowed and x.get("securityType") not in ("Common Stock","ADR","Depositary Receipt","NY Reg Shrs","REIT"):continue
                ids={x[k] for k in ("figi","shareClassFIGI","compositeFIGI") if x.get(k)}
                matches.update(t for t in missing if ids & ticker_figis[t])
            if len(matches)==1:found[next(iter(matches))].add(c)
    print("Foreign fallback recovered:",sorted(missing & set(found)),flush=True)
    print("OpenFIGI returned security classes for watchlist:",dict(type_counts),flush=True)
    print("OpenFIGI verified tickers:",sorted(found),flush=True)
    print("Unmapped:",sorted(watch-set(found)),flush=True)
    print("Coverage:",len(found),"/",len(watch),flush=True)
    assert {"NVDA","AMD","MU","MSFT","AMZN"}<=set(found),"Core mapping failed"
    assert len(found)>=100,"Coverage below acceptance threshold; do not publish"
if __name__=="__main__":main()
