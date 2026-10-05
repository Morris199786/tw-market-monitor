"""Evidence-based Taiwan company identity and per-company price-target audit."""

import copy
import json
import re
import hashlib
import urllib.request
import unicodedata
from pathlib import Path


# 升版：
# 讓既有報告重新執行 target audit
VERSION = "2026-10-05-identity-target-v2"

ROOT = Path(__file__).resolve().parents[1]

SEEDS = {
    "2383": {
        "name": "台光電",
        "aliases": [
            "Elite Material",
            "Elite Materials",
            "Elite Material Co., Ltd.",
            "EMC",
        ],
    },
    "3013": {
        "name": "晟銘電",
        "aliases": [
            "Chenming Electronic Technology",
            "Chenming",
            "UNEEC",
        ],
    },
    "3653": {
        "name": "健策",
        "aliases": [
            "Jentech Precision Industrial",
            "Jentech",
        ],
    },
}


def norm(s):
    return re.sub(
        r"[^\w\u3400-\u9fff]+",
        "",
        str(s or "").casefold(),
    )


def compact(s):
    return re.sub(
        r"\s+",
        " ",
        str(s or ""),
    ).strip()


def read(path, default):
    try:
        return json.loads(
            path.read_text(
                encoding="utf-8"
            )
        )
    except (OSError, ValueError):
        return default


def registry(refresh=False):
    path = ROOT / "data/report_company_registry.json"

    out = read(
        path,
        {},
    )

    for t, m in read(
        ROOT / "data/master.json",
        {},
    ).get(
        "stocks",
        {},
    ).items():
        if m.get("market") in (
            "twse",
            "tpex",
        ):
            out.setdefault(
                t,
                {
                    "aliases": []
                },
            )["name"] = m.get(
                "name",
                t,
            )

    if refresh:
        urls = [
            "https://openapi.twse.com.tw/v1/opendata/t187ap03_L",
            "https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap03_O",
        ]

        for url in urls:
            try:
                with urllib.request.urlopen(
                    url,
                    timeout=20,
                ) as r:
                    rows = json.load(r)

                for row in rows:
                    t = str(
                        row.get("公司代號")
                        or row.get(
                            "SecuritiesCompanyCode"
                        )
                        or ""
                    ).strip()

                    if not re.fullmatch(
                        r"[1-9]\d{3}",
                        t,
                    ):
                        continue

                    item = out.setdefault(
                        t,
                        {
                            "aliases": []
                        },
                    )

                    item["name"] = (
                        row.get("公司簡稱")
                        or row.get(
                            "CompanyAbbreviation"
                        )
                        or item.get("name")
                        or row.get("公司名稱")
                        or t
                    )

                    for k in (
                        "公司名稱",
                        "公司簡稱",
                        "英文簡稱",
                        "英文全名",
                        "CompanyName",
                        "CompanyAbbreviation",
                        "EnglishCompanyName",
                        "EnglishAbbreviation",
                    ):
                        v = str(
                            row.get(k)
                            or ""
                        ).strip()

                        if len(v) >= 3:
                            item.setdefault(
                                "aliases",
                                [],
                            ).append(v)

            except Exception as exc:
                print(
                    "Company registry source unavailable:",
                    type(exc).__name__,
                )

    for t, m in out.items():
        m.setdefault(
            "aliases",
            [],
        ).extend(
            [
                m.get(
                    "name",
                    "",
                ),
                re.sub(
                    r"[-*]?(?:KY)?$",
                    "",
                    m.get(
                        "name",
                        "",
                    ),
                ),
            ]
        )

    for t, m in SEEDS.items():
        old = out.get(
            t,
            {},
        )

        out[t] = {
            "name": (
                old.get("name")
                or m["name"]
            ),
            "aliases": sorted(
                set(
                    old.get(
                        "aliases",
                        [],
                    )
                    + m["aliases"]
                    + [m["name"]]
                )
            ),
        }

    if refresh:
        path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        path.write_text(
            json.dumps(
                out,
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

    return out


_ALIAS_CACHE = {}
_PATTERN_CACHE = {}


def alias_hits(text, companies):
    key = (
        id(companies),
        hashlib.sha256(
            text.encode()
        ).digest(),
    )

    if key in _ALIAS_CACHE:
        return set(
            _ALIAS_CACHE[key]
        )

    if id(companies) not in _PATTERN_CACHE:
        names = {}

        for t, m in companies.items():
            for alias in (
                [m.get("name", "")]
                + m.get(
                    "aliases",
                    [],
                )
            ):
                if alias:
                    names.setdefault(
                        alias.casefold(),
                        set(),
                    ).add(t)

        terms = []

        for alias in sorted(
            names,
            key=len,
            reverse=True,
        ):
            terms.append(
                (
                    r"(?<![\w])"
                    if alias.isascii()
                    else ""
                )
                + re.escape(alias)
                + (
                    r"(?![\w])"
                    if alias.isascii()
                    else ""
                )
            )

        _PATTERN_CACHE[
            id(companies)
        ] = (
            re.compile(
                "|".join(terms),
                re.I,
            ),
            names,
        )

    pattern, names = (
        _PATTERN_CACHE[
            id(companies)
        ]
    )

    hits = set()

    for match in pattern.finditer(
        text
    ):
        word = match.group()

        if (
            len(word) <= 3
            and word.isascii()
            and word != word.upper()
        ):
            continue

        hits.update(
            names[
                word.casefold()
            ]
        )

    _ALIAS_CACHE[
        key
    ] = frozenset(hits)

    return hits


def explicit_tickers(text):
    return (
        set(
            re.findall(
                r"(?<!\d)([1-9]\d{3})"
                r"(?:\s+TT\b|\.(?:TW|TWO)\b)",
                text,
                re.I,
            )
        )
        |
        set(
            re.findall(
                r"[A-Za-z\u3400-\u9fff]"
                r"\s*[(（]"
                r"([1-9]\d{3})"
                r"[)）]",
                text,
            )
        )
    )


def resolve(
    ticker,
    name,
    text,
    companies,
):
    raw = str(
        ticker
        or ""
    ).strip()

    t = re.sub(
        r"(?:\s+TT|\.(?:TW|TWO))$",
        "",
        raw,
        flags=re.I,
    )

    name_hits = {
        k
        for k, v in companies.items()
        if norm(name)
        and norm(name)
        in {
            norm(
                v.get("name")
            ),
            *map(
                norm,
                v.get(
                    "aliases",
                    [],
                ),
            ),
        }
    }

    supported = (
        explicit_tickers(text)
        | alias_hits(
            text,
            companies,
        )
    )

    if (
        t in companies
        and t in supported
    ):
        if (
            name_hits
            and t not in name_hits
        ):
            raise ValueError(
                "company name/ticker conflict: "
                + t
            )

        return (
            t,
            companies[t]["name"],
        )

    if len(name_hits) == 1:
        candidate = next(
            iter(name_hits)
        )

        if candidate in supported:
            return (
                candidate,
                companies[
                    candidate
                ]["name"],
            )

    if (
        re.fullmatch(
            r"[1-9]\d{3}"
            r"(?:\.TW|\.TWO)?",
            raw,
        )
        or name_hits
    ):
        raise ValueError(
            "unsupported or ambiguous Taiwan identity: "
            + raw
            + " "
            + str(name)
        )

    # Foreign companies must not be
    # converted into Taiwan peers.
    return (
        raw,
        str(name or ""),
    )


def _target_matches(page):
    """
    Return candidate target-price matches.

    Supported examples include:

    Target price: TWD2,460
    Target price: TWD 2,460
    Target price: NT$2,460
    Target price TWD 2,460
    Price target: TWD2,460
    12-month target price: TWD2,460
    12 month target price: TWD 2,460
    12M target price: TWD2,460
    PO: TWD2,460
    目標價：2,460元

    The target itself still needs issuer validation
    inside page_targets().
    """

    pattern = re.compile(
        r"(?:"
        r"\b(?:12[\s-]*(?:month|m)\s+)?"
        r"target\s+price"
        r"|"
        r"\bprice\s+target"
        r"|"
        r"\bPO"
        r"|"
        r"目標價"
        r")"
        r"\s*"
        r"(?:"
        r"上修|下修|調高|調低|調升|調降"
        r")?"
        r"\s*"
        r"(?:至|為|to)?"
        r"\s*"
        r"[:：]?"
        r"\s*"
        r"(?:(TWD|NT\$|NTD|USD|US\$|KRW)\s*)?"
        r"("
        r"\d[\d,]*(?:\.\d+)?[kK]?"
        r"|"
        r"n\.?a\.?(?!\w)"
        r")",
        re.I,
    )

    return list(
        pattern.finditer(page)
    )


def _issuer_for_target(
    page,
    match,
    companies,
):
    """
    Identify the issuer attached to a target-price block.

    Preference:
    1. explicit ticker before the target on the same page
    2. explicit ticker in the first 1,800 chars
    3. exactly one Taiwan ticker on the page
    4. exactly one company alias before the target
    5. exactly one company alias in the first 1,800 chars

    If ambiguous, return None rather than guessing.
    """

    head = page[
        :match.start()
    ]

    # Strongest evidence:
    # explicit ticker before target.
    ids = (
        explicit_tickers(head)
        & set(companies)
    )

    if len(ids) == 1:
        return next(
            iter(ids)
        )

    # Broker cover/header commonly places
    # issuer + ticker near the beginning.
    ids = (
        explicit_tickers(
            page[:1800]
        )
        & set(companies)
    )

    if len(ids) == 1:
        return next(
            iter(ids)
        )

    # If the page contains only one explicit
    # Taiwan ticker, it is safe to use.
    ids = (
        explicit_tickers(page)
        & set(companies)
    )

    if len(ids) == 1:
        return next(
            iter(ids)
        )

    # Alias fallback before target.
    ids = (
        alias_hits(
            head,
            companies,
        )
        & set(companies)
    )

    if len(ids) == 1:
        return next(
            iter(ids)
        )

    # Final alias fallback limited to header area.
    ids = (
        alias_hits(
            page[:1800],
            companies,
        )
        & set(companies)
    )

    if len(ids) == 1:
        return next(
            iter(ids)
        )

    return None


def _target_value(match):
    raw = match.group(2)

    if raw.lower().startswith(
        "n"
    ):
        return None

    multiplier = (
        1000
        if raw[-1:].lower() == "k"
        else 1
    )

    number = raw.rstrip(
        "kK"
    ).replace(
        ",",
        "",
    )

    return (
        float(number)
        * multiplier
    )


def _target_currency(
    page,
    match,
):
    currency = (
        match.group(1)
        or ""
    ).upper()

    if currency:
        return currency

    suffix = re.match(
        r"\s*(TWD|NTD|NT\$)"
        r"\b",
        page[
            match.end():
        ],
        re.I,
    )

    if suffix:
        return (
            suffix.group(1)
            .upper()
        )

    return ""


def _valid_taiwan_currency(
    page,
    match,
    value,
    currency,
):
    """
    Numeric Taiwan targets must have
    explicit TWD/NT$/NTD evidence or
    Chinese 元 immediately associated
    with 目標價.

    This prevents arbitrary numbers from
    peer tables becoming Taiwan targets.
    """

    if value is None:
        return True

    if currency in (
        "TWD",
        "NT$",
        "NTD",
    ):
        return True

    matched_label = (
        match.group(0)
        or ""
    )

    if "目標價" not in matched_label:
        return False

    if re.match(
        r"\s*元",
        page[
            match.end():
        ],
    ):
        return True

    values = re.findall(
        r"目標價"
        r"[^\n\d]{0,15}"
        r"(\d[\d,]*(?:\.\d+)?)"
        r"\s*元",
        page,
    )

    return any(
        float(
            v.replace(
                ",",
                "",
            )
        )
        == value
        for v in values
    )


def _rating_and_action(
    page,
    match,
):
    """
    Only assign maintain when source wording
    explicitly supports it.

    A bare BUY rating is still recorded as Buy,
    but does not automatically mean the broker
    'maintained' the rating.
    """

    window = page[
        max(
            0,
            match.start() - 1500,
        ):
        min(
            len(page),
            match.end() + 1500,
        )
    ]

    if re.search(
        r"\b(?:reiterate|reiterated|maintain|maintained)"
        r"(?:s|ed|ing)?"
        r"\s+(?:our\s+)?BUY\b",
        window,
        re.I,
    ):
        return (
            "Buy",
            "maintain",
        )

    if re.search(
        r"\bBUY\b",
        window,
        re.I,
    ):
        return (
            "Buy",
            "none",
        )

    return (
        "",
        "none",
    )


def page_targets(
    text,
    companies,
):
    """
    Extract issuer-specific price targets.

    Important:
    - never infer a target from a peer table
    - issuer must be uniquely supported on the page
    - Taiwan numeric targets require currency evidence
    - supports broker wording such as
      "12-month target price: TWD2,460"
    """

    views = []

    text = unicodedata.normalize(
        "NFKC",
        text,
    )

    for page_no, page in enumerate(
        text.split("\f"),
        1,
    ):
        matches = _target_matches(
            page
        )

        if not matches:
            continue

        for match in matches:
            t = _issuer_for_target(
                page,
                match,
                companies,
            )

            if not t:
                continue

            if t not in companies:
                continue

            value = _target_value(
                match
            )

            currency = (
                _target_currency(
                    page,
                    match,
                )
            )

            # Explicit From / To revision table:
            # second same-line TWD price is
            # the new/current target.
            line = page[
                match.start():
            ].split(
                "\n",
                1,
            )[0]

            context_before = page[
                max(
                    0,
                    match.start() - 350,
                ):
                match.start()
            ]

            if re.search(
                r"From\s+To",
                context_before,
                re.I,
            ):
                pair = re.findall(
                    r"(?:NT\$|TWD|NTD)"
                    r"\s*"
                    r"(\d[\d,]*(?:\.\d+)?)",
                    line,
                    re.I,
                )

                if len(pair) == 2:
                    value = float(
                        pair[1].replace(
                            ",",
                            "",
                        )
                    )

                    currency = "TWD"

            if not _valid_taiwan_currency(
                page,
                match,
                value,
                currency,
            ):
                continue

            rating, action = (
                _rating_and_action(
                    page,
                    match,
                )
            )

            views.append(
                {
                    "ticker": t,
                    "name": companies[
                        t
                    ]["name"],
                    "target_price_new": value,
                    "target_price_old": None,
                    "currency": (
                        "TWD"
                        if value is not None
                        else ""
                    ),
                    "rating": rating,
                    "action": action,
                    "page": page_no,
                    "evidence": compact(
                        page[
                            max(
                                0,
                                match.start() - 160,
                            ):
                            min(
                                len(page),
                                match.end() + 160,
                            )
                        ]
                    ),
                    "target_unavailable": (
                        value is None
                    ),
                }
            )

    # One unambiguous current target per issuer.
    # Duplicate appearances of the SAME target
    # are fine.
    # Conflicting targets require manual review.
    out = []

    for t in sorted(
        {
            v["ticker"]
            for v in views
        }
    ):
        rows = [
            v
            for v in views
            if v["ticker"] == t
        ]

        values = {
            v["target_price_new"]
            for v in rows
        }

        if len(values) > 1:
            raise ValueError(
                "conflicting target prices for "
                + t
            )

        # Prefer the row carrying an explicit
        # rating/action when duplicate target
        # references exist.
        rows.sort(
            key=lambda v: (
                bool(v.get("rating")),
                v.get("action")
                == "maintain",
            ),
            reverse=True,
        )

        out.append(
            rows[0]
        )

    return out


def view_line(v):
    if (
        v.get(
            "target_price_new"
        )
        is None
    ):
        return (
            f"{v['name']} "
            f"{v['ticker']}"
            "｜未提供目標價"
        )

    rating = (
        "維持買進，"
        if v.get("action")
        == "maintain"
        else (
            v.get(
                "rating",
                "",
            )
            + "，"
            if v.get("rating")
            else ""
        )
    )

    return (
        f"{v['name']} "
        f"{v['ticker']}"
        f"｜{rating}"
        "目標價 "
        f"NT${v['target_price_new']:,.0f}"
    )


def audit_report(
    report,
    src,
    companies,
):
    r = copy.deepcopy(
        report
    )

    text = str(
        src.get("text")
        or ""
    )

    if not text.strip():
        raise ValueError(
            "source text unavailable; "
            "cannot audit existing report"
        )

    changes = []

    if (
        r.get("report_type")
        == "company"
    ):
        # Issuer on the cover takes precedence
        # over generated Chinese translations.
        cover = (
            text.split("\f")[0][
                :3500
            ]
        )

        ids = explicit_tickers(
            cover[:1500]
        )

        if (
            len(ids) == 1
            and next(iter(ids))
            in companies
        ):
            t = next(
                iter(ids)
            )

            old_name = r.get(
                "name",
                "",
            )

            old_t = r.get(
                "ticker",
                "",
            )

            r["ticker"] = t
            r["name"] = (
                companies[t]["name"]
            )

            if (
                old_name
                and old_name
                != r["name"]
            ):
                # Replace a hallucinated label
                # only when it is absent from
                # the source itself.
                if (
                    old_name in text
                    and re.search(
                        r"[\u3400-\u9fff]",
                        old_name,
                    )
                    and norm(old_name)
                    not in {
                        norm(x)
                        for x in companies[
                            t
                        ].get(
                            "aliases",
                            [],
                        )
                    }
                ):
                    raise ValueError(
                        "cover and generated "
                        "issuer conflict "
                        "requiring review"
                    )

                for k in (
                    "title",
                    "detail",
                    "push_reason",
                ):
                    r[k] = str(
                        r.get(k)
                        or ""
                    ).replace(
                        old_name,
                        r["name"],
                    )

                for k in (
                    "summary",
                    "key_points",
                    "forecast_changes",
                    "risks",
                ):
                    r[k] = [
                        str(x).replace(
                            old_name,
                            r["name"],
                        )
                        for x in r.get(
                            k,
                            [],
                        )
                    ]

                changes.append(
                    f"issuer "
                    f"{old_t}/"
                    f"{old_name} -> "
                    f"{t}/"
                    f"{r['name']}"
                )

        else:
            (
                r["ticker"],
                r["name"],
            ) = resolve(
                r.get("ticker"),
                r.get("name"),
                text,
                companies,
            )

    for b in r.get(
        "beneficiaries",
        [],
    ):
        (
            b["ticker"],
            b["name"],
        ) = resolve(
            b.get("ticker"),
            b.get("name"),
            text,
            companies,
        )

    views = page_targets(
        text,
        companies,
    )

    r["stock_views"] = (
        views
    )

    if (
        r.get("report_type")
        == "company"
    ):
        own = next(
            (
                v
                for v in views
                if v["ticker"]
                == r.get("ticker")
            ),
            None,
        )

        if own:
            old = r.get(
                "target_price_old"
            )

            normalized = (
                unicodedata.normalize(
                    "NFKC",
                    text,
                )
            )

            if old not in (
                None,
                "",
            ):
                amount = re.escape(
                    f"{float(old):g}"
                ).replace(
                    "\\.",
                    "[.]",
                )

                old_ok = re.search(
                    r"(?:目標價|target|TP)"
                    r"[^\n]{0,80}"
                    r"(?<![\d.])"
                    + amount
                    + r"(?![\d.])",
                    normalized.replace(
                        ",",
                        "",
                    ),
                    re.I,
                )

                if not old_ok:
                    old = None

            else:
                old = None

            r[
                "target_price_old"
            ] = old

            r[
                "target_price_new"
            ] = own[
                "target_price_new"
            ]

            # Prefer source-validated rating
            # when it exists.
            if own.get("rating"):
                r["rating"] = (
                    own["rating"]
                )

            if (
                own.get("action")
                == "maintain"
            ):
                r["action"] = (
                    "maintain"
                )

            if own[
                "target_unavailable"
            ]:
                r["action"] = "none"
                r["rating"] = ""
                r[
                    "target_price_old"
                ] = None

        elif (
            r.get(
                "target_price_new"
            )
            is not None
        ):
            raise ValueError(
                "price target has no "
                "validated issuer-specific "
                "source block"
            )

    lines = [
        view_line(v)
        for v in views
        if v.get(
            "target_price_new"
        )
        is not None
    ]

    if lines:
        r[
            "recommendation_headlines"
        ] = lines

        r["summary"] = (
            lines
            + [
                x
                for x in r.get(
                    "summary",
                    [],
                )
                if x not in lines
            ]
        )

        r["push_reason"] = (
            "；".join(lines)
        )

    r[
        "identity_changes"
    ] = changes

    # Successful audit clears all previous
    # review/error state.
    r.pop(
        "validation_error",
        None,
    )

    r.pop(
        "audit_error",
        None,
    )

    r.pop(
        "audit_failed_at",
        None,
    )

    r[
        "audit_version"
    ] = VERSION

    r[
        "validation_status"
    ] = "verified"

    r[
        "source_text_hash"
    ] = hashlib.sha256(
        text.encode()
    ).hexdigest()

    return r
