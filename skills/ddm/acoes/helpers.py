"""skills/ddm/acoes/helpers.py - Pure-function helpers for the acoes skill.

Functions:
  - format_brl(v)        - format a BRL value (44.30 -> "R$ 44,30")
  - format_int(v)        - PT-BR thousands (52792400 -> "52.792.400")
  - format_pct(v)        - signed percentage (2.78 -> "+2,78%", -10.85 -> "-10,85%")
  - format_value(v, unit) - dispatch by unit
  - _format_mes_ano(ref_date) - "2026-07" -> "Jul/2026" for display
"""
from __future__ import annotations

_MESES = {
    "01": "Jan", "02": "Fev", "03": "Mar", "04": "Abr",
    "05": "Mai", "06": "Jun", "07": "Jul", "08": "Ago",
    "09": "Set", "10": "Out", "11": "Nov", "12": "Dez",
}


def format_brl(value, decimals: int = 2) -> str:
    """Format a BRL value: 44.30 -> "R$ 44,30".

    Returns "-" for None / unparseable values.
    """
    if value is None:
        return "-"
    try:
        formatted = f"{float(value):.{decimals}f}"
        return f"R$ {formatted.replace('.', ',')}"
    except (ValueError, TypeError):
        return str(value)


def format_int(value) -> str:
    """Format an integer with PT-BR thousands separators.

    52792400 -> "52.792.400" (dot as thousands separator).

    Returns "-" for None / unparseable values.
    """
    if value is None:
        return "-"
    try:
        n = int(value)
        # PT-BR uses '.' as the thousands separator.
        s = f"{n:,}".replace(",", ".")
        return s
    except (ValueError, TypeError):
        return str(value)


def format_pct(value, decimals: int = 2) -> str:
    """Format a percentage with explicit sign + PT-BR comma decimal.

    2.78  -> "+2,78%"
    -10.85 -> "-10,85%"
    0.00  -> "+0,00%"

    Returns "-" for None / unparseable values.
    """
    if value is None:
        return "-"
    try:
        formatted = f"{float(value):.{decimals}f}"
        sign = "+" if float(value) >= 0 else ""
        return f"{sign}{formatted.replace('.', ',')}%"
    except (ValueError, TypeError):
        return str(value)


def format_value(value, unit: str = "") -> str:
    """Dispatch by unit string."""
    if value is None:
        return "-"
    if unit == "brl":
        return format_brl(value)
    if unit == "int":
        return format_int(value)
    if unit == "pct":
        return format_pct(value)
    # Default: try to render as a string.
    return str(value)


def _format_mes_ano(ref_date: str) -> str:
    """Convert '2026-07' -> 'Jul/2026' for display."""
    if not ref_date or len(ref_date) != 7 or ref_date[4] != "-":
        return ref_date
    ano = ref_date[:4]
    mes = ref_date[5:7]
    return f"{_MESES.get(mes, mes)}/{ano}"
