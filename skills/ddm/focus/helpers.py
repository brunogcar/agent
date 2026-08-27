"""skills/ddm/focus/helpers.py - Helpers for the focus dashboard.

[v2] Updated for C2 schema migration (values now stored as REAL floats,
not PT-BR strings). format_value() now accepts an optional indicator name
to determine the display unit (%, R$, US$ mi) and formats floats back
to PT-BR display format.
"""
from __future__ import annotations


# [v2] Indicator → unit mapping. Used by format_value() to determine how
# to format the float for display. The Focus page has 3 unit types:
#   - "%"      — percentage indicators (IPCA, PIB, Selic, IGP-M, etc.)
#   - "R$"     — currency (Cambio = USD/BRL exchange rate)
#   - "US$ mi" — USD millions (Balança comercial, Investimento direto, Conta corrente)
_INDICATOR_UNITS: dict[str, str] = {
    # Percentage indicators
    "IPCA":               "%",
    "IPCA em 12 meses":   "%",
    "PIB Total":          "%",
    "PIB Agropecuária":   "%",
    "PIB Indústria":      "%",
    "PIB Serviços":       "%",
    "Selic":              "%",
    "IGP-M":              "%",
    "IGP-DI":             "%",
    "IPC-Fipe":           "%",
    "Taxa de desocupação": "%",
    # Currency (R$)
    "Câmbio":             "R$",
    "Cambio":             "R$",
    # USD millions
    "Balança comercial":  "US$ mi",
    "Balanca comercial":  "US$ mi",
    "Investimento direto": "US$ mi",
    "Conta corrente":     "US$ mi",
}

# Default unit if indicator is not in the mapping.
_DEFAULT_UNIT = ""


def _get_unit(indicator: str = "") -> str:
    """Get the display unit for an indicator name (case-insensitive)."""
    if not indicator:
        return _DEFAULT_UNIT
    # Try exact match first, then case-insensitive.
    if indicator in _INDICATOR_UNITS:
        return _INDICATOR_UNITS[indicator]
    for key, unit in _INDICATOR_UNITS.items():
        if key.lower() == indicator.lower():
            return unit
    return _DEFAULT_UNIT


def _format_float_ptbr(v: float, decimals: int = 2) -> str:
    """Format a float with PT-BR conventions (dot=thousands, comma=decimal).

    5.151     -> "5,151"     (4 decimals for percentages)
    5.2       -> "5,20"      (2 decimals for currency)
    76200.0   -> "76.200"    (0 decimals for large US$ millions)
    -60000.0  -> "-60.000"
    """
    negative = v < 0
    abs_val = abs(v)

    # Format with the specified decimals.
    s = f"{abs_val:.{decimals}f}"
    # Python uses "." for decimal — swap to PT-BR (comma=decimal, dot=thousands).
    # Algorithm: split on ".", swap separators.
    if "." in s:
        int_part, dec_part = s.split(".")
    else:
        int_part, dec_part = s, ""
    # Add thousands separators (dot) to the integer part.
    int_part_with_sep = f"{int(int_part):,}".replace(",", ".")
    # Reassemble.
    if dec_part:
        result = f"{int_part_with_sep},{dec_part}"
    else:
        result = int_part_with_sep
    return f"-{result}" if negative else result


def format_value(v, indicator: str = "") -> str:
    """Format a value for display.

    [v2] Now handles floats (C2 schema migration). Uses the indicator name
    to determine the display unit:
      - "%"      → "5,151%" (percentage, 4 decimals)
      - "R$"     → "R$ 5,20" (currency, 2 decimals)
      - "US$ mi" → "US$ 76.200 mi" (USD millions, 0 decimals)
      - ""       → plain number

    For backwards compatibility, still handles PT-BR strings (passes through).
    """
    if v is None:
        return "-"
    # If it's already a string (old DB or passthrough), preserve old behavior.
    if isinstance(v, str):
        s = v
        # US$ values: append " mi" if not already present.
        if "US$" in s and " mi" not in s and " bi" not in s:
            s = s.rstrip() + " mi"
        return s
    # Float (new C2 schema) — format with PT-BR conventions.
    if isinstance(v, (int, float)):
        unit = _get_unit(indicator)
        if unit == "%":
            # Percentages: 4 decimals (5,151% not 5,15%)
            return _format_float_ptbr(float(v), decimals=4) + "%"
        elif unit == "R$":
            # Currency: 2 decimals
            return f"R$ {_format_float_ptbr(float(v), decimals=2)}"
        elif unit == "US$ mi":
            # USD millions: 0 decimals (76.200 mi, not 76.200,00 mi)
            return f"US$ {_format_float_ptbr(float(v), decimals=0)} mi"
        else:
            # Unknown unit — plain number with 2 decimals.
            return _format_float_ptbr(float(v), decimals=2)
    return str(v)


def format_int(v) -> str:
    """Format integer with PT-BR thousands separators."""
    if v is None:
        return "-"
    try:
        return f"{int(v):,}".replace(",", ".")
    except (ValueError, TypeError):
        return str(v)


def comparison_symbol(comp: str) -> str:
    """Convert comparison enum to display symbol."""
    if comp == "up":
        return "▲"
    if comp == "down":
        return "▼"
    return "="


def comparison_color(comp: str) -> str:
    """Convert comparison enum to color."""
    if comp == "up":
        return "#22c55e"
    if comp == "down":
        return "#ef4444"
    return "#9ca3af"


def parse_numeric(value) -> float | None:
    """Parse a value to a float (for Chart.js).

    [v2] Now handles floats directly (C2 schema migration). For backwards
    compatibility, still parses PT-BR strings.
    """
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    s = str(value).strip()
    if not s or s in ("--", "-"):
        return None
    # Strip % suffix -- focus wants the raw number, not the decimal form.
    if "%" in s:
        s = s.replace("%", "").strip()
    # US$ values use US-style formatting (comma = thousands).
    if "US$" in s:
        s = s.replace("US$", "").strip()
        s = s.replace(",", "")
        try:
            return float(s) if s else None
        except (ValueError, TypeError):
            return None
    # R$ / plain PT-BR values: delegate to the shared parser.
    from data_sources.ddm._parsers import parse_br_number
    return parse_br_number(s)
