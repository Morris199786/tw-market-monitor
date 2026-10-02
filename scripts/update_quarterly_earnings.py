from sources import *
import os, re, html
from pathlib import Path

VERSION = "2026-10-02-v1"
DATA = ROOT / "data"
OUT = DATA / "quarterly_earnings.json"
SENT = DATA / "quarterly_earnings_sent.json"

TWSE_NEWS = f"{TWSE}/opendata/t187ap04_L"
TPEX_NEWS = f"{TPEX}/mopsfin_t187ap04_O"
TWSE_IS = f"{TWSE}/opendata/t187ap06_L_ci"
TPEX_IS = f"{TPEX}/mopsfin_t187ap06_O_ci"

def clean(v):
    return re.sub(r"\s+", " ", html.unescape(str(v or ""))).strip()

def roc_date(v):
    s=clean(v)
    m=re.search(r"(?:(20\d{2})|(\d{2,3}))[/-](\d{1,2})[/-](\d{1,2})",s)
    if not m:return ""
    y=int(m.group(1) or m.group(2)); y=y+1911 if y<1911 else y
    return f"{y:04d}-{int(m.group(3)):02d}-{int(m.group(4)):02d}"

def period_from(s,date=""):
    s=clean(s)
    m=re.search(r"(?:(20\d{2})|(\d{2,3}))\s*年?\s*第?\s*([1-4一二三四])\s*季",s)
    if m:
        y=int(m.group(1) or m.group(2)); y=y+1911 if y<1911 else y
        q={"一":1,"二":2,"三":3,"四":4}.get(m.group(3),int(m.group(3)) if m.group(3).isdigit() else 0)
        return f"{y}-Q{q}"
    if date:
        y,mn,_=map(int,date.split("-"))
        q=4 if mn<=3 else 1 if mn<=5 else 2 if mn<=8 else 3
        if q==4:y-=1
        return f"{y}-Q{q}"
    return ""

def previous(p):
    y=int(p[:4]); q=int(p[-1])
    return f"{y-1}-Q4" if q==1 else f"{y}-Q{q-1}"

def universe():
    d=load_json(DATA/"sectors.json",{})
    out={}
    for sec in d.get("sectors",[]):
        for x in sec.get("stocks",[]):
            t=str(x.get("ticker",""))
            if re.fullmatch(r"\d{4}",t):out[t]=x.get("name","")
    return out

def fetch_news():
    out=[]
    for market,url in (("twse",TWSE_NEWS),("tpex",TPEX_NEWS)):
        try: rows=get_json(url,timeout=45)
        except Exception as e:
            print("news fail",market,e);continue
        if isinstance(rows,dict):
            rows=next((rows[k] for k in ("data","records","result") if isinstance(rows.get(k),list)),[])
        for r in rows if isinstance(rows,list) else []:
            t=str(pick(r,["公司代號","證券代號","股票代號"],"")).strip()
            subject=clean(pick(r,["主旨","Subject"],""))
            d=roc_date(pick(r,["發言日期","公告日期","Date"],""))
            if re.fullmatch(r"\d{4}",t) and subject:
                out.append({"ticker":t,"subject":subject,"date":d})
    return out

def planned_date(s,fallback):
    found=[]
    for m in re.finditer(r"(?:(20\d{2})|(\d{2,3}))\s*[年/-]\s*(\d{1,2})\s*[月/-]\s*(\d{1,2})",s):
        y=int(m.group(1) or m.group(2));y=y+1911 if y<1911 else y
        found.append(f"{y:04d}-{int(m.group(3)):02d}-{int(m.group(4)):02d}")
    return found[-1] if found else fallback

def financials():
    rows=[]
    for market,url in (("twse",TWSE_IS),("tpex",TPEX_IS)):
        try:a=get_json(url,timeout=60)
        except Exception as e:
            print("financial fail",market,e);continue
        if isinstance(a,dict):
            a=next((a[k] for k in ("data","records","result") if isinstance(a.get(k),list)),[])
        for r in a if isinstance(a,list) else []:
            t=str(pick(r,["公司代號","證券代號"],"")).strip()
            yy=pick(r,["年度","Year"],"");qq=pick(r,["季別","Season"],"")
            if not re.fullmatch(r"\d{4}",t) or yy in ("",None) or qq in ("",None):continue
            y=int(float(yy));y=y+1911 if y<1911 else y;q=int(float(qq))
            rows.append({"ticker":t,"period":f"{y}-Q{q}",
                "revenue":n(pick(r,["營業收入","營業收入合計","Revenue"],None),None),
                "gross":n(pick(r,["營業毛利（毛損）","營業毛利(毛損)","營業毛利","GrossProfit"],None),None),
                "eps":n(pick(r,["基本每股盈餘（元）","基本每股盈餘(元)","基本每股盈餘","BasicEarningsPerShare"],None),None)})
    return rows

def metrics(rows):
    by={(r["ticker"],r["period"]):r for r in rows};out={}
    for (t,p),r in by.items():
        y=int(p[:4]);q=int(p[-1]);pr=by.get((t,f"{y}-Q{q-1}")) if q>1 else None
        def one(k):
            v=r.get(k)
            if v is None:return None
            return v if q==1 or not pr or pr.get(k) is None else v-pr[k]
        rev=one("revenue");gp=one("gross");eps=one("eps")
        out[(t,p)]={"eps":eps,"gross_margin":gp/rev*100 if gp is not None and rev not in (None,0) else None}
    return out

def tg(text):
    token=os.getenv("TELEGRAM_BOT_TOKEN","").strip();chat=os.getenv("TELEGRAM_CHAT_ID","").strip()
    if not token or not chat:return False
    r=S.post(f"https://api.telegram.org/bot{token}/sendMessage",
             data={"chat_id":chat,"text":text,"disable_web_page_preview":True},timeout=30)
    r.raise_for_status();return True

def f(v,s=""):
    return "—" if v is None else f"{v:.2f}{s}"

def main():
    uni=universe();old=load_json(OUT,{"upcoming":[]});sent=set(load_json(SENT,{"ids":[]}).get("ids",[]))
    upcoming={(x["ticker"],x["period"]):x for x in old.get("upcoming",[]) if x.get("ticker") and x.get("period")}
    for x in fetch_news():
        if x["ticker"] not in uni:continue
        s=x["subject"]
        if not ("財務報告" in s or "財務報表" in s):continue
        if not ("董事會預計召開日期" in s or "預計召開董事會" in s or "提報" in s):continue
        if "更正" in s:continue
        d=planned_date(s,x["date"]);p=period_from(s,d)
        if p:upcoming[(x["ticker"],p)]={"ticker":x["ticker"],"name":uni[x["ticker"]],"period":p,"planned_date":d,"subject":s}

    mm=metrics(financials());reports=[]
    for (t,p),cur in mm.items():
        if t not in uni:continue
        prev=mm.get((t,previous(p)),{})
        reports.append({"ticker":t,"name":uni[t],"period":p,"eps":cur.get("eps"),"gross_margin":cur.get("gross_margin"),
                        "prev_period":previous(p),"prev_eps":prev.get("eps"),"prev_gross_margin":prev.get("gross_margin")})
    reports.sort(key=lambda x:(x["period"],x["ticker"]),reverse=True)
    keys={(x["ticker"],x["period"]) for x in reports if x["eps"] is not None or x["gross_margin"] is not None}
    ups=[x for k,x in upcoming.items() if k not in keys]
    for x in ups:
        pm=mm.get((x["ticker"],previous(x["period"])),{})
        x["prev_period"]=previous(x["period"]);x["prev_eps"]=pm.get("eps");x["prev_gross_margin"]=pm.get("gross_margin")
    ups.sort(key=lambda x:(x.get("planned_date","9999"),x["ticker"]))

    today=now_tpe().date().isoformat()
    for x in ups:
        k=f'preview|{x["ticker"]}|{x["period"]}|{x["planned_date"]}'
        if k not in sent and x.get("planned_date","")>=today:
            if tg(f'📅 {x["name"]} {x["ticker"]}｜{x["period"]} 財報預告\n財報日期：{x["planned_date"]}\n上一季 EPS：{f(x.get("prev_eps"))} 元\n上一季毛利率：{f(x.get("prev_gross_margin"),"%")}'):sent.add(k)
    for x in reports:
        k=f'report|{x["ticker"]}|{x["period"]}'
        if k not in sent and x["period"]>="2026-Q3" and (x["eps"] is not None or x["gross_margin"] is not None):
            if tg(f'📊 {x["name"]} {x["ticker"]}｜{x["period"]} 財報\n本季 EPS：{f(x["eps"])} 元\n本季毛利率：{f(x["gross_margin"],"%")}\n上一季 EPS：{f(x["prev_eps"])} 元\n上一季毛利率：{f(x["prev_gross_margin"],"%")}'):sent.add(k)

    save_json(OUT,{"version":VERSION,"updated_at":now_tpe().isoformat(timespec="minutes"),"upcoming":ups,"reports":reports[:500]})
    save_json(SENT,{"updated_at":now_tpe().isoformat(timespec="minutes"),"ids":sorted(sent)[-4000:]})
    print("quarterly earnings","upcoming",len(ups),"reports",len(reports))

if __name__=="__main__":
    main()
