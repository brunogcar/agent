"""skills/ddm/fluxo/helpers.py - Pure-function helpers for the fluxo skill.

Fluxo values are stored in the DB as REAL (floats in millions of R$).
The helpers below format them back into PT-BR display strings:

  - format_brl(v)            - R$ 1.582,35 mi (PT-BR, with "mi" suffix for millions)
  - format_brl_from_millions(v) - R$ 1,58 bi (auto-scale: bi/mi/tri, PT-BR suffixes)
  - format_int(v)            - PT-BR thousands (52792400 -> "52.792.400")
  - format_pct(v)            - percentage
  - format_date(d)           - "2026-08-19" -> "19/08/2026" (PT-BR display)
  - format_value(v, unit)    - dispatch on unit

[v2] Added format_brl_from_millions() — wraps core.br_validator.format_brl()
with a millions→units conversion (×1_000_000) + EN→PT-BR suffix mapping
(B→bi, M→mi, T→tri). This is the auto-scaling formatter used by KPI cards:
large values (≥1B reais) show as "R$ X,XX bi", smaller ones stay as
"R$ X,XX mi". The existing format_brl() is kept for table cells (which
intentionally show full precision in millions for row-by-row comparison).
"""
from __future__ import annotations

import re

# [v2] Imported lazily inside format_brl_from_millions to avoid a hard
# import-time dependency on core.br_validator (which is always present
# but keeps the helper module self-contained for unit testing).
def _br_validator_format_brl(value, suffix=True):
    from core.br_validator import format_brl as _fmt
    return _fmt(value, suffix=suffix)


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


def format_brl_from_millions(value) -> str:
    """Format a value (in MILLIONS of R$) with auto-scale bi/mi/tri.

    Wraps core.br_validator.format_brl() with a millions→units conversion
    (×1_000_000) and maps the English suffixes to PT-BR:
      B → bi  (bilhões)
      M → mi  (milhões)
      T → tri (trilhões)

    Examples (value is in millions):
      20017.83  -> "R$ 20,02 bi"   (20_017.83M = 20.02B reais)
      6310.97   -> "R$ 6,31 bi"    (6_310.97M = 6.31B reais)
      44.94     -> "R$ 44,94 mi"   (44.94M = 44.94M reais — under 1B, stays mi)
      -39972.79 -> "R$ -39,97 bi"  (negative, auto-scale)
      None      -> "-"

    This is the formatter used by KPI cards where large totals need to
    be readable at a glance. Table cells keep format_brl() (full precision
    in millions) for row-by-row comparison.
    """
    if value is None:
        return "-"
    try:
        n = float(value)
    except (ValueError, TypeError):
        return "-"
    # Convert millions → units (reais), then delegate to br_validator.
    units = n * 1_000_000
    s = _br_validator_format_brl(units, suffix=True)
    # [v2.1] br_validator puts the negative sign BEFORE "R$" ("-R$ 3,86 B"),
    # but the existing format_brl convention puts it AFTER ("R$ -3,86 mi").
    # Move the leading "-" to after "R$ " for consistency.
    if s.startswith("-R$ "):
        s = "R$ -" + s[4:]
    # Map EN suffixes → PT-BR. br_validator outputs "R$ X,XX B" / " M" / " T".
    # Replace only the trailing suffix (space + letter at end), not any
    # "B"/"M"/"T" that might appear in the number itself (unlikely with
    # PT-BR formatting, but be safe).
    if s.endswith(" T"):
        s = s[:-2] + " tri"
    elif s.endswith(" B"):
        s = s[:-2] + " bi"
    elif s.endswith(" M"):
        s = s[:-2] + " mi"
    return s


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
