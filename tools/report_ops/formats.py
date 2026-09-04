"""report_ops/formats.py — Number formatting for reports (BRL, %, compact).

Shared between two consumers:
  1. Jinja2 filters registered in html.py (for HTML templates)
  2. The xlsx exporter in export.py (native Excel number formats)

DESIGN
------
Format *specs* are short string tags so a table column can declare its format
once ("brl", "pct", "num", ...) and both the HTML template (via the `fmt`
Jinja filter) and the xlsx exporter (via `excel_format()`) honour it
consistently. This keeps the report tool domain-agnostic: skills/adapters
only emit spec tags, never pre-formatted strings.

Spec vocabulary
---------------
  "brl"       Compact BRL with B/T/M suffixes        R$ 1,23 B
  "brl_full"  Full BRL with thousands separators     R$ 1.234.567,89
  "pct"       Fraction -> percentage                 0.1234 -> 12,34%
  "pct_raw"   Already-percent -> percentage          45.23  -> 45,23%
  "num"       Number with 2 decimals + thousands     1.234,56
  "int"       Integer with thousands                 1.234
  "compact"   Compact magnitude (no R$)              1,23 B
  "text"      Pass-through (default)                 as-is

None / NaN values always render as an em dash ("—") in HTML and as an empty
cell in xlsx — never as the string "None".

Reuses core.br_validator.format_brl for the BRL path so formatting stays
consistent with the rest of the BR financial stack.
"""
from __future__ import annotations

from typing import Any, Optional

# Sentinel rendered for missing values in HTML. xlsx uses empty cells instead.
_DASH = "—"

# Excel number-format strings per spec (applied to native numeric cells).
_EXCEL_FMT: dict[str, str] = {
    "brl":       '"R$ "#,##0.00',
    "brl_full":  '"R$ "#,##0.00',
    "pct":       "0.00%",
    "pct_raw":   '0.00"%"',
    "num":       "#,##0.00",
    "int":       "#,##0",
    "compact":   "#,##0.00",
    "text":      "@",
}


def _is_missing(v: Any) -> bool:
    """True for None / NaN / empty string — values that should render as dash."""
    if v is None:
        return True
    if isinstance(v, float):
        # NaN check (NaN != NaN)
        return v != v
    if isinstance(v, str):
        return v.strip() == ""
    return False


def fmt_brl(value: Any, suffix: bool = True) -> str:
    """Format a value as BRL. None/NaN -> dash.

    suffix=True  -> R$ 1,23 bi   (compact, PT-BR suffixes: bi/mi/tri)
    suffix=False -> R$ 1.234.567,89 (full)
    """
    if _is_missing(value):
        return _DASH
    try:
        from core.br_validator import format_brl
        s = format_brl(float(value), suffix=suffix)
        if suffix:
            if s.startswith("-R$ "):
                s = "R$ -" + s[4:]
            if s.endswith(" T"):
                s = s[:-2] + " tri"
            elif s.endswith(" B"):
                s = s[:-2] + " bi"
            elif s.endswith(" M"):
                s = s[:-2] + " mi"
            elif s.endswith(" K"):  # [v2.5 fix B37] K (thousand) → mil
                s = s[:-2] + " mil"
        return s
    except (TypeError, ValueError):
        return _DASH


def fmt_pct(value: Any, already_percent: bool = False) -> str:
    """Format a value as a percentage (pt-BR: 12,34%).

    already_percent=False (default): value is a fraction (0.1234 -> 12,34%).
        Used for ratios computed as a/b (margins, ROE, yield).
    already_percent=True: value is already a percent number (45.23 -> 45,23%).
        Used for FRE ownership percentages which CVM stores as plain numbers.
    """
    if _is_missing(value):
        return _DASH
    try:
        v = float(value)
    except (TypeError, ValueError):
        return _DASH
    if not already_percent:
        v = v * 100.0
    s = f"{v:.2f}".replace(".", ",")
    return f"{s}%"


def fmt_num(value: Any, decimals: int = 2) -> str:
    """Format a number with BR thousands separators. None/NaN -> dash."""
    if _is_missing(value):
        return _DASH
    try:
        v = float(value)
    except (TypeError, ValueError):
        return _DASH
    s = f"{v:,.{decimals}f}"
    # Swap US separators -> BR (., -> ,.)
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


def fmt_int(value: Any) -> str:
    """Format an integer with BR thousands separators. None/NaN -> dash."""
    return fmt_num(value, decimals=0)


def fmt_compact(value: Any) -> str:
    """Compact magnitude without currency: 1,23 T / 1,23 B / 3,45 M / 567 K. None -> dash.

    Mirrors the tier thresholds of core.br_validator.format_brl (T/B/M) so the
    `brl` and `compact` specs stay in lockstep.
    """
    if _is_missing(value):
        return _DASH
    try:
        v = float(value)
    except (TypeError, ValueError):
        return _DASH
    negative = v < 0
    a = abs(v)
    if a >= 1_000_000_000_000:
        s = f"{a / 1_000_000_000_000:.2f}".replace(".", ",")
        out = f"{s} T"
    elif a >= 1_000_000_000:
        s = f"{a / 1_000_000_000:.2f}".replace(".", ",")
        out = f"{s} B"
    elif a >= 1_000_000:
        s = f"{a / 1_000_000:.2f}".replace(".", ",")
        out = f"{s} M"
    elif a >= 1_000:
        s = f"{a / 1_000:.0f}".replace(".", ",")
        out = f"{s} K"
    else:
        s = f"{a:.2f}".replace(".", ",")
        out = s
    return f"-{out}" if negative else out


def fmt_dash(value: Any, default: str = _DASH) -> str:
    """Render missing values as a dash; pass through everything else as string."""
    if _is_missing(value):
        return default
    return str(value)


def apply_fmt(value: Any, spec: Optional[str]) -> str:
    """Dispatch a value through the formatter named by `spec`.

    This is the single entry point used by the `fmt` Jinja filter and by
    callers that want the HTML string for a given spec. Unknown specs fall
    back to text pass-through (safer than raising in a template render).
    """
    spec = (spec or "text").strip()
    if spec in ("brl",):
        return fmt_brl(value, suffix=True)
    if spec == "brl_full":
        return fmt_brl(value, suffix=False)
    if spec == "pct":
        return fmt_pct(value, already_percent=False)
    if spec == "pct_raw":
        return fmt_pct(value, already_percent=True)
    if spec == "num":
        return fmt_num(value, decimals=2)
    if spec == "int":
        return fmt_int(value)
    if spec == "compact":
        return fmt_compact(value)
    # "text" or unknown
    return fmt_dash(value)


def excel_format(spec: Optional[str]) -> str:
    """Return the Excel number-format string for a spec (for openpyxl).

    Unknown specs return "@" (text). Used by the xlsx exporter so numeric
    cells keep native values (sortable, summable) with a display format.
    """
    spec = (spec or "text").strip()
    return _EXCEL_FMT.get(spec, "@")


def is_numeric_spec(spec: Optional[str]) -> bool:
    """True if a spec produces a numeric Excel cell (vs text)."""
    return (spec or "text").strip() in {
        "brl", "brl_full", "pct", "pct_raw", "num", "int", "compact"
    }
