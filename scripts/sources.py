from __future__ import annotations
import json, math, re, time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
import requests

ROOT = Path(__file__).resolve().parents[1]
TZ = ZoneInfo("Asia/Taipei")

TWSE = "https://openapi.twse.com.tw/v1"
TPEX = "https://www.tpex.org.tw/openapi/v1"
TWSE_WEB = "https://www.twse.com.tw"
TDCC = "https://openapi.tdcc.com.tw/v1/opendata"
MIS = "https://mis.twse.com.tw/stock/api/getStockInfo.jsp"

S = requests.Session()
S.headers.update({
    "User-Agent":"Mozilla/5.0 (GitHub Actions; Taiwan Market Monitor)",
    "Accept":"application/json,text/plain,*/*"
})

def now_tpe():
    return datetime.now(TZ)

def get_json(url, params=None, timeout=30, tries=3):
    last = None
    for i in range(tries):
        try:
            r = S.get(url, params=params, timeout=timeout)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            last = e
            time.sleep(1.5*(i+1))
    raise RuntimeError(f"GET failed: {url}: {last}")

def load_json(path, default=None):
    p=Path(path)
    if not p.exists(): return {} if default is None else default
    return json.loads(p.read_text(encoding="utf-8"))

def save_json(path, data):
    p=Path(path); p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding="utf-8")

def n(v, default=0.0):
    if v is None: return default
    s=str(v).replace(",","").replace("%","").replace("＋","+").replace("−","-").replace("—","").strip()
    if s in ("","--","---","-"): return default
    try:return float(s)
    except:return default

def iv(v, default=0):
    try:return int(round(n(v,default)))
    except:return default

def pick(d, names, default=None):
    for k in names:
        if k in d and d[k] not in (None,""):
            return d[k]
    # partial / normalized match
    for k,v in d.items():
        nk=re.sub(r"\s+","",str(k))
        for name in names:
            if re.sub(r"\s+","",name) in nk and v not in (None,""):
                return v
    return default

def ordinary_ticker(t):
    return bool(re.fullmatch(r"\d{4}", str(t or "").strip()))

def percentile_map(values: dict[str,float]):
    items=sorted(values.items(),key=lambda kv:kv[1])
    out={}
    L=len(items)
    if not L:return out
    for i,(k,v) in enumerate(items):
        out[k]=100.0 if L==1 else i/(L-1)*100
    return out

def safe_mean(xs):
    xs=[x for x in xs if x is not None and not math.isnan(x)]
    return sum(xs)/len(xs) if xs else None

def fetch_twse_latest_quotes():
    arr=get_json(f"{TWSE}/exchangeReport/STOCK_DAY_ALL")
    out={}
    for r in arr:
        t=str(pick(r,["Code","證券代號","股票代號","公司代號"],"")).strip()
        if not ordinary_ticker(t): continue
        name=str(pick(r,["Name","證券名稱","股票名稱","公司簡稱"],"")).strip()
        close=n(pick(r,["ClosingPrice","收盤價","收盤"]))
        change=n(pick(r,["Change","漲跌價差","漲跌"]))
        vol=iv(pick(r,["TradeVolume","成交股數"]))
        value=iv(pick(r,["TradeValue","成交金額"]))
        prev=(close-change) if close else 0
        pct=(change/prev*100) if prev else 0
        out[t]={"ticker":t,"name":name,"market":"twse","price":close,"change":change,"change_pct":pct,
                "volume":vol,"turnover":value}
    return out

def fetch_tpex_latest_quotes():
    arr=get_json(f"{TPEX}/tpex_mainboard_daily_close_quotes")
    out={}
    for r in arr:
        t=str(pick(r,["SecuritiesCompanyCode","證券代號","代號","股票代號"],"")).strip()
        if not ordinary_ticker(t): continue
        name=str(pick(r,["CompanyName","證券名稱","名稱","公司名稱"],"")).strip()
        close=n(pick(r,["Close","收盤","收盤價"]))
        ch=n(pick(r,["Change","漲跌","漲跌價差"]))
        vol=iv(pick(r,["TradingShares","成交股數","成交量"]))
        value=iv(pick(r,["TransactionAmount","成交金額","成交值"]))
        # 有些 TPEx API Change 可能直接帶百分比，優先找 pct 欄
        pct_raw=pick(r,["ChangePercent","漲跌幅","漲跌幅(%)"],None)
        if pct_raw is not None:
            pct=n(pct_raw)
        else:
            prev=(close-ch) if close else 0
            pct=(ch/prev*100) if prev else 0
        out[t]={"ticker":t,"name":name,"market":"tpex","price":close,"change":ch,"change_pct":pct,
                "volume":vol,"turnover":value}
    return out

def fetch_master():
    out={}
    for market,url in [
        ("twse",f"{TWSE}/opendata/t187ap03_L"),
        ("tpex",f"{TPEX}/mopsfin_t187ap03_O")
    ]:
        try: arr=get_json(url)
        except Exception: continue
        for r in arr:
            t=str(pick(r,["公司代號","SecuritiesCompanyCode","股票代號","代號"],"")).strip()
            if not ordinary_ticker(t): continue
            name=str(pick(r,["公司簡稱","公司名稱","CompanyName","名稱"],"")).strip()
            industry=str(pick(r,["產業別","產業類別","Industry"],"")).strip()
            shares=iv(pick(r,["已發行普通股數或TDR原發行股數","已發行普通股數","發行股數","普通股股數"],0))
            cap=n(pick(r,["實收資本額","PaidInCapital"],0))
            par_raw=str(pick(r,["普通股每股面額","每股面額"],"10"))
            m=re.search(r"([\d.]+)",par_raw.replace(",",""))
            par=float(m.group(1)) if m else 10.0
            if shares<=0 and cap>0 and par>0: shares=int(cap/par)
            out[t]={"ticker":t,"name":name,"market":market,"industry":industry,"shares_issued":shares}
    return out

def fetch_twse_institutional(date=None):
    params={"response":"json","selectType":"ALLBUT0999"}
    if date: params["date"]=date.replace("-","")
    data=get_json(f"{TWSE_WEB}/rwd/zh/fund/T86",params=params)
    fields=data.get("fields",[])
    rows=data.get("data",[])
    out={}
    def idx_contains(words):
        for i,f in enumerate(fields):
            s=re.sub(r"\s+","",str(f))
            if all(w in s for w in words): return i
        return None
    idx_code=idx_contains(["證券代號"])
    idx_name=idx_contains(["證券名稱"])
    # TWSE T86 columns: 外陸(不含自營商)、投信、自營商(自行+避險)、三大法人
    idx_foreign=idx_contains(["外資及陸資","買賣超股數"])
    idx_trust=idx_contains(["投信","買賣超股數"])
    idx_dealer_self=idx_contains(["自營商","自行買賣","買賣超股數"])
    idx_dealer_hedge=idx_contains(["自營商","避險","買賣超股數"])
    idx_total=idx_contains(["三大法人","買賣超股數"])
    for row in rows:
        try:t=str(row[idx_code]).strip()
        except:continue
        if not ordinary_ticker(t):continue
        ds=iv(row[idx_dealer_self]) if idx_dealer_self is not None else 0
        dh=iv(row[idx_dealer_hedge]) if idx_dealer_hedge is not None else 0
        out[t]={
            "ticker":t,"name":str(row[idx_name]).strip() if idx_name is not None else "",
            "foreign":iv(row[idx_foreign]) if idx_foreign is not None else 0,
            "trust":iv(row[idx_trust]) if idx_trust is not None else 0,
            "dealer":ds+dh,
            "total":iv(row[idx_total]) if idx_total is not None else 0
        }
    return out

def fetch_tpex_institutional():
    arr=get_json(f"{TPEX}/tpex_3insti_daily_trading")
    out={}
    for r in arr:
        t=str(pick(r,["SecuritiesCompanyCode","證券代號","代號"],"")).strip()
        if not ordinary_ticker(t):continue
        name=str(pick(r,["CompanyName","證券名稱","名稱"],"")).strip()
        foreign=iv(pick(r,["ForeignInvestorsBalance","外資及陸資買賣超股數","外資及陸資買賣超"],0))
        trust=iv(pick(r,["InvestmentTrustBalance","投信買賣超股數","投信買賣超"],0))
        # 若有自行/避險分欄則相加
        d1=iv(pick(r,["DealerProprietaryBalance","自營商自行買賣買賣超股數","自營商自行買賣"],0))
        d2=iv(pick(r,["DealerHedgingBalance","自營商避險買賣超股數","自營商避險"],0))
        dealer=d1+d2
        total=iv(pick(r,["TotalBalance","三大法人買賣超股數","三大法人買賣超"],foreign+trust+dealer))
        out[t]={"ticker":t,"name":name,"foreign":foreign,"trust":trust,"dealer":dealer,"total":total}
    return out

def fetch_tdcc_distribution():
    data=get_json(f"{TDCC}/1-5",timeout=60)
    if isinstance(data,dict):
        for key in ("data","result","records"):
            if isinstance(data.get(key),list): return data[key]
    return data if isinstance(data,list) else []

def fetch_mis_quotes(tickers):
    channels=[]
    for t in tickers:
        channels.extend([f"tse_{t}.tw",f"otc_{t}.tw"])
    out={}
    for i in range(0,len(channels),120):
        ch=channels[i:i+120]
        params={"ex_ch":"|".join(ch),"json":"1","delay":"0"}
        data=get_json(MIS,params=params,timeout=25)
        for r in data.get("msgArray",[]):
            t=str(r.get("c","")).strip()
            if not ordinary_ticker(t) or t in out: continue
            y=n(r.get("y"))
            z=n(r.get("z"))
            if z<=0:
                bid=str(r.get("b","")).split("_")[0]
                ask=str(r.get("a","")).split("_")[0]
                z=n(bid) or n(ask) or y
            if y<=0 or z<=0: continue
            out[t]={"price":z,"prev_close":y,"change_pct":(z/y-1)*100,"exchange":r.get("ex","")}
        time.sleep(.2)
    return out
