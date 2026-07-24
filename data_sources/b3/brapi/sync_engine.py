"""data_sources/b3/brapi/sync_engine.py -- Sync brapi.dev data to local SQLite.

Two sync modes:
  1. sync_tickers() — fetch the full ticker list (1,796 tickers in 1 call)
  2. sync_history() — fetch historical OHLCV for a ticker and store to SQLite

The ticker sync replaces the 7,138-page InstrumentsConsolidated crawl.
The history sync gives us OHLCV data we don't have from the B3 API.
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone

from data_sources.b3.brapi.catalog import connect, ensure_schema, db_path
from data_sources.b3.brapi.fetcher import fetch_tickers, fetch_history


def _progress(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── Sync: tickers ────────────────────────────────────────────────────────────

def sync_tickers(force: bool = False) -> dict:
    """Sync the full ticker list from brapi.dev to brapi.db.

    This replaces the 7,138-page InstrumentsConsolidated sync.
    1 call → ~1,796 tickers.

    Args:
        force: Re-fetch even if recently synced.
    """
    result = fetch_tickers(force=force)
    if result.get("status") != "ok":
        return result

    tickers = result["tickers"]
    now = _now()

    conn = connect(read_only=False)
    ensure_schema(conn)
    try:
        # Full replace
        conn.execute("DELETE FROM tickers")
        conn.executemany(
            "INSERT INTO tickers (symbol, synced_at) VALUES (?, ?)",
            [(t, now) for t in tickers],
        )
        conn.execute(
            "INSERT OR REPLACE INTO sync_state (key, value, synced_at) "
            "VALUES ('tickers', ?, ?)",
            (str(len(tickers)), now),
        )
        conn.commit()
    finally:
        conn.close()

    _progress(f"[brapi] Synced {len(tickers):,} tickers")
    return {
        "status": "ok",
        "tickers_synced": len(tickers),
        "synced_at": now,
    }


# ── Sync: historical OHLCV ───────────────────────────────────────────────────

def sync_history(ticker: str, range: str = "1y", interval: str = "1d",
                 force: bool = False) -> dict:
    """Sync historical OHLCV for a ticker from brapi.dev to brapi.db.

    Args:
        ticker: B3 ticker (PETR4).
        range: Time range (1d, 5d, 1mo, 3mo, 6mo, 1y, 2y, 5y, 10y, ytd, max).
        interval: Bar interval (1d, 5d, 1wk, 1mo, 3mo).
        force: Re-fetch even if already synced.

    Returns:
        Dict with sync status + row count.
    """
    if not ticker:
        return {"status": "error", "error": "ticker is required"}

    ticker = ticker.strip().upper()
    now = _now()

    # Check if already synced (unless force)
    if not force:
        conn = connect(read_only=False)
        ensure_schema(conn)
        try:
            existing = conn.execute(
                "SELECT COUNT(*) as n FROM quotes WHERE symbol=?", (ticker,),
            ).fetchone()
            if existing and existing["n"] > 0:
                return {"status": "skipped", "ticker": ticker,
                        "rows": existing["n"]}
        finally:
            conn.close()

    # Fetch from brapi
    result = fetch_history(ticker, range=range, interval=interval, force=force)
    if result.get("status") != "ok":
        return result

    ohlcv = result.get("ohlcv", [])
    if not ohlcv:
        return {"status": "empty", "ticker": ticker,
                "error": "No OHLCV data returned"}

    conn = connect(read_only=False)
    ensure_schema(conn)
    try:
        # Delete old data for this ticker
        conn.execute("DELETE FROM quotes WHERE symbol=?", (ticker,))

        # Insert new data
        rows = []
        for bar in ohlcv:
            # Convert epoch to YYYY-MM-DD
            epoch = bar.get("date", 0)
            date_str = datetime.fromtimestamp(epoch, tz=timezone.utc).strftime("%Y-%m-%d")
            rows.append((
                ticker,
                date_str,
                bar.get("open"),
                bar.get("high"),
                bar.get("low"),
                bar.get("close"),
                bar.get("adjustedClose"),
                bar.get("volume"),
                now,
            ))

        conn.executemany(
            "INSERT OR REPLACE INTO quotes "
            "(symbol, date, open, high, low, close, adjusted_close, volume, synced_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            rows,
        )
        conn.execute(
            "INSERT OR REPLACE INTO sync_state (key, value, synced_at) "
            "VALUES (?, ?, ?)",
            (f"history:{ticker}:{range}:{interval}", str(len(rows)), now),
        )
        conn.commit()
    finally:
        conn.close()

    _progress(f"[brapi] {ticker}: {len(rows)} OHLCV bars synced ({range}/{interval})")
    return {
        "status": "ok",
        "ticker": ticker,
        "rows": len(rows),
        "range": range,
        "interval": interval,
        "synced_at": now,
    }
