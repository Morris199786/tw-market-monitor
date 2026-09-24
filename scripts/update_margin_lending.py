from sources import *
from datetime import datetime
from statistics import median
import math


HISTORY_TARGET = 22
TOP_N = 30

MIN_TWSE_MARGIN_ROWS = 200
MIN_TPEX_MARGIN_ROWS = 150
MIN_BORROW_ROWS = 250


def roc_date(iso_date):
    dt = datetime.strptime(
        iso_date,
        "%Y-%m-%d"
    )
    return (
        f"{dt.year - 1911}/"
        f"{dt.month:02d}/"
        f"{dt.day:02d}"
    )


def clean_field(x):
    return re.sub(
        r"\s+",
        "",
        re.sub(
            r"<[^>]+>",
            "",
            html.unescape(
                str(x or "")
            )
        )
    )


def idx_contains(fields, *needles):
    for i, f in enumerate(fields):
        s = clean_field(f)
        if all(
            any(
                str(opt) in s
                for opt in (
                    n
                    if isinstance(
                        n,
                        (list, tuple)
                    )
                    else [n]
                )
            )
            for n in needles
        ):
            return i
    return None


def tables_of(data):
    """
    TWSE / TPEx 回傳格式不完全一致：
    有些是 {"tables":[...]},
    有些直接把 fields / data 放在最外層。
    這裡統一轉成 table list。
    """
    if not isinstance(data, dict):
        return []

    tables = data.get(
        "tables",
        []
    )

    if (
        isinstance(tables, list)
        and tables
    ):
        return tables

    if (
        isinstance(
            data.get("fields"),
            list
        )
        and isinstance(
            data.get("data"),
            list
        )
    ):
        return [
            {
                "fields": data.get(
                    "fields",
                    []
                ),
                "data": data.get(
                    "data",
                    []
                ),
            }
        ]

    return []


def row_value(row, i, default=0):
    if (
        i is None
        or i < 0
        or i >= len(row)
    ):
        return default

    return row[i]


def get_twse_margin(date):
    data = get_json(
        f"{TWSE_WEB}/rwd/zh/marginTrading/MI_MARGN",
        params={
            "date": date.replace("-", ""),
            "response": "json",
            "selectType": "ALL",
        },
        timeout=45,
    )

    out = {}

    for tb in tables_of(data):
        fields = tb.get(
            "fields",
            []
        )
        rows = tb.get(
            "data",
            []
        )

        if not rows:
            continue

        ic = idx_contains(
            fields,
            ["代號", "證券代號", "股票代號"]
        )
        inn = idx_contains(
            fields,
            ["名稱", "證券名稱", "股票名稱"]
        )

        # TWSE 融資融券明細標準欄位順序：
        # 代號 名稱 融資買進 融資賣出 現金償還 前日餘額 今日餘額 限額 ...
        if ic is None and len(rows[0]) >= 15:
            ic = 0

        if ic is None:
            continue

        for row in rows:
            t = str(
                row_value(
                    row,
                    ic,
                    ""
                )
            ).strip()

            if not ordinary_ticker(t):
                continue

            if len(row) < 8:
                continue

            prev_bal = n(
                row_value(
                    row,
                    5,
                    0
                )
            )
            bal = n(
                row_value(
                    row,
                    6,
                    0
                )
            )
            limit_lots = n(
                row_value(
                    row,
                    7,
                    0
                )
            )

            out[t] = {
                "ticker": t,
                "name": clean_name(
                    row_value(
                        row,
                        inn if inn is not None else 1,
                        ""
                    )
                ),
                "market": "twse",
                "margin_prev_lots": prev_bal,
                "margin_balance_lots": bal,
                "margin_limit_lots": limit_lots,
                "margin_usage_pct": (
                    bal / limit_lots * 100
                    if limit_lots > 0
                    else None
                ),
            }

    return out


def get_tpex_margin(date):
    data = get_json(
        "https://www.tpex.org.tw/web/stock/margin_trading/margin_balance/margin_bal_result.php",
        params={
            "l": "zh-tw",
            "o": "json",
            "d": roc_date(date),
        },
        timeout=45,
    )

    out = {}

    for tb in tables_of(data):
        rows = tb.get(
            "data",
            []
        )

        for row in rows:
            if len(row) < 9:
                continue

            t = str(
                row[0]
            ).strip()

            if not ordinary_ticker(t):
                continue

            # TPEx：
            # 0代號 1名稱 2前資餘額 3資買 4資賣 5現償
            # 6資餘額 7資屬證金 8資使用率 9資限額 ...
            prev_bal = n(row[2])
            bal = n(row[6])
            usage = (
                n(row[8])
                if len(row) > 8
                else None
            )
            limit_lots = (
                n(row[9])
                if len(row) > 9
                else 0
            )

            out[t] = {
                "ticker": t,
                "name": clean_name(
                    row[1]
                ),
                "market": "tpex",
                "margin_prev_lots": prev_bal,
                "margin_balance_lots": bal,
                "margin_limit_lots": limit_lots,
                "margin_usage_pct": (
                    usage
                    if usage is not None
                    else (
                        bal
                        / limit_lots
                        * 100
                        if limit_lots > 0
                        else None
                    )
                ),
            }

    return out


def get_borrow_balance(date, master):
    """
    借券餘額：
    以欄名辨識，不再假設固定欄位位置。
    同一股票可能分不同借券系統列示，因此依股票代號加總。
    原始單位若為股，統一換算成張。
    """
    data = get_json(
        f"{TWSE_WEB}/exchangeReport/TWT72U",
        params={
            "date": date.replace("-", ""),
            "response": "json",
            "selectType": "SLBNLB",
        },
        timeout=45,
    )

    out = {}

    for tb in tables_of(data):
        fields = tb.get(
            "fields",
            []
        )
        rows = tb.get(
            "data",
            []
        )

        ic = idx_contains(
            fields,
            [
                "證券代號",
                "標的證券代號",
                "股票代號",
                "代號",
            ]
        )
        inn = idx_contains(
            fields,
            [
                "證券名稱",
                "中文名稱",
                "名稱",
            ]
        )
        iprev = idx_contains(
            fields,
            [
                "昨日借券餘額",
                "前日借券餘額",
            ]
        )
        inew = idx_contains(
            fields,
            [
                "今日新增借券",
                "本日新增借券",
                "新增借券",
            ]
        )
        ireturn = idx_contains(
            fields,
            [
                "今日還券",
                "本日還券",
                "還券了結",
                "還券",
            ]
        )
        ibal = idx_contains(
            fields,
            [
                "今日借券餘額",
                "本日借券餘額",
                "借券餘額",
            ]
        )

        if ic is None:
            # TWT72U 另一種格式：
            # 系統別、代號、昨餘額、新增、還券、今餘額、...
            if rows and len(rows[0]) >= 6:
                ic = 1
                iprev = 2
                inew = 3
                ireturn = 4
                ibal = 5
                inn = 9 if len(rows[0]) > 9 else None
            else:
                continue

        for row in rows:
            t = str(
                row_value(
                    row,
                    ic,
                    ""
                )
            ).strip()

            if (
                not ordinary_ticker(t)
                or t not in master
            ):
                continue

            prev_shares = n(
                row_value(
                    row,
                    iprev,
                    0
                )
            )
            new_shares = n(
                row_value(
                    row,
                    inew,
                    0
                )
            )
            return_shares = n(
                row_value(
                    row,
                    ireturn,
                    0
                )
            )
            balance_shares = n(
                row_value(
                    row,
                    ibal,
                    0
                )
            )

            x = out.setdefault(
                t,
                {
                    "ticker": t,
                    "name": clean_name(
                        row_value(
                            row,
                            inn,
                            master[t].get(
                                "name",
                                ""
                            )
                        )
                    ),
                    "market": master[t].get(
                        "market"
                    ),
                    "borrow_prev_lots": 0.0,
                    "borrow_new_lots": 0.0,
                    "borrow_return_lots": 0.0,
                    "borrow_balance_lots": 0.0,
                }
            )

            x["borrow_prev_lots"] += (
                prev_shares / 1000
            )
            x["borrow_new_lots"] += (
                new_shares / 1000
            )
            x["borrow_return_lots"] += (
                return_shares / 1000
            )
            x["borrow_balance_lots"] += (
                balance_shares / 1000
            )

    return out

def get_short_sale_balance(date, master):
    """
    融券／借券賣出餘額：
    只作借券異常的確認訊號，不等同借券餘額本身。
    使用欄名辨識；若欄名不可用，再使用官方固定欄位位置。
    """
    data = get_json(
        f"{TWSE_WEB}/exchangeReport/TWT93U",
        params={
            "date": date.replace("-", ""),
            "response": "json",
        },
        timeout=45,
    )

    out = {}

    for tb in tables_of(data):
        fields = tb.get(
            "fields",
            []
        )
        rows = tb.get(
            "data",
            []
        )

        ic = idx_contains(
            fields,
            [
                "證券代號",
                "股票代號",
                "代號",
            ]
        )

        iprev = idx_contains(
            fields,
            "借券賣出",
            [
                "前日餘額",
                "昨日餘額",
            ]
        )
        isold = idx_contains(
            fields,
            "借券賣出",
            [
                "賣出股數",
                "市場借券賣出",
                "本日市場借券賣出",
            ]
        )
        ireturn = idx_contains(
            fields,
            "借券賣出",
            [
                "還券股數",
                "還券",
            ]
        )
        iadj = idx_contains(
            fields,
            "借券賣出",
            [
                "調整股數",
                "調整",
            ]
        )
        ibal = idx_contains(
            fields,
            "借券賣出",
            [
                "餘額股數",
                "餘額",
            ]
        )

        if ic is None and rows:
            ic = 1 if len(rows[0]) >= 14 else 0

        for row in rows:
            if ic is None:
                continue

            t = str(
                row_value(
                    row,
                    ic,
                    ""
                )
            ).strip()

            if (
                not ordinary_ticker(t)
                or t not in master
            ):
                continue

            # 官方 TWT93U 固定格式 fallback：
            # 日期、證券代號、前融券...、前借券賣出餘額、
            # 本日市場借券賣出、還券、調整、本日借券賣出餘額...
            if (
                iprev is None
                or isold is None
                or ibal is None
            ):
                if len(row) >= 14:
                    # 若第一欄為日期，代號在 index 1
                    offset = (
                        1
                        if ordinary_ticker(
                            str(row[1]).strip()
                        )
                        else 0
                    )

                    if offset == 1:
                        iprev2 = 8
                        isold2 = 9
                        ireturn2 = 10
                        iadj2 = 11
                        ibal2 = 12
                    else:
                        iprev2 = 8
                        isold2 = 9
                        ireturn2 = 10
                        iadj2 = 11
                        ibal2 = 12
                else:
                    continue
            else:
                iprev2 = iprev
                isold2 = isold
                ireturn2 = ireturn
                iadj2 = iadj
                ibal2 = ibal

            out[t] = {
                "short_sell_prev_lots": (
                    n(
                        row_value(
                            row,
                            iprev2,
                            0
                        )
                    )
                    / 1000
                ),
                "short_sell_today_lots": (
                    n(
                        row_value(
                            row,
                            isold2,
                            0
                        )
                    )
                    / 1000
                ),
                "short_sell_return_lots": (
                    n(
                        row_value(
                            row,
                            ireturn2,
                            0
                        )
                    )
                    / 1000
                ),
                "short_sell_adjust_lots": (
                    n(
                        row_value(
                            row,
                            iadj2,
                            0
                        )
                    )
                    / 1000
                ),
                "short_sell_balance_lots": (
                    n(
                        row_value(
                            row,
                            ibal2,
                            0
                        )
                    )
                    / 1000
                ),
            }

    return out

def history_market_dates():
    out = []

    for p in sorted(
        (
            ROOT
            / "data/history/market"
        ).glob("*.json")
    ):
        d = load_json(
            p,
            {}
        )

        if (
            d.get("date")
            and d.get("stocks")
        ):
            out.append(
                d["date"]
            )

    return out


def load_market_snapshot(date):
    return load_json(
        ROOT
        / (
            "data/history/market/"
            f"{date}.json"
        ),
        {}
    ).get(
        "stocks",
        {}
    )


def fetch_daily_snapshot(
    date,
    master,
    need_short=False
):
    old_path = (
        ROOT
        / (
            "data/history/"
            "margin_lending/"
            f"{date}.json"
        )
    )

    old = load_json(
        old_path,
        {}
    )

    old_margin = old.get(
        "margin",
        {}
    )
    old_borrow = old.get(
        "borrow",
        {}
    )

    if (
        len(old_margin.get("twse", {}))
        >= MIN_TWSE_MARGIN_ROWS
        and len(old_margin.get("tpex", {}))
        >= MIN_TPEX_MARGIN_ROWS
        and (
            len(old_borrow.get("twse", {}))
            + len(old_borrow.get("tpex", {}))
        ) >= MIN_BORROW_ROWS
        and (
            not need_short
            or old.get(
                "short_sell_checked"
            )
        )
    ):
        return old

    twse_margin = {}
    tpex_margin = {}
    borrow_all = {}
    short_all = {}

    try:
        twse_margin = get_twse_margin(
            date
        )
    except Exception as e:
        print(
            "TWSE margin fail",
            date,
            repr(e)
        )

    try:
        tpex_margin = get_tpex_margin(
            date
        )
    except Exception as e:
        print(
            "TPEx margin fail",
            date,
            repr(e)
        )

    try:
        borrow_all = get_borrow_balance(
            date,
            master
        )
    except Exception as e:
        print(
            "borrow balance fail",
            date,
            repr(e)
        )

    if need_short:
        try:
            short_all = (
                get_short_sale_balance(
                    date,
                    master
                )
            )
        except Exception as e:
            print(
                "short sale balance fail",
                date,
                repr(e)
            )

    borrow_twse = {
        t: r
        for t, r in borrow_all.items()
        if r.get("market") == "twse"
    }

    borrow_tpex = {
        t: r
        for t, r in borrow_all.items()
        if r.get("market") == "tpex"
    }

    short_twse = {
        t: r
        for t, r in short_all.items()
        if master.get(
            t,
            {}
        ).get("market") == "twse"
    }

    short_tpex = {
        t: r
        for t, r in short_all.items()
        if master.get(
            t,
            {}
        ).get("market") == "tpex"
    }

    # 若本次抓不到，舊的健康資料可保留。
    if (
        len(twse_margin)
        < MIN_TWSE_MARGIN_ROWS
    ):
        twse_margin = old_margin.get(
            "twse",
            {}
        )

    if (
        len(tpex_margin)
        < MIN_TPEX_MARGIN_ROWS
    ):
        tpex_margin = old_margin.get(
            "tpex",
            {}
        )

    if (
        len(borrow_twse)
        + len(borrow_tpex)
        < MIN_BORROW_ROWS
    ):
        borrow_twse = old_borrow.get(
            "twse",
            {}
        )
        borrow_tpex = old_borrow.get(
            "tpex",
            {}
        )

    if need_short and not short_all:
        short_twse = old.get(
            "short_sell",
            {}
        ).get(
            "twse",
            {}
        )
        short_tpex = old.get(
            "short_sell",
            {}
        ).get(
            "tpex",
            {}
        )

    snap = {
        "date": date,
        "updated_at": (
            now_tpe()
            .isoformat(
                timespec="minutes"
            )
        ),
        "margin": {
            "twse": twse_margin,
            "tpex": tpex_margin,
        },
        "borrow": {
            "twse": borrow_twse,
            "tpex": borrow_tpex,
        },
        "short_sell": {
            "twse": short_twse,
            "tpex": short_tpex,
        },
        "short_sell_checked": (
            bool(need_short)
        ),
    }

    save_json(
        old_path,
        snap
    )

    return snap


def healthy_snapshot(snap):
    return (
        len(
            snap.get(
                "margin",
                {}
            ).get(
                "twse",
                {}
            )
        )
        >= MIN_TWSE_MARGIN_ROWS
        and len(
            snap.get(
                "margin",
                {}
            ).get(
                "tpex",
                {}
            )
        )
        >= MIN_TPEX_MARGIN_ROWS
        and (
            len(
                snap.get(
                    "borrow",
                    {}
                ).get(
                    "twse",
                    {}
                )
            )
            + len(
                snap.get(
                    "borrow",
                    {}
                ).get(
                    "tpex",
                    {}
                )
            )
        )
        >= MIN_BORROW_ROWS
    )


def pct_change(delta, base):
    if base > 0:
        return (
            delta
            / base
            * 100
        )

    if delta > 0:
        return 999.0

    return 0.0


def cap(v, lo, hi):
    return max(
        lo,
        min(
            hi,
            v
        )
    )


def latest_price_change(
    ticker,
    latest_market
):
    q = latest_market.get(
        ticker,
        {}
    )

    return float(
        q.get(
            "change_pct"
        )
        or 0
    )


def avg5_volume_lots(
    ticker,
    dates
):
    vals = []

    for d in dates[-5:]:
        q = load_market_snapshot(
            d
        ).get(
            ticker,
            {}
        )

        v = float(
            q.get(
                "volume"
            )
            or 0
        )

        if v > 0:
            vals.append(
                v / 1000
            )

    if not vals:
        return 0.0

    return (
        sum(vals)
        / len(vals)
    )


def metric_series(
    history,
    market,
    ticker,
    key,
):
    vals = []

    for h in history:
        row = (
            h.get(
                key,
                {}
            )
            .get(
                market,
                {}
            )
            .get(
                ticker
            )
        )

        if not row:
            continue

        field = (
            "margin_balance_lots"
            if key == "margin"
            else "borrow_balance_lots"
        )

        val = row.get(
            field
        )

        if val is None:
            continue

        vals.append(
            (
                h.get("date"),
                float(val)
            )
        )

    return vals


def short_series(
    history,
    market,
    ticker
):
    vals = []

    for h in history:
        row = (
            h.get(
                "short_sell",
                {}
            )
            .get(
                market,
                {}
            )
            .get(
                ticker
            )
        )

        if not row:
            continue

        v = row.get(
            "short_sell_balance_lots"
        )

        if v is None:
            continue

        vals.append(
            (
                h.get("date"),
                float(v)
            )
        )

    return vals


def build_item(
    ticker,
    meta,
    history,
    market,
    kind,
    market_dates,
    latest_market,
):
    series = metric_series(
        history,
        market,
        ticker,
        kind,
    )

    if len(series) < 2:
        return None

    dates = [
        x[0]
        for x in series
    ]
    vals = [
        x[1]
        for x in series
    ]

    deltas = [
        vals[i]
        - vals[i - 1]
        for i in range(
            1,
            len(vals)
        )
    ]

    d1 = deltas[-1]
    prev = vals[-2]
    balance = vals[-1]

    if len(vals) >= 6:
        d5 = (
            vals[-1]
            - vals[-6]
        )
        base5 = vals[-6]
        up5 = sum(
            1
            for x
            in deltas[-5:]
            if x > 0
        )
    else:
        d5 = d1
        base5 = prev
        up5 = sum(
            1
            for x
            in deltas
            if x > 0
        )

    if len(deltas) >= 10:
        up10 = sum(
            1
            for x
            in deltas[-10:]
            if x > 0
        )
    else:
        up10 = sum(
            1
            for x
            in deltas
            if x > 0
        )

    historical = (
        deltas[-21:-1]
        if len(deltas) >= 21
        else deltas[:-1]
    )

    abs_hist = [
        abs(x)
        for x in historical
        if x is not None
    ]

    normal_daily = (
        median(abs_hist)
        if abs_hist
        else 0
    )

    # 避免平常完全零變化時除以零。
    denom = max(
        normal_daily,
        1.0
    )

    anomaly20 = (
        d1 / denom
        if d1 > 0
        else 0
    )

    avg5 = avg5_volume_lots(
        ticker,
        market_dates
    )

    d1_vs_vol = (
        d1 / avg5 * 100
        if (
            d1 > 0
            and avg5 > 0
        )
        else 0
    )

    d5_vs_vol = (
        d5 / avg5 * 100
        if (
            d5 > 0
            and avg5 > 0
        )
        else 0
    )

    d1_pct = pct_change(
        d1,
        prev
    )
    d5_pct = pct_change(
        d5,
        base5
    )

    substantive = (
        d1 >= 100
        or d1_vs_vol >= 5
        or d1_pct >= 10
    )

    sudden = (
        d1 > 0
        and anomaly20 >= 1.5
        and substantive
    )

    trend = (
        d5 > 0
        and up5 >= 4
    )

    if sudden:
        priority = "sudden"
        priority_rank = 0
    elif trend:
        priority = "trend"
        priority_rank = 1
    else:
        priority = "increase"
        priority_rank = 2

    sudden_score = (
        cap(
            anomaly20 / 5 * 100,
            0,
            100
        )
        * 0.45
        + cap(
            d1_vs_vol / 20 * 100,
            0,
            100
        )
        * 0.30
        + cap(
            d1_pct / 50 * 100,
            0,
            100
        )
        * 0.15
        + cap(
            math.log10(
                max(
                    d1,
                    1
                )
            )
            / 4
            * 100,
            0,
            100
        )
        * 0.10
    )

    trend_score = (
        cap(
            up5 / 5 * 100,
            0,
            100
        )
        * 0.35
        + cap(
            up10 / 10 * 100,
            0,
            100
        )
        * 0.20
        + cap(
            d5_pct / 50 * 100,
            0,
            100
        )
        * 0.20
        + cap(
            d5_vs_vol / 40 * 100,
            0,
            100
        )
        * 0.25
    )

    if priority == "sudden":
        score = (
            sudden_score
            * 0.65
            + trend_score
            * 0.35
        )
    elif priority == "trend":
        score = (
            trend_score
            * 0.75
            + sudden_score
            * 0.25
        )
    else:
        score = (
            trend_score
            * 0.55
            + sudden_score
            * 0.45
        )

    price_change = (
        latest_price_change(
            ticker,
            latest_market
        )
    )

    tags = []

    if sudden:
        if anomaly20 >= 3:
            tags.append(
                "極端異常"
            )
        elif anomaly20 >= 2:
            tags.append(
                "明顯異常"
            )
        else:
            tags.append(
                "單日異動"
            )

        tags.append(
            (
                "融資暴增"
                if kind == "margin"
                else "借券暴增"
            )
        )

    if up5 >= 5:
        tags.append(
            "近5日5增"
        )
    elif up5 >= 4:
        tags.append(
            "近5日4增"
        )
    elif up5 >= 3:
        tags.append(
            "近5日偏增"
        )

    if kind == "margin":
        if (
            d1 > 0
            and price_change >= 1
        ):
            tags.append(
                "追價融資"
            )
        elif (
            d1 > 0
            and price_change < 0
        ):
            tags.append(
                "逆勢加融資"
            )
        elif trend:
            tags.append(
                "融資持續進場"
            )

    short_d1 = None
    short_d5 = None

    if kind == "borrow":
        ss = short_series(
            history,
            market,
            ticker
        )

        if len(ss) >= 2:
            sv = [
                x[1]
                for x in ss
            ]
            short_d1 = (
                sv[-1]
                - sv[-2]
            )

            if len(sv) >= 6:
                short_d5 = (
                    sv[-1]
                    - sv[-6]
                )

            if (
                short_d1 is not None
                and short_d1 > 0
            ):
                tags.append(
                    "借券賣出同步增加"
                )

    reason_bits = []

    if d1 > 0:
        reason_bits.append(
            f"今日+{d1:,.0f}張"
        )

    if anomaly20 > 0:
        reason_bits.append(
            "20日異常"
            f"{anomaly20:.1f}倍"
        )

    if d1_vs_vol > 0:
        reason_bits.append(
            "占5日均量"
            f"{d1_vs_vol:.1f}%"
        )

    if d5 > 0:
        reason_bits.append(
            f"5日+{d5:,.0f}張"
        )

    reason_bits.append(
        f"近5日{up5}日增加"
    )

    if (
        kind == "borrow"
        and short_d1 is not None
        and short_d1 > 0
    ):
        reason_bits.append(
            "借券賣出同步+"
            f"{short_d1:,.0f}張"
        )

    return {
        "ticker": ticker,
        "name": clean_name(
            meta.get(
                "name",
                ""
            )
        ),
        "market": market,
        "priority": priority,
        "priority_rank": priority_rank,
        "score": round(
            score,
            1
        ),
        "change_pct": price_change,
        "tags": tags,
        "reason": "｜".join(
            reason_bits
        ),
        "raw": {
            "balance_lots": round(
                balance,
                1
            ),
            "change_1d_lots": round(
                d1,
                1
            ),
            "change_1d_pct": round(
                d1_pct,
                2
            ),
            "change_5d_lots": round(
                d5,
                1
            ),
            "change_5d_pct": round(
                d5_pct,
                2
            ),
            "up_days_5d": up5,
            "up_days_10d": up10,
            "normal_daily_change_20d_lots": round(
                normal_daily,
                1
            ),
            "anomaly_20d": round(
                anomaly20,
                2
            ),
            "avg5_volume_lots": round(
                avg5,
                1
            ),
            "change_1d_vs_avg5_volume_pct": round(
                d1_vs_vol,
                2
            ),
            "change_5d_vs_avg5_volume_pct": round(
                d5_vs_vol,
                2
            ),
            "short_sell_change_1d_lots": (
                round(
                    short_d1,
                    1
                )
                if short_d1 is not None
                else None
            ),
            "short_sell_change_5d_lots": (
                round(
                    short_d5,
                    1
                )
                if short_d5 is not None
                else None
            ),
        },
    }


def rank_kind(
    kind,
    market,
    history,
    master,
    market_dates,
    latest_market,
):
    items = []

    for ticker, meta in master.items():
        ticker = str(ticker)

        if (
            not ordinary_ticker(
                ticker
            )
            or meta.get(
                "market"
            ) != market
        ):
            continue

        item = build_item(
            ticker,
            meta,
            history,
            market,
            kind,
            market_dates,
            latest_market,
        )

        if not item:
            continue

        raw = item["raw"]

        if (
            raw["change_1d_lots"] <= 0
            and raw["change_5d_lots"] <= 0
        ):
            continue

        items.append(
            item
        )

    items.sort(
        key=lambda x: (
            x["priority_rank"],
            -x["score"],
            -x["raw"][
                "change_1d_lots"
            ],
            -x["raw"][
                "change_5d_lots"
            ],
        )
    )

    return items[:TOP_N]


def logic_payload():
    return {
        "version": "2026-09-25-v3-parser-fix",
        "universe": (
            "全台股上市／上櫃普通股，"
            "不限科技股"
        ),
        "lookback_days": 20,
        "top_n_each_market": TOP_N,
        "ranking": [
            "第一順位：今日突然暴增",
            "第二順位：近5日持續累積",
            "第三順位：一般增加",
        ],
        "details": [
            "單日異常：比較今日餘額增加量、今日增幅、今日增加量占近5日均量，以及今日增加量相對過去20日正常每日變化的倍數",
            "20日正常每日變化使用每日餘額變化絕對值的中位數，降低單一極端日扭曲基準的問題",
            "突發異常需今日增加，20日異常倍數至少1.5倍，且今日至少符合：增加100張、占5日均量5%、或餘額增幅10%其中之一",
            "異常標籤：1.5～2倍＝單日異動，2～3倍＝明顯異常，3倍以上＝極端異常",
            "趨勢：觀察5日淨增加、5日增幅、近5日增加天數、近10日增加天數，以及5日增加量占近5日均量比例",
            "近5日5天增加標示「近5日5增」；4天增加標示「近5日4增」；這類持續累積排在單日突發異常之後",
            "融資另外結合股價：上漲且融資增加標示追價融資；下跌且融資增加標示逆勢加融資",
            "借券主排名使用借券餘額；借券賣出餘額只作確認訊號。兩者同步增加會另外標示，不把所有借券增加直接視為放空",
            "上市與上櫃分開排名，各取前30名",
        ],
        "score_is_probability": False,
    }


def main():
    master = load_json(
        ROOT / "data/master.json",
        {}
    ).get(
        "stocks",
        {}
    )

    market_latest = load_json(
        ROOT / "data/market_latest.json",
        {}
    )

    latest_market = market_latest.get(
        "stocks",
        {}
    )

    dates = history_market_dates()

    if len(dates) < 6:
        raise RuntimeError(
            "market history too short"
        )

    candidate_dates = (
        dates[-HISTORY_TARGET:]
    )

    history = []

    # 最近6日才需要借券賣出確認訊號，
    # 20日異常基準主要依融資／借券餘額本身。
    short_dates = set(
        candidate_dates[-6:]
    )

    for date in candidate_dates:
        snap = fetch_daily_snapshot(
            date,
            master,
            need_short=(
                date in short_dates
            ),
        )

        if healthy_snapshot(
            snap
        ):
            history.append(
                snap
            )

    if len(history) < 6:
        raise RuntimeError(
            "margin/lending history "
            f"only {len(history)} healthy days"
        )

    # 只採最後一個健康交易日作為最新日期。
    latest_date = history[-1][
        "date"
    ]

    # 對應行情日期也以實際健康歷史為準。
    usable_dates = [
        x["date"]
        for x in history
    ]

    out = {
        "date": latest_date,
        "updated_at": (
            now_tpe()
            .isoformat(
                timespec="minutes"
            )
        ),
        "complete": (
            len(history) >= 21
        ),
        "history_days": len(
            history
        ),
        "logic": logic_payload(),
        "margin": {
            "twse": [],
            "tpex": [],
        },
        "borrow": {
            "twse": [],
            "tpex": [],
        },
    }

    for kind in (
        "margin",
        "borrow"
    ):
        for market in (
            "twse",
            "tpex"
        ):
            out[kind][market] = (
                rank_kind(
                    kind,
                    market,
                    history,
                    master,
                    usable_dates,
                    latest_market,
                )
            )

    save_json(
        ROOT
        / "data/margin_lending.json",
        out
    )

    print(
        "margin_lending",
        latest_date,
        "history",
        len(history),
        "margin",
        len(out["margin"]["twse"]),
        len(out["margin"]["tpex"]),
        "borrow",
        len(out["borrow"]["twse"]),
        len(out["borrow"]["tpex"]),
    )


if __name__ == "__main__":
    main()
