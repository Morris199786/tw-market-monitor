from sources import ROOT, load_json, ordinary_ticker


DEFAULT_TECH_CODES = {
    "24",  # 半導體
    "25",  # 電腦及週邊設備
    "26",  # 光電
    "27",  # 通信網路
    "28",  # 電子零組件
    "29",  # 電子通路
    "30",  # 資訊服務
    "31",  # 其他電子
    "32",  # 數位雲端
}


def _config():
    return load_json(
        ROOT / "config.json",
        {}
    )


def _sector_tickers():
    """
    19 個自訂科技族群成分股全部視為科技股。

    注意：
    sectors.json 只是「保證納入」來源之一，
    絕對不是科技股股票池的上限。
    """
    d = load_json(
        ROOT / "data/sectors.json",
        {}
    )

    out = set()

    for sec in d.get("sectors", []):
        for row in sec.get("stocks", []):
            t = str(
                row.get("ticker")
                or ""
            ).strip()

            if ordinary_ticker(t):
                out.add(t)

    return out


def _supply_chain_tickers():
    """
    官方分類不是電子業，但核心產品直接供應
    半導體／PCB／CCL／光通訊／AI伺服器／電子材料
    等科技供應鏈的公司白名單。
    """
    cfg = _config()

    return {
        str(x).strip()
        for x in cfg.get(
            "tech_supply_chain_tickers",
            []
        )
        if ordinary_ticker(
            str(x).strip()
        )
    }


def _tech_codes():
    cfg = _config()

    configured = {
        str(x).strip()
        for x in cfg.get(
            "tech_industry_codes",
            []
        )
        if str(x).strip()
    }

    return configured or DEFAULT_TECH_CODES


def _tech_names():
    cfg = _config()

    return {
        str(x).strip()
        for x in cfg.get(
            "tech_industries",
            []
        )
        if str(x).strip()
    }


def _excluded_tickers():
    """
    預留人工排除機制。

    若未來某檔雖落在官方科技分類，
    但你明確不想視為科技股，可在 config.json 增加：
      "tech_exclude_tickers": ["xxxx"]
    """
    cfg = _config()

    return {
        str(x).strip()
        for x in cfg.get(
            "tech_exclude_tickers",
            []
        )
        if ordinary_ticker(
            str(x).strip()
        )
    }


def tech_universe_sources():
    """
    回傳目前科技股判定使用的三個納入來源，
    方便除錯與未來檢查。
    """
    return {
        "industry_codes": _tech_codes(),
        "industry_names": _tech_names(),
        "sector_tickers": _sector_tickers(),
        "supply_chain_tickers": _supply_chain_tickers(),
        "excluded_tickers": _excluded_tickers(),
    }


def is_tech_stock(ticker, meta):
    """
    新版科技股定義：

    科技股 =
      ① 官方科技產業
      ∪
      ② 19 個自訂科技族群成分股
      ∪
      ③ 跨產業科技供應鏈白名單

    最後再扣除人工排除名單。

    這樣可避免南亞、台玻、富喬、建榮、雙鍵、
    中華化等官方分類偏傳產但實際屬科技供應鏈的公司
    被錯誤排除。
    """
    t = str(
        ticker
        or ""
    ).strip()

    if not ordinary_ticker(t):
        return False

    if not isinstance(meta, dict):
        return False

    if meta.get("market") not in (
        "twse",
        "tpex"
    ):
        return False

    src = tech_universe_sources()

    if t in src["excluded_tickers"]:
        return False

    industry = str(
        meta.get("industry")
        or ""
    ).strip()

    if industry in src["industry_codes"]:
        return True

    if industry in src["industry_names"]:
        return True

    if t in src["sector_tickers"]:
        return True

    if t in src["supply_chain_tickers"]:
        return True

    return False


def tech_tickers(master):
    """
    全台股科技普通股股票池。

    回傳 set[str]，供：
    - 突然放量
    - 進階篩選
    - 大戶籌碼
    - AI 選股
    - 未來融資／借券科技股模式

    全部共用同一套標準。
    """
    if not isinstance(master, dict):
        return set()

    return {
        str(t)
        for t, meta in master.items()
        if is_tech_stock(
            t,
            meta
        )
    }


def tech_universe_breakdown(master):
    """
    除錯用：回傳每一檔科技股是因為哪個條件被納入。
    不影響正式排行。
    """
    src = tech_universe_sources()

    out = {}

    for t, meta in master.items():
        t = str(t)

        if not ordinary_ticker(t):
            continue

        if meta.get("market") not in (
            "twse",
            "tpex"
        ):
            continue

        if t in src["excluded_tickers"]:
            continue

        industry = str(
            meta.get("industry")
            or ""
        ).strip()

        reasons = []

        if industry in src["industry_codes"]:
            reasons.append(
                "official_tech_industry_code"
            )

        if industry in src["industry_names"]:
            reasons.append(
                "official_tech_industry_name"
            )

        if t in src["sector_tickers"]:
            reasons.append(
                "custom_19_sector"
            )

        if t in src["supply_chain_tickers"]:
            reasons.append(
                "cross_industry_supply_chain"
            )

        if reasons:
            out[t] = {
                "ticker": t,
                "name": meta.get(
                    "name",
                    ""
                ),
                "market": meta.get(
                    "market"
                ),
                "industry": industry,
                "reasons": reasons,
            }

    return out
