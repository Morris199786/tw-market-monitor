from sources import *
import time

INDEX_CHANNELS = {
    "twse": "tse_t00.tw",
    "tpex": "otc_o00.tw",
}


def NumberLike(v):
    try:
        return float(v)
    except (ValueError, TypeError):
        return 0.0


def latest_tdcc_totals():
    files = sorted(
        (ROOT / "data/history/holders").glob("*.json"),
        reverse=True
    )

    for p in files:
        stocks = load_json(p, {}).get("stocks", {})

        totals = {
            str(t): int(r.get("total") or 0)
            for t, r in stocks.items()
        }

        totals = {
            t: v
            for t, v in totals.items()
            if v > 0
        }

        if totals:
            print(
                "heatmap share fallback:",
                p.name,
                len(totals)
            )
            return totals

    return {}


def first_book_price(raw):
    for part in str(raw or "").split("_"):
        v = n(part)

        if v > 0:
            return v

    return 0.0


def get_mis_batch_with_retry(channels):
    last_error = None

    for attempt, wait in enumerate([0, 2, 5], 1):
        if wait:
            time.sleep(wait)

        try:
            data = get_json(
                MIS,
                params={
                    "ex_ch": "|".join(channels),
                    "json": "1",
                    "delay": "0",
                },
                timeout=25,
            )

            if isinstance(data, dict):
                return data

        except Exception as exc:
            last_error = exc
            print(
                "MIS retry",
                attempt,
                str(exc)
            )

    if last_error:
        print("MIS failed:", last_error)

    return {}


def fetch_heatmap_quotes(tickers, master):
    channels = []
    channel_to_ticker = {}

    for ticker in tickers:
        market = str(
            master.get(ticker, {}).get("market", "")
        ).lower()

        exchange = (
            "otc"
            if market in ("tpex", "otc", "上櫃")
            else "tse"
        )

        channel = f"{exchange}_{ticker}.tw"

        channels.append(channel)
        channel_to_ticker[channel] = ticker

    result = {}

    for start in range(0, len(channels), 80):
        batch = channels[start:start + 80]

        data = get_mis_batch_with_retry(batch)

        for row in data.get("msgArray", []):
            channel = str(row.get("ch") or "")

            ticker = channel_to_ticker.get(channel)

            if not ticker:
                ticker = str(row.get("c") or "")

            if ticker not in tickers:
                continue

            previous = NumberLike(row.get("y"))

            if previous <= 0:
                continue

            traded = NumberLike(row.get("z"))

            if traded > 0:
                price = traded
                source = "mis_trade"
            else:
                bid = first_book_price(row.get("b"))
                ask = first_book_price(row.get("a"))

                if bid > 0 and ask > 0:
                    price = (bid + ask) / 2
                else:
                    price = bid or ask

                source = "mis_book"

            if price <= 0:
                continue

            change = (
                price / previous - 1
            ) * 100

            result[ticker] = {
                "price": price,
                "change_pct": change,
                "exchange": str(row.get("ex") or ""),
                "quote_source": source,
            }

    return result


def previous_quotes():
    old = load_json(
        ROOT / "data/heatmap.json",
        {}
    )

    out = {}

    for sector in old.get("sectors", []):
        for row in sector.get("stocks", []):
            ticker = str(row.get("ticker") or "")

            if not ordinary_ticker(ticker):
                continue

            price = NumberLike(row.get("price"))
            change = row.get("change_pct")

            if price <= 0 or change is None:
                continue

            out[ticker] = {
                "price": price,
                "change_pct": float(change),
            }

    return out


def fetch_index_quotes():
    """
    抓取加權指數與櫃買指數

    僅接受：
    1. 有有效指數值
    2. 有有效昨收
    3. 行情日期為今天

    不使用前一交易日行情冒充今日即時資料
    """

    data = get_mis_batch_with_retry(
        list(INDEX_CHANNELS.values())
    )

    today = now_tpe().strftime("%Y%m%d")

    out = {}

    for row in data.get("msgArray", []):
        channel = str(
            row.get("ch") or ""
        ).lower()

        market = next(
            (
                key
                for key, value in INDEX_CHANNELS.items()
                if value.lower() == channel
            ),
            None
        )

        if not market:
            code = str(
                row.get("c") or ""
            ).lower()

            exchange = str(
                row.get("ex") or ""
            ).lower()

            if code == "t00" and exchange == "tse":
                market = "twse"

            elif code == "o00" and exchange == "otc":
                market = "tpex"

        if not market:
            continue

        price = NumberLike(row.get("z"))
        previous = NumberLike(row.get("y"))

        if price <= 0 or previous <= 0:
            continue

        raw_date = str(
            row.get("d") or ""
        ).replace("-", "").replace("/", "")

        if raw_date != today:
            continue

        change = (
            price / previous - 1
        ) * 100

        out[market] = {
            "price": price,
            "value": price,
            "prev_close": previous,
            "change_pct": round(change, 4),
            "date": today,
            "time": str(row.get("t") or ""),
            "source": "twse_mis",
            "live": True,
        }

    return out


def previous_index_quotes():
    """
    只允許沿用今天已取得的指數

    沿用資料會標示 live=False
    """

    old = load_json(
        ROOT / "data/heatmap.json",
        {}
    )

    today = now_tpe().strftime("%Y%m%d")

    old_date = str(
        old.get("updated_at") or ""
    )[:10].replace("/", "").replace("-", "")

    if old_date != today:
        return {}

    previous = (
        old.get("indices")
        or old.get("index_quotes")
        or {}
    )

    out = {}

    for market, quote in previous.items():
        if market not in INDEX_CHANNELS:
            continue

        if not isinstance(quote, dict):
            continue

        date = str(
            quote.get("date") or ""
        ).replace("-", "")

        if date != today:
            continue

        price = NumberLike(
            quote.get("price")
            or quote.get("value")
        )

        prev_close = NumberLike(
            quote.get("prev_close")
        )

        if price <= 0 or prev_close <= 0:
            continue

        out[market] = {
            **quote,
            "price": price,
            "value": price,
            "prev_close": prev_close,
            "change_pct": round(
                (price / prev_close - 1) * 100,
                4
            ),
            "source": "previous_heatmap",
            "live": False,
        }

    return out


def main():
    cfg = load_json(
        ROOT / "data/sectors.json",
        {}
    )

    master = load_json(
        ROOT / "data/master.json",
        {}
    ).get("stocks", {})

    if not master:
        master = fetch_master()

        save_json(
            ROOT / "data/master.json",
            {
                "updated_at": now_tpe().isoformat(
                    timespec="minutes"
                ),
                "stocks": master,
            }
        )

    tdcc_totals = latest_tdcc_totals()

    tickers = sorted({
        str(stock["ticker"])
        for sector in cfg.get("sectors", [])
        for stock in sector.get("stocks", [])
    })

    quotes = fetch_heatmap_quotes(
        tickers,
        master
    )

    old_quotes = previous_quotes()

    previous_fallback = 0

    for ticker in tickers:
        if ticker in quotes:
            continue

        if ticker not in old_quotes:
            continue

        quotes[ticker] = {
            **old_quotes[ticker],
            "exchange": master.get(
                ticker,
                {}
            ).get("market", ""),
            "quote_source": "previous_heatmap",
        }

        previous_fallback += 1

    # 抓取即時大盤與 OTC
    indices = fetch_index_quotes()

    # 同日有效資料備援
    for market, quote in previous_index_quotes().items():
        indices.setdefault(market, quote)

    sectors = []

    for sector in cfg.get("sectors", []):
        members = []
        weighted = 0.0
        capsum = 0.0
        missing = []

        for stock in sector.get("stocks", []):
            ticker = str(stock["ticker"])

            quote = quotes.get(ticker)
            info = master.get(ticker, {})

            name = (
                stock.get("name")
                or info.get("name")
                or ticker
            )

            master_shares = int(
                info.get("shares_issued") or 0
            )

            shares = (
                master_shares
                or int(tdcc_totals.get(ticker) or 0)
            )

            if not quote:
                missing.append(ticker)

                members.append({
                    "ticker": ticker,
                    "name": name,
                    "price": None,
                    "change_pct": None,
                    "market_cap": None,
                    "weight": None,
                    "shares_source": None,
                    "quote_source": None,
                })

                continue

            price = quote.get("price")
            change = quote.get("change_pct")

            if (
                shares <= 0
                or NumberLike(price) <= 0
                or change is None
            ):
                missing.append(ticker)

                members.append({
                    "ticker": ticker,
                    "name": name,
                    "price": price,
                    "change_pct": change,
                    "market_cap": None,
                    "weight": None,
                    "shares_source": None,
                    "quote_source": quote.get(
                        "quote_source"
                    ),
                })

                continue

            cap = float(price) * shares

            capsum += cap
            weighted += float(change) * cap

            members.append({
                "ticker": ticker,
                "name": name,
                "price": price,
                "change_pct": round(
                    float(change),
                    2
                ),
                "market_cap": cap,
                "weight": None,
                "shares_source": (
                    "master"
                    if master_shares > 0
                    else "tdcc"
                ),
                "quote_source": quote.get(
                    "quote_source"
                ),
            })

        for member in members:
            if (
                member["market_cap"] is not None
                and capsum > 0
            ):
                member["weight"] = (
                    member["market_cap"] / capsum
                )

        sectors.append({
            "name": sector["name"],
            "change_pct": (
                round(weighted / capsum, 2)
                if capsum > 0
                else None
            ),
            "complete": len(missing) == 0,
            "missing": missing,
            "stocks": members,
        })

    result = {
        "updated_at": now_tpe().strftime(
            "%Y/%m/%d %H:%M"
        ),
        "method": "market_cap_weighted",
        "source": (
            "TWSE MIS + TPEx MIS + "
            "TDCC share fallback"
        ),

        # app.js 實際讀取這個欄位
        "indices": indices,

        # 保留舊欄位相容性
        "index_quotes": indices,

        # 原本熱力圖資料
        "sectors": sectors,
    }

    save_json(
        ROOT / "data/heatmap.json",
        result
    )

    print(
        "heatmap",
        len(sectors),
        "quotes",
        len(quotes),
        "indices",
        list(indices),
        "previous_fallback",
        previous_fallback,
        "missing",
        sum(
            len(x["missing"])
            for x in sectors
        )
    )


if __name__ == "__main__":
    main()
