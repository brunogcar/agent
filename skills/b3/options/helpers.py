"""skills/b3/options/helpers.py - Pure-function helpers for the options skill.

No I/O. All functions take already-fetched values (lists/dicts/floats) and
return formatted strings. This separation makes the logic trivially
testable without mocking the DB.

Functions:
  - format_value(value, unit)  — human-readable PT-BR string
  - format_brl(v)              — format as R$ X.XXX,XX (PT-BR convention)
  - format_int(v)               — format with thousands separator (PT-BR)
"""
from __future__ import annotations


def format_brl(v) -> str:
    """Format a value as Brazilian Reais: R$ 1.234,56.

    PT-BR convention: dot for thousands, comma for decimals. Returns "-"
    for None / non-numeric input.
    """
    if v is None:
        return "-"
    try:
        # Use _ as a temp placeholder so the comma/dot swap doesn't collide.
        return f"R$ {float(v):,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")
    except (ValueError, TypeError):
        return str(v)


def format_int(v) -> str:
    """Format an integer with PT-BR thousands separators: 1.234.567.

    Returns "-" for None / non-numeric input.
    """
    if v is None:
        return "-"
    try:
        return f"{int(v):,}".replace(",", ".")
    except (ValueError, TypeError):
        return str(v)


# Display format per unit. Mirrors the bcb/macro PT-BR convention + adds a
# "ratio" unit for the Put/Call ratio (4 decimal places, comma decimal).
_UNIT_FORMAT = {
    "% a.d.": lambda v: f"{v:.6f}%" if v is not None else "-",
    "% a.a.": lambda v: f"{v:.2f}%" if v is not None else "-",
    "%":      lambda v: f"{v:.2f}%" if v is not None else "-",
    "R$":     lambda v: format_brl(v),
    "R$ mil": lambda v: f"R$ {v:,.0f} mil".replace(",", ".") if v is not None else "-",
    "ratio":  lambda v: f"{v:.4f}".replace(".", ",") if v is not None else "-",
}


def format_value(value, unit: str = "") -> str:
    """Format a numeric value for display given its unit.

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
