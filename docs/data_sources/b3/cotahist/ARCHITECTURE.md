<- Back to [COTAHIST Overview](../COTAHIST.md)

# 🏗️ Architecture

## 🔗 Source Code Reference

| File | Purpose |
|---|---|
| `data_sources/b3/cotahist/__init__.py` | MANIFEST + route — sub-domain hub, 3 modes |
| `data_sources/b3/cotahist/catalog.py` | Schema constants: COTAHIST_URL, FIRST_YEAR, BDI_FILTER, COTAHIST_LAYOUT (26 fixed-width columns), NUMERIC_COLS, SQL schema, DB path/connect helpers |
| `data_sources/b3/cotahist/sync_engine.py` | Download annual ZIP → stream-parse fixed-width TXT (245 bytes/record) → batch INSERT (50K). BDI filter at sync time (reduces DB from ~5.7GB to ~1-2GB). |
| `data_sources/b3/cotahist/query_engine.py` | Query: `query(ticker, date_from, date_to, year, limit, market_type)` — OHLCV history with filters. Defaults to market_type=10 (spot) to avoid duplicate rows from fractional market. |
| `data_sources/b3/cotahist/status_reporter.py` | Status: cotahist.db stats (total rows, distinct tickers, date range, years synced). |

## Data Flow

```
Download: https://bvmf.bmfbovespa.com.br/InstDados/SerHist/COTAHIST_A{year}.ZIP
  ↓
Unzip → COTAHIST_A{year}.TXT (~765MB, latin-1 encoding)
  ↓
Stream parse: line-by-line (245 bytes/record, 26 columns)
  ↓
BDI filter: keep only BDI codes {02, 12, 14, 96} (equities + FIIs + fractional)
  ↓
Batch INSERT: 50,000 rows per transaction
  ↓
Record sync_state (year, rows_added, duration_s)
```

## Fixed-Width Layout (26 columns)

| Column | Type | Position | Description |
|---|---|---|---|
| regtype | text | 1-2 | Record type: 00=header, 01=trade, 99=trailer |
| refdate | text | 3-10 | Trade date YYYYMMDD |
| bdi_code | int | 11-12 | BDI market segment code |
| symbol | text | 13-24 | Ticker symbol (PETR4) |
| market_type | int | 25-27 | Market type (10=spot, 12=fractional) |
| open | real | 57-69 | Opening price (÷100) |
| high | real | 70-82 | Session high |
| low | real | 83-95 | Session low |
| close | real | 109-121 | Closing price |
| volume | real | 171-188 | Financial volume (BRL) |
| ... | ... | ... | 16 more columns (see catalog.py COTAHIST_LAYOUT) |

## Design Decisions

- **BDI filter at sync time**: COTAHIST contains every B3 security — stocks, bonds, options, warrants, funds. BDI codes {02, 12, 14, 96} filter to equities + FIIs + fractional, reducing the DB from ~5.7GB to ~1-2GB.
- **market_type=10 default**: A ticker can trade on both lote padrão (10) and fracionário (12) markets on the same day, producing duplicate rows. Defaulting to market_type=10 avoids duplicates.
- **Streaming parser**: The TXT file is ~765MB per year. Line-by-line streaming avoids loading the entire file into memory.
- **Batch INSERT (50K)**: Reduces SQLite write overhead. Without batching, individual INSERTs are 10x slower.
- **Numeric columns ÷100**: B3 stores prices without decimal points (3850 = R$38.50). NUMERIC_COLS are divided by 100 during parsing.
- **FIRST_YEAR=2010**: Matches CVM DFP start year. No need to go earlier — no financial statements before 2010.

---

*Last updated: 2026-07-25 (v1.0).*
