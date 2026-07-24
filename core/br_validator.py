"""
core/br_validator.py — Brazilian financial data validation and parsing.
Internal utility module (NOT an MCP tool).

Used by skills/b3, skills/cvm, and LLM-generated pandas scripts to safely
parse BRL currency, BR dates, and BOVESPA tickers without schema drift.
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
    'R$ 1.000,50' -> 1000.50
    '-R$ 50,00'   -> -50.00
    '1.234,56'    -> 1234.56
    'R$ 596,36 B' -> 596360000000.0   (billions — investsite format)
    'R$ 1,25 T'   -> 1250000000000.0  (trillions — investsite format)
    'R$ 50,00 M'  -> 50000000.0       (millions — investsite format)
    '27,18%'      -> 0.2718            (percentage)
    """
    if isinstance(value, (int, float)):
        return float(value)
    if not isinstance(value, str):
        raise ValueError(f"Cannot parse BRL from {type(value)}")

    clean = value.strip()
    if not clean:
        return 0.0

    negative = clean.startswith("-")
    clean = clean.replace("R$", "").replace("-", "").strip()

    # [v1.1] Handle percentage: "27,18%" -> 0.2718
    is_percentage = "%" in clean
    clean = clean.replace("%", "")

    # [v1.1] Handle magnitude suffixes (investsite format): B=billion, T=trillion, M=million
    multiplier = 1.0
    # Match suffix at end (case-insensitive), must be a standalone letter
    suffix_match = re.match(r"^(.*?)([BTM])$", clean, re.IGNORECASE)
    if suffix_match:
        clean = suffix_match.group(1).strip()
        suffix = suffix_match.group(2).upper()
        if suffix == "B":
            multiplier = 1_000_000_000  # billion
        elif suffix == "T":
            multiplier = 1_000_000_000_000  # trillion
        elif suffix == "M":
            multiplier = 1_000_000  # million

    # Remove thousands separator (.) and replace decimal separator (,) with (.)
    clean = clean.replace(".", "").replace(",", ".")

    try:
        result = float(clean)
        if is_percentage:
            result = result / 100.0
        result = result * multiplier
        return -result if negative else result
    except ValueError:
        raise ValueError(f"Invalid BRL format: {value}")


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
    Handles PETR4, TAEE11, IBOV, etc.
    """
    if not symbol:
        raise ValueError("Empty ticker")
        
    clean = symbol.strip().upper()
    
    # Allows 3-6 letters, optionally followed by 1 or 2 numbers
    if not re.match(r"^[A-Z]{3,6}\d{0,2}$", clean):
        raise ValueError(f"Invalid ticker format: {symbol}")
        
    return clean


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