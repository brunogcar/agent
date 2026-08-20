"""skills/ddm/juros/helpers.py - Pure-function helpers for the juros skill.

[v4] Fixed _heat_color to return a dict {text, bg, color} (was returning just
a string color hash). The heatmap_table macro expects dicts.
"""
from __future__ import annotations
from statistics import mean

_UNIT_FORMAT = {
    "%":     lambda v: format_pct(v, 2),
    "% a.m.": lambda v: format_pct(v, 2),
    "% a.a.": lambda v: format_pct(v, 2),
}

_MONTHS_PT = [
    "Jan", "Fev", "Mar", "Abr", "Mai", "Jun",
    "Jul", "Ago", "Set", "Out", "Nov", "Dez",
]


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
    """Format '2026-07' → 'Jul/2026'."""
    if not ref_date or "-" not in ref_date:
        return ref_date or ""
    try:
        year_str, mon_str = ref_date.split("-", 1)
        idx = int(mon_str) - 1
        if 0 <= idx < 12:
            return f"{_MONTHS_PT[idx]}/{year_str}"
    except (ValueError, IndexError):
        pass
    return ref_date


def _heat_color(value, vmin: float, vmax: float) -> dict:
    """[v4] Compute heatmap cell color + text as a dict.

    Returns: {"text": "13,65", "bg": "#eff7ef", "color": "#000"} or
             {"text": "-", "bg": "", "color": ""} for None.
    """
    if value is None:
        return {"text": "-", "bg": "", "color": ""}

    try:
        v = float(value)
    except (ValueError, TypeError):
        return {"text": "-", "bg": "", "color": ""}

    # Format the text as PT-BR number (no % sign — the matrix shows raw rates)
    text = f"{v:.2f}".replace(".", ",")

    lo = float(vmin) if vmin is not None else 0.0
    hi = float(vmax) if vmax is not None else 0.0
    if hi == lo:
        return {"text": text, "bg": "#ffffff", "color": "#000"}

    # Decide midpoint. Default: 0 if it's within [lo, hi], else (lo+hi)/2.
    mid = 0.0 if lo <= 0.0 <= hi else (lo + hi) / 2.0

    # Normalize to 0..1
    t = max(0.0, min(1.0, (v - lo) / (hi - lo)))
    mid_t = (mid - lo) / (hi - lo) if hi != lo else 0.5

    if t <= mid_t:
        # Red→white. t=0 at lo (full red), t=mid_t at mid (white).
        ratio = t / mid_t if mid_t > 0 else 1.0
        r = int(220 + (255 - 220) * ratio)
        g = int(38 + (255 - 38) * ratio)
        b = int(38 + (255 - 38) * ratio)
    else:
        # White→green. t=mid_t at mid (white), t=1 at hi (full green).
        ratio = (t - mid_t) / (1 - mid_t) if mid_t < 1 else 1.0
        r = int(255 + (22 - 255) * ratio)
        g = int(255 + (163 - 255) * ratio)
        b = int(255 + (74 - 255) * ratio)

    bg = f"#{r:02x}{g:02x}{b:02x}"
    brightness = (r + g + b) / 3
    color = "#000" if brightness > 140 else "#fff"

    return {"text": text, "bg": bg, "color": color}


def build_observation_rows(observations: list[dict], limit: int = 0) -> list[list]:
    """Reshape observation dicts into table rows. DESC (newest first)."""
    rows = sorted(observations, key=lambda o: o.get("ref_date", ""), reverse=True)
    if limit > 0:
        rows = rows[:limit]
    out = []
    for o in rows:
        out.append([
            _format_mes_ano(o.get("ref_date", "")),
            format_pct(o.get("month_value")),
            format_pct(o.get("media_no_ano")),
            format_pct(o.get("media_12m")),
        ])
    return out
