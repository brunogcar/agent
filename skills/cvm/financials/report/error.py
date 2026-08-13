"""skills/cvm/financials/report/error.py -- Error utilities + small helpers.

Hosts the ``build_error_section`` text builder used by the dashboard to
degrade gracefully when a sub-mode call fails, plus a few small utility
functions used across multiple submodules:

  - ``build_error_section(stage, error)`` — text section describing the
    failure for a single sub-mode call.
  - ``_safe_engine_call(fn, *args, **kwargs)`` — wrap a calculations
    engine call; returns its float result or None on failure (used by
    ``build_dfc_quality_section`` + ``build_dividend_sustainability_section``
    to gracefully degrade when DFC/DVA engines raise FileNotFoundError).
  - ``annual_metric(latest_annual_period, name)`` — read a metric value
    from a latest annual period dict.
  - ``annual_ratio(latest_annual_period, name)`` — read a ratio value from
    a latest annual period dict.
  - ``_metrics_from_period(p)`` — extract named metrics from a period dict,
    supporting BOTH the annual shape (``metrics`` field) AND the quarterly-
    statement shape (``accounts`` dict only).
"""
from __future__ import annotations

from skills.cvm.financials.report._helpers import _num_or_none


def annual_metric(latest_annual_period: dict | None, name: str) -> float | None:
    if not latest_annual_period:
        return None
    return (latest_annual_period.get("metrics") or {}).get(name)


def annual_ratio(latest_annual_period: dict | None, name: str) -> float | None:
    if not latest_annual_period:
        return None
    return (latest_annual_period.get("ratios") or {}).get(name)


def _metrics_from_period(p: dict) -> dict:
    """[v1.24] Extract named metrics from a period dict, supporting BOTH the
    annual shape (``metrics`` field pre-computed by annual/quarterly summary
    builders) AND the quarterly-statement shape (``accounts`` dict only — no
    pre-computed metrics, because ``_fetch_all_statements_quarterly`` returns
    raw accounts).

    Used by ``build_statement_trend_chart`` and ``build_dfc_trend_chart`` so
    they can consume either period type transparently.

    Codes extracted (matches ``_extract_metrics`` in fetchers.py):
      - receita_liquida  ← 3.01
      - ebit             ← 3.05
      - da               ← 6.01.01.02 (fallback 6.02.01.02 — direct method)
      - ebitda           ← ebit + da (ebit_only fallback when da missing)
      - lucro_liquido    ← 3.11
      - fco              ← 6.01
      - fci              ← 6.02
      - fcf              ← 6.03
    """
    m = p.get("metrics")
    if m is not None:
        return m
    accounts = p.get("accounts") or {}

    def _v(code: str) -> float | None:
        a = accounts.get(code)
        if a is None:
            return None
        return _num_or_none(a.get("valor_brl"))

    receita = _v("3.01")
    ebit = _v("3.05")
    da = _v("6.01.01.02")
    if da is None:
        da = _v("6.02.01.02")  # DFC_MD direct-method fallback
    ebitda: float | None = None
    if ebit is not None and da is not None:
        ebitda = ebit + da
    elif ebit is not None:
        ebitda = ebit  # ebit_only fallback

    return {
        "receita_liquida": receita,
        "ebit": ebit,
        "ebitda": ebitda,
        "lucro_liquido": _v("3.11"),
        "fco": _v("6.01"),
        "fci": _v("6.02"),
        "fcf": _v("6.03"),
    }


# ── Error-section helper (used by dashboard for failed sub-mode calls) ───────

def build_error_section(stage: str, error: str) -> dict:
    """Build a `type: "text"` section describing a failed sub-mode call."""
    return {
        "type": "text",
        "text": (
            f"{stage} indisponível para esta empresa. "
            f"Detalhe: {error}"
        ),
    }


# ── [new commit] F12: DFC quality analysis ───────────────────────────────────

def _safe_engine_call(fn, *args, **kwargs) -> float | None:
    """Call a calculations engine fn; return its float result or None on failure.

    Used by build_dfc_quality_section / build_dividend_sustainability_section
    to gracefully degrade when the DFC or DVA DB is missing — engine calls
    raise FileNotFoundError etc., which we swallow so a single missing
    statement doesn't crash the whole dashboard tab.
    """
    try:
        v = fn(*args, **kwargs)
    except Exception:
        return None
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None
