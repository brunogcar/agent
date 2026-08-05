"""skills/bcb/macro/helpers.py - Pure-function helpers for the macro skill.

No I/O. All functions take already-fetched values (lists/dicts/floats) and
return formatted strings or derived numbers. This separation makes the logic
trivially testable without mocking the DB.

Functions:
  - format_value(value, unit)        - human-readable PT-BR string
  - annualize_rate(daily_pct)        - daily % a.d. -> % a.a. (x 252)
  - compute_stats(values)            - min/max/mean/last for a numeric list
  - build_observation_table(observations) - rows for a report table section
  - accumulate_12m(monthly_values)   - rolling 12-month sum (for IPCA etc.)
"""

from __future__ import annotations

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
    [ref_date_str, formatted_value_str] (list of lists, NOT list of dicts)
    so the dashboard template's data_table macro can iterate cells directly.

    If limit > 0, only the last `limit` rows are returned (after sorting
    ascending by ref_date).
    """
    rows = sorted(observations, key=lambda o: o.get("ref_date", ""))
    if limit > 0:
        rows = rows[-limit:]
    return [[o.get("ref_date", ""), format_value(o.get("value"), unit)]
            for o in rows]


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
