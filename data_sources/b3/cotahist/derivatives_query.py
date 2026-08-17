"""data_sources/b3/cotahist/derivatives_query.py -- Derivatives query functions.

Query the `cotahist_derivatives` table (same DB as equities).
Functions for options (chain, P/C ratio, volume by strike, exercise),
term (chain, history), and general derivatives stats.

[v1.2] Merged from the former `data_sources/b3/cotahist_derivatives/` sub-domain.
All derivatives data lives in the same cotahist.db -- no separate data source.

[v3] Term queries now query by `underlying` column (not `symbol`). Stock
tickers are stripped to the company root (PETR4 -> PETR) for the lookup.
Index tickers (IBOV, IBRX, SMLL) are used as-is. Stock term contracts
(BDI 26) are largely NOT in COTAHIST (B3 routes them to BTC -- Balcao
Organizado); the error message suggests ticker='IBOV' for index term data
(BDI 74, which IS in COTAHIST -- 134K+ rows of IBOV futures).
"""
from __future__ import annotations

from data_sources.b3.cotahist.catalog import connect
from data_sources.b3.cotahist.catalog import STOCK_EXERCISE_BDI, TERM_BDI


# -- Helpers -----------------------------------------------------------------

def _strip_trailing_digits(s: str) -> str:
    """Strip trailing digits from a ticker (PETR4 -> PETR, VALE3 -> VALE).

    For indices like IBOV, IBRX, SMLL (no trailing digit), returns as-is.
    """
    s = s.strip().upper()
    while s and s[-1].isdigit():
        s = s[:-1]
    return s


def _is_stock_ticker(ticker: str) -> bool:
    """Check if a ticker looks like a stock (ends with digit) vs an index."""
    t = ticker.strip().upper()
    return bool(t) and t[-1].isdigit()


# -- Options queries ---------------------------------------------------------

def options_chain(underlying: str = "", maturity: str = "", limit: int = 200) -> dict:
    """Get the options chain for an underlying + optional maturity.

    Args:
        underlying: 4-letter code (e.g. "PETR"). Also accepts full tickers
                    like "PETR4" -- the "4" is stripped automatically.
        maturity:   YYYY-MM-DD expiration date (optional -- if empty, returns
                    the nearest maturity).
        limit:      Max results. Default 200.

    Returns:
        {"status": "ok", "underlying": ..., "maturity": ..., "count": N,
         "options": [{symbol, bdi_code, option_type, strike, strike_parsed,
                      maturity, close, volume, best_bid, best_ask, ...}, ...]}
    """
    if not underlying:
        return {"status": "error", "error": "underlying is required"}

    u = _strip_trailing_digits(underlying)
    if not u:
        return {"status": "error", "error": f"invalid underlying: {underlying}"}

    try:
        conn = connect(read_only=True)
    except FileNotFoundError as e:
        return {"status": "not_synced", "error": str(e)}

    try:
        if not maturity:
            row = conn.execute(
                "SELECT DISTINCT maturity FROM cotahist_derivatives "
                "WHERE underlying = ? AND maturity IS NOT NULL AND maturity >= date('now') "
                "ORDER BY maturity ASC LIMIT 1",
                (u,),
            ).fetchone()
            if row:
                maturity = row["maturity"]
            else:
                row = conn.execute(
                    "SELECT DISTINCT maturity FROM cotahist_derivatives "
                    "WHERE underlying = ? AND maturity IS NOT NULL "
                    "ORDER BY maturity DESC LIMIT 1",
                    (u,),
                ).fetchone()
                if row:
                    maturity = row["maturity"]

        if not maturity:
            return {"status": "not_found", "underlying": u,
                    "error": f"no options found for {u}"}

        latest_row = conn.execute(
            "SELECT MAX(refdate) as latest FROM cotahist_derivatives "
            "WHERE underlying = ? AND maturity = ?",
            (u, maturity),
        ).fetchone()
        latest_date = latest_row["latest"] if latest_row else None

        if not latest_date:
            return {"status": "not_found", "underlying": u, "maturity": maturity,
                    "error": f"no data for {u} maturity {maturity}"}

        rows = conn.execute(
            """SELECT symbol, bdi_code, market_type, corp_name, spec_code,
                      open, high, low, close, best_bid, best_ask,
                      trade_count, contracts, volume, strike, strike_parsed,
                      maturity, option_type, underlying, refdate
               FROM cotahist_derivatives
               WHERE underlying = ? AND maturity = ? AND refdate = ?
               ORDER BY option_type, strike_parsed""",
            (u, maturity, latest_date),
        ).fetchall()

        if not rows:
            return {"status": "not_found", "underlying": u, "maturity": maturity,
                    "error": f"no options for {u} maturity {maturity} on {latest_date}"}

        options = [dict(r) for r in rows]
        return {
            "status": "ok",
            "underlying": u,
            "maturity": maturity,
            "refdate": latest_date,
            "count": len(options),
            "options": options,
        }
    finally:
        conn.close()


def available_maturities(underlying: str = "") -> dict:
    """Get all available expiration dates for an underlying."""
    if not underlying:
        return {"status": "error", "error": "underlying is required"}

    u = _strip_trailing_digits(underlying)

    try:
        conn = connect(read_only=True)
    except FileNotFoundError as e:
        return {"status": "not_synced", "error": str(e)}

    try:
        rows = conn.execute(
            "SELECT maturity, COUNT(*) as count "
            "FROM cotahist_derivatives WHERE underlying = ? AND maturity IS NOT NULL "
            "GROUP BY maturity ORDER BY maturity ASC",
            (u,),
        ).fetchall()
        if not rows:
            return {"status": "not_found", "underlying": u,
                    "error": f"no options found for {u}"}
        return {
            "status": "ok",
            "underlying": u,
            "maturities": [{"maturity": r["maturity"], "count": r["count"]} for r in rows],
        }
    finally:
        conn.close()


def put_call_ratio(underlying: str = "", days: int = 90) -> dict:
    """Compute daily put/call ratio (volume-based) for an underlying.

    P/C ratio = total put volume / total call volume per day.
    High ratio (>1) = bearish sentiment. Low (<1) = bullish.
    """
    if not underlying:
        return {"status": "error", "error": "underlying is required"}

    u = _strip_trailing_digits(underlying)

    try:
        conn = connect(read_only=True)
    except FileNotFoundError as e:
        return {"status": "not_synced", "error": str(e)}

    try:
        rows = conn.execute(
            """SELECT refdate,
                      SUM(CASE WHEN option_type = 'CALL' THEN volume ELSE 0 END) as call_vol,
                      SUM(CASE WHEN option_type = 'PUT'  THEN volume ELSE 0 END) as put_vol
               FROM cotahist_derivatives
               WHERE underlying = ?
               GROUP BY refdate
               ORDER BY refdate DESC
               LIMIT ?""",
            (u, days),
        ).fetchall()

        if not rows:
            return {"status": "not_found", "underlying": u,
                    "error": f"no options data for {u}"}

        observations = []
        for r in reversed(rows):
            call_vol = r["call_vol"] or 0
            put_vol = r["put_vol"] or 0
            ratio = (put_vol / call_vol) if call_vol > 0 else None
            observations.append({
                "ref_date": r["refdate"],
                "call_volume": call_vol,
                "put_volume": put_vol,
                "ratio": ratio,
            })

        return {
            "status": "ok",
            "underlying": u,
            "count": len(observations),
            "observations": observations,
        }
    finally:
        conn.close()


def volume_by_strike(underlying: str = "", maturity: str = "") -> dict:
    """Get total volume per strike for an underlying + maturity."""
    if not underlying:
        return {"status": "error", "error": "underlying is required"}

    u = _strip_trailing_digits(underlying)

    try:
        conn = connect(read_only=True)
    except FileNotFoundError as e:
        return {"status": "not_synced", "error": str(e)}

    try:
        if not maturity:
            row = conn.execute(
                "SELECT DISTINCT maturity FROM cotahist_derivatives "
                "WHERE underlying = ? AND maturity IS NOT NULL AND maturity >= date('now') "
                "ORDER BY maturity ASC LIMIT 1",
                (u,),
            ).fetchone()
            if row:
                maturity = row["maturity"]
            else:
                row = conn.execute(
                    "SELECT DISTINCT maturity FROM cotahist_derivatives "
                    "WHERE underlying = ? AND maturity IS NOT NULL "
                    "ORDER BY maturity DESC LIMIT 1",
                    (u,),
                ).fetchone()
                if row:
                    maturity = row["maturity"]

        if not maturity:
            return {"status": "not_found", "underlying": u,
                    "error": f"no options found for {u}"}

        latest_row = conn.execute(
            "SELECT MAX(refdate) as latest FROM cotahist_derivatives "
            "WHERE underlying = ? AND maturity = ?",
            (u, maturity),
        ).fetchone()
        latest_date = latest_row["latest"] if latest_row else None

        if not latest_date:
            return {"status": "not_found", "underlying": u, "maturity": maturity}

        rows = conn.execute(
            """SELECT strike_parsed,
                      SUM(CASE WHEN option_type = 'CALL' THEN volume ELSE 0 END) as call_vol,
                      SUM(CASE WHEN option_type = 'PUT'  THEN volume ELSE 0 END) as put_vol,
                      SUM(CASE WHEN option_type = 'CALL' THEN 1 ELSE 0 END) as call_count,
                      SUM(CASE WHEN option_type = 'PUT'  THEN 1 ELSE 0 END) as put_count
               FROM cotahist_derivatives
               WHERE underlying = ? AND maturity = ? AND refdate = ?
               GROUP BY strike_parsed
               ORDER BY strike_parsed""",
            (u, maturity, latest_date),
        ).fetchall()

        strikes = [{
            "strike": r["strike_parsed"],
            "call_volume": r["call_vol"] or 0,
            "put_volume": r["put_vol"] or 0,
            "call_count": r["call_count"],
            "put_count": r["put_count"],
        } for r in rows]

        return {
            "status": "ok",
            "underlying": u,
            "maturity": maturity,
            "refdate": latest_date,
            "count": len(strikes),
            "strikes": strikes,
        }
    finally:
        conn.close()


def exercise_summary(underlying: str = "", days: int = 90) -> dict:
    """Get daily exercise summary for stock options (BDI 38/42).

    Exercise = when option holders exercise their right to buy (calls) or
    sell (puts) the underlying stock at the strike price.
    """
    if not underlying:
        return {"status": "error", "error": "underlying is required"}

    u = _strip_trailing_digits(underlying)

    try:
        conn = connect(read_only=True)
    except FileNotFoundError as e:
        return {"status": "not_synced", "error": str(e)}

    try:
        bdi_list = ",".join(str(b) for b in STOCK_EXERCISE_BDI)
        rows = conn.execute(
            f"""SELECT refdate,
                       SUM(CASE WHEN bdi_code = 38 THEN volume ELSE 0 END) as call_ex_vol,
                       SUM(CASE WHEN bdi_code = 42 THEN volume ELSE 0 END) as put_ex_vol,
                       SUM(CASE WHEN bdi_code = 38 THEN contracts ELSE 0 END) as call_ex_count,
                       SUM(CASE WHEN bdi_code = 42 THEN contracts ELSE 0 END) as put_ex_count
                FROM cotahist_derivatives
                WHERE underlying = ? AND bdi_code IN ({bdi_list})
                GROUP BY refdate
                ORDER BY refdate DESC
                LIMIT ?""",
            (u, days),
        ).fetchall()

        if not rows:
            return {"status": "not_found", "underlying": u,
                    "error": f"no exercise data for {u}"}

        observations = []
        for r in reversed(rows):
            call_vol = r["call_ex_vol"] or 0
            put_vol = r["put_ex_vol"] or 0
            observations.append({
                "ref_date": r["refdate"],
                "call_exercise_volume": call_vol,
                "put_exercise_volume": put_vol,
                "total": call_vol + put_vol,
                "call_exercise_contracts": r["call_ex_count"] or 0,
                "put_exercise_contracts": r["put_ex_count"] or 0,
            })

        return {
            "status": "ok",
            "underlying": u,
            "count": len(observations),
            "observations": observations,
        }
    finally:
        conn.close()


# -- Term queries ------------------------------------------------------------
# [v3] Term queries search by `underlying` column (NOT `symbol`).
# - Indices (IBOV): underlying = "IBOV" -> matches 134K+ rows (BDI 74)
# - Stocks (PETR4): underlying = "PETR" (stripped) -> BDI 26 has 0 rows
#   (B3 routes stock term to BTC). The error message explains this.

def _term_not_found_response(ticker: str, underlying: str) -> dict:
    """Build a helpful 'not found' response for term queries.

    Explains WHY no data was found + suggests alternatives.
    """
    is_stock = _is_stock_ticker(ticker)
    if is_stock:
        return {
            "status": "not_found",
            "ticker": underlying,
            "error": (
                f"no term contracts for {ticker} (underlying={underlying}). "
                "Stock term contracts (BDI 26) are largely NOT available in "
                "COTAHIST -- B3 routes them to BTC (Balcao Organizado). "
                "COTAHIST term data is predominantly IBOV index futures "
                "(BDI 74). Try ticker='IBOV' for index term data."
            ),
        }
    return {
        "status": "not_found",
        "ticker": underlying,
        "error": f"no term contracts for {underlying}",
    }


def term_chain(ticker: str = "", limit: int = 100) -> dict:
    """Get active term contracts for a ticker.

    [v3] Queries by `underlying` column (not `symbol`).
    - Indices (IBOV, IBRX, SMLL): underlying = ticker as-is -> matches
      134K+ rows for IBOV (BDI 74).
    - Stocks (PETR4, VALE3): underlying = stripped company root (PETR, VALE)
      -> BDI 26 has 0 rows (B3 routes stock term to BTC).

    Args:
        ticker: Stock ticker (e.g. "PETR4") or index (e.g. "IBOV").
        limit:  Max results. Default 100.

    Returns:
        {"status": "ok", "ticker": ..., "count": N,
         "contracts": [{refdate, symbol, maturity, close, volume, contracts, days_settle}, ...]}
    """
    if not ticker:
        return {"status": "error", "error": "ticker is required"}

    t = ticker.strip().upper()
    u = _strip_trailing_digits(t)  # PETR4 -> PETR; IBOV -> IBOV

    try:
        conn = connect(read_only=True)
    except FileNotFoundError as e:
        return {"status": "not_synced", "error": str(e)}

    try:
        bdi_list = ",".join(str(b) for b in TERM_BDI)
        rows = conn.execute(
            f"""SELECT refdate, symbol, maturity, close, volume, contracts, days_settle,
                      best_bid, best_ask, open, high, low, trade_count
               FROM cotahist_derivatives
               WHERE underlying = ? AND bdi_code IN ({bdi_list})
               ORDER BY refdate DESC
               LIMIT ?""",
            (u, limit),
        ).fetchall()

        if not rows:
            return _term_not_found_response(t, u)

        contracts = [dict(r) for r in rows]
        return {
            "status": "ok",
            "ticker": u,
            "count": len(contracts),
            "contracts": contracts,
        }
    finally:
        conn.close()


def term_history(ticker: str = "", days: int = 90) -> dict:
    """Get daily term volume + term price history for a ticker.

    [v3] Queries by `underlying` column (not `symbol`).
    See `term_chain` for the lookup rules + data availability notes.

    Shows the daily total volume + average term price for term contracts.
    Used to plot the term market activity over time.

    Args:
        ticker: Stock ticker (e.g. "PETR4") or index (e.g. "IBOV").
        days:   Number of most-recent trading days. Default 90.

    Returns:
        {"status": "ok", "ticker": ..., "count": N,
         "observations": [{ref_date, total_volume, total_contracts, avg_price}, ...]}
    """
    if not ticker:
        return {"status": "error", "error": "ticker is required"}

    t = ticker.strip().upper()
    u = _strip_trailing_digits(t)

    try:
        conn = connect(read_only=True)
    except FileNotFoundError as e:
        return {"status": "not_synced", "error": str(e)}

    try:
        bdi_list = ",".join(str(b) for b in TERM_BDI)
        rows = conn.execute(
            f"""SELECT refdate,
                       SUM(volume) as total_vol,
                       SUM(contracts) as total_contracts,
                       AVG(close) as avg_price
               FROM cotahist_derivatives
               WHERE underlying = ? AND bdi_code IN ({bdi_list})
               GROUP BY refdate
               ORDER BY refdate DESC
               LIMIT ?""",
            (u, days),
        ).fetchall()

        if not rows:
            return _term_not_found_response(t, u)

        observations = []
        for r in reversed(rows):
            observations.append({
                "ref_date": r["refdate"],
                "total_volume": r["total_vol"] or 0,
                "total_contracts": r["total_contracts"] or 0,
                "avg_price": r["avg_price"],
            })

        return {
            "status": "ok",
            "ticker": u,
            "count": len(observations),
            "observations": observations,
        }
    finally:
        conn.close()
