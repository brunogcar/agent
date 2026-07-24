"""
core/br_validator.py — Brazilian financial data validation and parsing.
Internal utility module (NOT an MCP tool).

Used by skills/b3, skills/cvm, skills/investsite, and LLM-generated pandas
scripts to safely parse BRL currency, BR dates, BOVESPA tickers, CVM escala,
and percentages without schema drift.

[v1.2] Added: parse_escala() (CVM ESCALA_MOEDA), format_brl(), parse_percentage().
       Fixed: validate_ticker() now accepts futures/options suffixes.
       Moved: parse_escala() here from data_sources/cvm/_db.py (single source).
"""
from __future__ import annotations

import re
from datetime import datetime
from pydantic import BaseModel, field_validator


# =============================================================================
# Helper Functions (For Python/Pandas usage)
# =============================================================================

def parse_brl(value: str | float | int) -> float:
    """
    Converts Brazilian Real string to float.

    Handles:
      'R$ 1.000,50'     -> 1000.50
      '-R$ 50,00'       -> -50.00
      '1.234,56'        -> 1234.56
      'R$ 596,36 B'     -> 596360000000.0   (billions — investsite format)
      'R$ 1,25 T'       -> 1250000000000.0  (trillions — investsite format)
      'R$ 50,00 M'      -> 50000000.0       (millions — investsite format)
      '27,18%'          -> 0.2718            (percentage as decimal)
      '27,18'           -> 27.18             (plain number with BR decimal)
    """
    if isinstance(value, (int, float)):
        return float(value)
    if not isinstance(value, str):
        raise ValueError(f"Cannot parse BRL from {type(value)}")

    clean = value.strip()
    if not clean:
        return 0.0

    negative = clean.startswith("-")
    # Remove R$ prefix (handle both "R$" and "R\$" — PowerShell escaping)
    clean = clean.replace("R$", "").replace("R\\$", "").replace("-", "").strip()

    # Handle percentage: "27,18%" -> 0.2718
    is_percentage = "%" in clean
    clean = clean.replace("%", "").strip()

    # Handle magnitude suffixes (investsite format): B=billion, T=trillion, M=million
    multiplier = 1.0
    suffix_match = re.match(r"^(.*?)([BTM])$", clean, re.IGNORECASE)
    if suffix_match:
        clean = suffix_match.group(1).strip()
        suffix = suffix_match.group(2).upper()
        if suffix == "B":
            multiplier = 1_000_000_000
        elif suffix == "T":
            multiplier = 1_000_000_000_000
        elif suffix == "M":
            multiplier = 1_000_000

    # Remove thousands separator (.) and replace decimal separator (,) with (.)
    clean = clean.replace(".", "").replace(",", ".").strip()

    try:
        result = float(clean)
        if is_percentage:
            result = result / 100.0
        result = result * multiplier
        return -result if negative else result
    except ValueError:
        raise ValueError(f"Invalid BRL format: {value}")


def parse_percentage(value: str | float | int, as_decimal: bool = False) -> float:
    """
    Parse a percentage string to a number.

    '27,18%'  -> 27.18  (as_decimal=False, default — the number shown)
    '27,18%'  -> 0.2718 (as_decimal=True — for multiplication)
    '5,15'    -> 5.15   (no % sign, treated as plain number)
    """
    if isinstance(value, (int, float)):
        return value / 100.0 if as_decimal else float(value)
    if not isinstance(value, str):
        raise ValueError(f"Cannot parse percentage from {type(value)}")

    clean = value.strip().replace("%", "").strip()
    # Use parse_brl without the % handling to get the raw number
    num = parse_brl(clean)
    return num / 100.0 if as_decimal else num


def format_brl(value: float | int, suffix: bool = True) -> str:
    """
    Format a float as a Brazilian Real string.

    1000.50 -> 'R$ 1.000,50'
    -50.0   -> '-R$ 50,00'
    596360000000.0 -> 'R$ 596,36 B' (when suffix=True)

    Args:
        value: The number to format.
        suffix: If True, use B/T/M suffixes for large numbers (investsite style).
                If False, format as full number with thousands separators.
    """
    if isinstance(value, int):
        value = float(value)

    negative = value < 0
    abs_val = abs(value)

    if suffix:
        if abs_val >= 1_000_000_000_000:
            formatted = f"{abs_val / 1_000_000_000_000:.2f}".replace(".", ",")
            result = f"R$ {formatted} T"
        elif abs_val >= 1_000_000_000:
            formatted = f"{abs_val / 1_000_000_000:.2f}".replace(".", ",")
            result = f"R$ {formatted} B"
        elif abs_val >= 1_000_000:
            formatted = f"{abs_val / 1_000_000:.2f}".replace(".", ",")
            result = f"R$ {formatted} M"
        else:
            s = f"{abs_val:,.2f}"
            s = s.replace(",", "X").replace(".", ",").replace("X", ".")
            result = f"R$ {s}"
    else:
        s = f"{abs_val:,.2f}"
        s = s.replace(",", "X").replace(".", ",").replace("X", ".")
        result = f"R$ {s}"

    return f"-{result}" if negative else result


def parse_br_date(value: str, fmt: str = "%Y-%m-%d") -> datetime:
    """
    Parses common Brazilian date formats.
    Handles 'DD/MM/YYYY' (default BR) and 'YYYY-MM-DD' (ISO/CVM).
    """
    if not value or not isinstance(value, str):
        raise ValueError("Invalid date")

    clean = value.strip()

    # Try DD/MM/YYYY first (Standard BR format)
    if re.match(r"^\d{2}/\d{2}/\d{4}$", clean):
        return datetime.strptime(clean, "%d/%m/%Y")

    # Try ISO (CVM API format)
    try:
        return datetime.strptime(clean, "%Y-%m-%d")
    except ValueError:
        pass

    # Fallback to provided format
    return datetime.strptime(clean, fmt)


def validate_ticker(symbol: str) -> str:
    """
    Standardizes BOVESPA tickers.
    Strips whitespace, uppercases, and validates basic format.

    Handles:
      - Equities: PETR4, VALE3, ITUB4
      - Units: KLBN11, TAEE11
      - Indices: IBOV, IBRX
      - Futures/options: DOLM25, PETRJ25 (letter + F/G/H/J/K/M/N/Q/U/V/X/Z for month)

    Rejects: empty, non-alpha, lowercase-only, special chars.
    """
    if not symbol:
        raise ValueError("Empty ticker")

    clean = symbol.strip().upper()

    # Allows 3-6 letters, optionally followed by 1-2 digits (equities/units)
    # OR futures format: 3+ letters + 1 month letter + 2 digits
    # OR indices: 3-6 letters only
    if not re.match(r"^[A-Z]{3,6}\d{0,2}$", clean):
        # Try futures/options pattern: LETTERS + MONTH_LETTER + DIGITS
        if not re.match(r"^[A-Z]{2,5}[FGHJKMNQUVXZ]\d{1,2}$", clean):
            raise ValueError(f"Invalid ticker format: {symbol}")

    return clean


def parse_escala(escala: str | None) -> float:
    """
    Parse CVM ESCALA_MOEDA string to a numeric multiplier.

    CVM CSVs store scale as Portuguese words, not numbers:
      'MIL'     -> 1000.0     (thousands)
      'MILHAR'  -> 1000.0     (thousands variant)
      'MILHOES' -> 1000000.0  (millions)
      'MILHAO'  -> 1000000.0  (million singular)
      'UNIDADE' -> 1.0        (units)
      'UNIDADES' -> 1.0       (units plural)
      '' / None -> 1.0        (empty = treat as units)

    This was previously in data_sources/cvm/_db.py — moved here (v1.2) for
    reuse across all financial skills.

    Examples:
        parse_escala('MIL') -> 1000.0
        parse_escala('MILHOES') -> 1000000.0
        parse_escala('UNIDADE') -> 1.0
        parse_escala('') -> 1.0
        parse_escala(None) -> 1.0
    """
    if not escala:
        return 1.0
    key = str(escala).strip().upper()

    _ESCALA_MAP = {
        "MIL":      1_000.0,
        "MILHAR":   1_000.0,
        "MILHOES":  1_000_000.0,
        "MILHAO":   1_000_000.0,
        "UNIDADE":  1.0,
        "UNIDADES": 1.0,
        "":         1.0,
    }

    if key in _ESCALA_MAP:
        return _ESCALA_MAP[key]

    # Try parsing as a number directly (some sources may store numeric)
    try:
        return float(key)
    except ValueError:
        return 1.0  # unknown escala = treat as units (safe default)


# =============================================================================
# Pydantic V2 Models (For Structured Data / API Validation)
# =============================================================================

class B3Dividend(BaseModel):
    """Schema for B3 dividend/corporate action data."""
    ticker: str
    isin: str | None = None
    value_brl: float
    date_approved: datetime | None = None
    date_ex: datetime | None = None
    date_payment: datetime | None = None

    @field_validator("ticker", mode="before")
    @classmethod
    def check_ticker(cls, v):
        return validate_ticker(v)

    @field_validator("value_brl", mode="before")
    @classmethod
    def check_brl(cls, v):
        return parse_brl(v)

    @field_validator("date_approved", "date_ex", "date_payment", mode="before")
    @classmethod
    def check_dates(cls, v):
        if not v:
            return None
        return parse_br_date(v)
