"""skills/ddm/acoes/helpers.py - Pure-function helpers for the acoes skill.

Functions:
  - format_brl(v)        - format a BRL value (44.30 -> "R$ 44,30")
  - format_int(v)        - PT-BR thousands (52792400 -> "52.792.400")
  - format_pct(v)        - signed percentage (2.78 -> "+2,78%", -10.85 -> "-10,85%")
  - format_value(v, unit) - dispatch by unit
  - _format_mes_ano(ref_date) - "2026-07" -> "Jul/2026" for display
  - _format_data(ref_date)   - "2026-07-15" -> "15/07/2026" for display
  - distribution_snapshots(dates, prices_by_date) - [v2] bucket every
    snapshot's prices into the shared 22-range palette (counts + shares
    that sum to EXACTLY 100 per date) — the numerics behind the
    distribution-over-time charts. Used by BOTH the skill's static
    dashboard and the WebUI Ações family (no forked bucketing).
"""
from __future__ import annotations

_MESES = {
    "01": "Jan", "02": "Fev", "03": "Mar", "04": "Abr",
    "05": "Mai", "06": "Jun", "07": "Jul", "08": "Ago",
    "09": "Set", "10": "Out", "11": "Nov", "12": "Dez",
}


def format_brl(value, decimals: int = 2) -> str:
    """Format a BRL value: 44.30 -> "R$ 44,30".

    Returns "-" for None / unparseable values.
    """
    if value is None:
        return "-"
    try:
        formatted = f"{float(value):.{decimals}f}"
        return f"R$ {formatted.replace('.', ',')}"
    except (ValueError, TypeError):
        return str(value)


def format_int(value) -> str:
    """Format an integer with PT-BR thousands separators.

    52792400 -> "52.792.400" (dot as thousands separator).

    Returns "-" for None / unparseable values.
    """
    if value is None:
        return "-"
    try:
        n = int(value)
        # PT-BR uses '.' as the thousands separator.
        s = f"{n:,}".replace(",", ".")
        return s
    except (ValueError, TypeError):
        return str(value)


def format_pct(value, decimals: int = 2) -> str:
    """Format a percentage with explicit sign + PT-BR comma decimal.

    2.78  -> "+2,78%"
    -10.85 -> "-10,85%"
    0.00  -> "+0,00%"

    Returns "-" for None / unparseable values.
    """
    if value is None:
        return "-"
    try:
        formatted = f"{float(value):.{decimals}f}"
        sign = "+" if float(value) >= 0 else ""
        return f"{sign}{formatted.replace('.', ',')}%"
    except (ValueError, TypeError):
        return str(value)


def format_value(value, unit: str = "") -> str:
    """Dispatch by unit string."""
    if value is None:
        return "-"
    if unit == "brl":
        return format_brl(value)
    if unit == "int":
        return format_int(value)
    if unit == "pct":
        return format_pct(value)
    # Default: try to render as a string.
    return str(value)


def _format_mes_ano(ref_date: str) -> str:
    """Convert '2026-07' -> 'Jul/2026' for display."""
    if not ref_date or len(ref_date) != 7 or ref_date[4] != "-":
        return ref_date
    ano = ref_date[:4]
    mes = ref_date[5:7]
    return f"{_MESES.get(mes, mes)}/{ano}"


def _format_data(ref_date: str) -> str:
    """Convert '2026-07-15' -> '15/07/2026' for display (PT-BR date)."""
    if not ref_date or len(ref_date) != 10 or ref_date[4] != "-":
        return ref_date
    return f"{ref_date[8:10]}/{ref_date[5:7]}/{ref_date[:4]}"


def distribution_snapshots(dates: list[str],
                           prices_by_date: list[list]) -> dict:
    """[v2] Bucket every stored snapshot's prices into the 22-range palette.

    The single bucketing behind the distribution-over-time charts — used
    by the skill's static dashboard AND the WebUI Ações family (the
    ``skills._colors.price`` palette is the same one the current-snapshot
    bar chart colors by, so the evolution reads with the same key).

    Args:
        dates:          snapshot dates, ASC ('2026-06-01', ...).
        prices_by_date: per-date list of last_price floats (aligned with
                        dates; None entries are skipped by the palette).

    Returns:
        {"ranges":  [{"label": "2 \u2264 X < 5", "color": "#f8bbd0",
                      "text_color": "#000"}, ... x22],   # lowest first
         "counts":  [[n_per_range], ... per date],        # raw counts
         "shares":  [[pct_per_range], ... per date],      # sums EXACTLY
                                                              100.00
         "totals":  [n_priced_stocks, ... per date]}
    The exact-100 normalization puts the rounding drift (sum of roundings)
    on the LARGEST share of each date, so a stacked 100% area chart never
    overflows the 100 line because of float dust.
    """
    # Lazy import (keeps the module importable in standalone mode).
    from skills._colors.price import _RANGES, price_distribution

    counts: list[list[int]] = []
    totals: list[int] = []
    for prices in prices_by_date:
        buckets = price_distribution(prices or [])
        counts.append([b["count"] for b in buckets])
        totals.append(sum(b["count"] for b in buckets))

    shares: list[list[float]] = []
    for row, total in zip(counts, totals):
        if total > 0:
            row_shares = [round(100.0 * c / total, 2) for c in row]
            # Absorb the rounding drift into the largest band.
            drift = round(100.0 - sum(row_shares), 2)
            if drift:
                big = max(range(len(row_shares)),
                          key=lambda i: row_shares[i])
                row_shares[big] = round(row_shares[big] + drift, 2)
        else:
            row_shares = [0.0] * len(row)
        shares.append(row_shares)

    return {
        "ranges": [
            {"label": label, "color": bg, "text_color": color}
            for (_, _, bg, color, label) in _RANGES
        ],
        "counts": counts,
        "shares": shares,
        "totals": totals,
    }
