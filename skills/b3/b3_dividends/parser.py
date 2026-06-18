"""
skills/b3/b3_dividends/parser.py
Parse B3 dividends JSON into normalized row dicts for SQLite storage.

Matches the Google Sheets pattern: fillSection() validates rows before writing.
Here we validate at parse time: skip rows with empty isin_code or approved_on.

Date normalization: B3 returns DD/MM/YYYY strings. We convert to YYYY-MM-DD
so SQLite ORDER BY and range queries work correctly (lexicographic = chronological).
"""
from __future__ import annotations

from typing import Any

from skills.b3.b3_dividends.dividends_catalog import get_schema, get_date_columns


def _normalize_date(date_str: str | None) -> str | None:
    """Convert DD/MM/YYYY → YYYY-MM-DD. Return None if invalid or empty.

    Args:
        date_str: Raw date from B3 API (e.g., "15/03/2024").

    Returns:
        ISO date string (e.g., "2024-03-15") or None.

    Note:
        B3 uses DD/MM/YYYY. SQLite string comparison of DD/MM/YYYY is broken
        because "20/01/2024" > "15/02/2024" lexicographically. ISO format fixes this.
    """
    if not date_str:
        return None
    v = str(date_str).strip()
    if not v or v.lower() in ("null", "none", "nan", "-"):
        return None
    parts = v.split("/")
    if len(parts) != 3:
        return None
    try:
        day, month, year = parts
        # Validate numeric
        d, m, y = int(day), int(month), int(year)
        if not (1 <= d <= 31 and 1 <= m <= 12 and 1900 <= y <= 2100):
            return None
        return f"{y:04d}-{m:02d}-{d:02d}"
    except (ValueError, TypeError):
        return None


def _validate_row(row: dict[str, Any]) -> bool:
    """Validate a parsed row before it reaches storage.

    Matches Google Sheets fillSection() pattern: skip rows with empty
    ISIN or approved date — these are the minimum required fields.

    Args:
        row: Parsed row dict.

    Returns:
        True if row is valid and should be stored.
    """
    isin = str(row.get("isin_code", "")).strip()
    approved = str(row.get("approved_on", "")).strip()
    return bool(isin) and bool(approved)


def parse_cash_dividends(items: list[dict], ticker: str) -> list[dict]:
    """Parse B3 cashDividends JSON into normalized row dicts.

    Args:
        items: Raw JSON from B3 API (content[0].cashDividends).
        ticker: Full ticker symbol (e.g., "PETR4", "VALE3").

    Returns:
        List of validated row dicts ready for storage.

    Note:
        Dates are normalized from DD/MM/YYYY to YYYY-MM-DD.
        Rows with empty isin_code or approved_on are skipped.
    """
    schema_name = "CashDividends"
    date_cols = set(get_date_columns(schema_name))
    rows: list[dict] = []

    for item in items:
        row = {
            "ticker": ticker,
            "label": item.get("label", ""),
            "isin_code": item.get("isinCode", ""),
            "approved_on": item.get("approvedOn", ""),
            "last_date_prior": item.get("lastDatePrior", ""),
            "rate": item.get("rate", ""),
            "related_to": item.get("relatedTo", ""),
            "payment_date": item.get("paymentDate", ""),
        }
        # Normalize dates
        for col in date_cols:
            row[col] = _normalize_date(row[col])
        if _validate_row(row):
            rows.append(row)

    return rows


def parse_stock_dividends(items: list[dict], ticker: str) -> list[dict]:
    """Parse B3 stockDividends JSON into normalized row dicts.

    Args:
        items: Raw JSON from B3 API (content[0].stockDividends).
        ticker: Full ticker symbol.

    Returns:
        List of validated row dicts.
    """
    schema_name = "StockDividends"
    date_cols = set(get_date_columns(schema_name))
    rows: list[dict] = []

    for item in items:
        row = {
            "ticker": ticker,
            "label": item.get("label", ""),
            "isin_code": item.get("isinCode", ""),
            "approved_on": item.get("approvedOn", ""),
            "last_date_prior": item.get("lastDatePrior", ""),
            "factor": item.get("factor", ""),
            "asset_issued": item.get("assetIssued", ""),
        }
        for col in date_cols:
            row[col] = _normalize_date(row[col])
        if _validate_row(row):
            rows.append(row)

    return rows


def parse_subscriptions(items: list[dict], ticker: str) -> list[dict]:
    """Parse B3 subscriptions JSON into normalized row dicts.

    Args:
        items: Raw JSON from B3 API (content[0].subscriptions).
        ticker: Full ticker symbol.

    Returns:
        List of validated row dicts.
    """
    schema_name = "Subscriptions"
    date_cols = set(get_date_columns(schema_name))
    rows: list[dict] = []

    for item in items:
        row = {
            "ticker": ticker,
            "label": item.get("label", ""),
            "isin_code": item.get("isinCode", ""),
            "approved_on": item.get("approvedOn", ""),
            "last_date_prior": item.get("lastDatePrior", ""),
            "percentage": item.get("percentage", ""),
            "asset_issued": item.get("assetIssued", ""),
            "price_unit": item.get("priceUnit", ""),
            "trading_period": item.get("tradingPeriod", ""),
            "subscription_date": item.get("subscriptionDate", ""),
        }
        for col in date_cols:
            row[col] = _normalize_date(row[col])
        if _validate_row(row):
            rows.append(row)

    return rows


def parse_all(company_data: dict, ticker: str) -> dict[str, list[dict]]:
    """Parse all dividend types from a B3 company data object.

    Args:
        company_data: The first element of the B3 API response list.
        ticker: Full ticker symbol.

    Returns:
        Dict mapping schema name → list of parsed rows.
            {
                "CashDividends": [...],
                "StockDividends": [...],
                "Subscriptions": [...],
            }
    """
    return {
        "CashDividends": parse_cash_dividends(company_data.get("cashDividends", []), ticker),
        "StockDividends": parse_stock_dividends(company_data.get("stockDividends", []), ticker),
        "Subscriptions": parse_subscriptions(company_data.get("subscriptions", []), ticker),
    }
