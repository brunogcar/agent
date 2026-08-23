"""data_sources/ddm/_parsers.py -- Shared PT-BR parsing wrappers for DDM fetchers.

Thin wrappers around core.br_validator that return None/"" instead of
raising ValueError, and handle DDM-specific formats (mi suffix, Mon/YYYY
month labels).

All 7 DDM fetchers (inflation, juros, poupanca, acoes, dividends, fluxo,
focus) import from here instead of defining their own local parsers.
This is the single entry point for PT-BR parsing in the DDM data-source
layer.

[v1] Created as part of the code-review-driven consolidation (replaces
7 copies of _parse_br_number / _parse_br_date / _strip_html that had
subtle, inconsistent behavior — see review C0/C1/B6/B7).

Functions:
  - strip_html(s)                 -> str
  - parse_br_number(value)        -> float | None
  - parse_br_int(value)           -> int | None
  - parse_br_percentage(value)    -> float | None
  - parse_br_date_iso(value)      -> str  (YYYY-MM-DD or "")
  - parse_mes_ano(value)          -> str  (YYYY-MM or "")
"""
from __future__ import annotations

import re

from core.br_validator import parse_brl
from core.br_validator import parse_br_date as _parse_br_date_dt


# PT-BR month abbreviations -> 2-digit month number.
# Used by parse_mes_ano for DDM historical-row labels ("Jul/2026" -> "2026-07").
_MONTHS_PT = {
    "Jan": "01", "Fev": "02", "Mar": "03", "Abr": "04",
    "Mai": "05", "Jun": "06", "Jul": "07", "Ago": "08",
    "Set": "09", "Out": "10", "Nov": "11", "Dez": "12",
}


def strip_html(s: str) -> str:
    """Strip all HTML tags from a string and collapse whitespace.

    Equivalent to the per-fetcher _strip_html that was duplicated 7 times.
    """
    if not s:
        return ""
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", s)).strip()


def parse_br_number(value) -> float | None:
    """Parse a PT-BR number string to float. Returns None for invalid.

    Handles:
      "1.582,35"       -> 1582.35   (dot=thousands, comma=decimal)
      "44,30"          -> 44.30
      "-1,5"           -> -1.5
      "R$ 1.234,56"    -> 1234.56   (R$ prefix)
      "0,017250"       -> 0.017250
      "1.582,35 mi"    -> 1582.35   (mi suffix stripped)
      "--"             -> None
      "" / None        -> None

    Delegates to core.br_validator.parse_brl after stripping DDM-specific
    suffixes (mi). R$ prefix + thousands are handled by parse_brl itself.

    Note: for percentage strings ("5,151%"), use parse_br_percentage
    instead — parse_brl divides by 100, which is usually NOT what DDM
    callers want (they want the raw number 5.151, not 0.05151).
    """
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    s = strip_html(str(value))
    if not s or s in ("--", "-"):
        return None
    # Strip DDM-specific "mi" (millions) suffix.
    s = re.sub(r"\bmi\b", "", s, flags=re.IGNORECASE).strip()
    if not s:
        return None
    try:
        result = parse_brl(s)
        # parse_brl("") returns 0.0, but DDM convention is None for empty.
        # Guard: if the stripped string has no digits, treat as None.
        if result == 0.0 and not any(c.isdigit() for c in s):
            return None
        return result
    except (ValueError, TypeError):
        return None


def parse_br_int(value) -> int | None:
    """Parse a PT-BR integer string to int. Returns None for invalid.

    Handles: "52.792.400" -> 52792400 (dot=thousands separator).
    Delegates to parse_br_number then truncates to int.
    """
    f = parse_br_number(value)
    if f is None:
        return None
    return int(f)


def parse_br_percentage(value) -> float | None:
    """Parse a PT-BR percentage string to float (the number shown, NOT decimal).

    Handles:
      "+2,78%"   -> 2.78
      "-10,85%"  -> -10.85
      "5,151%"   -> 5.151
      "27,18"    -> 27.18  (no % sign, treated as plain number)

    Returns None for empty / "--" / unparseable inputs.

    Note: this returns the NUMBER SHOWN (5.151), not the decimal (0.05151).
    If you need the decimal form, divide by 100 in the caller.
    """
    if value is None:
        return None
    s = strip_html(str(value))
    if not s or s == "--":
        return None
    # Strip % ourselves so parse_brl doesn't divide by 100.
    s = s.replace("%", "").strip()
    if not s:
        return None
    return parse_br_number(s)


def parse_br_date_iso(value) -> str:
    """Parse a PT-BR date string to YYYY-MM-DD. Returns "" for invalid.

    Handles:
      "01/07/2026"  -> "2026-07-01"  (DD/MM/YYYY)
      "1/7/2026"    -> "2026-07-01"  (single-digit day/month)
      "2026-07-01"  -> "2026-07-01"  (ISO, passthrough)
      "--"          -> ""
      "" / None     -> ""

    Validates day (1-31), month (1-12), year (1900-2100).
    """
    if not value:
        return ""
    s = strip_html(str(value)).strip()
    if not s or s == "--":
        return ""
    # Try DD/MM/YYYY first (with flexible 1-2 digit day/month).
    m = re.match(r"^(\d{1,2})/(\d{1,2})/(\d{4})$", s)
    if m:
        d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if 1 <= d <= 31 and 1 <= mo <= 12 and 1900 <= y <= 2100:
            return f"{y:04d}-{mo:02d}-{d:02d}"
        return ""
    # Try ISO YYYY-MM-DD.
    try:
        dt = _parse_br_date_dt(s)
        return dt.strftime("%Y-%m-%d")
    except (ValueError, TypeError):
        return ""


def parse_mes_ano(value) -> str:
    """Convert 'Jul/2026' -> '2026-07'. Returns "" for unparseable.

    DDM historical rows use PT-BR month abbreviations (Mon/YYYY).
    Uses strict lookup: returns "" if the month abbreviation is not
    recognized (no silent fallback to January — fixes review B8 at the
    Python boundary).

    Handles:
      "Jul/2026"      -> "2026-07"
      "jul/2026"      -> "2026-07"  (case-insensitive)
      "XXX/2026"      -> ""         (unknown month, NOT January)
      "2026-07"       -> ""         (not Mon/YYYY format)
      "" / None       -> ""
    """
    if not value:
        return ""
    s = str(value).strip()
    m = re.match(r"^([A-Za-z]{3})/(\d{4})$", s)
    if not m:
        return ""
    mon, year = m.group(1), m.group(2)
    # Strict lookup: try exact match, then title-case (for lowercase input).
    month_num = _MONTHS_PT.get(mon)
    if not month_num:
        month_num = _MONTHS_PT.get(mon.capitalize())
    if not month_num:
        return ""
    return f"{year}-{month_num}"
