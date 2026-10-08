"""Evidence-based Taiwan company identity and per-company price-target audit."""
import copy
import json
import re
import hashlib
import urllib.request
import unicodedata
from pathlib import Path

VERSION = "2026-10-05-identity-target-v2"
ROOT = Path(__file__).resolve().parents[1]
SEEDS = {
    "2383": {"name": "台光電", "aliases": ["Elite Material", "Elite Materials", "Elite Material Co., Ltd.", "EMC"]},
    "3013": {"name": "晟銘電", "aliases": ["Chenming Electronic Technology", "Chenming", "UNEEC"]},
    "3653": {"name": "健策", "aliases": ["Jentech Precision Industrial", "Jentech"]},
}


def norm(s):
    return re.sub(r"[^\w\u3400-\u9fff]+", "", str(s or "").casefold())


def compact(s):
    return re.sub(r"\s+", " ", str(s or "")).strip()


def read(path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def _dedupe_aliases(values):
    result, seen = [], set()
    for value in values or []:
        alias = str(value or "").strip()
        if not alias:
            continue
        key = unicodedata.normalize("NFKC", alias).casefold()
        if key not in seen:
            seen.add(key)
            result.append(alias)
    return result


def registry(refresh=False):
    path = ROOT / "data/report_company_registry.json"
    raw = read(path, {})
    out = {}
    for t, m in raw.items():
        if not isinstance(m, dict):
            continue
        ticker = str(t or "").strip()
        if ticker:
            out[ticker] = {"name": str(m.get("name") or ticker).strip(),
                           "aliases": _dedupe_aliases(m.get("aliases", []))}
    for t, m in read(ROOT / "data/master.json", {}).get("stocks", {}).items():
        if m.get("market") in ("twse", "tpex"):
            item = out.setdefault(t, {"name": t, "aliases": []})
            item["name"] = str(m.get("name") or item.get("name") or t).strip()
            item["aliases"] = _dedupe_aliases(item.get("aliases", []))
    if refresh:
        urls = ["https://openapi.twse.com.tw/v1/opendata/t187ap03_L",
                "https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap03_O"]
        for url in urls:
            try:
                with urllib.request.urlopen(url, timeout=20) as r:
                    rows = json.load(r)
                for row in rows:
                    t = str(row.get("公司代號") or row.get("SecuritiesCompanyCode") or "").strip()
                    if not re.fullmatch(r"[1-9]\d{3}", t):
                        continue
                    item = out.setdefault(t, {"name": t, "aliases": []})
                    item["name"] = str(row.get("公司簡稱") or row.get("CompanyAbbreviation") or
                                       item.get("name") or row.get("公司名稱") or t).strip()
                    new_aliases = []
                    for k in ("公司名稱", "公司簡稱", "英文簡稱", "英文全名", "CompanyName",
                              "CompanyAbbreviation", "EnglishCompanyName", "EnglishAbbreviation"):
                        v = str(row.get(k) or "").strip()
                        if len(v) >= 3:
                            new_aliases.append(v)
                    item["aliases"] = _dedupe_aliases(item.get("aliases", []) + new_aliases)
            except Exception as exc:
                print("Company registry source unavailable:", type(exc).__name__)
    for t, m in out.items():
        name = str(m.get("name") or t).strip()
        short_name = re.sub(r"[-*]?(?:KY)?$", "", name)
        m["name"] = name
        m["aliases"] = _dedupe_aliases(m.get("aliases", []) + [name, short_name])
    for t, m in SEEDS.items():
        old = out.get(t, {})
        out[t] = {"name": old.get("name") or m["name"],
                  "aliases": _dedupe_aliases(old.get("aliases", []) + m["aliases"] + [m["name"]])}
    for m in out.values():
        m["aliases"] = _dedupe_aliases(m.get("aliases", []))
    if refresh:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
        _retry_fixed_target_conflicts_once()
    return out


def _retry_fixed_target_conflicts_once():
    """One-time retry of the legacy current-vs-previous target audit error.

    The AI workflow calls registry(refresh=True) BEFORE loading report_inbox.
    We clear only the old error marker for affected reports, once per file.
    A persistent retry flag prevents endless paid API retries if another
    independent validation error remains. No successful report is touched.
    """
    path = ROOT / "data/report_inbox.json"
    inbox = read(path, {})
    changed = False
    for src in inbox.get("items", []):
        if (src.get("status") != "audit_error"
                or not str(src.get("ai_error") or "").startswith("conflicting target prices for ")
                or src.get("target_conflict_repair_attempted")):
            continue
        src["target_conflict_repair_attempted"] = True
        for key in ("audit_failed_version", "audit_failed_text_hash", "audit_failed_at"):
            src.pop(key, None)
        changed = True
    if changed:
        path.write_text(json.dumps(inbox, ensure_ascii=False, indent=2), encoding="utf-8")
        print("Enabled one-time retry for legacy target-price conflicts")


_ALIAS_CACHE = {}
_PATTERN_CACHE = {}


def alias_hits(text, companies):
    key = (id(companies), hashlib.sha256(text.encode()).digest())
    if key in _ALIAS_CACHE:
        return set(_ALIAS_CACHE[key])
    if id(companies) not in _PATTERN_CACHE:
        names = {}
        for t, m in companies.items():
            for alias in [m.get("name", "")] + m.get("aliases", []):
                if alias:
                    names.setdefault(alias.casefold(), set()).add(t)
        terms = [(r"(?<![\w])" if alias.isascii() else "") + re.escape(alias) +
                 (r"(?![\w])" if alias.isascii() else "")
                 for alias in sorted(names, key=len, reverse=True)]
        _PATTERN_CACHE[id(companies)] = (re.compile("|".join(terms), re.I), names)
    pattern, names = _PATTERN_CACHE[id(companies)]
    hits = set()
    for match in pattern.finditer(text):
        word = match.group()
        if len(word) <= 3 and word.isascii() and word != word.upper():
            continue
        hits.update(names[word.casefold()])
    _ALIAS_CACHE[key] = frozenset(hits)
    return hits


def explicit_tickers(text):
    return (set(re.findall(r"(?<!\d)([1-9]\d{3})(?:\s+TT\b|\.(?:TW|TWO)\b)", text, re.I)) |
            set(re.findall(r"[A-Za-z\u3400-\u9fff]\s*[(（]([1-9]\d{3})[)）]", text)))


def resolve(ticker, name, text, companies):
    raw = str(ticker or "").strip()
    t = re.sub(r"(?:\s+TT|\.(?:TW|TWO))$", "", raw, flags=re.I)
    name_hits = {k for k, v in companies.items() if norm(name) and norm(name) in
                 {norm(v.get("name")), *map(norm, v.get("aliases", []))}}
    supported = explicit_tickers(text) | alias_hits(text, companies)
    if t in companies and t in supported:
        if name_hits and t not in name_hits:
            raise ValueError("company name/ticker conflict: " + t)
        return t, companies[t]["name"]
    if len(name_hits) == 1:
        candidate = next(iter(name_hits))
        if candidate in supported:
            return candidate, companies[candidate]["name"]
    if re.fullmatch(r"[1-9]\d{3}(?:\.TW|\.TWO)?", raw) or name_hits:
        raise ValueError("unsupported or ambiguous Taiwan identity: " + raw + " " + str(name))
    return raw, str(name or "")


def _target_matches(page):
    pattern = re.compile(
        r"(?:\b(?:12[\s-]*(?:month|m)\s+)?target\s+price|\bprice\s+target|\bPO|目標價)"
        r"\s*(?:上修|下修|調高|調低|調升|調降)?\s*(?:至|為|to)?\s*[:：]?\s*"
        r"(?:(TWD|NT\$|NTD|USD|US\$|KRW)\s*)?"
        r"(\d[\d,]*(?:\.\d+)?[kK]?|n\.?a\.?(?!\w))", re.I)
    return list(pattern.finditer(page))


def _issuer_for_target(page, match, companies):
    head = page[:match.start()]
    for ids in (explicit_tickers(head) & set(companies),
                explicit_tickers(page[:1800]) & set(companies),
                explicit_tickers(page) & set(companies),
                alias_hits(head, companies) & set(companies),
                alias_hits(page[:1800], companies) & set(companies)):
        if len(ids) == 1:
            return next(iter(ids))
    return None


def _target_value(match):
    raw = match.group(2)
    if raw.lower().startswith("n"):
        return None
    multiplier = 1000 if raw[-1:].lower() == "k" else 1
    return float(raw.rstrip("kK").replace(",", "")) * multiplier


def _target_currency(page, match):
    currency = (match.group(1) or "").upper()
    if currency:
        return currency
    suffix = re.match(r"\s*(TWD|NTD|NT\$)\b", page[match.end():], re.I)
    return suffix.group(1).upper() if suffix else ""


def _valid_taiwan_currency(page, match, value, currency):
    if value is None:
        return True
    if currency in ("TWD", "NT$", "NTD"):
        return True
    if "目標價" not in (match.group(0) or ""):
        return False
    if re.match(r"\s*元", page[match.end():]):
        return True
    values = re.findall(r"目標價[^\n\d]{0,15}(\d[\d,]*(?:\.\d+)?)\s*元", page)
    return any(float(v.replace(",", "")) == value for v in values)


def _rating_and_action(page, match):
    window = page[max(0, match.start()-1500):min(len(page), match.end()+1500)]
    if re.search(r"\b(?:reiterate|reiterated|maintain|maintained)(?:s|ed|ing)?\s+(?:our\s+)?BUY\b", window, re.I):
        return "Buy", "maintain"
    if re.search(r"\bBUY\b", window, re.I):
        return "Buy", "none"
    return "", "none"


def _historical_target(page, match):
    """Reject previous/old/earlier targets, not the current recommendation."""
    prefix = page[max(0, match.start()-60):match.start()]
    # Require adjacency: a previous-target qualifier must directly prefix the label.
    return bool(re.search(
        r"(?:前次|前期|上次|原|舊|先前|過去|前一(?:次|期)|previous|prior|former|old|previously)"
        r"\s*(?:的|之|the|our)?\s*$", prefix, re.I))


def _target_context_rank(page, match, page_no):
    """Prefer the cover's current target over later narrative/peer-table mentions."""
    prefix = page[max(0, match.start()-80):match.start()]
    line = page[match.start():].split("\n", 1)[0]
    # Explicit current-target wording is stronger than plain repeated narrative.
    explicit_current = bool(re.search(r"(?:最新|本次|目前|現行|current|new|revised)\s*$", prefix, re.I))
    cover = page_no == 1 and match.start() < 3500
    return (int(explicit_current), int(cover), -match.start())


def page_targets(text, companies):
    """Validate issuer-specific *current* target prices; never treat previous TP as current."""
    views = []
    text = unicodedata.normalize("NFKC", text)
    for page_no, page in enumerate(text.split("\f"), 1):
        for match in _target_matches(page):
            if _historical_target(page, match):
                continue
            t = _issuer_for_target(page, match, companies)
            if not t or t not in companies:
                continue
            value = _target_value(match)
            currency = _target_currency(page, match)
            line = page[match.start():].split("\n", 1)[0]
            context_before = page[max(0, match.start()-350):match.start()]
            if re.search(r"From\s+To", context_before, re.I):
                pair = re.findall(r"(?:NT\$|TWD|NTD)\s*(\d[\d,]*(?:\.\d+)?)", line, re.I)
                if len(pair) == 2:
                    value, currency = float(pair[1].replace(",", "")), "TWD"
            if not _valid_taiwan_currency(page, match, value, currency):
                continue
            rating, action = _rating_and_action(page, match)
            views.append({
                "ticker": t, "name": companies[t]["name"], "target_price_new": value,
                "target_price_old": None, "currency": "TWD" if value is not None else "",
                "rating": rating, "action": action, "page": page_no,
                "evidence": compact(page[max(0, match.start()-160):min(len(page), match.end()+160)]),
                "target_unavailable": value is None,
                "_rank": _target_context_rank(page, match, page_no),
            })
    out = []
    for t in sorted({v["ticker"] for v in views}):
        rows = [v for v in views if v["ticker"] == t]
        # Cover-page current target takes precedence over targets in the report body.
        # Different CURRENT targets with equal confidence remain a hard error.
        best_rank = max(v["_rank"][:2] for v in rows)
        top = [v for v in rows if v["_rank"][:2] == best_rank]
        values = {v["target_price_new"] for v in top}
        if len(values) > 1:
            raise ValueError("conflicting current target prices for " + t)
        top.sort(key=lambda v: (bool(v.get("rating")), v.get("action") == "maintain", v["_rank"]), reverse=True)
        chosen = top[0]
        chosen.pop("_rank", None)
        out.append(chosen)
    return out


def view_line(v):
    if v.get("target_price_new") is None:
        return f"{v['name']} {v['ticker']}｜未提供目標價"
    rating = ("維持買進，" if v.get("action") == "maintain" else
              (v.get("rating", "") + "，" if v.get("rating") else ""))
    return f"{v['name']} {v['ticker']}｜{rating}目標價 NT${v['target_price_new']:,.0f}"


def audit_report(report, src, companies):
    r = copy.deepcopy(report)
    text = str(src.get("text") or "")
    if not text.strip():
        raise ValueError("source text unavailable; cannot audit existing report")
    changes = []
    if r.get("report_type") == "company":
        cover = text.split("\f")[0][:3500]
        ids = explicit_tickers(cover[:1500])
        if len(ids) == 1 and next(iter(ids)) in companies:
            t = next(iter(ids))
            old_name, old_t = r.get("name", ""), r.get("ticker", "")
            r["ticker"], r["name"] = t, companies[t]["name"]
            if old_name and old_name != r["name"]:
                if (old_name in text and re.search(r"[\u3400-\u9fff]", old_name)
                        and norm(old_name) not in {norm(x) for x in companies[t].get("aliases", [])}):
                    raise ValueError("cover and generated issuer conflict requiring review")
                for k in ("title", "detail", "push_reason"):
                    r[k] = str(r.get(k) or "").replace(old_name, r["name"])
                for k in ("summary", "key_points", "forecast_changes", "risks"):
                    r[k] = [str(x).replace(old_name, r["name"]) for x in r.get(k, [])]
                changes.append(f"issuer {old_t}/{old_name} -> {t}/{r['name']}")
        else:
            r["ticker"], r["name"] = resolve(r.get("ticker"), r.get("name"), text, companies)
    for b in r.get("beneficiaries", []):
        b["ticker"], b["name"] = resolve(b.get("ticker"), b.get("name"), text, companies)
    views = page_targets(text, companies)
    r["stock_views"] = views
    if r.get("report_type") == "company":
        own = next((v for v in views if v["ticker"] == r.get("ticker")), None)
        if own:
            old = r.get("target_price_old")
            normalized = unicodedata.normalize("NFKC", text)
            if old not in (None, ""):
                amount = re.escape(f"{float(old):g}").replace("\\.", "[.]")
                old_ok = re.search(r"(?:目標價|target|TP)[^\n]{0,80}(?<![\d.])" + amount + r"(?![\d.])",
                                   normalized.replace(",", ""), re.I)
                if not old_ok:
                    old = None
            else:
                old = None
            r["target_price_old"] = old
            r["target_price_new"] = own["target_price_new"]
            if own.get("rating"):
                r["rating"] = own["rating"]
            if own.get("action") == "maintain":
                r["action"] = "maintain"
            if own["target_unavailable"]:
                r["action"], r["rating"], r["target_price_old"] = "none", "", None
        elif r.get("target_price_new") is not None:
            raise ValueError("price target has no validated issuer-specific source block")
    lines = [view_line(v) for v in views if v.get("target_price_new") is not None]
    if lines:
        r["recommendation_headlines"] = lines
        r["summary"] = lines + [x for x in r.get("summary", []) if x not in lines]
        r["push_reason"] = "；".join(lines)
    r["identity_changes"] = changes
    for key in ("validation_error", "audit_error", "audit_failed_at"):
        r.pop(key, None)
    r["audit_version"] = VERSION
    r["validation_status"] = "verified"
    r["source_text_hash"] = hashlib.sha256(text.encode()).hexdigest()
    return r
