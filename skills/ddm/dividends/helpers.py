"""skills/ddm/dividends/helpers.py - Pure-function helpers for the dividends skill.

Functions:
  - format_brl(v)     - format a REAL value as a PT-BR Real string
                         ("R$ 0,017250" for small values, "R$ 7,96" for
                         larger ones). 6 decimals when |v| < 1.0, 2 otherwise.
  - format_int(v)     - format an integer with PT-BR thousands separators
                         (e.g. 1234567 -> "1.234.567").
  - format_pct(v)     - format a float as a PT-BR percentage ("12,34%").
  - format_value(v, unit) - dispatch on unit ("R$" | "%" | "int" | "").
  - format_date(d)    - convert "2026-07-01" (YYYY-MM-DD) -> "01/07/2026"
                         (DD/MM/YYYY PT-BR display). Empty input -> "".

[v2] Shared numerics for the Proventos reorganization (WebUI v1.18 family
+ the skill's static dashboard — the "no forked numerics" pattern the
acoes skill set in v1.17: ONE bucketing/aggregation module used by BOTH
sides):
  - is_bdr(ticker)              - B3 BDR tickers end in "34" (AAPL34,
                                  GDBR34...). The DDM agenda mixes BDR
                                  events (~40%) with B3 natives — and BDR
                                  payouts (R$ 1,70-6,32) live in a
                                  different value universe than native
                                  dividends (R$ 0,01-1,13), so every view
                                  splits on this predicate.
  - summarize(dividends, today) - scoped KPI numerics: totals, by_tipo,
                                  biggest, next payment, distinct tickers,
                                  median/mean value.
  - bucketize(dividends)        - the 8 value-range buckets × tipo counts
                                  (moved from report.py's inline loop).
  - aggregate_by_empresa(divs)  - per-ticker: events, total/avg/max value,
                                  tipo split, last payment, BDR flag.
  - aggregate_by_day(divs)      - per-payment-date: events, value, BDR
                                  share, top-3 payers (the day's tooltip).
"""
from __future__ import annotations

from datetime import datetime, timezone
from statistics import median


def format_brl(v) -> str:
    """Format a REAL value as a PT-BR Real string.

    Dividend values range from R$0.006 to R$7.96. For values < 1.0 we use
    6 decimals so small per-share amounts stay readable ("R$ 0,017250").
    For values >= 1.0 we use 2 decimals ("R$ 7,96").

    Returns "-" for None / non-numeric inputs.
    """
    if v is None:
        return "-"
    try:
        f = float(v)
    except (ValueError, TypeError):
        return str(v)
    if abs(f) < 1.0:
        s = f"{f:.6f}"
    else:
        s = f"{f:.2f}"
    return f"R$ {s.replace('.', ',')}"


def format_int(v) -> str:
    """Format an integer with PT-BR thousands separators.

    1234567 -> "1.234.567". Returns "-" for None.
    """
    if v is None:
        return "-"
    try:
        n = int(v)
    except (ValueError, TypeError):
        return str(v)
    s = f"{n:,}".replace(",", ".")
    return s


def format_pct(v, decimals: int = 2) -> str:
    """Format a float as a PT-BR percentage.

    0.1234 -> "0,12%". Returns "-" for None.
    """
    if v is None:
        return "-"
    try:
        f = float(v)
    except (ValueError, TypeError):
        return str(v)
    s = f"{f:.{decimals}f}"
    return f"{s.replace('.', ',')}%"


def format_value(v, unit: str = "") -> str:
    """Dispatch on unit string.

    unit="R$"  -> format_brl
    unit="%"   -> format_pct
    unit="int" -> format_int
    else       -> format_brl (default for dividend values)
    """
    if unit == "%":
        return format_pct(v)
    if unit == "int":
        return format_int(v)
    # Default: Real (dividends are R$ amounts).
    return format_brl(v)


def format_date(d) -> str:
    """Convert '2026-07-01' (YYYY-MM-DD) -> '01/07/2026' (DD/MM/YYYY).

    PT-BR display format. Returns "" for empty / malformed inputs.
    """
    if not d:
        return ""
    s = str(d).strip()
    if len(s) != 10 or s[4] != "-" or s[7] != "-":
        return s
    yyyy, mm, dd = s[:4], s[5:7], s[8:10]
    return f"{dd}/{mm}/{yyyy}"


# ── [v2] shared numerics (skill static + WebUI DividendosService) ───────────

def is_bdr(ticker: str) -> bool:
    """True for B3 BDR tickers — suffix "34" (AAPL34, GDBR34, MSFT34...).

    BDRs (Brazilian Depositary Receipts) are FOREIGN companies' shares
    traded on B3; their per-share payouts dwarf B3 natives (the agenda's
    top values R$ 1,70-6,32 are all BDRs vs natives topping at ~R$ 1,13),
    which is why every Proventos view splits on this predicate.
    """
    return bool(ticker) and str(ticker).strip().upper().endswith("34")


def _val(d: dict) -> float | None:
    """Coerce an event's value to float; None when missing/invalid."""
    v = d.get("value")
    if v is None:
        return None
    try:
        return float(v)
    except (ValueError, TypeError):
        return None


def _is_jcp(d: dict) -> bool:
    return (d.get("tipo") or "").strip().upper() == "JCP"


def summarize(dividends: list[dict], today_iso: str = "") -> dict:
    """Scoped KPI numerics for one slice of the agenda (natives OR BDRs).

    Pure Python over the query engine's rows — the same numbers feed the
    skill's static tabs and the WebUI subtabs (the query_engine.summary()
    SQL covers only the WHOLE agenda; the scoped views compute here).

    Returns:
        {"total": <int>, "by_tipo": {"Dividendo": n, "JCP": n},
         "total_value": <float>, "biggest": {ticker, tipo, value,
         record_date, payment_date} | None, "next_payment_date": <str>,
         "tickers": <int distinct>, "median_value": <float | None>,
         "mean_value": <float | None>}
    """
    out = {
        "total": 0, "by_tipo": {"Dividendo": 0, "JCP": 0},
        "total_value": 0.0, "biggest": None, "next_payment_date": "",
        "tickers": 0, "median_value": None, "mean_value": None,
    }
    if not dividends:
        return out

    values: list[float] = []
    biggest: dict | None = None
    for d in dividends:
        out["total"] += 1
        out["by_tipo"]["JCP" if _is_jcp(d) else "Dividendo"] += 1
        v = _val(d)
        if v is not None:
            values.append(v)
            out["total_value"] += v
            if biggest is None or v > biggest["value"]:
                biggest = {
                    "ticker": d.get("ticker", ""),
                    "tipo": d.get("tipo", ""),
                    "value": v,
                    "record_date": d.get("record_date", ""),
                    "payment_date": d.get("payment_date", ""),
                }
    out["biggest"] = biggest
    out["tickers"] = len({d.get("ticker", "") for d in dividends})
    if values:
        out["median_value"] = median(values)
        out["mean_value"] = sum(values) / len(values)

    # Next payment: the earliest payment_date strictly in the future vs
    # `today_iso`; if all are past (or no today given), the latest one —
    # the query_engine.summary() contract.
    today = today_iso or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    pay_dates = sorted({d.get("payment_date") for d in dividends
                        if d.get("payment_date")})
    if pay_dates:
        future = [p for p in pay_dates if p >= today]
        out["next_payment_date"] = future[0] if future else pay_dates[-1]
    return out


# The 8 value-range buckets (label, lower inclusive, upper exclusive) —
# the v1 static's chart scale, kept identical (PT-BR comma labels).
DISTRIBUTION_BUCKETS: list[tuple[str, float, float]] = [
    ("<0,05",       0.00,   0.05),
    ("0,05-0,10",   0.05,   0.10),
    ("0,10-0,25",   0.10,   0.25),
    ("0,25-0,50",   0.25,   0.50),
    ("0,50-1,00",   0.50,   1.00),
    ("1,00-2,00",   1.00,   2.00),
    ("2,00-5,00",   2.00,   5.00),
    ("≥5,00",       5.00,   float("inf")),
]


def bucketize(dividends: list[dict]) -> dict:
    """Count events per value-range bucket, split by tipo (the ONE scale).

    Returns:
        {"labels": [...8], "dividendo": [...8], "jcp": [...8],
         "totals": [...8]}
    """
    labels = [b[0] for b in DISTRIBUTION_BUCKETS]
    div = [0] * len(DISTRIBUTION_BUCKETS)
    jcp = [0] * len(DISTRIBUTION_BUCKETS)
    for d in dividends:
        v = _val(d)
        if v is None:
            continue
        for i, (_lbl, lo, hi) in enumerate(DISTRIBUTION_BUCKETS):
            if lo <= v < hi:
                (jcp if _is_jcp(d) else div)[i] += 1
                break
    return {
        "labels": labels,
        "dividendo": div,
        "jcp": jcp,
        "totals": [a + b for a, b in zip(div, jcp)],
    }


def aggregate_by_empresa(dividends: list[dict]) -> list[dict]:
    """Aggregate the agenda per ticker — the "quem paga?" view.

    One row per ticker: event count, tipo split, summed/avg/max value,
    the single biggest event, the last (latest) payment date, BDR flag.
    Sorted by total_value DESC (the biggest payers first).
    """
    by: dict[str, dict] = {}
    for d in dividends:
        t = d.get("ticker", "") or ""
        row = by.setdefault(t, {
            "ticker": t, "is_bdr": is_bdr(t), "events": 0,
            "n_dividendo": 0, "n_jcp": 0, "total_value": 0.0,
            "values": [], "max_event": None, "last_payment": "",
        })
        row["events"] += 1
        row["n_jcp" if _is_jcp(d) else "n_dividendo"] += 1
        v = _val(d)
        if v is not None:
            row["total_value"] += v
            row["values"].append(v)
            if row["max_event"] is None or v > row["max_event"]["value"]:
                row["max_event"] = {
                    "tipo": d.get("tipo", ""),
                    "value": v,
                    "payment_date": d.get("payment_date", ""),
                }
        pay = d.get("payment_date") or ""
        if pay > row["last_payment"]:
            row["last_payment"] = pay
    for row in by.values():
        vals = row.pop("values")
        row["avg_value"] = (sum(vals) / len(vals)) if vals else None
    return sorted(by.values(), key=lambda r: -r["total_value"])


def aggregate_by_day(dividends: list[dict]) -> list[dict]:
    """Aggregate the agenda per payment date — the "quando cai?" view.

    One row per payment_date (rows without one are skipped): event count,
    summed value, BDR event count + value, and the day's top-3 payers by
    value (the Data cell tooltip). Sorted by date ASC.
    """
    by: dict[str, dict] = {}
    for d in dividends:
        day = d.get("payment_date") or ""
        if not day:
            continue
        row = by.setdefault(day, {
            "date": day, "events": 0, "value": 0.0,
            "bdr_events": 0, "bdr_value": 0.0, "payers": [],
        })
        row["events"] += 1
        v = _val(d)
        if v is not None:
            row["value"] += v
            row["payers"].append((d.get("ticker", ""), v))
            if is_bdr(d.get("ticker", "")):
                row["bdr_events"] += 1
                row["bdr_value"] += v
    for row in by.values():
        row["payers"].sort(key=lambda p: -p[1])
        del row["payers"][3:]  # top-3 only
    return [by[d] for d in sorted(by)]
