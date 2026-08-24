"""skills/ddm/focus/helpers.py - Helpers for the focus dashboard."""
from __future__ import annotations


def format_value(v) -> str:
    """Display value as-is (already formatted by source).

    [v5.1 fix] DDM Focus reports USD values in millions of USD (e.g.
    "US$ 77,200" = $77.2 billion). Without a unit suffix, "US$ 77,200"
    looks like $77 thousand. Append " mi" to US$ values for context.
    R$ values are already in millions (the DDM convention) and don't
    need a suffix (the "mi" is implied by the R$ context).
    """
    if v is None:
        return "-"
    s = str(v)
    # US$ values: append " mi" (millions of USD) for context.
    # DDM Focus reports: Investimento direto, Balança comercial,
    # Conta corrente — all in USD millions.
    if s.startswith("US$") or "US$" in s:
        if " mi" not in s and " bi" not in s:
            s = s.rstrip() + " mi"
    return s


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
    """Parse a PT-BR formatted value to a float (for Chart.js only).

    [v5 fix B19] Replaced the custom currency/percent parser with the
    shared data_sources.ddm._parsers.parse_br_number. The old parser
    had a bug: for "R$ 1.234,56" it stripped both separators -> 123456.0
    (should be 1234.56). The shared parser delegates to
    core.br_validator.parse_brl which handles R$ prefix + PT-BR
    thousands (.) and decimal (,) correctly.

    For percentage strings ("5,151%"), strips the % before calling
    parse_br_number (focus wants 5.151, not 0.05151 -- parse_brl would
    divide by 100).

    For US$ prefix strings ("US$ -60,000"), the focus page uses US-style
    formatting (comma = thousands, dot = decimal) -- NOT PT-BR. We strip
    the US$ prefix and the commas, then parse as a regular float.
    (parse_brl would misinterpret "76,200" as 76.2 via PT-BR decimal
    comma, but for US$ the value is 76200 million USD -- trade balance.)

    Examples:
      - "5,151%"      -> 5.151
      - "R$ 1.234,56" -> 1234.56  (was 123456.0 before fix)
      - "R$ 5,200"    -> 5.2       (cambio: 5.2 R$/USD)
      - "US$ -60,000" -> -60000.0  (US-style: comma = thousands)
      - "US$ 76,200"  -> 76200.0
      - "149"         -> 149.0
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
    # Strip prefix + commas, then parse as float (handles negative sign).
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
