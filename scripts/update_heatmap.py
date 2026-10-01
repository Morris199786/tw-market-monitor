from sources import *

import time


def latest_tdcc_totals():
    """
    用最新一份 TDCC 大戶歷史快照補發行股數。
    master.json 對部分上櫃公司會拿不到 shares_issued，
    但 TDCC level 17 的 total 就是該檔集保總股數，可作為市值加權 fallback。
    """
    files = sorted(
        (ROOT / "data/history/holders").glob("*.json"),
        reverse=True,
    )

    for p in files:
        d = load_json(
            p,
            {},
        )

        stocks = d.get(
            "stocks",
            {},
        )

        if not stocks:
            continue

        totals = {}

        for ticker, row in stocks.items():
            total = int(
                row.get("total")
                or 0
            )

            if total > 0:
                totals[
                    str(ticker)
                ] = total

        if totals:
            print(
                "heatmap share fallback:",
                p.name,
                len(totals),
            )

            return totals

    return {}


def first_book_price(raw):
    """
    MIS a / b 可能是：
    222.00_221.50_...
    找第一個有效正數。
    """
    for part in str(
        raw or ""
    ).split("_"):
        v = n(part)

        if v > 0:
            return v

    return 0.0


def get_mis_batch_with_retry(
    channels,
):
    """
    TWSE MIS 偶爾會主動 reset GitHub Actions 連線。

    每一批最多嘗試 3 次：
    第 1 次失敗 -> 等 2 秒
    第 2 次失敗 -> 等 5 秒
    第 3 次失敗 -> 放棄這一批

    放棄的股票之後會由 previous_heatmap fallback 補上，
    不讓單次 MIS 網路錯誤造成整個 Action 失敗。
    """
    waits = [
        0,
        2,
        5,
    ]

    last_error = None

    for attempt in range(
        1,
        4,
    ):
        if waits[
            attempt - 1
        ] > 0:
            time.sleep(
                waits[
                    attempt - 1
                ]
            )

        try:
            data = get_json(
                MIS,
                params={
                    "ex_ch": "|".join(
                        channels
                    ),
                    "json": "1",
                    "delay": "0",
                },
                timeout=25,
            )

            if not isinstance(
                data,
                dict,
            ):
                raise RuntimeError(
                    "MIS response is not dict"
                )

            print(
                "MIS batch success",
                f"attempt={attempt}",
                f"channels={len(channels)}",
            )

            return data

        except Exception as e:
            last_error = e

            print(
                "MIS batch failed",
                f"attempt={attempt}/3",
                f"channels={len(channels)}",
                repr(e),
            )

    print(
        "WARNING: MIS batch skipped after 3 attempts:",
        repr(last_error),
    )

    return {
        "msgArray": [],
    }


def fetch_heatmap_quotes(
    tickers,
    master,
):
    """
    熱力圖專用即時行情。

    重要修正：
    1. 已知上市／上櫃市場時，只查正確 channel
       twse -> tse_xxxx.tw
       tpex -> otc_xxxx.tw

    2. 不再同時查 tse + otc 後用「第一筆」結果
       避免上櫃股票先吃到錯市場 placeholder

    3. z 沒有成交價時，可用最佳買／賣價暫時 fallback

    4. z / bid / ask 全都沒有時，不准拿昨收 y 冒充現價
       否則會把漲停股誤顯示成 0%

    5. MIS ConnectionReset / timeout 時自動重試
       單一 batch 最終失敗也不讓整個 Action 掛掉
    """
    channels = []

    for t in tickers:
        market = str(
            master.get(
                t,
                {},
            ).get(
                "market",
                "",
            )
        ).lower()

        if market == "twse":
            channels.append(
                f"tse_{t}.tw"
            )

        elif market == "tpex":
            channels.append(
                f"otc_{t}.tw"
            )

        else:
            # master 若真的沒有市場資料才兩邊都查
            channels.extend(
                [
                    f"tse_{t}.tw",
                    f"otc_{t}.tw",
                ]
            )

    out = {}
    quality = {}

    for i in range(
        0,
        len(channels),
        120,
    ):
        ch = channels[
            i:i + 120
        ]

        # MIS 加入 retry / fallback
        data = get_mis_batch_with_retry(
            ch
        )

        for r in data.get(
            "msgArray",
            [],
        ):
            t = str(
                r.get(
                    "c",
                    "",
                )
            ).strip()

            if not ordinary_ticker(
                t
            ):
                continue

            prev_close = n(
                r.get("y")
            )

            trade = n(
                r.get("z")
            )

            bid = first_book_price(
                r.get("b")
            )

            ask = first_book_price(
                r.get("a")
            )

            quote_source = ""
            score = 0

            if trade > 0:
                price = trade
                quote_source = (
                    "mis_trade"
                )
                score = 3

            elif (
                bid > 0
                or ask > 0
            ):
                # 沒最新成交時，先用盤中最佳報價
                # 雙邊都有就取中間價，避免偏一側
                if (
                    bid > 0
                    and ask > 0
                ):
                    price = (
                        bid + ask
                    ) / 2
                else:
                    price = (
                        bid
                        or ask
                    )

                quote_source = (
                    "mis_book"
                )
                score = 2

            else:
                # 絕對不要：
                # price = prev_close
                #
                # 因為「即時價沒抓到」
                # 不等於「今天平盤」
                continue

            if (
                prev_close <= 0
                or price <= 0
            ):
                continue

            # 未知市場 ticker 可能還是有兩筆
            # 保留品質較好的那一筆
            if (
                score
                < quality.get(
                    t,
                    -1,
                )
            ):
                continue

            out[t] = {
                "price": price,
                "prev_close": (
                    prev_close
                ),
                "change_pct": (
                    (
                        price
                        / prev_close
                    )
                    - 1
                )
                * 100,
                "exchange": r.get(
                    "ex",
                    "",
                ),
                "quote_source": (
                    quote_source
                ),
            }

            quality[t] = score

        time.sleep(0.2)

    return out


def previous_quotes():
    """
    讀取上一輪 heatmap.json 的有效值。

    如果 MIS 這一輪剛好缺資料，
    沿用上一輪有效即時值，
    而不是顯示假的 0%。
    """
    old = load_json(
        ROOT
        / "data/heatmap.json",
        {},
    )

    out = {}

    for sec in old.get(
        "sectors",
        [],
    ):
        for x in sec.get(
            "stocks",
            [],
        ):
            t = str(
                x.get(
                    "ticker",
                )
                or ""
            )

            price = x.get(
                "price"
            )

            change_pct = x.get(
                "change_pct"
            )

            if (
                ordinary_ticker(t)
                and price is not None
                and NumberLike(
                    price
                ) > 0
                and change_pct
                is not None
            ):
                out[t] = {
                    "price": float(
                        price
                    ),
                    "change_pct": float(
                        change_pct
                    ),
                }

    return out


def main():
    cfg = load_json(
        ROOT
        / "data/sectors.json",
        {},
    )

    master = load_json(
        ROOT
        / "data/master.json",
        {},
    ).get(
        "stocks",
        {},
    )

    if not master:
        master = fetch_master()

        save_json(
            ROOT
            / "data/master.json",
            {
                "updated_at": (
                    now_tpe()
                    .isoformat(
                        timespec="minutes"
                    )
                ),
                "stocks": master,
            },
        )

    # TDCC fallback：
    # 主要解決上櫃 shares_issued = 0
    tdcc_totals = (
        latest_tdcc_totals()
    )

    tickers = sorted(
        {
            str(
                stock["ticker"]
            )
            for sector in cfg.get(
                "sectors",
                [],
            )
            for stock in sector.get(
                "stocks",
                [],
            )
        }
    )

    # 改用熱力圖專用正確市場 channel 抓法
    # MIS 失敗會自動 retry
    quotes = fetch_heatmap_quotes(
        tickers,
        master,
    )

    # MIS 本輪真的漏資料時，才沿用上一輪有效值
    old_quotes = previous_quotes()
    previous_fallback = 0

    for t in tickers:
        if t in quotes:
            continue

        old = old_quotes.get(
            t
        )

        if not old:
            continue

        quotes[t] = {
            "price": old[
                "price"
            ],
            "change_pct": old[
                "change_pct"
            ],
            "exchange": (
                master.get(
                    t,
                    {},
                ).get(
                    "market",
                    "",
                )
            ),
            "quote_source": (
                "previous_heatmap"
            ),
        }

        previous_fallback += 1

    sectors = []

    for sec in cfg.get(
        "sectors",
        [],
    ):
        members = []
        weighted = 0.0
        capsum = 0.0
        missing = []

        for s in sec.get(
            "stocks",
            [],
        ):
            t = str(
                s["ticker"]
            )

            q = quotes.get(
                t
            )

            m = master.get(
                t,
                {},
            )

            short_name = (
                s.get("name")
                or m.get("name")
                or t
            )

            shares = int(
                m.get(
                    "shares_issued"
                )
                or 0
            )

            if shares <= 0:
                shares = int(
                    tdcc_totals.get(
                        t
                    )
                    or 0
                )

            if not q:
                missing.append(
                    t
                )

                members.append(
                    {
                        "ticker": t,
                        "name": (
                            short_name
                        ),
                        "price": None,
                        "change_pct": None,
                        "market_cap": None,
                        "weight": None,
                        "shares_source": None,
                        "quote_source": None,
                    }
                )

                continue

            price = q.get(
                "price"
            )

            change_pct = q.get(
                "change_pct"
            )

            if (
                shares <= 0
                or price is None
                or NumberLike(
                    price
                ) <= 0
                or change_pct
                is None
            ):
                missing.append(
                    t
                )

                members.append(
                    {
                        "ticker": t,
                        "name": (
                            short_name
                        ),
                        "price": price,
                        "change_pct": (
                            change_pct
                        ),
                        "market_cap": None,
                        "weight": None,
                        "shares_source": None,
                        "quote_source": (
                            q.get(
                                "quote_source"
                            )
                        ),
                    }
                )

                continue

            cap = (
                float(price)
                * shares
            )

            capsum += cap

            weighted += (
                float(
                    change_pct
                )
                * cap
            )

            members.append(
                {
                    "ticker": t,
                    "name": (
                        short_name
                    ),
                    "price": price,
                    "change_pct": round(
                        float(
                            change_pct
                        ),
                        2,
                    ),
                    "market_cap": cap,
                    "weight": None,
                    "shares_source": (
                        "master"
                        if int(
                            m.get(
                                "shares_issued"
                            )
                            or 0
                        ) > 0
                        else "tdcc"
                    ),
                    "quote_source": (
                        q.get(
                            "quote_source"
                        )
                    ),
                }
            )

        sector_pct = (
            weighted / capsum
            if capsum
            else None
        )

        for x in members:
            if (
                x[
                    "market_cap"
                ] is not None
                and capsum
            ):
                x[
                    "weight"
                ] = (
                    x[
                        "market_cap"
                    ]
                    / capsum
                )

        sectors.append(
            {
                "name": (
                    sec["name"]
                ),
                "change_pct": (
                    round(
                        sector_pct,
                        2,
                    )
                    if sector_pct
                    is not None
                    else None
                ),
                "complete": (
                    len(
                        missing
                    )
                    == 0
                ),
                "missing": (
                    missing
                ),
                "stocks": (
                    members
                ),
            }
        )

    save_json(
        ROOT
        / "data/heatmap.json",
        {
            "updated_at": (
                now_tpe()
                .strftime(
                    "%Y/%m/%d %H:%M"
                )
            ),
            "method": (
                "market_cap_weighted"
            ),
            "source": (
                "TWSE MIS correct-market live quote "
                "+ MIS retry "
                "+ previous valid quote fallback "
                "+ TWSE/TPEx master "
                "+ TDCC share fallback"
            ),
            "sectors": (
                sectors
            ),
        },
    )

    print(
        "heatmap",
        len(
            sectors
        ),
        "quotes",
        len(
            quotes
        ),
        "previous_fallback",
        previous_fallback,
        "missing",
        sum(
            len(
                x["missing"]
            )
            for x in sectors
        ),
    )


def NumberLike(v):
    try:
        return float(v)
    except Exception:
        return 0.0


if __name__ == "__main__":
    main()
