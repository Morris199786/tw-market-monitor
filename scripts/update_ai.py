from sources import *


FACTOR_LABELS = {
    "foreign": "外資",
    "trust": "投信",
    "dealer": "自營商",
    "holders": "大戶籌碼",
    "volume_price": "量價",
    "turnover": "當日成交熱度",
    "turnover_5d": "近5日成交熱度",
}


def tracked_candidates(master):
    """
    AI 選股股票池 = sectors.json 內所有自訂追蹤股
    只保留 master.json 有市場別資訊的股票。
    """
    d = load_json(
        ROOT / "data/sectors.json",
        {}
    )

    tickers = {
        str(x.get("ticker"))
        for s in d.get("sectors", [])
        for x in s.get("stocks", [])
        if x.get("ticker")
    }

    return {
        t: m
        for t, m in master.items()
        if t in tickers
    }


def display_names():
    """
    顯示名稱優先使用 sectors.json 的市場簡稱。
    """
    out = {}

    d = load_json(
        ROOT / "data/sectors.json",
        {}
    )

    for s in d.get("sectors", []):
        for x in s.get("stocks", []):
            t = str(
                x.get("ticker") or ""
            ).strip()

            name = str(
                x.get("name") or ""
            ).strip()

            if t and name:
                out[t] = name

    return out


def healthy_inst_day(d):
    """
    避免 AI 又吃到過去錯誤 cache：
    TWSE / TPEx 都必須有資料，而且四大分類不是整體全 0。
    """
    if not d.get("date") or not d.get("closes"):
        return False

    for mk in ("twse", "tpex"):
        rows = d.get(mk, {})

        if len(rows) < 50:
            return False

        for kind in (
            "foreign",
            "trust",
            "dealer",
            "total"
        ):
            if not any(
                int(r.get(kind) or 0) != 0
                for r in rows.values()
            ):
                return False

    return True


def hist_inst_last5():
    """
    往回找最近 5 個「通過健康檢查」的法人交易日，
    不再單純取資料夾最後 5 個 JSON。
    """
    files = sorted(
        (
            ROOT
            / "data/history/institutional"
        ).glob("*.json"),
        reverse=True
    )

    out = []

    for p in files:
        d = load_json(
            p,
            {}
        )

        if healthy_inst_day(d):
            out.append(d)

        if len(out) >= 5:
            break

    return list(reversed(out))


def holder_metrics(holders):
    """
    大戶籌碼因子：
    同一檔股票若同時進入 400 張與 1000 張大戶增加榜，
    取兩者「週增幅 percentage points」平均。
    """
    result = {
        "twse": {},
        "tpex": {}
    }

    for mk in (
        "twse",
        "tpex"
    ):
        by = {}

        for kind in (
            "400",
            "1000"
        ):
            for x in (
                holders
                .get(mk, {})
                .get(kind, [])
            ):
                by.setdefault(
                    x["ticker"],
                    []
                ).append(
                    float(
                        x.get("delta")
                        or 0
                    )
                )

        result[mk] = {
            t: (
                safe_mean(v)
                or 0
            )
            for t, v in by.items()
        }

    return result


def logic_payload(
    mode,
    weights,
    dates_used
):
    """
    直接寫入 ai_picks.json，
    前端不用再把選股邏輯硬編碼。
    """
    factors = []

    order = (
        [
            "foreign",
            "trust",
            "dealer",
            "holders",
            "turnover_5d",
        ]
        if mode == "sunday"
        else [
            "foreign",
            "trust",
            "dealer",
            "holders",
            "volume_price",
            "turnover",
        ]
    )

    for key in order:
        factors.append(
            {
                "key": key,
                "label": FACTOR_LABELS[key],
                "weight": float(
                    weights.get(key, 0)
                ),
                "weight_pct": round(
                    float(
                        weights.get(
                            key,
                            0
                        )
                    ) * 100,
                    1
                )
            }
        )

    if mode == "sunday":
        details = [
            "股票池：自訂 19 個科技族群內個股",
            "外資／投信／自營商：最近 5 個有效交易日，逐日「買賣超股數 × 當日收盤價」加總，再除以同期間成交金額，最後於上市／上櫃各自做百分位排名",
            "大戶籌碼：400 張與 1000 張大戶持股比率週增幅的平均值，再做同市場百分位排名",
            "近5日成交熱度：最近 5 個交易日成交金額加總，再做同市場百分位排名",
            "總分：各因子 0–100 分乘以權重後加總",
            "排名：上市、上櫃分開排名，各取前 20 名",
            "分數代表同市場追蹤股的相對強弱，不代表未來上漲機率"
        ]
    else:
        details = [
            "股票池：自訂 19 個科技族群內個股",
            "外資／投信／自營商：最近 5 個有效交易日，逐日「買賣超股數 × 當日收盤價」加總，再除以同期間成交金額，最後於上市／上櫃各自做百分位排名",
            "大戶籌碼：400 張與 1000 張大戶持股比率週增幅的平均值，再做同市場百分位排名",
            "量價：只有當日股價上漲才計分；5日量比 1.0x 以下為 0 分，2.0x 以上封頂 100 分，中間線性換算",
            "當日成交熱度：當日成交金額在同市場追蹤股中的百分位排名",
            "總分：各因子 0–100 分乘以權重後加總",
            "排名：上市、上櫃分開排名，各取前 20 名",
            "分數代表同市場追蹤股的相對強弱，不代表未來上漲機率"
        ]

    return {
        "version": "2026-09-24-v2",
        "mode": mode,
        "universe": "sectors.json 自訂科技股",
        "lookback_days": 5,
        "institutional_dates": dates_used,
        "factors": factors,
        "details": details,
        "top_n_each_market": 20,
        "markets_ranked_separately": True,
        "score_is_probability": False,
    }


def main():
    cfg = load_json(
        ROOT / "config.json",
        {}
    )

    master = load_json(
        ROOT / "data/master.json",
        {}
    ).get(
        "stocks",
        {}
    )

    names = display_names()
    candidates = tracked_candidates(
        master
    )

    market = load_json(
        ROOT / "data/market_latest.json",
        {}
    ).get(
        "stocks",
        {}
    )

    holders = load_json(
        ROOT / "data/holders.json",
        {}
    )

    volume = load_json(
        ROOT / "data/volume.json",
        {}
    ).get(
        "items",
        []
    )

    volmap = {
        x["ticker"]: x
        for x in volume
    }

    hist = hist_inst_last5()

    if len(hist) < 5:
        raise RuntimeError(
            f"AI needs 5 healthy institutional days, got {len(hist)}"
        )

    dates_used = [
        h.get("date")
        for h in hist
    ]

    metrics = {
        mk: {
            k: {}
            for k in (
                "foreign",
                "trust",
                "dealer"
            )
        }
        for mk in (
            "twse",
            "tpex"
        )
    }

    turn5 = {
        "twse": {},
        "tpex": {}
    }

    for t, m in candidates.items():
        mk = m["market"]

        if mk not in (
            "twse",
            "tpex"
        ):
            continue

        inst_amt = {
            k: 0.0
            for k in metrics[mk]
        }

        trn = 0.0

        for h in hist:
            q = h.get(
                "closes",
                {}
            ).get(
                t,
                {}
            )

            turnover = float(
                q.get("turnover")
                or 0
            )

            trn += turnover

            r = h.get(
                mk,
                {}
            ).get(
                t,
                {}
            )

            price = float(
                q.get("price")
                or 0
            )

            for k in inst_amt:
                inst_amt[k] += (
                    int(
                        r.get(k)
                        or 0
                    )
                    * price
                )

        denom = (
            trn
            if trn > 0
            else 1
        )

        for k in inst_amt:
            metrics[mk][k][t] = (
                inst_amt[k]
                / denom
            )

        turn5[mk][t] = trn

    holder_metric = holder_metrics(
        holders
    )

    is_sunday = (
        now_tpe().weekday() == 6
    )

    mode = (
        "sunday"
        if is_sunday
        else "trade_day"
    )

    weights = (
        cfg["ai_weights_sunday"]
        if is_sunday
        else cfg["ai_weights_trade_day"]
    )

    out = {
        "updated_at": (
            now_tpe()
            .isoformat(
                timespec="minutes"
            )
        ),
        "mode": mode,
        "complete": True,
        "logic": logic_payload(
            mode,
            weights,
            dates_used
        ),
        "twse": [],
        "tpex": [],
    }

    for mk in (
        "twse",
        "tpex"
    ):
        pf = {
            k: percentile_map(
                metrics[mk][k]
            )
            for k in (
                "foreign",
                "trust",
                "dealer"
            )
        }

        ph = percentile_map(
            holder_metric[mk]
        )

        pt = percentile_map(
            turn5[mk]
        )

        daily_turn = {
            t2: (
                market
                .get(t2, {})
                .get("turnover", 0)
                or 0
            )
            for t2, m2
            in candidates.items()
            if m2.get("market") == mk
        }

        pd = percentile_map(
            daily_turn
        )

        scores = []

        for t, m in candidates.items():
            if m.get("market") != mk:
                continue

            q = market.get(
                t,
                {}
            )

            change_pct = float(
                q.get("change_pct")
                or 0
            )

            volume_ratio_5d = float(
                volmap
                .get(t, {})
                .get(
                    "volume_ratio_5d",
                    0
                )
                or 0
            )

            vp = (
                min(
                    100,
                    max(
                        0,
                        (
                            volume_ratio_5d
                            - 1
                        )
                        * 100
                    )
                )
                if change_pct > 0
                else 0
            )

            factor_scores = {
                "foreign": round(
                    pf["foreign"].get(
                        t,
                        0
                    ),
                    1
                ),
                "trust": round(
                    pf["trust"].get(
                        t,
                        0
                    ),
                    1
                ),
                "dealer": round(
                    pf["dealer"].get(
                        t,
                        0
                    ),
                    1
                ),
                "holders": round(
                    ph.get(
                        t,
                        0
                    ),
                    1
                ),
            }

            if is_sunday:
                factor_scores[
                    "turnover_5d"
                ] = round(
                    pt.get(
                        t,
                        0
                    ),
                    1
                )
            else:
                factor_scores[
                    "volume_price"
                ] = round(
                    vp,
                    1
                )

                factor_scores[
                    "turnover"
                ] = round(
                    pd.get(
                        t,
                        0
                    ),
                    1
                )

            contributions = {}

            score = 0.0

            for key, weight in weights.items():
                fs = float(
                    factor_scores.get(
                        key,
                        0
                    )
                )

                contribution = (
                    float(weight)
                    * fs
                )

                contributions[key] = round(
                    contribution,
                    2
                )

                score += contribution

            tags = []

            if factor_scores["trust"] >= 75:
                tags.append(
                    "投信偏多"
                )

            if factor_scores["foreign"] >= 75:
                tags.append(
                    "外資偏多"
                )

            if factor_scores["dealer"] >= 75:
                tags.append(
                    "自營商偏多"
                )

            if (
                factor_scores["holders"] >= 75
                and holder_metric[mk].get(
                    t,
                    0
                ) > 0
            ):
                tags.append(
                    "大戶增加"
                )

            if is_sunday:
                if (
                    factor_scores[
                        "turnover_5d"
                    ] >= 75
                ):
                    tags.append(
                        "近5日成交活躍"
                    )
            else:
                if (
                    factor_scores[
                        "turnover"
                    ] >= 75
                ):
                    tags.append(
                        "當日成交活躍"
                    )

                if (
                    factor_scores[
                        "volume_price"
                    ] >= 50
                ):
                    tags.append(
                        "量價偏多"
                    )

            if change_pct < 0:
                tags.append(
                    "當日下跌"
                )

            # 依「實際加權貢獻」挑出前三大選股理由，
            # 避免 reason 與真正分數來源不一致。
            ranked_reasons = sorted(
                contributions.items(),
                key=lambda kv: kv[1],
                reverse=True
            )

            reason_parts = [
                f"{FACTOR_LABELS[k]}貢獻 {v:.1f} 分"
                for k, v
                in ranked_reasons[:3]
                if v > 0
            ]

            reason = (
                "｜".join(
                    reason_parts
                )
                if reason_parts
                else "目前沒有明顯正向因子"
            )

            scores.append(
                {
                    "ticker": t,
                    "name": (
                        names.get(t)
                        or m.get(
                            "name",
                            ""
                        )
                    ),
                    "score": round(
                        score,
                        1
                    ),
                    "change_pct": (
                        q.get(
                            "change_pct"
                        )
                    ),
                    "tags": tags,
                    "reason": reason,
                    "factor_scores": factor_scores,
                    "contributions": contributions,
                    "raw": {
                        "holder_delta_avg_ppt": round(
                            float(
                                holder_metric[
                                    mk
                                ].get(
                                    t,
                                    0
                                )
                            ),
                            4
                        ),
                        "volume_ratio_5d": round(
                            volume_ratio_5d,
                            4
                        ),
                        "turnover_today": (
                            q.get(
                                "turnover"
                            )
                            or 0
                        ),
                        "turnover_5d": (
                            turn5[
                                mk
                            ].get(
                                t,
                                0
                            )
                            or 0
                        ),
                    }
                }
            )

        scores.sort(
            key=lambda x: x["score"],
            reverse=True
        )

        out[mk] = scores[
            :cfg.get(
                "top_n",
                {}
            ).get(
                "ai",
                20
            )
        ]

    # 自動驗證：上市／上櫃各 20 檔、分數範圍合理、邏輯 metadata 存在
    for mk in (
        "twse",
        "tpex"
    ):
        if len(out[mk]) != 20:
            raise RuntimeError(
                f"AI {mk} expected 20 picks, got {len(out[mk])}"
            )

        for x in out[mk]:
            if not (
                0 <= float(
                    x.get("score")
                    or 0
                ) <= 100
            ):
                raise RuntimeError(
                    f"AI invalid score: {mk} {x.get('ticker')} {x.get('score')}"
                )

            if not x.get(
                "factor_scores"
            ):
                raise RuntimeError(
                    f"AI missing factor_scores: {mk} {x.get('ticker')}"
                )

    save_json(
        ROOT / "data/ai_picks.json",
        out
    )

    print(
        "ai",
        out["mode"],
        len(out["twse"]),
        len(out["tpex"]),
        "dates",
        dates_used,
        "logic",
        out["logic"]["version"]
    )


if __name__ == "__main__":
    main()
