"""data_sources/b3/cotahist_derivatives/query_engine.py -- Query derivatives data."""
from __future__ import annotations

from data_sources.b3.cotahist_derivatives.catalog import connect, BDI_LABELS, STOCK_EXERCISE_BDI


def options_chain(underlying: str = "", maturity: str = "", limit: int = 200) -> dict:
    """Get the options chain for an underlying + optional maturity.

    Args:
        underlying: 4-letter code (e.g. "PETR"). Also accepts full tickers
                    like "PETR4" — the "4" is stripped automatically.
        maturity:   YYYY-MM-DD expiration date (optional — if empty, returns
                    the nearest maturity).
        limit:      Max results. Default 200.

    Returns:
        {"status": "ok", "underlying": ..., "maturity": ..., "count": N,
         "options": [{symbol, bdi_code, option_type, strike, strike_parsed,
                      maturity, close, volume, best_bid, best_ask, ...}, ...]}
    """
    if not underlying:
        return {"status": "error", "error": "underlying is required"}

    # Normalize: strip trailing digits (PETR4 → PETR).
    u = underlying.strip().upper()
    while u and u[-1].isdigit():
        u = u[:-1]
    if not u:
        return {"status": "error", "error": f"invalid underlying: {underlying}"}

    try:
        conn = connect(read_only=True)
    except FileNotFoundError as e:
        return {"status": "not_synced", "error": str(e)}

    try:
        # If no maturity specified, find the nearest one.
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
                # No future maturities — get the most recent one.
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

        # Get the latest trading day for this underlying + maturity.
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
    """Get all available expiration dates for an underlying.

    Returns:
        {"status": "ok", "underlying": ..., "maturities": [{maturity, count}, ...]}
    """
    if not underlying:
        return {"status": "error", "error": "underlying is required"}

    u = underlying.strip().upper()
    while u and u[-1].isdigit():
        u = u[:-1]

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

    Args:
        underlying: 4-letter code (e.g. "PETR") or full ticker ("PETR4").
        days:       Number of most-recent trading days. Default 90.

    Returns:
        {"status": "ok", "underlying": ..., "count": N,
         "observations": [{ref_date, call_volume, put_volume, ratio}, ...]}
    """
    if not underlying:
        return {"status": "error", "error": "underlying is required"}

    u = underlying.strip().upper()
    while u and u[-1].isdigit():
        u = u[:-1]

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

        # Reverse to ascending order + compute ratio.
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
    """Get total volume per strike for an underlying + maturity.

    Returns call + put volume per strike, for the latest trading day.

    Returns:
        {"status": "ok", "underlying": ..., "maturity": ..., "refdate": ...,
         "strikes": [{strike, call_volume, put_volume, call_count, put_count}, ...]}
    """
    if not underlying:
        return {"status": "error", "error": "underlying is required"}

    u = underlying.strip().upper()
    while u and u[-1].isdigit():
        u = u[:-1]

    try:
        conn = connect(read_only=True)
    except FileNotFoundError as e:
        return {"status": "not_synced", "error": str(e)}

    try:
        # Find nearest maturity if not specified.
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

    Shows total call + put exercise volume per day for an underlying.
    Exercise = when option holders actually exercise their right to
    buy (calls) or sell (puts) the underlying stock at the strike price.

    Args:
        underlying: 4-letter code (e.g. "PETR") or full ticker ("PETR4").
        days:       Number of most-recent trading days. Default 90.

    Returns:
        {"status": "ok", "underlying": ..., "count": N,
         "observations": [{ref_date, call_exercise_vol, put_exercise_vol, total}, ...]}
    """
    if not underlying:
        return {"status": "error", "error": "underlying is required"}

    u = underlying.strip().upper()
    while u and u[-1].isdigit():
        u = u[:-1]

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
