from __future__ import annotations

import html
import json
import math
import re
import time
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
    "User-Agent": "Mozilla/5.0 (GitHub Actions; Taiwan Market Monitor)",
    "Accept": "application/json,text/plain,*/*",
    "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.7",
})


def now_tpe():
    return datetime.now(TZ)


def get_json(url, params=None, timeout=30, tries=4):
    last = None

    for i in range(tries):
        try:
            r = S.get(url, params=params, timeout=timeout)
            r.raise_for_status()
            return r.json()

        except Exception as e:
            last = e

            if i < tries - 1:
                time.sleep(1.2 * (i + 1))

    raise RuntimeError(f"GET failed: {url}: {last}")


def load_json(path, default=None):
    p = Path(path)

    if not p.exists():
        return {} if default is None else default

    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {} if default is None else default


def save_json(path, data):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)

    p.write_text(
        json.dumps(
            data,
            ensure_ascii=False,
            indent=2
        ),
        encoding="utf-8"
    )


def n(v, default=0.0):
    if v is None:
        return default

    s = str(v)

    s = html.unescape(s)
    s = re.sub(r"<[^>]+>", "", s)

    s = (
        s.replace(",", "")
         .replace("%", "")
         .replace("＋", "+")
         .replace("−", "-")
         .replace("－", "-")
         .replace("—", "")
         .strip()
    )

    if s in ("", "--", "---", "-"):
        return default

    try:
        return float(s)
    except Exception:
        return default


def iv(v, default=0):
    try:
        return int(round(n(v, default)))
    except Exception:
        return default


def pick(d, names, default=None):
    for k in names:
        if k in d and d[k] not in (None, ""):
            return d[k]

    for k, v in d.items():
        nk = re.sub(r"\s+", "", str(k))

        for name in names:
            if (
                re.sub(r"\s+", "", name) in nk
                and v not in (None, "")
            ):
                return v

    return default


def ordinary_ticker(t):
    return bool(
        re.fullmatch(
            r"\d{4}",
            str(t or "").strip()
        )
    )


def clean_name(name):
    s = html.unescape(str(name or "")).strip()

    s = (
        s.replace("股份有限公司", "")
         .replace("有限公司", "")
         .strip()
    )

    return s


def percentile_map(values: dict[str, float]):
    items = sorted(
        values.items(),
        key=lambda kv: kv[1]
    )

    out = {}
    L = len(items)

    if not L:
        return out

    for i, (k, v) in enumerate(items):
        out[k] = (
            100.0
            if L == 1
            else i / (L - 1) * 100
        )

    return out


def safe_mean(xs):
    xs = [
        x for x in xs
        if x is not None
        and not math.isnan(x)
    ]

    return (
        sum(xs) / len(xs)
        if xs
        else None
    )


def _idx(fields, *needles):
    for i, f in enumerate(fields):
        s = html.unescape(str(f))
        s = re.sub(r"<[^>]+>", "", s)
        s = re.sub(r"\s+", "", s)

        ok = True

        for needle in needles:
            opts = (
                needle
                if isinstance(needle, (list, tuple))
                else [needle]
            )

            if not any(str(x) in s for x in opts):
                ok = False
                break

        if ok:
            return i

    return None


# ---------------------------------------------------------
# 每日收盤行情
# ---------------------------------------------------------

def fetch_twse_latest_quotes():
    arr = get_json(
        f"{TWSE}/exchangeReport/STOCK_DAY_ALL"
    )

    out = {}

    for r in arr:
        t = str(
            pick(
                r,
                [
                    "Code",
                    "證券代號",
                    "股票代號",
                    "公司代號"
                ],
                ""
            )
        ).strip()

        if not ordinary_ticker(t):
            continue

        name = clean_name(
            pick(
                r,
                [
                    "Name",
                    "證券名稱",
                    "股票名稱",
                    "公司簡稱"
                ],
                ""
            )
        )

        close = n(
            pick(
                r,
                ["ClosingPrice", "收盤價", "收盤"]
            )
        )

        change = n(
            pick(
                r,
                ["Change", "漲跌價差", "漲跌"]
            )
        )

        vol = iv(
            pick(
                r,
                ["TradeVolume", "成交股數"]
            )
        )

        value = iv(
            pick(
                r,
                ["TradeValue", "成交金額"]
            )
        )

        prev = close - change if close else 0
        pct = change / prev * 100 if prev else 0

        out[t] = {
            "ticker": t,
            "name": name,
            "market": "twse",
            "price": close,
            "change": change,
            "change_pct": pct,
            "volume": vol,
            "turnover": value
        }

    return out


def fetch_tpex_latest_quotes():
    arr = get_json(
        f"{TPEX}/tpex_mainboard_daily_close_quotes"
    )

    out = {}

    for r in arr:
        t = str(
            pick(
                r,
                [
                    "SecuritiesCompanyCode",
                    "證券代號",
                    "代號",
                    "股票代號"
                ],
                ""
            )
        ).strip()

        if not ordinary_ticker(t):
            continue

        name = clean_name(
            pick(
                r,
                [
                    "CompanyName",
                    "證券名稱",
                    "名稱",
                    "公司名稱"
                ],
                ""
            )
        )

        close = n(
            pick(
                r,
                ["Close", "收盤", "收盤價"]
            )
        )

        ch = n(
            pick(
                r,
                ["Change", "漲跌", "漲跌價差"]
            )
        )

        vol = iv(
            pick(
                r,
                [
                    "TradingShares",
                    "成交股數",
                    "成交量"
                ]
            )
        )

        value = iv(
            pick(
                r,
                [
                    "TransactionAmount",
                    "成交金額",
                    "成交值"
                ]
            )
        )

        pct_raw = pick(
            r,
            [
                "ChangePercent",
                "漲跌幅",
                "漲跌幅(%)"
            ],
            None
        )

        if pct_raw is not None:
            pct = n(pct_raw)
        else:
            prev = close - ch if close else 0
            pct = ch / prev * 100 if prev else 0

        out[t] = {
            "ticker": t,
            "name": name,
            "market": "tpex",
            "price": close,
            "change": ch,
            "change_pct": pct,
            "volume": vol,
            "turnover": value
        }

    return out


# ---------------------------------------------------------
# 歷史收盤行情
# ---------------------------------------------------------

def fetch_twse_quotes_by_date(date):
    ds = date.replace("-", "")

    data = get_json(
        f"{TWSE_WEB}/rwd/zh/afterTrading/MI_INDEX",
        params={
            "response": "json",
            "date": ds,
            "type": "ALLBUT0999"
        },
        timeout=45
    )

    table = None

    for tb in data.get("tables", []):
        fs = tb.get("fields", [])

        if (
            _idx(fs, "證券代號") is not None
            and _idx(fs, "收盤價") is not None
        ):
            table = tb
            break

    if (
        not table
        and data.get("fields")
        and data.get("data")
    ):
        table = {
            "fields": data["fields"],
            "data": data["data"]
        }

    if not table:
        return {}

    fields = table.get("fields", [])
    rows = table.get("data", [])

    ic = _idx(fields, "證券代號")
    inn = _idx(fields, "證券名稱")
    iclose = _idx(fields, "收盤價")
    ivol = _idx(fields, "成交股數")
    ival = _idx(fields, "成交金額")
    ichg = _idx(fields, ["漲跌價差", "漲跌"])
    isign = _idx(fields, "漲跌(+/-)")

    out = {}

    for row in rows:
        try:
            t = str(row[ic]).strip()
        except Exception:
            continue

        if not ordinary_ticker(t):
            continue

        close = n(
            row[iclose]
            if iclose is not None
            else 0
        )

        ch = n(
            row[ichg]
            if ichg is not None
            else 0
        )

        if isign is not None:
            sg = html.unescape(str(row[isign]))
            sg = re.sub(r"<[^>]+>", "", sg)

            if "-" in sg or "－" in sg:
                ch = -abs(ch)
            elif "+" in sg or "＋" in sg:
                ch = abs(ch)

        prev = close - ch if close else 0

        out[t] = {
            "ticker": t,
            "name": clean_name(
                row[inn]
                if inn is not None
                else ""
            ),
            "market": "twse",
            "price": close,
            "change": ch,
            "change_pct": (
                ch / prev * 100
                if prev
                else 0
            ),
            "volume": (
                iv(row[ivol])
                if ivol is not None
                else 0
            ),
            "turnover": (
                iv(row[ival])
                if ival is not None
                else 0
            )
        }

    return out


def fetch_tpex_quotes_by_date(date):
    dt = datetime.strptime(
        date,
        "%Y-%m-%d"
    )

    roc = f"{dt.year - 1911}/{dt:%m/%d}"

    data = get_json(
        "https://www.tpex.org.tw/web/stock/aftertrading/otc_quotes_no1430/stk_wn1430_result.php",
        params={
            "l": "zh-tw",
            "d": roc,
            "se": "EW",
            "o": "json"
        },
        timeout=45
    )

    tables = data.get("tables", [])

    if not tables:
        return {}

    tb = tables[0]

    fields = tb.get("fields", [])
    rows = tb.get("data", [])

    if not rows:
        return {}

    ic = _idx(fields, ["代號", "證券代號"])
    inn = _idx(fields, ["名稱", "證券名稱"])
    iclose = _idx(fields, "收盤")
    ichg = _idx(fields, "漲跌")
    ivol = _idx(fields, "成交股數")
    ival = _idx(fields, "成交金額")

    # TPEx 偶爾欄名改版，保留位置 fallback
    if ic is None:
        ic = 0

    if inn is None:
        inn = 1

    if iclose is None:
        iclose = 2

    if ichg is None:
        ichg = 3

    if ivol is None:
        ivol = 7

    if ival is None:
        ival = 8

    out = {}

    for row in rows:
        try:
            t = str(row[ic]).strip()
        except Exception:
            continue

        if not ordinary_ticker(t):
            continue

        close = n(row[iclose])
        ch = n(row[ichg])

        prev = close - ch if close else 0

        out[t] = {
            "ticker": t,
            "name": clean_name(row[inn]),
            "market": "tpex",
            "price": close,
            "change": ch,
            "change_pct": (
                ch / prev * 100
                if prev
                else 0
            ),
            "volume": iv(row[ivol]),
            "turnover": iv(row[ival])
        }

    return out


# ---------------------------------------------------------
# 公司基本資料
# ---------------------------------------------------------

def fetch_master():
    out = {}

    sources = [
        (
            "twse",
            f"{TWSE}/opendata/t187ap03_L"
        ),
        (
            "tpex",
            f"{TPEX}/mopsfin_t187ap03_O"
        )
    ]

    for market, url in sources:
        try:
            arr = get_json(url)
        except Exception as e:
            print(
                "master source fail",
                market,
                e
            )
            continue

        if isinstance(arr, dict):
            for key in (
                "data",
                "result",
                "records"
            ):
                if isinstance(arr.get(key), list):
                    arr = arr[key]
                    break

        if not isinstance(arr, list):
            continue

        for r in arr:
            t = str(
                pick(
                    r,
                    [
                        "公司代號",
                        "SecuritiesCompanyCode",
                        "股票代號",
                        "證券代號",
                        "代號"
                    ],
                    ""
                )
            ).strip()

            if not ordinary_ticker(t):
                continue

            name = clean_name(
                pick(
                    r,
                    [
                        "公司簡稱",
                        "CompanyAbbreviation",
                        "證券名稱",
                        "名稱",
                        "公司名稱",
                        "CompanyName"
                    ],
                    ""
                )
            )

            industry = str(
                pick(
                    r,
                    [
                        "產業別",
                        "產業類別",
                        "Industry"
                    ],
                    ""
                )
            ).strip()

            shares = iv(
                pick(
                    r,
                    [
                        "已發行普通股數或TDR原發行股數",
                        "已發行普通股數",
                        "普通股股數",
                        "發行股數",
                        "IssuedShares",
                        "SharesIssued"
                    ],
                    0
                )
            )

            cap = n(
                pick(
                    r,
                    [
                        "實收資本額",
                        "PaidInCapital",
                        "PaidinCapital"
                    ],
                    0
                )
            )

            par_raw = str(
                pick(
                    r,
                    [
                        "普通股每股面額",
                        "每股面額",
                        "ParValue"
                    ],
                    "10"
                )
            )

            m = re.search(
                r"([\d.]+)",
                par_raw.replace(",", "")
            )

            par = (
                float(m.group(1))
                if m
                else 10.0
            )

            if (
                shares <= 0
                and cap > 0
                and par > 0
            ):
                shares = int(cap / par)

            out[t] = {
                "ticker": t,
                "name": name,
                "market": market,
                "industry": industry,
                "shares_issued": shares
            }

    return out


# ---------------------------------------------------------
# 上市法人
# ---------------------------------------------------------

def fetch_twse_institutional(date=None):
    params = {
        "response": "json",
        "selectType": "ALLBUT0999"
    }

    if date:
        params["date"] = date.replace("-", "")

    data = get_json(
        f"{TWSE_WEB}/rwd/zh/fund/T86",
        params=params,
        timeout=45
    )

    fields = data.get("fields", [])
    rows = data.get("data", [])

    # 有時資料會包在 tables
    if not rows:
        for tb in data.get("tables", []):
            fs = tb.get("fields", [])
            rs = tb.get("data", [])

            if (
                rs
                and _idx(fs, "證券代號") is not None
            ):
                fields = fs
                rows = rs
                break

    out = {}

    idx_code = _idx(
        fields,
        "證券代號"
    )

    idx_name = _idx(
        fields,
        "證券名稱"
    )

    idx_foreign = _idx(
        fields,
        ["外陸資", "外資及陸資"],
        "買賣超"
    )

    idx_trust = _idx(
        fields,
        "投信",
        "買賣超"
    )

    idx_dealer_total = _idx(
        fields,
        "自營商買賣超股數"
    )

    idx_dealer_self = _idx(
        fields,
        "自營商",
        "自行買賣",
        "買賣超"
    )

    idx_dealer_hedge = _idx(
        fields,
        "自營商",
        "避險",
        "買賣超"
    )

    idx_total = _idx(
        fields,
        "三大法人",
        "買賣超"
    )

    if idx_code is None:
        return {}

    for row in rows:
        try:
            t = str(row[idx_code]).strip()
        except Exception:
            continue

        if not ordinary_ticker(t):
            continue

        if idx_dealer_total is not None:
            dealer = iv(row[idx_dealer_total])
        else:
            dealer = (
                iv(row[idx_dealer_self])
                if idx_dealer_self is not None
                else 0
            ) + (
                iv(row[idx_dealer_hedge])
                if idx_dealer_hedge is not None
                else 0
            )

        foreign = (
            iv(row[idx_foreign])
            if idx_foreign is not None
            else 0
        )

        trust = (
            iv(row[idx_trust])
            if idx_trust is not None
            else 0
        )

        total = (
            iv(row[idx_total])
            if idx_total is not None
            else foreign + trust + dealer
        )

        out[t] = {
            "ticker": t,
            "name": clean_name(
                row[idx_name]
                if idx_name is not None
                else ""
            ),
            "foreign": foreign,
            "trust": trust,
            "dealer": dealer,
            "total": total
        }

    return out


# ---------------------------------------------------------
# 上櫃法人
# ---------------------------------------------------------

def _parse_tpex_inst_table(fields, rows):
    out = {}

    if not fields or not rows:
        return out

    idx_code = _idx(
        fields,
        ["代號", "證券代號"]
    )

    idx_name = _idx(
        fields,
        ["名稱", "證券名稱"]
    )

    idx_foreign = _idx(
        fields,
        ["外資及陸資", "外資"],
        "買賣超"
    )

    idx_trust = _idx(
        fields,
        "投信",
        "買賣超"
    )

    idx_dealer_total = _idx(
        fields,
        "自營商",
        "買賣超"
    )

    idx_total = _idx(
        fields,
        ["三大法人", "合計"],
        "買賣超"
    )

    if idx_code is None:
        return out

    for row in rows:
        try:
            t = str(row[idx_code]).strip()
        except Exception:
            continue

        if not ordinary_ticker(t):
            continue

        foreign = (
            iv(row[idx_foreign])
            if idx_foreign is not None
            else 0
        )

        trust = (
            iv(row[idx_trust])
            if idx_trust is not None
            else 0
        )

        dealer = (
            iv(row[idx_dealer_total])
            if idx_dealer_total is not None
            else 0
        )

        total = (
            iv(row[idx_total])
            if idx_total is not None
            else foreign + trust + dealer
        )

        out[t] = {
            "ticker": t,
            "name": clean_name(
                row[idx_name]
                if idx_name is not None
                else ""
            ),
            "foreign": foreign,
            "trust": trust,
            "dealer": dealer,
            "total": total
        }

    return out


def fetch_tpex_institutional(date=None):
    if date:
        dt = datetime.strptime(
            date,
            "%Y-%m-%d"
        )

        roc = (
            f"{dt.year - 1911}/{dt:%m/%d}"
        )

        data = get_json(
            "https://www.tpex.org.tw/web/stock/3insti/daily_trade/3itrade_hedge_result.php",
            params={
                "l": "zh-tw",
                "o": "json",
                "se": "EW",
                "t": "D",
                "d": roc,
                "s": "0,asc"
            },
            timeout=45
        )

        out = {}

        # 舊格式 aaData
        aa = data.get("aaData", [])

        if aa:
            for row in aa:
                if len(row) < 24:
                    continue

                t = str(row[0]).strip()

                if not ordinary_ticker(t):
                    continue

                foreign = iv(row[10])
                trust = iv(row[13])
                dealer = iv(row[22])
                total = iv(row[23])

                out[t] = {
                    "ticker": t,
                    "name": clean_name(row[1]),
                    "foreign": foreign,
                    "trust": trust,
                    "dealer": dealer,
                    "total": total
                }

            if out:
                return out

        # 新格式 tables
        for tb in data.get("tables", []):
            parsed = _parse_tpex_inst_table(
                tb.get("fields", []),
                tb.get("data", [])
            )

            if parsed:
                return parsed

        # 有些回傳直接是 fields / data
        parsed = _parse_tpex_inst_table(
            data.get("fields", []),
            data.get("data", [])
        )

        if parsed:
            return parsed

        return {}

    # 最新一日優先使用 TPEx OpenAPI
    arr = get_json(
        f"{TPEX}/tpex_3insti_daily_trading"
    )

    if isinstance(arr, dict):
        for key in (
            "data",
            "result",
            "records"
        ):
            if isinstance(arr.get(key), list):
                arr = arr[key]
                break

    if not isinstance(arr, list):
        return {}

    out = {}

    for r in arr:
        t = str(
            pick(
                r,
                [
                    "SecuritiesCompanyCode",
                    "證券代號",
                    "代號"
                ],
                ""
            )
        ).strip()

        if not ordinary_ticker(t):
            continue

        name = clean_name(
            pick(
                r,
                [
                    "CompanyName",
                    "證券名稱",
                    "名稱"
                ],
                ""
            )
        )

        foreign = iv(
            pick(
                r,
                [
                    "ForeignInvestorsBalance",
                    "ForeignInvestorsNet",
                    "外資及陸資買賣超股數",
                    "外資及陸資買賣超"
                ],
                0
            )
        )

        trust = iv(
            pick(
                r,
                [
                    "InvestmentTrustBalance",
                    "InvestmentTrustNet",
                    "投信買賣超股數",
                    "投信買賣超"
                ],
                0
            )
        )

        dealer = iv(
            pick(
                r,
                [
                    "DealerBalance",
                    "DealerNet",
                    "自營商買賣超股數",
                    "自營商買賣超"
                ],
                0
            )
        )

        if dealer == 0:
            dealer = (
                iv(
                    pick(
                        r,
                        [
                            "DealerProprietaryBalance",
                            "自營商自行買賣買賣超股數",
                            "自營商自行買賣"
                        ],
                        0
                    )
                )
                +
                iv(
                    pick(
                        r,
                        [
                            "DealerHedgingBalance",
                            "自營商避險買賣超股數",
                            "自營商避險"
                        ],
                        0
                    )
                )
            )

        total = iv(
            pick(
                r,
                [
                    "TotalBalance",
                    "三大法人買賣超股數",
                    "三大法人買賣超"
                ],
                foreign + trust + dealer
            )
        )

        out[t] = {
            "ticker": t,
            "name": name,
            "foreign": foreign,
            "trust": trust,
            "dealer": dealer,
            "total": total
        }

    return out


# ---------------------------------------------------------
# TDCC
# ---------------------------------------------------------

def fetch_tdcc_distribution():
    data = get_json(
        f"{TDCC}/1-5",
        timeout=60
    )

    if isinstance(data, dict):
        for key in (
            "data",
            "result",
            "records"
        ):
            if isinstance(data.get(key), list):
                return data[key]

    return (
        data
        if isinstance(data, list)
        else []
    )


# ---------------------------------------------------------
# TWSE MIS 即時行情
# ---------------------------------------------------------

def fetch_mis_quotes(tickers):
    channels = []

    for t in tickers:
        channels.extend([
            f"tse_{t}.tw",
            f"otc_{t}.tw"
        ])

    out = {}

    for i in range(
        0,
        len(channels),
        120
    ):
        ch = channels[i:i + 120]

        data = get_json(
            MIS,
            params={
                "ex_ch": "|".join(ch),
                "json": "1",
                "delay": "0"
            },
            timeout=25
        )

        for r in data.get("msgArray", []):
            t = str(
                r.get("c", "")
            ).strip()

            if (
                not ordinary_ticker(t)
                or t in out
            ):
                continue

            y = n(r.get("y"))
            z = n(r.get("z"))

            # 盤中若最新成交價暫時空白，使用最佳買／賣價 fallback
            if z <= 0:
                bid = str(
                    r.get("b", "")
                ).split("_")[0]

                ask = str(
                    r.get("a", "")
                ).split("_")[0]

                z = (
                    n(bid)
                    or n(ask)
                    or y
                )

            if y <= 0 or z <= 0:
                continue

            out[t] = {
                "price": z,
                "prev_close": y,
                "change_pct": (
                    z / y - 1
                ) * 100,
                "exchange": r.get(
                    "ex",
                    ""
                )
            }

        time.sleep(0.2)

    return out
