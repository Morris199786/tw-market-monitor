from sources import *
import os, re, html
from datetime import datetime, timedelta
from pathlib import Path

VERSION = "2026-10-02-v2-mops-cumulative-safe"
DATA = ROOT / "data"
OUT = DATA / "quarterly_earnings.json"
SENT = DATA / "quarterly_earnings_sent.json"
HISTORY = DATA / "quarterly_earnings_history.json"

TWSE_NEWS = f"{TWSE}/opendata/t187ap04_L"
TPEX_NEWS = f"{TPEX}/mopsfin_t187ap04_O"
TWSE_IS = f"{TWSE}/opendata/t187ap06_L_ci"
TPEX_IS = f"{TPEX}/mopsfin_t187ap06_O_ci"

def clean(v):
    return re.sub(r"\s+", " ", html.unescape(str(v or ""))).strip()

def num(v):
    if v is None: return None
    s=clean(v).replace(",","").replace("−","-").replace("－","-")
    if s in ("","-","--","N/A","nan","None"): return None
    try: return float(s)
    except: return None

def roc_date(v):
    s=clean(v)
    m=re.search(r"(?:(20\d{2})|(\d{2,3}))[/-]?(\d{2})[/-]?(\d{2})",s)
    if not m: return ""
    y=int(m.group(1) or m.group(2))
    if y<1911: y+=1911
    return f"{y:04d}-{int(m.group(3)):02d}-{int(m.group(4)):02d}"

def period_from_text(s, fallback_date=""):
    s=clean(s)
    patterns=[
        r"(?:(20\d{2})|(\d{2,3}))\s*年?\s*第?\s*([1-4一二三四])\s*季",
        r"(?:(20\d{2})|(\d{2,3}))\s*Q\s*([1-4])",
    ]
    for pat in patterns:
        m=re.search(pat,s,re.I)
        if m:
            y=int(m.group(1) or m.group(2))
            if y<1911: y+=1911
            q={"一":1,"二":2,"三":3,"四":4}.get(m.group(3), int(m.group(3)) if m.group(3).isdigit() else 0)
            return f"{y}-Q{q}"
    if fallback_date:
        y,mn,_=map(int,fallback_date.split("-"))
        # 董事會日期只能做保守推定：4-5月 Q1、7-8月 Q2、10-11月 Q3、2-3月前一年度Q4
        if mn in (4,5): return f"{y}-Q1"
        if mn in (7,8): return f"{y}-Q2"
        if mn in (10,11): return f"{y}-Q3"
        if mn in (2,3): return f"{y-1}-Q4"
    return ""

def previous(p):
    y=int(p[:4]); q=int(p[-1])
    return f"{y-1}-Q4" if q==1 else f"{y}-Q{q-1}"

def fetch_universe():
    out={}
    try:
        m=fetch_master()
        if isinstance(m,dict):
            for t,x in m.items():
                if re.fullmatch(r"\d{4}",str(t)):
                    out[str(t)]=clean(x.get("name") if isinstance(x,dict) else x)
        elif isinstance(m,list):
            for x in m:
                t=str(x.get("ticker") or x.get("code") or "")
                if re.fullmatch(r"\d{4}",t): out[t]=clean(x.get("name",""))
    except Exception as e:
        print("fetch_master fail",e)
    if not out:
        d=load_json(DATA/"sectors.json",{})
        for sec in d.get("sectors",[]):
            for x in sec.get("stocks",[]):
                t=str(x.get("ticker",""))
                if re.fullmatch(r"\d{4}",t): out[t]=clean(x.get("name",""))
    return out

def rows_from_api(url):
    a=get_json(url,timeout=60)
    if isinstance(a,dict):
        a=next((a[k] for k in ("data","records","result") if isinstance(a.get(k),list)),[])
    return a if isinstance(a,list) else []

def fetch_news():
    out=[]
    for market,url in (("twse",TWSE_NEWS),("tpex",TPEX_NEWS)):
        try: rows=rows_from_api(url)
        except Exception as e:
            print("news fail",market,e); continue
        for r in rows:
            t=str(pick(r,["公司代號","證券代號","股票代號"],"")).strip()
            if not re.fullmatch(r"\d{4}",t): continue
            out.append({
                "ticker":t,
                "market":market,
                "name":clean(pick(r,["公司名稱","證券名稱"],"")),
                "subject":clean(pick(r,["主旨","Subject"],"")),
                "date":roc_date(pick(r,["發言日期","公告日期","Date"],"")),
                "time":clean(pick(r,["發言時間","公告時間","Time"],"")),
                "raw":r
            })
    return out

def extract_planned_date(subject, announce_date):
    s=clean(subject)
    # 主旨若直接帶日期
    ms=list(re.finditer(r"(?:(20\d{2})|(\d{2,3}))\s*[年/-]\s*(\d{1,2})\s*[月/-]\s*(\d{1,2})",s))
    if ms:
        m=ms[-1]; y=int(m.group(1) or m.group(2)); y=y+1911 if y<1911 else y
        return f"{y:04d}-{int(m.group(3)):02d}-{int(m.group(4)):02d}"
    # OpenAPI主旨常只說「董事會預計召開日期」，實際日期在重訊說明。
    # 若主旨沒有日期，不拿公告日冒充財報日。
    return ""

def is_preview_subject(s):
    s=clean(s)
    if not ("財務報告" in s or "財務報表" in s): return False
    if any(k in s for k in ("通過","決議","提報董事會通過")): return False
    return any(k in s for k in ("董事會預計召開","預計召開董事會","預計提報董事會","預計於"))

def is_report_subject(s):
    s=clean(s)
    return ("財務報告" in s or "財務報表" in s) and any(k in s for k in ("通過","決議","提報董事會通過"))

def financial_snapshot():
    rows=[]
    for market,url in (("twse",TWSE_IS),("tpex",TPEX_IS)):
        try: a=rows_from_api(url)
        except Exception as e:
            print("financial fail",market,e); continue
        for r in a:
            t=str(pick(r,["公司代號","證券代號"],"")).strip()
            yy=pick(r,["年度","Year"],""); qq=pick(r,["季別","Season"],"")
            if not re.fullmatch(r"\d{4}",t) or yy in ("",None) or qq in ("",None): continue
            try:
                y=int(float(str(yy).replace(",",""))); y=y+1911 if y<1911 else y
                q=int(float(str(qq).replace(",","")))
            except: continue
            rows.append({
                "ticker":t,"market":market,"period":f"{y}-Q{q}",
                # TWSE/TPEx OpenAPI t187ap06 是 YTD 累計口徑
                "cum_revenue":num(pick(r,["營業收入","營業收入合計","Revenue"],None)),
                "cum_gross":num(pick(r,["營業毛利（毛損）","營業毛利(毛損)","營業毛利","GrossProfit"],None)),
                "cum_eps":num(pick(r,["基本每股盈餘（元）","基本每股盈餘(元)","基本每股盈餘","BasicEarningsPerShare"],None)),
            })
    return rows

def merge_history(snapshot):
    hist=load_json(HISTORY,{"rows":[]})
    by={}
    for r in hist.get("rows",[]):
        if r.get("ticker") and r.get("period"): by[(r["ticker"],r["period"])]=r
    for r in snapshot: by[(r["ticker"],r["period"])]=r
    rows=list(by.values())
    rows.sort(key=lambda x:(x.get("period",""),x.get("ticker","")))
    save_json(HISTORY,{"version":VERSION,"updated_at":now_tpe().isoformat(timespec="minutes"),"rows":rows})
    return by

def single_metrics(by,t,p):
    r=by.get((t,p))
    if not r: return {"eps":None,"gross_margin":None}
    q=int(p[-1])
    rev=r.get("cum_revenue"); gp=r.get("cum_gross"); ceps=r.get("cum_eps")
    if q==1:
        srev,sgp,seps=rev,gp,ceps
    else:
        pp=previous(p); pr=by.get((t,pp))
        if not pr:
            return {"eps":None,"gross_margin":None}
        srev = rev-pr.get("cum_revenue") if rev is not None and pr.get("cum_revenue") is not None else None
        sgp  = gp-pr.get("cum_gross") if gp is not None and pr.get("cum_gross") is not None else None
        # 累計 EPS 不能直接相減當正式單季 EPS（宇瞻35.51-14.54 != 官方20.93）
        # 因此 Q2/Q3/Q4 不用錯誤相減值；等正式單季來源補入 history 的 single_eps。
        seps = r.get("single_eps")
    gm=sgp/srev*100 if sgp is not None and srev not in (None,0) else None
    return {"eps":seps,"gross_margin":gm}

def f(v,s=""):
    return "—" if v is None else f"{float(v):.2f}{s}"

def tg(text):
    token=os.getenv("TELEGRAM_BOT_TOKEN","").strip()
    chat=os.getenv("TELEGRAM_CHAT_ID","").strip()
    if not token or not chat: return False
    r=S.post(f"https://api.telegram.org/bot{token}/sendMessage",
             data={"chat_id":chat,"text":text,"disable_web_page_preview":True},timeout=30)
    r.raise_for_status(); return True

def main():
    uni=fetch_universe()
    old=load_json(OUT,{"upcoming":[],"reports":[]})
    sent=set(load_json(SENT,{"ids":[]}).get("ids",[]))
    news=fetch_news()
    by=merge_history(financial_snapshot())

    # 保留之前已解析到、而且仍在未來的 upcoming
    today=now_tpe().date().isoformat()
    upcoming={}
    for x in old.get("upcoming",[]):
        if x.get("ticker") and x.get("period") and x.get("planned_date","")>=today:
            upcoming[(x["ticker"],x["period"])]=x

    # 每日重大訊息：預告只接受真正財報董事會公告，不把法說會當財報日
    for x in news:
        t=x["ticker"]
        if t not in uni: continue
        s=x["subject"]
        if not is_preview_subject(s): continue
        d=extract_planned_date(s,x["date"])
        p=period_from_text(s,d or x["date"])
        # 主旨沒帶實際董事會日期時，不用公告日亂填；先略過，避免假日期
        if not d or not p: continue
        upcoming[(t,p)]={
            "ticker":t,"name":uni.get(t) or x["name"] or t,"period":p,
            "planned_date":d,"announcement_date":x["date"],"subject":s
        }

    # 最新正式財報：OpenAPI 是最新季累計快照
    reports=[]
    for (t,p),r in by.items():
        if t not in uni: continue
        cur=single_metrics(by,t,p)
        prevp=previous(p); prev=single_metrics(by,t,prevp)
        reports.append({
            "ticker":t,"name":uni[t],"period":p,
            "eps":cur["eps"],"gross_margin":cur["gross_margin"],
            "prev_period":prevp,"prev_eps":prev["eps"],"prev_gross_margin":prev["gross_margin"],
            "cum_eps":r.get("cum_eps")
        })

    reports.sort(key=lambda x:(x["period"],x["ticker"]),reverse=True)
    published={(x["ticker"],x["period"]) for x in reports if x.get("gross_margin") is not None or x.get("eps") is not None}
    ups=[]
    for k,x in upcoming.items():
        if k in published: continue
        pm=single_metrics(by,x["ticker"],previous(x["period"]))
        x["prev_period"]=previous(x["period"])
        x["prev_eps"]=pm["eps"]; x["prev_gross_margin"]=pm["gross_margin"]
        ups.append(x)
    ups.sort(key=lambda x:(x.get("planned_date","9999"),x["ticker"]))

    # 只推未來預告；正式財報只有在單季 EPS / 毛利率可正確取得時才推
    for x in ups:
        k=f'preview|{x["ticker"]}|{x["period"]}|{x["planned_date"]}'
        if k not in sent and x["planned_date"]>=today:
            msg=(f'📅 {x["name"]} {x["ticker"]}｜{x["period"]} 財報預告\n'
                 f'財報董事會：{x["planned_date"]}\n'
                 f'上一季 EPS：{f(x.get("prev_eps"))} 元\n'
                 f'上一季毛利率：{f(x.get("prev_gross_margin"),"%")}')
            if tg(msg): sent.add(k)

    # 不再把 35.51 這種累計 EPS 當宇瞻 Q2 單季 EPS 推播
    for x in reports:
        if x["period"] < "2026-Q3": continue
        if x.get("eps") is None and x.get("gross_margin") is None: continue
        k=f'report|{x["ticker"]}|{x["period"]}'
        if k in sent: continue
        msg=(f'📊 {x["name"]} {x["ticker"]}｜{x["period"]} 財報\n'
             f'本季 EPS：{f(x.get("eps"))} 元\n'
             f'本季毛利率：{f(x.get("gross_margin"),"%")}\n'
             f'上一季 EPS：{f(x.get("prev_eps"))} 元\n'
             f'上一季毛利率：{f(x.get("prev_gross_margin"),"%")}')
        if tg(msg): sent.add(k)

    save_json(OUT,{
        "version":VERSION,
        "updated_at":now_tpe().isoformat(timespec="minutes"),
        "upcoming":ups,
        "reports":reports[:800]
    })
    save_json(SENT,{
        "updated_at":now_tpe().isoformat(timespec="minutes"),
        "ids":sorted(sent)[-4000:]
    })
    print("quarterly earnings", "universe",len(uni),"upcoming",len(ups),"reports",len(reports))
    print("NOTE: t187ap06 EPS is cumulative YTD; cumulative EPS is never presented as single-quarter EPS.")

if __name__=="__main__":
    main()
