from sources import *


MIN_TWSE_MASTER = 800
MIN_TPEX_MASTER = 600
MIN_TOTAL_MASTER = 1500


def market_slice(stocks, market):
    return {
        str(t): row
        for t, row in (stocks or {}).items()
        if (
            ordinary_ticker(t)
            and isinstance(row, dict)
            and row.get("market") == market
        )
    }


def main():
    old_data = load_json(
        ROOT / "data/master.json",
        {}
    )

    old_stocks = old_data.get(
        "stocks",
        {}
    )

    old_twse = market_slice(
        old_stocks,
        "twse"
    )

    old_tpex = market_slice(
        old_stocks,
        "tpex"
    )

    print(
        "old master",
        "total",
        len(old_stocks),
        "twse",
        len(old_twse),
        "tpex",
        len(old_tpex),
    )

    # fetch_master() 會分別抓 TWSE / TPEx。
    # 若其中一個來源暫時 502，它仍可能回傳另一個市場，
    # 所以不能直接拿結果覆蓋原本完整的 master.json。
    try:
        fresh = fetch_master()
    except Exception as e:
        print(
            "fresh master fetch failed",
            repr(e)
        )
        fresh = {}

    fresh_twse = market_slice(
        fresh,
        "twse"
    )

    fresh_tpex = market_slice(
        fresh,
        "tpex"
    )

    print(
        "fresh master",
        "total",
        len(fresh),
        "twse",
        len(fresh_twse),
        "tpex",
        len(fresh_tpex),
    )

    result = {}
    source_status = {}

    # -------------------------
    # TWSE
    # -------------------------
    if len(fresh_twse) >= MIN_TWSE_MASTER:
        result.update(
            fresh_twse
        )

        source_status["twse"] = {
            "source": "fresh",
            "count": len(fresh_twse),
        }

    elif len(old_twse) >= MIN_TWSE_MASTER:
        print(
            "TWSE fresh incomplete -> fallback old cache",
            len(fresh_twse),
            "old",
            len(old_twse),
        )

        result.update(
            old_twse
        )

        source_status["twse"] = {
            "source": "fallback_cache",
            "fresh_count": len(fresh_twse),
            "count": len(old_twse),
        }

    else:
        raise RuntimeError(
            "TWSE master unavailable: "
            f"fresh={len(fresh_twse)} "
            f"old={len(old_twse)}"
        )

    # -------------------------
    # TPEx
    # -------------------------
    if len(fresh_tpex) >= MIN_TPEX_MASTER:
        result.update(
            fresh_tpex
        )

        source_status["tpex"] = {
            "source": "fresh",
            "count": len(fresh_tpex),
        }

    elif len(old_tpex) >= MIN_TPEX_MASTER:
        print(
            "TPEx fresh incomplete -> fallback old cache",
            len(fresh_tpex),
            "old",
            len(old_tpex),
        )

        result.update(
            old_tpex
        )

        source_status["tpex"] = {
            "source": "fallback_cache",
            "fresh_count": len(fresh_tpex),
            "count": len(old_tpex),
        }

    else:
        raise RuntimeError(
            "TPEx master unavailable: "
            f"fresh={len(fresh_tpex)} "
            f"old={len(old_tpex)}"
        )

    final_twse = market_slice(
        result,
        "twse"
    )

    final_tpex = market_slice(
        result,
        "tpex"
    )

    if len(result) < MIN_TOTAL_MASTER:
        raise RuntimeError(
            "master completeness check failed: "
            f"total={len(result)} "
            f"twse={len(final_twse)} "
            f"tpex={len(final_tpex)}"
        )

    if len(final_twse) < MIN_TWSE_MASTER:
        raise RuntimeError(
            "TWSE master completeness check failed: "
            f"{len(final_twse)}"
        )

    if len(final_tpex) < MIN_TPEX_MASTER:
        raise RuntimeError(
            "TPEx master completeness check failed: "
            f"{len(final_tpex)}"
        )

    payload = {
        "updated_at": (
            now_tpe()
            .isoformat(
                timespec="minutes"
            )
        ),
        "count": len(result),
        "market_count": {
            "twse": len(final_twse),
            "tpex": len(final_tpex),
        },
        "source_status": source_status,
        "stocks": result,
    }

    save_json(
        ROOT / "data/master.json",
        payload
    )

    print(
        "master saved",
        len(result),
        "twse",
        len(final_twse),
        "tpex",
        len(final_tpex),
        "status",
        source_status,
    )


if __name__ == "__main__":
    main()
