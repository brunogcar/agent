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
"""
from __future__ import annotations


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
