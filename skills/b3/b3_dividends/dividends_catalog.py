"""
skills/b3/b3_dividends/dividends_catalog.py
Schema registry for B3 Corporate Actions / Dividends (Proventos).

Source: https://sistemaswebb3-listados.b3.com.br/listedCompaniesProxy/CompanyCall/GetListedSupplementCompany/{base64}
Format: JSON API, utf8 encoding, base64-encoded params {"issuingCompany": ticker, "language": "pt-br"}.
Storage: memory_db/b3/dividends.db (isolated, never touches existing DBs).

Test URL (PETR4): https://sistemaswebb3-listados.b3.com.br/listedCompaniesProxy/CompanyCall/GetListedSupplementCompany/eyJpc3N1aW5nQ29tcGFueSI6IlBFVFIiLCJsYW5ndWFnZSI6InB0LWJyIn0=

Layout spec: https://www.b3.com.br/data/files/65/50/AD/26/29C8B51095EE46B5790D8AA8/CorporateActions_B3.pdf

Adapted from Google Sheets JavaScript: doGetProventos() → fillCashDividends(), fillStockDividends(), fillSubscriptions()
"""
from __future__ import annotations

ColDef = tuple[str, str, str]

B3_SCHEMAS: dict[str, dict] = {
    "CashDividends": {
        "prefix": "CashDiv",
        "db_file": "dividends.db",
        "table": "cash_dividends",
        "pk": "isin_code",
        "encoding": "utf8",
        "separator": None,
        "description": "Cash dividends (proventos em dinheiro) for B3-listed companies.",
        "indexes": ["ticker", "isin_code", "approved_on", "payment_date"],
        # _ingested_at is NOT listed here — it is added by storage.py as metadata
        "columns": {
            "ticker": ("TickerSymbol", "text", "Company ticker (e.g. PETR4, VALE3, WEGE3, SAPR11)"),
            "label": ("Label", "text", "Dividend description"),
            "isin_code": ("ISIN", "text", "International Securities Identification Number"),
            "approved_on": ("ApprovedDate", "text", "Date approved YYYY-MM-DD (normalized from DD/MM/YYYY)"),
            "last_date_prior": ("LastDateWithRight", "text", "Last date to have right YYYY-MM-DD"),
            "rate": ("RateBRL", "real", "Dividend amount in BRL"),
            "related_to": ("RelatedTo", "text", "Reference period or event"),
            "payment_date": ("PaymentDate", "text", "Payment date YYYY-MM-DD"),
        },
        # Columns that contain dates in DD/MM/YYYY from the API — must be normalized to ISO
        "date_columns": ["approved_on", "last_date_prior", "payment_date"],
    },
    "StockDividends": {
        "prefix": "StockDiv",
        "db_file": "dividends.db",
        "table": "stock_dividends",
        "pk": "isin_code",
        "encoding": "utf8",
        "separator": None,
        "description": "Stock dividends (dividendos em ações) for B3-listed companies.",
        "indexes": ["ticker", "isin_code", "approved_on"],
        "columns": {
            "ticker": ("TickerSymbol", "text", "Company ticker"),
            "label": ("Label", "text", "Dividend description"),
            "isin_code": ("ISIN", "text", "ISIN code"),
            "approved_on": ("ApprovedDate", "text", "Date approved YYYY-MM-DD"),
            "last_date_prior": ("LastDateWithRight", "text", "Last date with right YYYY-MM-DD"),
            "factor": ("Factor", "real", "Stock dividend factor/ratio"),
            "asset_issued": ("AssetIssued", "text", "New asset/ticker issued"),
        },
        "date_columns": ["approved_on", "last_date_prior"],
    },
    "Subscriptions": {
        "prefix": "Subscription",
        "db_file": "dividends.db",
        "table": "subscriptions",
        "pk": "isin_code",
        "encoding": "utf8",
        "separator": None,
        "description": "Subscription rights (direitos de subscrição) for B3-listed companies.",
        "indexes": ["ticker", "isin_code", "approved_on", "subscription_date"],
        "columns": {
            "ticker": ("TickerSymbol", "text", "Company ticker"),
            "label": ("Label", "text", "Subscription description"),
            "isin_code": ("ISIN", "text", "ISIN code"),
            "approved_on": ("ApprovedDate", "text", "Date approved YYYY-MM-DD"),
            "last_date_prior": ("LastDateWithRight", "text", "Last date with right YYYY-MM-DD"),
            "percentage": ("Percentage", "real", "Subscription percentage"),
            "asset_issued": ("AssetIssued", "text", "Asset issued for subscription"),
            "price_unit": ("IssuePriceBRL", "real", "Issue price per unit in BRL"),
            "trading_period": ("TradingPeriod", "text", "Trading window description"),
            "subscription_date": ("SubscriptionDate", "text", "Subscription deadline YYYY-MM-DD"),
        },
        "date_columns": ["approved_on", "last_date_prior", "subscription_date"],
    },
}

NUMERIC_COLS: dict[str, set[str]] = {
    "CashDividends": {"rate"},
    "StockDividends": {"factor"},
    "Subscriptions": {"percentage", "price_unit"},
}

INTEGER_COLS: dict[str, set[str]] = {
    "CashDividends": set(),
    "StockDividends": set(),
    "Subscriptions": set(),
}


def get_schema(name: str) -> dict:
    """Return the full schema dict for a given schema name.

    Args:
        name: One of "CashDividends", "StockDividends", "Subscriptions".

    Raises:
        KeyError: If the schema name is not recognized.
    """
    if name not in B3_SCHEMAS:
        raise KeyError(f"Unknown schema '{name}'. Available: {list(B3_SCHEMAS.keys())}")
    return B3_SCHEMAS[name]


def all_file_names() -> list[str]:
    """Return all registered schema names."""
    return list(B3_SCHEMAS.keys())


def get_columns(name: str) -> dict[str, ColDef]:
    """Return the column definitions for a schema.

    Returns:
        Dict mapping column name → (english_name, sql_type, description).
    """
    return get_schema(name)["columns"]


def get_numeric_cols(name: str) -> set[str]:
    """Return the set of column names that should be coerced to float/real."""
    return NUMERIC_COLS.get(name, set())


def get_integer_cols(name: str) -> set[str]:
    """Return the set of column names that should be coerced to int."""
    return INTEGER_COLS.get(name, set())


def get_date_columns(name: str) -> list[str]:
    """Return the list of column names that contain DD/MM/YYYY dates from the API.

    These must be normalized to YYYY-MM-DD before storage so SQLite range queries work.
    """
    return get_schema(name).get("date_columns", [])


def build_create_sql(name: str) -> str:
    """Build a CREATE TABLE statement for a schema, including PRIMARY KEY.

    The PRIMARY KEY is taken from the schema's 'pk' field. This ensures
    duplicate ISINs are rejected or updated, not silently inserted twice.

    Args:
        name: Schema name.

    Returns:
        SQL CREATE TABLE string.
    """
    schema = get_schema(name)
    table = schema["table"]
    cols = schema["columns"]
    pk = schema.get("pk", "")

    col_defs: list[str] = []
    for b3_code, (_, typ, _) in cols.items():
        col_defs.append(f"    {b3_code} {typ}")

    # Add metadata column — not part of the source schema, managed by storage layer
    col_defs.append("    _ingested_at text")

    # Add PRIMARY KEY constraint if defined
    if pk and pk in cols:
        col_defs.append(f"    PRIMARY KEY ({pk})")

    lines = [f"CREATE TABLE IF NOT EXISTS {table} (", ",\n".join(col_defs), ");"]
    return "\n".join(lines)


def describe(name: str) -> str:
    """Return a human-readable description of a schema."""
    schema = get_schema(name)
    lines = [f"{name} ({schema['description']})", ""]
    for code, (eng, typ, desc) in schema["columns"].items():
        lines.append(f"  {code:30s} {eng:25s} {desc}")
    return "\n".join(lines)
