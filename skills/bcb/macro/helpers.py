"""skills/bcb/macro/helpers.py - Pure-function helpers for the macro skill.

No I/O. All functions take already-fetched values (lists/dicts/floats) and
return formatted strings or derived numbers. This separation makes the logic
trivially testable without mocking the DB.

Functions:
  - format_value(value, unit)        - human-readable PT-BR string
  - format_date(iso)                 - "2024-01-03" -> "03/01/2024" (DD/MM/YYYY)
  - annualize_rate(daily_pct)        - daily % a.d. -> % a.a. (x 252)
  - compute_stats(values)            - min/max/mean/last for a numeric list
  - build_observation_table(observations) - rows for a report table section
  - accumulate_12m(monthly_values)   - rolling 12-month sum (for IPCA etc.)
  - group_by_month(observations)     - daily obs -> monthly last-value (for Selic table)

[v2] Added format_date() — converts ISO YYYY-MM-DD to PT-BR DD/MM/YYYY for
display. build_observation_rows() now returns date cells as dicts with
{text: DD/MM/YYYY, data-value: YYYY-MM-DD} so the sortTable JS can sort
chronologically by the ISO data-value (not lexicographically on DD/MM/YYYY).
[v1.7] Added group_by_month() — groups daily observations by YYYY-MM, keeping
the last value of each month. Used for the Juros tab Selic table (Selic
changes ~every 45 days, not daily — monthly view is more meaningful).
"""

from __future__ import annotations

import re
from statistics import mean


# Display format per unit. Mirrors the brapi/CVM PT-BR convention.
_UNIT_FORMAT = {
    "% a.d.": lambda v: f"{v:.6f}%" if v is not None else "-",
    "% a.a.": lambda v: f"{v:.2f}%" if v is not None else "-",
    "%":      lambda v: f"{v:.2f}%" if v is not None else "-",
    "R$":     lambda v: f"R$ {v:,.4f}".replace(",", "_").replace(".", ",").replace("_", ".") if v is not None else "-",
    "R$ mil": lambda v: f"R$ {v:,.0f} mil".replace(",", ".") if v is not None else "-",
}


def format_value(value, unit: str = "") -> str:
    """Format a numeric value for display given its BCB unit.

    Falls back to a plain str() for unknown units. Returns "-" for None.
    """
    if value is None:
        return "-"
    fmt = _UNIT_FORMAT.get(unit)
    if fmt is None:
        return str(value)
    try:
        return fmt(value)
    except (ValueError, TypeError):
        return str(value)


def format_date(iso: str) -> str:
    """Convert ISO YYYY-MM-DD to PT-BR display DD/MM/YYYY.

    "2024-01-03" -> "03/01/2024"
    "" -> "-"
    "03/01/2024" -> "03/01/2024"  (already PT-BR -> passthrough)
    "2024-01" -> "01/2024"  (monthly -> MM/YYYY)

    Returns "-" for empty / unparseable inputs.
    """
    if not iso:
        return "-"
    s = str(iso).strip()
    # Already PT-BR (DD/MM/YYYY)?
    if len(s) == 10 and s[2] == "/" and s[5] == "/":
        return s
    # ISO YYYY-MM-DD?
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})$", s)
    if m:
        y, mo, day = m.group(1), m.group(2), m.group(3)
        return f"{day}/{mo}/{y}"
    # Monthly YYYY-MM?
    m = re.match(r"^(\d{4})-(\d{2})$", s)
    if m:
        y, mo = m.group(1), m.group(2)
        return f"{mo}/{y}"
    return s


def annualize_rate(daily_pct: float | None) -> float | None:
    """Convert a daily percent rate (% a.d.) to annualized (% a.a.).

    BCB daily rates are base-252 annualized: multiply by 252 to get the
    annualized rate. Returns None if input is None.
    """
    if daily_pct is None:
        return None
    return daily_pct * 252.0


def compute_stats(values: list[float | None]) -> dict:
    """Compute min/max/mean/last for a list of numeric values.

    None values are filtered out before computation. Returns a dict with all
    fields set to None if the input is empty or all-None.
    """
    nums = [v for v in values if v is not None]
    if not nums:
        return {"min": None, "max": None, "mean": None,
                "last": None, "count": 0}
    return {
        "min":   min(nums),
        "max":   max(nums),
        "mean":  mean(nums),
        "last":  nums[-1],
        "count": len(nums),
    }


def build_observation_rows(observations: list[dict],
                           unit: str = "",
                           limit: int = 0) -> list[list]:
    """Reshape observation dicts into list-of-lists rows for a table section.

    Each input dict has {"ref_date", "value"}. Output rows are
    [date_cell, formatted_value_str] where date_cell is a dict with:
      - "text": DD/MM/YYYY (PT-BR display)
      - "data-value": YYYY-MM-DD (ISO date, for chronological sorting)

    The data-value attribute is critical — the sortTable JS sorts text cells
    by data-value when present, so dates sort chronologically even though
    they display as DD/MM/YYYY (which would sort lexicographically wrong).

    If limit > 0, only the last `limit` rows are returned (after sorting
    ascending by ref_date).
    """
    rows = sorted(observations, key=lambda o: o.get("ref_date", ""))
    if limit > 0:
        rows = rows[-limit:]
    result = []
    for o in rows:
        ref = o.get("ref_date", "")
        date_cell = {"text": format_date(ref)}
        if ref:
            date_cell["data-value"] = str(ref)
        result.append([date_cell, format_value(o.get("value"), unit)])
    return result


def group_by_month(observations: list[dict]) -> list[dict]:
    """Group daily observations by YYYY-MM, keeping the LAST value of each month.

    Used for the Juros tab Selic/CDI tables — Selic changes ~every 45 days,
    not daily, so a daily table is mostly redundant. Monthly view shows the
    rate at month-end, which is what matters for comparison.

    Input: list of {"ref_date": "YYYY-MM-DD", "value": float} dicts.
    Output: list of {"ref_date": "YYYY-MM", "value": float} dicts, sorted ASC.
    """
    by_month: dict[str, float] = {}
    for o in observations:
        ref = o.get("ref_date", "")
        if len(ref) < 7:
            continue
        month_key = ref[:7]  # YYYY-MM
        val = o.get("value")
        if val is not None:
            by_month[month_key] = val  # last value wins (observations are ASC)
    return [{"ref_date": k, "value": v} for k, v in sorted(by_month.items())]


def accumulate_12m(monthly_values: list[dict]) -> list[dict]:
    """Rolling 12-month sum over monthly values (e.g. for IPCA acumulado).

    Input: list of {"ref_date", "value"} sorted ascending by ref_date.
    Output: same length list with an extra "acum_12m" key per row. The first
    11 rows have acum_12m=None (not enough history). Row N has the sum of
    values[N-11..N].
    """
    out = []
    for i, row in enumerate(monthly_values):
        window = monthly_values[max(0, i - 11): i + 1]
        if len(window) < 12:
            acum = None
        else:
            nums = [w.get("value") for w in window if w.get("value") is not None]
            acum = sum(nums) if nums else None
        out.append({"ref_date": row.get("ref_date", ""),
                    "value": row.get("value"),
                    "acum_12m": acum})
    return out
