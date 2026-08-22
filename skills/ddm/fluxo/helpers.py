"""skills/ddm/fluxo/helpers.py - Pure-function helpers for the fluxo skill.

Fluxo values are stored in the DB as REAL (floats in millions of R$).
The helpers below format them back into PT-BR display strings:

  - format_brl(v)    - R$ 1.582,35 mi (PT-BR, with "mi" suffix for millions)
  - format_int(v)    - PT-BR thousands (52792400 -> "52.792.400")
  - format_pct(v)    - percentage
  - format_date(d)   - "2026-08-19" -> "19/08/2026" (PT-BR display)
  - format_value(v, unit) - dispatch on unit
"""
from __future__ import annotations

import re


def format_brl(value, unit: str = "mi") -> str:
    """Format a value as PT-BR with the "mi" (millions) suffix.

    -1582.35 -> "R$ -1.582,35 mi"  (negative, dot=thousands, comma=decimal)
     1029.81 -> "R$ 1.029,81 mi"
       42.36 -> "R$ 42,36 mi"
       None  -> "-"

    The "mi" suffix indicates the value is in millions of R$ (Brazilian
    Reais), which is how the /fluxo page renders values.
    """
    if value is None:
        return "-"
    try:
        n = float(value)
    except (ValueError, TypeError):
        return "-"
    # Format with PT-BR conventions: dot for thousands, comma for decimals.
    # Use 2 decimal places (the source page uses 2 decimals consistently).
    formatted = f"{n:,.2f}"
    # Python's f-string uses "," for thousands and "." for decimal - swap
    # to PT-BR (dot=thousands, comma=decimal).
    # Algorithm: temporarily swap "," -> "X" -> "." -> "X" -> ",".
    formatted = formatted.replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R$ {formatted} {unit}"


def format_int(value) -> str:
    """Format an integer with PT-BR thousands separators.

    52792400 -> "52.792.400" (dot as thousands separator).

    Returns "-" for None / unparseable values.
    """
    if value is None:
        return "-"
    try:
        n = int(value)
        s = f"{n:,}".replace(",", ".")
        return s
    except (ValueError, TypeError):
        return str(value)


def format_pct(value) -> str:
    """Format a value as a PT-BR percentage.

    5.151 -> "5,151%"
    -2.10 -> "-2,10%"

    Returns "-" for None / unparseable values.
    """
    if value is None:
        return "-"
    try:
        n = float(value)
        s = f"{n:,.3f}".replace(",", "X").replace(".", ",").replace("X", ".")
        return f"{s}%"
    except (ValueError, TypeError):
        return "-"


def format_date(d: str) -> str:
    """Convert YYYY-MM-DD to PT-BR display DD/MM/YYYY.

    "2026-08-19" -> "19/08/2026"
    "" -> "-"
    "19/08/2026" -> "19/08/2026"  (already PT-BR -> passthrough)

    Returns "-" for empty / unparseable inputs.
    """
    if not d:
        return "-"
    s = str(d).strip()
    # Already PT-BR (DD/MM/YYYY)?
    if len(s) == 10 and s[2] == "/" and s[5] == "/":
        return s
    # ISO YYYY-MM-DD?
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})$", s)
    if m:
        y, mo, day = m.group(1), m.group(2), m.group(3)
        return f"{day}/{mo}/{y}"
    return s


def format_value(value, unit: str = "mi") -> str:
    """Dispatch on unit to the right formatter.

    unit="mi" (default) -> format_brl (R$ X,XX mi)
    unit="%"             -> format_pct
    unit="int"           -> format_int

    Returns "-" for unknown units / None values.
    """
    if value is None:
        return "-"
    if unit == "%":
        return format_pct(value)
    if unit == "int":
        return format_int(value)
    # Default: treat as currency value in millions.
    return format_brl(value, unit=unit)
