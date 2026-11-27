"""data_sources/b3/cotahist/query_engine.py -- Query COTAHIST data.

Read-only queries against cotahist.db:
  - query(ticker, date_from, date_to, year, limit) — OHLCV history
  - market_snapshot() — latest-session close + previous close per symbol
    (the WebUI landing page rankings: most traded / gainers / losers;
    quote enrichment for index constituents) [v1.19]
  - quotes_for(symbols) — same quote shape for a GIVEN symbol list, each
    at its OWN last session (portfolio valuation: illiquid papers silent
    for 10+ sessions still get their last traded price) [v1.21]
  - range_52w(symbols) — trailing-52-week high/low per symbol (the
    Painel's Tickers Observados "Máx/Mín 52 sem" columns) [v1.28.3]
  - series_52w(symbols) — trailing-52-week close series per symbol,
    resampled to ≤40 points (the Painel ticker cards' sparklines) [v1.28.3]
  - DB stats (years synced, row counts, date range)
"""

from __future__ import annotations

import re
from datetime import date, timedelta

from data_sources.b3.cotahist.catalog import connect, db_path, BDI_SHARE_LIKE

# B3 share-like symbols (PETR4, BOVA11, UNIT11, AAPL34…) — the same shape
# the WebUI ticker validation uses. Filters option series (PETRF274 —
# 3 trailing digits) and malformed codes out of the market-wide snapshot.
_SYMBOL_RE = re.compile(r"^[A-Z]{4,6}\d{1,2}[A-Z]?$")

# [v1.28.2] The quotable universe in the WHERE clauses below — the share-like
# BDI set as an SQL IN list ("bdi_code = 2" was the old scope: equities only,
# which silently hid ETFs — BDI 14 — from the landing page's BOVA11/SMAL11/
# IVVB11 KPI row, and would have hidden the BDR rows too).
_BDI_IN = "(" + ",".join(str(c) for c in sorted(BDI_SHARE_LIKE)) + ")"


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

    Scope: lote padrão spot rows (market_type=10, bdi_code IN (2, 12, 14,
    34, 35, 36) — the share-like universe: stocks, units, FIIs, ETFs and
    BDRs, no subscription rights / split receipts / fractional-market
    duplicates, close > 0, share-like symbols only. [v1.28.2] the scope
    used to be bdi_code=2 (equities): the ETFs (BDI 14) never reached the
    quotes map, so the Painel's BOVA11/SMAL11/IVVB11 KPI row rendered
    empty and BDR rows (BDI 34/35/36, once synced) would have met the
    same fate; each symbol row now carries its ``bdi_code`` so the
    callers can slice the universe (the rankings stay equities-only, the
    BDR card scopes by ticker, the ETF row reads the three tickers).

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
             "bdi_code": 2,                       # 2=equity 12=FII 14=ETF
             "close": 34.5, "prev_close": 38.9,   # None when single-session
             "variation_pct": -11.31,             # None without prev_close
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
            f"""
            WITH scoped AS (
              SELECT symbol, corp_name, refdate, bdi_code, close, volume, trade_count
              FROM cotahist
              WHERE market_type = 10 AND bdi_code IN {_BDI_IN}
                AND close IS NOT NULL AND close > 0
                AND refdate >= ?
            ),
            deduped AS (
              SELECT symbol, corp_name, refdate, bdi_code, close, volume, trade_count,
                     ROW_NUMBER() OVER (
                       PARTITION BY symbol, refdate
                       ORDER BY volume DESC, trade_count DESC) AS d,
                     DENSE_RANK() OVER (
                       PARTITION BY symbol ORDER BY refdate DESC) AS s
              FROM scoped
            )
            SELECT r1.symbol, r1.corp_name, r1.refdate, r1.bdi_code,
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
            "bdi_code": int(r["bdi_code"]) if r["bdi_code"] else None,
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


# [v1.21] Portfolio quotes — latest + previous close for a GIVEN symbol
# list. market_snapshot() windows the scan to the last _SNAPSHOT_SESSIONS
# sessions (the landing-page rankings only care about actives); an
# illiquid paper silent for 10+ sessions falls out of that window, which
# is wrong for portfolio valuation (the LAST TRADED price is the honest
# "Valor Hoje"). This variant rides idx_cotahist_symbol instead: the
# filter IS the bound, so per-symbol window functions run over each
# symbol's own history (a few thousand rows each — sub-second for a
# whole portfolio). Same deduped CTE + row shape as market_snapshot().
def quotes_for(symbols: list[str]) -> dict:
    """Latest-session quote per requested symbol (own last session).

    [v1.28.2] Same share-like universe as market_snapshot() (equities,
    FIIs, ETFs, BDRs — bdi_code IN (2, 12, 14, 34, 35, 36)): a portfolio
    can hold any of them, and the old ``bdi_code = 2`` scope left ETF/FII/
    BDR positions quote-less.

    [v1.28.3] Each symbol ALSO carries its own last session's
    HIGH/LOW (``day_high``/``day_low``) — the Painel's ⭐ Tickers
    Observados "Mín (dia) / Máx (dia)" columns. NULL high/low (the
    fixture shape) degrades to None → "—".

    Returns the market_snapshot() symbols shape filtered to ``symbols``
    plus the day range::

        {"status": "ok",
         "symbols": [{"ticker": "POMO4", "name": "MARCOPOLO",
                      "bdi_code": 2,
                      "close": 2.44, "prev_close": 2.40,
                      "variation_pct": 1.67,
                      "volume": 1.2e5, "trade_count": 340,
                      "day_high": 2.50, "day_low": 2.38}],
         "session_date": "2026-11-20"}    # latest refdate among the returns

    "not_synced" when cotahist.db is missing. Symbols with no rows are
    simply absent from ``symbols`` (the caller degrades per-ticker).
    Invalid shapes are dropped (the _SYMBOL_RE guard).
    """
    wanted = sorted({(s or "").strip().upper() for s in symbols
                     if _SYMBOL_RE.match((s or "").strip().upper())})
    if not wanted:
        return {"status": "ok", "session_date": "", "symbols": []}

    try:
        conn = connect(read_only=True)
    except FileNotFoundError as e:
        return {"status": "not_synced", "error": str(e)}

    out: list[dict] = []
    session_date = ""
    try:
        # SQLite's default host-parameter limit is 999 — chunk defensively.
        for i in range(0, len(wanted), 500):
            chunk = wanted[i:i + 500]
            marks = ",".join("?" * len(chunk))
            rows = conn.execute(
                f"""
                WITH scoped AS (
                  SELECT symbol, corp_name, refdate, bdi_code, close, high, low,
                         volume, trade_count
                  FROM cotahist
                  WHERE market_type = 10 AND bdi_code IN {_BDI_IN}
                    AND close IS NOT NULL AND close > 0
                    AND symbol IN ({marks})
                ),
                deduped AS (
                  SELECT symbol, corp_name, refdate, bdi_code, close, high, low,
                         volume, trade_count,
                         ROW_NUMBER() OVER (
                           PARTITION BY symbol, refdate
                           ORDER BY volume DESC, trade_count DESC) AS d,
                         DENSE_RANK() OVER (
                           PARTITION BY symbol ORDER BY refdate DESC) AS s
                  FROM scoped
                )
                SELECT r1.symbol, r1.corp_name, r1.refdate, r1.bdi_code,
                       r1.close, r1.volume, r1.trade_count,
                       r1.high AS day_high, r1.low AS day_low,
                       r2.close AS prev_close
                FROM deduped r1
                LEFT JOIN deduped r2
                  ON r2.symbol = r1.symbol AND r2.s = 2 AND r2.d = 1
                WHERE r1.d = 1 AND r1.s = 1
                """,
                chunk,
            ).fetchall()
            for r in rows:
                close = float(r["close"])
                prev = float(r["prev_close"]) if r["prev_close"] else None
                variation = ((close / prev) - 1.0) * 100.0 if prev else None
                if r["refdate"] and r["refdate"] > session_date:
                    session_date = r["refdate"]
                out.append({
                    "ticker": (r["symbol"] or "").strip().upper(),
                    "name": (r["corp_name"] or "").strip(),
                    "bdi_code": int(r["bdi_code"]) if r["bdi_code"] else None,
                    "close": close,
                    "prev_close": prev,
                    "variation_pct": variation,
                    "volume": float(r["volume"]) if r["volume"] else 0.0,
                    "trade_count": int(r["trade_count"]) if r["trade_count"] else 0,
                    # [v1.28.3] The OWN session's high/low — the
                    # Painel's ⭐ Tickers Observados "Mín/Máx (dia)"
                    # columns. NULL (the fixture shape) degrades to None
                    # → "—" on the row.
                    "day_high": float(r["day_high"]) if r["day_high"] else None,
                    "day_low": float(r["day_low"]) if r["day_low"] else None,
                })
    finally:
        conn.close()

    return {"status": "ok", "session_date": session_date,
            "count": len(out), "symbols": out}


# [v1.28.3] The Painel's Tickers Observados gained "Máx/Mín 52 sem"
# columns — the trailing-52-week range per watched ticker. The window is
# anchored on the DB's OWN latest refdate (not the wall clock): a stale
# sync still yields the honest 52-week window of the data we have, and
# the query never depends on the machine's date.
_52W_DAYS = 365


def range_52w(symbols: list[str]) -> dict:
    """Trailing-52-week high + low for a GIVEN symbol list.

    Same universe as quotes_for() (lote padrão, share-like BDIs, close >
    0) plus ``high > 0 AND low > 0`` — a spurious zero print would own
    the MIN. Rows with NULL high/low (the fixture shape) are simply not
    aggregated by MAX/MIN.

    Returns::

        {"status": "ok",
         "symbols": [{"ticker": "PETR4", "high_52": 40.10, "low_52": 30.15},
                     ...],
         "window_from": "2025-11-26",   # cutoff actually used
         "ref_date": "2026-11-26"}      # the DB's latest refdate

    "not_synced" when cotahist.db is missing; symbols with no rows in
    the window are simply absent from ``symbols`` (the caller degrades
    per-ticker). Invalid shapes are dropped (the _SYMBOL_RE guard).
    """
    wanted = sorted({(s or "").strip().upper() for s in symbols
                     if _SYMBOL_RE.match((s or "").strip().upper())})
    if not wanted:
        return {"status": "ok", "symbols": [], "window_from": "",
                "ref_date": ""}

    try:
        conn = connect(read_only=True)
    except FileNotFoundError as e:
        return {"status": "not_synced", "error": str(e)}

    try:
        row = conn.execute(
            "SELECT MAX(refdate) AS latest FROM cotahist "
            "WHERE market_type = 10 AND bdi_code IN " + _BDI_IN
        ).fetchone()
        latest = (row["latest"] if row else None) or ""
        if not latest:
            return {"status": "not_found", "symbols": [],
                    "window_from": "", "ref_date": ""}
        # latest is YYYY-MM-DD — the arithmetic rides Python's date.
        cutoff = (date.fromisoformat(latest) - timedelta(days=_52W_DAYS)
                  ).isoformat()

        out: list[dict] = []
        # SQLite's default host-parameter limit is 999 — chunk defensively.
        for i in range(0, len(wanted), 500):
            chunk = wanted[i:i + 500]
            marks = ",".join("?" * len(chunk))
            rows = conn.execute(
                f"""
                SELECT symbol, MAX(high) AS high_52, MIN(low) AS low_52
                FROM cotahist
                WHERE market_type = 10 AND bdi_code IN {_BDI_IN}
                  AND close IS NOT NULL AND close > 0
                  AND high IS NOT NULL AND high > 0
                  AND low IS NOT NULL AND low > 0
                  AND refdate >= ? AND symbol IN ({marks})
                GROUP BY symbol
                """,
                [cutoff, *chunk],
            ).fetchall()
            for r in rows:
                out.append({
                    "ticker": (r["symbol"] or "").strip().upper(),
                    "high_52": float(r["high_52"]) if r["high_52"] else None,
                    "low_52": float(r["low_52"]) if r["low_52"] else None,
                })
    finally:
        conn.close()

    return {"status": "ok", "symbols": out,
            "window_from": cutoff, "ref_date": latest}


# [v1.28.3] The Painel's ticker KPI cards render a SPARKLINE of the
# trailing 52 weeks — the same window range_52w() aggregates, as the close
# SERIES instead of the high/low bounds. The resample cap keeps the payload
# light (12 cards × 40 points ≈ 480 floats — a full daily series would be
# ~3.000) while the line still reads as the year's shape: the stride
# sampling keeps the first point, every Nth close and ALWAYS the last one
# (the last close is the dot the price tag points at — it must be there).
_SERIES_MAX_POINTS = 40


def series_52w(symbols: list[str],
               max_points: int = _SERIES_MAX_POINTS) -> dict:
    """Trailing-52-week CLOSE series per symbol, resampled to max_points.

    Same universe and window anchor as range_52w() (lote padrão,
    share-like BDIs, close > 0, cutoff on the DB's OWN latest refdate —
    a stale sync still yields the honest window of the data we have).
    The series is ASCENDING by date and ends on the symbol's LAST close
    in the window (the sparkline's right edge = the quoted price).

    Returns::

        {"status": "ok",
         "symbols": [{"ticker": "PETR4",
                      "points": [38.10, 37.95, ...],   # ≤ max_points
                      "last": 38.10}, ...],            # points[-1]
         "window_from": "2025-11-26",   # cutoff actually used
         "ref_date": "2026-11-26"}      # the DB's latest refdate

    "not_synced" when cotahist.db is missing; symbols with no rows in
    the window are simply absent from ``symbols`` (the caller degrades
    per-ticker). Invalid shapes are dropped (the _SYMBOL_RE guard).
    """
    wanted = sorted({(s or "").strip().upper() for s in symbols
                     if _SYMBOL_RE.match((s or "").strip().upper())})
    if not wanted:
        return {"status": "ok", "symbols": [], "window_from": "",
                "ref_date": ""}

    try:
        conn = connect(read_only=True)
    except FileNotFoundError as e:
        return {"status": "not_synced", "error": str(e)}

    def _resample(closes: list[float]) -> list[float]:
        """Stride-sample to ≤ max_points, ALWAYS keeping first + last."""
        n = len(closes)
        if n <= max_points:
            return closes
        step = n / float(max_points)
        # max_points - 1 stride picks + the last close → ≤ max_points
        idxs = {int(i * step) for i in range(max_points - 1)}
        idxs.add(n - 1)          # the sparkline's dot = the last close
        return [closes[i] for i in sorted(idxs)]

    try:
        row = conn.execute(
            "SELECT MAX(refdate) AS latest FROM cotahist "
            "WHERE market_type = 10 AND bdi_code IN " + _BDI_IN
        ).fetchone()
        latest = (row["latest"] if row else None) or ""
        if not latest:
            return {"status": "not_found", "symbols": [],
                    "window_from": "", "ref_date": ""}
        cutoff = (date.fromisoformat(latest) - timedelta(days=_52W_DAYS)
                  ).isoformat()

        out: list[dict] = []
        # SQLite's default host-parameter limit is 999 — chunk defensively.
        for i in range(0, len(wanted), 500):
            chunk = wanted[i:i + 500]
            marks = ",".join("?" * len(chunk))
            rows = conn.execute(
                f"""
                SELECT symbol, refdate, close
                FROM cotahist
                WHERE market_type = 10 AND bdi_code IN {_BDI_IN}
                  AND close IS NOT NULL AND close > 0
                  AND refdate >= ? AND symbol IN ({marks})
                ORDER BY symbol, refdate
                """,
                [cutoff, *chunk],
            ).fetchall()
            by_sym: dict[str, list[float]] = {}
            for r in rows:
                by_sym.setdefault((r["symbol"] or "").strip().upper(),
                                   []).append(float(r["close"]))
            for sym, closes in by_sym.items():
                points = _resample(closes)
                out.append({"ticker": sym, "points": points,
                            "last": points[-1]})
    finally:
        conn.close()

    return {"status": "ok", "symbols": out,
            "window_from": cutoff, "ref_date": latest}
