"""report/_helpers.py — Shared utilities for valuation report builders.

Contains safe accessors, formatters, and derive_* helpers that compute
additional metrics from components already in ratios_dict (no new engine calls).
"""
from __future__ import annotations

from typing import Any

from tools.report_ops.formats import apply_fmt
from skills.cvm._shared_report.tooltips import get_tooltip as _get_tooltip


# ── Safe accessor + formatter ────────────────────────────────────────────────

def _safe_get(ratios_dict: dict | None, key: str) -> Any:
    """Pull a key from ratios_dict, returning None when missing."""
    if not isinstance(ratios_dict, dict):
        return None
    return ratios_dict.get(key)


def _fmt(value: Any, spec: str) -> str:
    """Format a value using apply_fmt, returning dash for None."""
    if value is None:
        return "—"
    try:
        return apply_fmt(value, spec)
    except Exception:
        return str(value)


def _safe_div(a: Any, b: Any) -> float | None:
    """Divide a/b, returning None when either side is None or b is zero."""
    if a is None or b is None or b == 0:
        return None
    try:
        return a / b
    except (TypeError, ValueError, ZeroDivisionError):
        return None


# ── Constants ────────────────────────────────────────────────────────────────

# Price multiples shown in the top table + comparison bar chart.
_MULTIPLES_PRICE: list[tuple[str, str, str, str]] = [
    ("P/L",       "p_l",       "num", "Cheap if < 10; expensive if > 25"),
    ("P/VPA",     "p_vpa",     "num", "Cheap if < 1; expensive if > 3"),
    ("P/EBIT",    "p_ebit",    "num", "Cheap if < 8; expensive if > 20"),
    ("P/EBITDA",  "p_ebitda",  "num", "Cheap if < 8; expensive if > 15"),
    ("PSR",       "psr",       "num", "Cheap if < 1; expensive if > 3"),
    ("P/EV",      "p_ev",      "num", "Cheap if < 1; expensive if > 3"),
    ("P/FCO",     "p_fco",     "num", "Cheap if < 10; expensive if > 25"),
    ("P/FCF",     "p_fcf",     "num", "Cheap if < 15; expensive if > 30"),
]

# EV multiples
_MULTIPLES_EV: list[tuple[str, str, str, str]] = [
    ("EV/EBIT",   "ev_ebit",   "num", "Cheap if < 8; expensive if > 15"),
    ("EV/EBITDA", "ev_ebitda", "num", "Cheap if < 8; expensive if > 15"),
    ("EV/Sales",  "ev_sales",  "num", "Cheap if < 1; expensive if > 3"),
    ("EV/FCF",    "ev_fcf",    "num", "Cheap if < 10; expensive if > 25"),
    ("P/EV",      "p_ev",      "num", "Cheap if < 1; expensive if > 3"),
]

# Less-common multiples. Key is ratios_dict key. P/Ativo, P/Passivo, P/RB
# come from the calculations registry (metric names apa/ppa/rbpa hold the
# ratio value). P/CG and P/DB are derived from components in _derive_multiples.
_MULTIPLES_LESS_COMMON: list[tuple[str, str, str, str]] = [
    ("P/Ativos",        "apa",                    "num", "Cheap if < 1; expensive if > 2"),
    ("P/Passivos",      "ppa",                    "num", "Higher = more leveraged"),
    ("P/RB",            "rbpa",                   "num", "Cheap if < 1; expensive if > 3"),
    ("P/CG",            "p_cg",                   "num", "Higher = pricier vs working capital"),
    ("P/DB",            "p_db",                   "num", "Higher = pricier vs gross debt"),
    ("P/Tangible Book", "price_to_tangible_book", "num", "Cheap if < 1; expensive if > 3"),
]

# Multiples shown in the comparison bar chart (raw values, no normalization).
_MULTIPLES_CHART: list[tuple[str, str]] = [
    ("P/L",       "p_l"),
    ("P/VPA",     "p_vpa"),
    ("EV/EBITDA", "ev_ebitda"),
    ("PSR",       "psr"),
]

_MULTIPLES_CHART_COLORS = ["#3b82f6", "#22c55e", "#f59e0b", "#a855f7"]

# Per-share metrics. Tuple: (label, value_key, ratio_key)
_PER_SHARE_ITEMS: list[tuple[str, str, str | None]] = [
    ("LPA",  "lpa",  "p_l"),     # price/LPA = P/L
    ("VPA",  "vpa",  "p_vpa"),   # price/VPA = P/VPA
    ("DPA",  "dpa",  None),      # price/DPA = (computed) — multiple, not yield
    ("RPA",  "rps",  "psr"),     # price/RPA = PSR
    ("RBPA", "rbpa", None),      # gross revenue / shares
    ("CGPA", "cgpa", None),      # working_capital / shares
    ("DBPA", "dbpa", None),      # divida_bruta / shares
    ("APA",  "apa",  None),      # total_assets / shares
    ("PPA",  "ppa",  None),      # total_liabilities / shares
]


# ── Derived metrics (no new engine calls) ────────────────────────────────────

def _derive_multiples(ratios_dict: dict | None) -> dict[str, float | None]:
    """Compute multiples NOT directly stored in ratios_dict.

    These are derived from components that ARE in ratios_dict:
      - p_ebitda = market_cap / ebitda
      - ev_ebit  = ev / ebit
      - p_ev     = market_cap / ev
      - p_cg     = market_cap / working_capital
      - p_db     = market_cap / divida_bruta

    P/Ativo (apa), P/Passivo (ppa), P/RB (rbpa) now come from the
    calculations registry — they are NOT derived here.
    """
    if not isinstance(ratios_dict, dict):
        return {}

    market_cap = ratios_dict.get("market_cap")
    ev         = ratios_dict.get("ev")
    ebit       = ratios_dict.get("ebit")
    ebitda     = ratios_dict.get("ebitda")
    wc         = ratios_dict.get("working_capital")
    db         = ratios_dict.get("divida_bruta")

    return {
        "p_ebitda":   _safe_div(market_cap, ebitda),
        "ev_ebit":    _safe_div(ev, ebit),
        "p_ev":       _safe_div(market_cap, ev),
        "p_cg":       _safe_div(market_cap, wc),
        "p_db":       _safe_div(market_cap, db),
    }


def _derive_per_share(ratios_dict: dict | None) -> dict[str, float | None]:
    """Compute per-share values NOT directly stored in ratios_dict.

    These are derived from components that ARE in ratios_dict:
      - cgpa = working_capital / shares
      - dbpa = divida_bruta / shares
    """
    if not isinstance(ratios_dict, dict):
        return {}

    shares = ratios_dict.get("total_shares")
    wc     = ratios_dict.get("working_capital")
    db     = ratios_dict.get("divida_bruta")

    return {
        "cgpa": _safe_div(wc, shares),
        "dbpa": _safe_div(db, shares),
    }


def _derive_detailed_leverage(ratios_dict: dict | None) -> dict[str, float | None]:
    """Compute detailed leverage metrics NOT directly stored in ratios_dict.

    These are derived from components that ARE in ratios_dict:
      - dl_ebit     = (divida_bruta - caixa) / ebit
      - gross_de    = divida_bruta / patrimonio_liquido
    """
    if not isinstance(ratios_dict, dict):
        return {}

    db  = ratios_dict.get("divida_bruta")
    cx  = ratios_dict.get("caixa")
    ebt = ratios_dict.get("ebit")
    pl  = ratios_dict.get("patrimonio_liquido")

    dl = None
    if db is not None and cx is not None:
        dl = db - cx

    return {
        "dl_ebit":           _safe_div(dl, ebt),
        "gross_de":          _safe_div(db, pl),
        "net_debt_ebit":     _safe_div(dl, ebt),
        "gross_debt_equity": _safe_div(db, pl),
    }
