"""skills/ddm/focus/helpers.py - Helpers for the focus dashboard."""
from __future__ import annotations


def format_value(v) -> str:
    """Display value as-is (already formatted by source)."""
    if v is None:
        return "-"
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
    """Parse a PT-BR formatted value to a float (for Chart.js only).

    [v4] Fixed: currency values use comma as THOUSANDS separator,
    percentage values use comma as DECIMAL separator.

    Examples:
      - "5,151%"   → 5.151    (percentage: comma = decimal)
      - "14,000%"   → 14.0     (percentage: comma = decimal)
      - "R$ 5,200"  → 5200.0   (currency: comma = thousands, remove)
      - "R$ 5,278"  → 5278.0   (currency: comma = thousands, remove)
      - "US$ -60,000" → -60000.0 (currency: comma = thousands, remove)
      - "US$ 76,200"  → 76200.0  (currency: comma = thousands, remove)
      - "149"       → 149.0    (plain number)
    """
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    s = str(value).strip()
    if not s or s == "--" or s == "-":
        return None

    has_percent = "%" in s
    is_currency = "R$" in s or "US$" in s

    # Strip prefixes/suffixes
    s = s.replace("R$", "").replace("US$", "").replace("%", "").strip()
    if not s:
        return None

    if is_currency:
        # Currency: comma = thousands separator → remove it
        # Also remove dots (thousands) just in case
        s = s.replace(".", "").replace(",", "")
    elif has_percent:
        # Percentage: comma = decimal separator → replace with dot
        # Remove dots (thousands) just in case
        s = s.replace(".", "").replace(",", ".")
    else:
        # Plain number: try percentage convention first (comma = decimal)
        s = s.replace(".", "").replace(",", ".")

    try:
        return float(s)
    except (ValueError, TypeError):
        return None
