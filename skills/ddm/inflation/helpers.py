"""skills/ddm/inflation/helpers.py - Pure-function helpers for the inflation skill.

[v2] Changes:
  - build_observation_rows: DESC sort (newest first) per user request.
  - _format_mes_ano: converts "2026-07" → "Jul/2026" for display.
  - _heat_color: diverging red→white→green for monthly, white→blue for annual.

Functions:
  - format_value, format_pct, compute_stats, build_observation_rows
  - _format_mes_ano(ref_date)  - "2026-07" → "Jul/2026"
  - _heat_color(value, vmin, vmax, scheme) - heatmap cell color
"""
from __future__ import annotations
from statistics import mean

_MESES = {
    "01": "Jan", "02": "Fev", "03": "Mar", "04": "Abr",
    "05": "Mai", "06": "Jun", "07": "Jul", "08": "Ago",
    "09": "Set", "10": "Out", "11": "Nov", "12": "Dez",
}

_UNIT_FORMAT = {
    "%":  lambda v: format_pct(v, 2),
    "% a.m.": lambda v: format_pct(v, 2),
    "% a.a.": lambda v: format_pct(v, 2),
}


def format_pct(value, decimals: int = 2) -> str:
    if value is None:
        return "-"
    try:
        formatted = f"{value:.{decimals}f}"
        return f"{formatted.replace('.', ',')}%"
    except (ValueError, TypeError):
        return str(value)


def format_value(value, unit: str = "") -> str:
    if value is None:
        return "-"
    fmt = _UNIT_FORMAT.get(unit)
    if fmt is None:
        return format_pct(value, 2)
    try:
        return fmt(value)
    except (ValueError, TypeError):
        return str(value)


def compute_stats(values: list[float | None]) -> dict:
    nums = [v for v in values if v is not None]
    if not nums:
        return {"min": None, "max": None, "mean": None, "last": None, "count": 0}
    return {"min": min(nums), "max": max(nums), "mean": mean(nums),
            "last": nums[-1], "count": len(nums)}


def _format_mes_ano(ref_date: str) -> str:
    """Convert '2026-07' → 'Jul/2026' for display."""
    if not ref_date or len(ref_date) != 7 or ref_date[4] != "-":
        return ref_date
    ano = ref_date[:4]
    mes = ref_date[5:7]
    return f"{_MESES.get(mes, mes)}/{ano}"


def _heat_color(value, vmin: float, vmax: float, scheme: str = "diverging") -> dict:
    """Compute heatmap cell color.

    scheme="diverging": red (low/negative) → white (zero) → green (high/positive)
    scheme="sequential": white (low) → dark blue (high)
    """
    if value is None:
        return {"text": "-", "bg": "", "color": ""}

    text = f"{value:.2f}".replace(".", ",")

    if vmax == vmin:
        t = 0.5
    else:
        t = (value - vmin) / (vmax - vmin)
        t = max(0.0, min(1.0, t))

    if scheme == "diverging":
        if vmin < 0 and vmax > 0:
            zero_t = -vmin / (vmax - vmin)
        else:
            zero_t = 0.5

        if t < zero_t:
            ratio = t / zero_t if zero_t > 0 else 1.0
            r = int(239 + (255 - 239) * ratio)
            g = int(68 + (255 - 68) * ratio)
            b = int(68 + (255 - 68) * ratio)
        else:
            ratio = (t - zero_t) / (1 - zero_t) if zero_t < 1 else 1.0
            r = int(255 + (34 - 255) * ratio)
            g = int(255 + (197 - 255) * ratio)
            b = int(255 + (94 - 255) * ratio)

        bg = f"#{r:02x}{g:02x}{b:02x}"
        brightness = (r + g + b) / 3
        color = "#000" if brightness > 140 else "#fff"
    else:
        # Sequential: white → dark blue (#1e40af)
        r = int(255 + (30 - 255) * t)
        g = int(255 + (64 - 255) * t)
        b = int(255 + (175 - 255) * t)
        bg = f"#{r:02x}{g:02x}{b:02x}"
        brightness = (r + g + b) / 3
        color = "#000" if brightness > 140 else "#fff"

    return {"text": text, "bg": bg, "color": color}


def build_observation_rows(observations: list[dict], limit: int = 0) -> list[list]:
    """Reshape observation dicts into table rows.

    [v2] DESC sort (newest first). Date display uses _format_mes_ano.
    """
    rows = sorted(observations, key=lambda o: o.get("ref_date", ""), reverse=True)
    if limit > 0:
        rows = rows[:limit]
    out = []
    for o in rows:
        out.append([
            _format_mes_ano(o.get("ref_date", "")),
            format_pct(o.get("month_value")),
            format_pct(o.get("year_acumulado")),
            format_pct(o.get("acumulado_12m")),
        ])
    return out
