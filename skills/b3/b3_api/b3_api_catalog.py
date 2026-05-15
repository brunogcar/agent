"""
skills/b3/catalog.py -- Schema registry for B3 public data files.

SOURCE: Official B3 glossary PDFs (InstrumentsConsolidatedFileV2_EN.pdf,
TradeInformationConsolidatedFileV3_EN.pdf, etc.) provided by the project owner.

WHAT THIS IS
------------
Single source of truth for every B3 file's:
  - API prefix (used to find the latest file in the publications API)
  - SQLite DB filename (where local data is stored)
  - Column definitions: B3 code -> (english name, sqlite type, description)
  - Which columns to index (for fast TckrSymb/ISIN lookups)

WHY A CATALOG INSTEAD OF HARDCODING
-------------------------------------
- sync.py reads column names from here, never from magic strings
- query.py validates requested fields against this catalog
- dispatcher.py builds the dynamic docstring from this catalog
- Adding a new B3 file = add one entry here, nothing else changes

DECISION: SQLite types are kept simple (text, real, int).
B3 sends everything as strings in the CSV. sync.py converts numeric
columns to float/int on insert using NUMERIC_COLS set. Dates stay as
text (DD/MM/YYYY format from B3) -- query.py handles date filtering.

STORAGE PATH: cfg.memory_root / "b3" / db_file
  e.g. D:/mcp/agent/memory_db/b3/instruments.db
WHY memory_db: co-located with ChromaDB, single backup target,
  already excluded from git via .gitignore on memory_db/.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Type alias for column definition tuples
# (english_name, sqlite_type, description)
# ---------------------------------------------------------------------------
ColDef = tuple[str, str, str]


# ---------------------------------------------------------------------------
# Master schema registry
# ---------------------------------------------------------------------------

B3_SCHEMAS: dict[str, dict] = {

    # ── InstrumentsConsolidatedFile ─────────────────────────────────────────
    # Master reference file. 53 columns. Links all other files via TckrSymb/ISIN.
    # Contains: company name, governance level, market segment, capital, lot size.
    "Instruments": {
        "prefix":  "InstrumentsConsolidatedFile",
        "db_file": "instruments.db",
        "table":   "instruments",
        "pk":      "TckrSymb",
        "encoding": "ISO-8859-1",
        "separator": ";",
        "description": "Master instrument reference: all listed securities with company info, segment, governance",
        "indexes": ["TckrSymb", "ISIN", "SgmtNm", "SctyCtgyNm", "Asst"],
        "columns": {
            "RptDt":             ("ReportDate",                  "text", "Reference date of the information"),
            "TckrSymb":          ("TickerSymbol",                "text", "Ticker symbol (e.g. PETR4, ITUB3)"),
            "Asst":              ("Asset",                       "text", "Underlying asset (e.g. PETR, DOL, BGI)"),
            "AsstDesc":          ("AssetDescription",            "text", "Commodity/asset description"),
            "SgmtNm":            ("SegmentName",                 "text", "Market segment (Equity-Cash, Derivatives, etc.)"),
            "MktNm":             ("MarketName",                  "text", "Market name"),
            "SctyCtgyNm":        ("SecurityCategoryName",        "text", "Security category (3rd classification level)"),
            "XprtnDt":           ("ExpirationDate",              "text", "Maturity/expiration date of the instrument"),
            "XprtnCd":           ("ExpirationCode",              "text", "Contract expiration code (MYY or MYOA format)"),
            "TradgStartDt":      ("TradingStartDate",            "text", "Date trading started"),
            "TradgEndDt":        ("TradingEndDate",              "text", "Date trading ended"),
            "BaseCd":            ("BaseCode",                    "text", "Day count basis (252, 360, 365)"),
            "ConvsCritNm":       ("ConversionCriteriaName",      "text", "Rate-to-price conversion type (linear/exponential)"),
            "MtrtyDtTrgtPt":     ("MaturityDateTargetPoint",     "real", "Contract value in points for rate conversion"),
            "ReqrdConvsInd":     ("RequiredConversionIndicator", "text", "Whether rate must be converted to price"),
            "ISIN":              ("ISIN",                        "text", "International Securities Identification Number"),
            "CFICd":             ("CFICode",                     "text", "CFI classification code"),
            "DlvryNtceStartDt":  ("DeliveryNoticeStartDate",     "text", "Start date of delivery notice window"),
            "DlvryNtceEndDt":    ("DeliveryNoticeEndDate",       "text", "End date of delivery notice window"),
            "OptnTp":            ("OptionType",                  "text", "Call or Put"),
            "CtrctMltplr":       ("ContractMultiplier",          "real", "Contract size ratio (e.g. 50 for Dollar futures)"),
            "AsstQtnQty":        ("AssetQuotationQuantity",      "real", "Commodity quantity the trading price is based on"),
            "AllcnRndLot":       ("AllocationRoundLot",          "int",  "Standard lot size for allocation"),
            "TradgCcy":          ("TradingCurrency",             "text", "Trading currency code"),
            "DlvryTpNm":         ("DeliveryTypeName",            "text", "Physical or Financial delivery at maturity"),
            "WdrwlDays":         ("WithdrawalDays",              "int",  "Days from session to contract expiration"),
            "WrkgDays":          ("WorkingDays",                 "int",  "Business days to contract expiration"),
            "ClnrDays":          ("CalendarDays",                "int",  "Calendar days to contract expiration"),
            "RlvrBasePricNm":    ("RolloverBasePriceName",       "text", "Base price for strategy full value calculation"),
            "OpngFutrPosDay":    ("OpeningFuturePositionDay",    "int",  "Days between strategy trade and futures position open"),
            "SdTpCd1":           ("SideTypeCode1",               "text", "Leg 1 side when buying strategy (BUYI/SELL)"),
            "UndrlygTckrSymb1":  ("UnderlyingTickerSymbol1",     "text", "Underlying instrument ticker for leg 1"),
            "SdTpCd2":           ("SideTypeCode2",               "text", "Leg 2 side when buying strategy (BUYI/SELL)"),
            "UndrlygTckrSymb2":  ("UnderlyingTickerSymbol2",     "text", "Underlying instrument ticker for leg 2"),
            "PureGoldWght":      ("PureGoldWeight",              "real", "Pure gold weight in futures contract (grams)"),
            "ExrcPric":          ("ExercisePrice",               "real", "Strike price for options/derivatives"),
            "OptnStyle":         ("OptionStyle",                 "text", "American or European exercise style"),
            "ValTpNm":           ("ValueTypeName",               "text", "Price or Rate"),
            "PrmUpfrntInd":      ("PremiumUpfrontIndicator",     "text", "Whether equity option premium is paid upfront"),
            "OpngPosLmtDt":      ("OpeningPositionLimitDate",    "text", "Deadline for open positions"),
            "DstrbtnId":         ("DistributionIdentification",  "text", "Asset version code (paired with ISIN for stocks/gold)"),
            "PricFctr":          ("PriceFactor",                 "int",  "Shares per price unit (1 or 1000)"),
            "DaysToSttlm":       ("DaysToSettlement",            "int",  "Settlement days"),
            "SrsTpNm":           ("SeriesTypeName",              "text", "Series type for strike price updates"),
            "PrtcnFlg":          ("ProtectionFlag",              "text", "Option protected against corporate events"),
            "AutomtcExrcInd":    ("AutomaticExerciseIndicator",  "text", "Whether option is auto-exercised"),
            "SpcfctnCd":         ("SpecificationCode",           "text", "Stock class code (ON, PN, etc.)"),
            "CrpnNm":            ("CorporationName",             "text", "Full company/institution name"),
            "CorpActnStartDt":   ("CorporateActionStartDate",    "text", "Start date of dividend/bonus corporate action"),
            "CtdyTrtmntTpNm":    ("CustodyTreatmentTypeName",    "text", "Custody treatment type"),
            "MktCptlstn":        ("MarketCapitalisation",        "real", "Share capital value in BRL"),
            "CorpGovnLvlNm":     ("CorporateGovernanceLevelName","text", "Governance level: N1/N2/NM/MB/MA"),
            "StdTradgLot":       ("StandardTradingLot",          "int",  "Standard trading lot size"),
        },
    },

    # ── TradeInformationConsolidatedFile ────────────────────────────────────
    # Daily trade statistics for the regular session. One row per TckrSymb.
    # Key fields: last price, volume, VWAP, oscillation %, adjusted quote.
    "Trades": {
        "prefix":  "TradeInformationConsolidatedFile",
        "db_file": "trades.db",
        "table":   "trades",
        "pk":      "TckrSymb",
        "encoding": "ISO-8859-1",
        "separator": ";",
        "description": "Daily regular session trade stats: prices, volume, oscillation per ticker",
        "indexes": ["TckrSymb", "ISIN", "RptDt"],
        "columns": {
            "RptDt":         ("ReportDate",               "text", "Reference date (DD/MM/YYYY)"),
            "TckrSymb":      ("TickerSymbol",             "text", "Ticker symbol"),
            "ISIN":          ("ISIN",                     "text", "ISIN code"),
            "SgmtNm":        ("SegmentName",              "text", "Market segment"),
            "MinPric":       ("MinimumPrice",             "real", "Minimum price of the session"),
            "MaxPric":       ("MaximumPrice",             "real", "Maximum price of the session"),
            "TradAvrgPric":  ("TradeAveragePrice",        "real", "VWAP - volume-weighted average price"),
            "LastPric":      ("LastPrice",                "real", "Closing/last price of the session"),
            "OscnPctg":      ("OscillationPercentage",   "real", "Daily oscillation percentage"),
            "AdjstdQt":      ("AdjustedQuote",           "real", "Adjusted closing quote"),
            "AdjstdQtTax":   ("AdjustedQuoteTax",        "real", "Adjusted quote including tax"),
            "RefPric":       ("ReferencePrice",           "real", "Reference price"),
            "TradQty":       ("TradeQuantity",            "int",  "Number of trades/contracts in session"),
            "FinInstrmQty":  ("FinancialInstrumentQty",  "int",  "Quantity of financial instruments traded"),
            "NtlFinVol":     ("NationalFinancialVolume",  "real", "Total financial volume traded in BRL"),
        },
    },

    # ── TradeInformationConsolidatedAfterHoursFile ──────────────────────────
    # Same schema as Trades but for the after-market session.
    # Disseminated every night after the after-hours session closes.
    "AfterHours": {
        "prefix":  "TradeInformationConsolidatedAfterHoursFile",
        "db_file": "after_hours.db",
        "table":   "after_hours",
        "pk":      "TckrSymb",
        "encoding": "ISO-8859-1",
        "separator": ";",
        "description": "After-hours session trade stats: same schema as Trades, different session",
        "indexes": ["TckrSymb", "ISIN", "RptDt"],
        "columns": {
            "RptDt":         ("ReportDate",               "text", "Reference date (DD/MM/YYYY)"),
            "TckrSymb":      ("TickerSymbol",             "text", "Ticker symbol"),
            "ISIN":          ("ISIN",                     "text", "ISIN code"),
            "SgmtNm":        ("SegmentName",              "text", "Market segment"),
            "MinPric":       ("MinimumPrice",             "real", "Minimum price in after-hours session"),
            "MaxPric":       ("MaximumPrice",             "real", "Maximum price in after-hours session"),
            "TradAvrgPric":  ("TradeAveragePrice",        "real", "VWAP in after-hours session"),
            "LastPric":      ("LastPrice",                "real", "Last price in after-hours session"),
            "OscnPctg":      ("OscillationPercentage",   "real", "Oscillation % in after-hours session"),
            "AdjstdQt":      ("AdjustedQuote",           "real", "Adjusted quote after-hours"),
            "AdjstdQtTax":   ("AdjustedQuoteTax",        "real", "Adjusted quote tax after-hours"),
            "RefPric":       ("ReferencePrice",           "real", "Reference price"),
            "TradQty":       ("TradeQuantity",            "int",  "Contracts traded in after-hours"),
            "FinInstrmQty":  ("FinancialInstrumentQty",  "int",  "Financial instruments traded"),
            "NtlFinVol":     ("NationalFinancialVolume",  "real", "Volume in BRL after-hours"),
        },
    },

    # ── DerivativesOpenPositionFile ─────────────────────────────────────────
    # Open interest for derivatives (futures, options). One row per TckrSymb.
    # Key fields: open interest, daily variation, covered/uncovered split.
    "Derivatives": {
        "prefix":  "DerivativesOpenPositionFile",
        "db_file": "derivatives.db",
        "table":   "derivatives",
        "pk":      "TckrSymb",
        "encoding": "ISO-8859-1",
        "separator": ";",
        "description": "Derivatives open interest: futures and options positions, daily variation",
        "indexes": ["TckrSymb", "ISIN", "Asst", "SgmtNm"],
        "columns": {
            "RptDt":          ("ReportDate",            "text", "Reference date"),
            "TckrSymb":       ("TickerSymbol",          "text", "Ticker symbol"),
            "ISIN":           ("ISIN",                  "text", "ISIN code"),
            "Asst":           ("Asset",                 "text", "Underlying asset"),
            "SgmtNm":         ("SegmentName",           "text", "Market segment (Equity deriv., Financial, etc.)"),
            "XprtnCd":        ("ExpirationCode",        "text", "Contract expiration code"),
            "OpnIntrst":      ("OpenInterest",          "int",  "Total open contracts"),
            "VartnOpnIntrst": ("VariationOpenInterest", "int",  "Change in open contracts vs prior day"),
            "DstrbtnId":      ("DistributionId",        "text", "Distribution identification code"),
            "CvrdQty":        ("CoveredQuantity",       "int",  "Covered (hedged) quantity"),
            "TtlBlckdPos":    ("TotalBlockedPosition",  "int",  "Total blocked positions"),
            "UcvrdQty":       ("UncoveredQuantity",     "int",  "Uncovered (naked) quantity"),
            "TtlPos":         ("TotalPosition",         "int",  "Total positions (covered + uncovered)"),
            "BrrwrQty":       ("BorrowerQuantity",      "int",  "Number of borrower clients"),
            "LndrQty":        ("LenderQuantity",        "int",  "Number of lender clients"),
            "CurQty":         ("CurrentQuantity",       "int",  "Current quantity"),
            "FwdPric":        ("ForwardPrice",          "real", "Forward contract price"),
        },
    },

    # ── MarginScenarioLiquidAssetsFile ──────────────────────────────────────
    # Risk/margin scenario data. One row per PRFNm + VrtxCd + ScnroId combination.
    # More specialized -- used for margin calculation, volatility surfaces, curves.
    # Key: PRFNm links back to Instruments via the asset name (e.g. VLPETR4 -> PETR4).
    # ScnroId: 9998=neutral, 9999=high envelope, 10000=low envelope.
    "MarginScenario": {
        "prefix":  "MarginScenarioLiquidAssetsFile",
        "db_file": "margin_scenario.db",
        "table":   "margin_scenario",
        "pk":      None,  # composite key: PRFNm + VrtxCd + ScnroId
        "encoding": "ISO-8859-1",
        "separator": ";",
        "description": "Margin/risk scenarios: price shock values for risk calculation (volatility, curves, reference prices)",
        "indexes": ["PRFNm", "ScnroId", "RptDt"],
        "columns": {
            "RptDt":    ("ReportDate", "text", "Reference date"),
            "PRFNm":    ("PRFName",    "text", "PRF name (e.g. VLPETR4 = Volatility PETR4 + delta)"),
            "VrtxCd":   ("VertexCode", "text", "Vertex or distribution code (0 for non-curve PRFs)"),
            "ScnroId":  ("ScenarioId", "int",  "Scenario: 9998=neutral, 9999=high, 10000=low"),
            "PRFVal":   ("PRFValue",   "real", "PRF value with shock applied (4 decimal places)"),
            "TpShck":   ("TypeShock",  "text", "Shock type: A=Additive, M=Multiplicative"),
        },
    },
}


# ---------------------------------------------------------------------------
# Numeric columns that need type conversion on insert
# B3 CSVs are all strings -- these get cast to float/int in sync.py
# ---------------------------------------------------------------------------

NUMERIC_COLS: dict[str, set[str]] = {
    "Instruments": {
        "MtrtyDtTrgtPt", "CtrctMltplr", "AsstQtnQty", "AllcnRndLot",
        "WdrwlDays", "WrkgDays", "ClnrDays", "OpngFutrPosDay",
        "PureGoldWght", "ExrcPric", "PricFctr", "DaysToSttlm",
        "MktCptlstn", "StdTradgLot",
    },
    "Trades": {
        "MinPric", "MaxPric", "TradAvrgPric", "LastPric", "OscnPctg",
        "AdjstdQt", "AdjstdQtTax", "RefPric", "TradQty", "FinInstrmQty",
        "NtlFinVol",
    },
    "AfterHours": {
        "MinPric", "MaxPric", "TradAvrgPric", "LastPric", "OscnPctg",
        "AdjstdQt", "AdjstdQtTax", "RefPric", "TradQty", "FinInstrmQty",
        "NtlFinVol",
    },
    "Derivatives": {
        "OpnIntrst", "VartnOpnIntrst", "CvrdQty", "TtlBlckdPos",
        "UcvrdQty", "TtlPos", "BrrwrQty", "LndrQty", "CurQty", "FwdPric",
    },
    "MarginScenario": {
        "ScnroId", "PRFVal",
    },
}


# ---------------------------------------------------------------------------
# Helper functions used by sync.py, query.py, and dispatcher.py
# ---------------------------------------------------------------------------

def get_schema(name: str) -> dict:
    """Return schema for a file name. Raises KeyError if not found."""
    if name not in B3_SCHEMAS:
        raise KeyError(
            f"Unknown B3 file '{name}'. "
            f"Available: {list(B3_SCHEMAS.keys())}"
        )
    return B3_SCHEMAS[name]


def all_file_names() -> list[str]:
    """Return all registered B3 file names."""
    return list(B3_SCHEMAS.keys())


def get_columns(name: str) -> dict[str, ColDef]:
    """Return column definitions for a file."""
    return get_schema(name)["columns"]


def get_numeric_cols(name: str) -> set[str]:
    """Return set of columns that should be cast to numeric on insert."""
    return NUMERIC_COLS.get(name, set())


def build_create_sql(name: str) -> str:
    """
    Generate CREATE TABLE IF NOT EXISTS SQL for a B3 file's SQLite table.
    Column order matches the order in the columns dict (insertion order, Python 3.7+).
    """
    schema  = get_schema(name)
    table   = schema["table"]
    cols    = schema["columns"]
    numeric = get_numeric_cols(name)

    col_defs = []
    for b3_code, (_, sqlite_type, _) in cols.items():
        # Use the actual B3 column code as the SQLite column name.
        # DECISION: keep B3 codes as column names (not english names) because:
        #   1. The CSV header uses B3 codes -- no translation needed on insert
        #   2. query.py can accept both codes and english names (via catalog lookup)
        #   3. Easier to cross-reference with B3 documentation
        col_defs.append(f"    {b3_code} {sqlite_type}")

    # Add ingestion timestamp for freshness checks
    col_defs.append("    _ingested_at text")

    lines = [f"CREATE TABLE IF NOT EXISTS {table} ("]
    lines.append(",\n".join(col_defs))
    lines.append(");")
    return "\n".join(lines)


def describe(name: str) -> str:
    """Return a human-readable description of a file's columns. Used in help text."""
    schema = get_schema(name)
    lines  = [f"{name} ({schema['description']})", ""]
    for code, (eng, typ, desc) in schema["columns"].items():
        lines.append(f"  {code:20s} {eng:30s} {desc}")
    return "\n".join(lines)
