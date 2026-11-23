"""data_sources/b3/cotahist/query_engine.py -- Query COTAHIST data.

Read-only queries against cotahist.db:
  - query(ticker, date_from, date_to, year, limit) — OHLCV history
  - market_snapshot() — latest-session close + previous close per symbol
    (the WebUI landing page rankings: most traded / gainers / losers;
    quote enrichment for index constituents) [v1.19]
  - DB stats (years synced, row counts, date range)
"""

from __future__ import annotations

import re

from data_sources.b3.cotahist.catalog import connect, db_path

# B3 share-like symbols (PETR4, BOVA11, UNIT11, AAPL34…) — the same shape
# the WebUI ticker validation uses. Filters option series (PETRF274 —
# 3 trailing digits) and malformed codes out of the market-wide snapshot.
_SYMBOL_RE = re.compile(r"^[A-Z]{4,6}\d{1,2}[A-Z]?$")


def query(
    ticker: str = "",
    date_from: str = "",
    date_to: str = "",
    year: int = 0,
    limit: int = 100,
    market_type: int = 10,
) -> dict:
    """Query historical OHLCV from COTAHIST.

    Args:
        ticker: Ticker symbol (PETR4). Empty = all tickers.
        date_from: Start date YYYY-MM-DD.
        date_to: End date YYYY-MM-DD.
        year: Filter by year (e.g., 2025). Takes precedence over date_from/date_to.
        limit: Max rows. Default: 100.
        market_type: Filter by market type. 10=lote padrão (default, avoids
                     duplicate rows from fractional market). 0 = all market types.

    Returns:
        Dict with OHLCV rows.
    """
    try:
        conn = connect(read_only=True)
    except FileNotFoundError as e:
        return {"status": "not_synced", "error": str(e)}

    try:
        conditions = []
        params: list = []

        if ticker:
            conditions.append("symbol = ?")
            params.append(ticker.strip().upper())

        if year:
            conditions.append("refdate LIKE ?")
            params.append(f"{year}%")
        else:
            if date_from:
                conditions.append("refdate >= ?")
                params.append(date_from)
            if date_to:
                conditions.append("refdate <= ?")
                params.append(date_to)

        # [v1.0.1] Filter by market_type to avoid duplicate rows (lote padrão vs fracionário)
        if market_type > 0:
            conditions.append("market_type = ?")
            params.append(market_type)

        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""

        rows = conn.execute(
            f"""SELECT refdate, symbol, corp_name, open, high, low, close,
                      average, volume, trade_count, contracts, isin,
                      market_type, bdi_code, best_bid, best_ask
               FROM cotahist {where}
               ORDER BY refdate DESC, symbol
               LIMIT ?""",
            params + [limit],
        ).fetchall()

        if not rows:
            return {"status": "not_found", "count": 0, "rows": []}

        return {
            "status": "ok",
            "count": len(rows),
            "rows": [dict(r) for r in rows],
        }
    finally:
        conn.close()


# [v1.19 fix 1] The snapshot only needs each symbol's LATEST and PREVIOUS
# session — restricting the window functions to the last few sessions turns
# a whole-history scan (minutes on a multi-year cotahist.db) into an indexed
# sub-second query. 10 sessions is generous headroom: DENSE_RANK s=1/s=2
# within the window are the true latest/previous sessions for every symbol
# that traded in it (only symbols silent for 10+ sessions fall out — none
# of them belong on a landing-page ranking).
_SNAPSHOT_SESSIONS = 10


def market_snapshot() -> dict:
    """Latest-session snapshot for EVERY symbol — close + previous close.

    [WebUI v1.19] Powers the landing page rankings (most traded / maiores
    altas / maiores baixas) and the quote enrichment of the index top-10
    cards (value + variação vs previous close per constituent).

    Scope: lote padrão spot rows (market_type=10, bdi_code=2 — stocks,
    units, BDRs, ETFs, FIIs; drops subscription rights / split receipts
    / fractional-market duplicates), close > 0, share-like symbols only.

    [v1.19 fix 1] PERF: the window functions originally ran over the WHOLE
    table — every session ever synced, all BDIs — which took minutes on a
    real multi-year cotahist.db (and the landing page fired it repeatedly).
    Now a cheap indexed ``DISTINCT refdate`` query takes the last
    ``_SNAPSHOT_SESSIONS`` sessions and the CTE is restricted to them
    (``refdate >= floor`` rides the idx_cotahist_refdate range scan).

    Returns::

        {
          "status": "ok",
          "session_date": "2026-11-20",       # latest session overall
          "symbols": [
            {"ticker": "PETR4", "name": "PETROBRAS PN N2",
             "close": 34.5, "prev_close": 38.9,     # None when single-session
             "variation_pct": -11.31,               # None without prev_close
             "volume": 2.1e9, "trade_count": 88000},
            ...
          ]
        }

    "not_synced" when cotahist.db is missing; "not_found" when the table
    is empty. Rankings are the caller's job (presentation, not data).
    """
    try:
        conn = connect(read_only=True)
    except FileNotFoundError as e:
        return {"status": "not_synced", "error": str(e)}

    try:
        # Step 1 — the last N sessions overall (reverse index scan on
        # idx_cotahist_refdate; microseconds even on a huge table).
        sessions = [
            r[0] for r in conn.execute(
                "SELECT DISTINCT refdate FROM cotahist "
                "ORDER BY refdate DESC LIMIT ?",
                (_SNAPSHOT_SESSIONS,),
            ).fetchall()
        ]
        if not sessions:
            return {"status": "not_found", "count": 0, "symbols": []}
        floor = min(sessions)

        # Step 2 — the ranked CTE, restricted to the recent window.
        rows = conn.execute(
            """
            WITH scoped AS (
              SELECT symbol, corp_name, refdate, close, volume, trade_count
              FROM cotahist
              WHERE market_type = 10 AND bdi_code = 2
                AND close IS NOT NULL AND close > 0
                AND refdate >= ?
            ),
            deduped AS (
              SELECT symbol, corp_name, refdate, close, volume, trade_count,
                     ROW_NUMBER() OVER (
                       PARTITION BY symbol, refdate
                       ORDER BY volume DESC, trade_count DESC) AS d,
                     DENSE_RANK() OVER (
                       PARTITION BY symbol ORDER BY refdate DESC) AS s
              FROM scoped
            )
            SELECT r1.symbol, r1.corp_name, r1.refdate,
                   r1.close, r1.volume, r1.trade_count,
                   r2.close AS prev_close
            FROM deduped r1
            LEFT JOIN deduped r2
              ON r2.symbol = r1.symbol AND r2.s = 2 AND r2.d = 1
            WHERE r1.d = 1 AND r1.s = 1
            """,
            (floor,),
        ).fetchall()
    finally:
        conn.close()

    if not rows:
        return {"status": "not_found", "count": 0, "symbols": []}

    symbols: list[dict] = []
    session_date = ""
    for r in rows:
        ticker = (r["symbol"] or "").strip().upper()
        if not _SYMBOL_RE.match(ticker):
            continue
        close = float(r["close"])
        prev = float(r["prev_close"]) if r["prev_close"] else None
        variation = ((close / prev) - 1.0) * 100.0 if prev else None
        if r["refdate"] and r["refdate"] > session_date:
            session_date = r["refdate"]
        symbols.append({
            "ticker": ticker,
            "name": (r["corp_name"] or "").strip(),
            "close": close,
            "prev_close": prev,
            "variation_pct": variation,
            "volume": float(r["volume"]) if r["volume"] else 0.0,
            "trade_count": int(r["trade_count"]) if r["trade_count"] else 0,
        })

    return {
        "status": "ok",
        "session_date": session_date,
        "count": len(symbols),
        "symbols": symbols,
    }
