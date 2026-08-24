"""data_sources/b3/api/query_engine.py -- Query B3 market data.

Query instruments (tickers, ISIN, company names), trades (prices, volume),
and other B3 tables stored in local SQLite DBs.
"""

from __future__ import annotations

import sqlite3
from typing import Any

from data_sources.b3.api.catalog import B3_TABLES, connect, db_path


def query(
    table: str = "instruments",
    ticker: str = "",
    columns: list[str] | None = None,
    filters: dict | None = None,
    limit: int = 100,
) -> dict:
    """Query B3 data from local SQLite DB.

    Args:
        table: Table name (instruments, trades, after_hours, derivatives).
        ticker: Ticker symbol filter (e.g., "PETR4"). Empty = all.
        columns: Specific columns to return. None = all.
        filters: Dict of {column: value} for additional filtering.
        limit: Max rows. Default: 100.

    Returns:
        Dict with rows + column names.
    """
    if table not in B3_TABLES:
        return {"status": "error",
                "error": f"Unknown table '{table}'. Available: {list(B3_TABLES.keys())}"}

    try:
        conn = connect(table, read_only=True)
    except FileNotFoundError as e:
        return {"status": "not_synced", "error": str(e)}

    try:
        db_table = B3_TABLES[table]["table"]

        # Get actual column names from the table
        col_rows = conn.execute(f"PRAGMA table_info({db_table})").fetchall()
        if not col_rows:
            return {"status": "error", "error": f"Table {db_table} has no columns. Run sync first."}
        all_cols = [r["name"] for r in col_rows if r["name"] != "_ingested_at"]

        # Select columns
        if columns:
            select_cols = [c for c in columns if c in all_cols]
            if not select_cols:
                select_cols = all_cols
        else:
            select_cols = all_cols
        select_str = ", ".join(select_cols)

        # Build WHERE
        conditions = []
        params: list = []

        if ticker and "TckrSymb" in all_cols:
            conditions.append("TckrSymb = ?")
            params.append(ticker.upper())

        if filters:
            for col, val in filters.items():
                if col in all_cols:
                    conditions.append(f"{col} LIKE ?")
                    params.append(f"%{val}%")

        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""

        rows = conn.execute(
            f"SELECT {select_str} FROM {db_table} {where} LIMIT ?",
            params + [limit],
        ).fetchall()

        if not rows:
            return {"status": "not_found", "table": table, "count": 0, "rows": []}

        return {
            "status": "ok",
            "table": table,
            "count": len(rows),
            "columns": select_cols,
            "rows": [dict(r) for r in rows],
        }

    finally:
        conn.close()


def lookup_ticker(ticker: str = "") -> dict:
    """Look up a single ticker in the instruments table.

    Returns company name, ISIN, segment, governance level, etc.
    """
    if not ticker:
        return {"status": "error", "error": "ticker is required"}

    result = query(table="instruments", ticker=ticker, limit=1)
    if result["status"] == "ok" and result["rows"]:
        return {"status": "ok", "ticker": ticker.upper(), "instrument": result["rows"][0]}
    return {"status": "not_found", "ticker": ticker, "error": f"Ticker '{ticker}' not found in instruments table"}


def search_company(name: str = "", limit: int = 20) -> dict:
    """Search instruments by company name fragment."""
    if not name:
        return {"status": "error", "error": "name is required"}

    result = query(
        table="instruments",
        filters={"CrpnNm": name},
        limit=limit,
    )
    if result["status"] == "ok":
        return {
            "status": "ok",
            "query": name,
            "count": result["count"],
            "instruments": result["rows"],
        }
    return result


# ── [v2.0] Open Positions (DerivativesOpenPosition) ─────────────────────────
#
# The derivatives.db table has 17 columns including:
#   TckrSymb      — option ticker (PETRA201)
#   SgmtNm        — "EQUITY CALL" or "EQUITY PUT" (also FORWARD, FINANCIAL...)
#   OpnIntrst     — open interest (total contracts)
#   VartnOpnIntrst — daily variation
#   CvrdQty       — covered quantity (Coberta)
#   TtlBlckdPos   — total blocked position (Travada)
#   UcvrdQty      — uncovered quantity (Descoberta)
#   TtlPos        — total position (Total)
#   BrrwrQty      — borrower quantity (Titulares = holders/longs)
#   LndrQty       — lender quantity (Lançadores = writers/shorts)
#   FwdPric       — forward price
#
# The instruments.db table (52 cols) is joined on TckrSymb to enrich each
# derivatives row with:
#   ExrcPric      — strike price (PT-BR format: "45,13")
#   XprtnDt       — expiration date (YYYY-MM-DD)
#   OptnStyle     — "AMER" or "EURO"
#   OptnTp        — "Call" or "Put"
#   CrpnNm        — company name
#   UndrlygTckrSymb1 — underlying ticker (PETR4)
#
# SQLite can't JOIN across DBs without ATTACH, so the join is done in Python.
# Graceful degradation: if instruments.db is missing, returns just the
# derivatives data without the join (strike=None, days_to_expiration=None).

def _strip_trailing_digits(s: str) -> str:
    """Strip trailing digits from a ticker (PETR4 -> PETR, VALE3 -> VALE)."""
    s = (s or "").strip().upper()
    while s and s[-1].isdigit():
        s = s[:-1]
    return s


def _to_int(value) -> int:
    """Parse a PT-BR number string to int (returns 0 for invalid/empty)."""
    if value is None:
        return 0
    if isinstance(value, (int, float)):
        return int(value)
    try:
        from data_sources.ddm._parsers import parse_br_number
        f = parse_br_number(str(value))
        return int(f) if f is not None else 0
    except Exception:
        return 0


def _to_float(value) -> float | None:
    """Parse a PT-BR number string to float (returns None for invalid/empty)."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        from data_sources.ddm._parsers import parse_br_number
        return parse_br_number(str(value))
    except Exception:
        return None


def _load_instruments_index() -> dict[str, dict] | None:
    """Load the instruments.db into a TckrSymb -> metadata dict.

    Returns None if instruments.db doesn't exist (graceful degradation).
    Only the columns relevant to options are loaded: ExrcPric, XprtnDt,
    OptnStyle, OptnTp, CrpnNm, UndrlygTckrSymb1.
    """
    try:
        conn = connect("instruments", read_only=True)
    except (FileNotFoundError, Exception):
        return None

    try:
        # Inspect which columns exist (the instruments table has 52 cols;
        # not all may be present if the sync was partial).
        col_rows = conn.execute("PRAGMA table_info(instruments)").fetchall()
        all_cols = {r["name"] for r in col_rows if r["name"] != "_ingested_at"}
        wanted = ["TckrSymb", "ExrcPric", "XprtnDt", "OptnStyle",
                  "OptnTp", "CrpnNm", "UndrlygTckrSymb1"]
        select_cols = [c for c in wanted if c in all_cols]
        if "TckrSymb" not in select_cols:
            return None  # Can't index without the primary key

        select_str = ", ".join(select_cols)
        rows = conn.execute(f"SELECT {select_str} FROM instruments").fetchall()

        index: dict[str, dict] = {}
        for r in rows:
            ticker = (r["TckrSymb"] or "").strip().upper()
            if not ticker:
                continue
            index[ticker] = {k: r[k] for k in select_cols if k != "TckrSymb"}
        return index
    finally:
        conn.close()


def open_positions(underlying: str = "") -> dict:
    """Get open positions (open interest + position breakdown) for an underlying.

    Queries the B3 API derivatives.db (DerivativesOpenPosition CSV bulk
    download) for all options where TckrSymb starts with the underlying,
    then joins with instruments.db to enrich each option with strike,
    expiration date, option style, and company name.

    Args:
        underlying: 4-letter code (e.g. "PETR") or full ticker ("PETR4").
                    Trailing digits are stripped automatically.

    Returns:
        {"status": "ok", "underlying": <normalized>, "refdate": ...,
         "summary": {CALL: {...}, PUT: {...}},
         "by_strike": [{strike, call_oi, put_oi, ...}, ...],
         "detail": [{ticker, type, strike, expiration, days_to_expiration,
                     oi, var_oi, covered, blocked, uncovered, total,
                     holders, writers, forward}, ...]}

    Graceful degradation:
        - If derivatives.db doesn't exist → {"status": "not_synced", ...}
        - If instruments.db doesn't exist → returns derivatives data with
          strike=None, days_to_expiration=None (degraded join).
        - Filters: only "EQUITY CALL" + "EQUITY PUT" SgmtNm; rows where
          OpnIntrst=0 AND TtlPos=0 are skipped (no positions).
    """
    if not underlying:
        return {"status": "error", "error": "underlying is required"}

    u = _strip_trailing_digits(underlying)
    if not u:
        return {"status": "error", "error": f"invalid underlying: {underlying}"}

    # ── Connect to derivatives.db ────────────────────────────────────────
    try:
        conn = connect("derivatives", read_only=True)
    except FileNotFoundError as e:
        return {"status": "not_synced", "error": str(e)}
    except Exception as e:
        return {"status": "error", "error": f"{type(e).__name__}: {e}"}

    try:
        col_rows = conn.execute("PRAGMA table_info(derivatives)").fetchall()
        all_cols = {r["name"] for r in col_rows if r["name"] != "_ingested_at"}
        if "TckrSymb" not in all_cols:
            return {"status": "error",
                    "error": "derivatives table has no TckrSymb column (sync may be partial)"}

        # Build SELECT for the columns we care about (skip missing ones).
        wanted = ["TckrSymb", "SgmtNm", "OpnIntrst", "VartnOpnIntrst",
                  "CvrdQty", "TtlBlckdPos", "UcvrdQty", "TtlPos",
                  "BrrwrQty", "LndrQty", "FwdPric", "RptDt"]
        select_cols = [c for c in wanted if c in all_cols]
        select_str = ", ".join(select_cols)

        # Filter: SgmtNm IN ('EQUITY CALL', 'EQUITY PUT') AND TckrSymb LIKE 'PETR%'
        # Use parameter binding for the LIKE pattern.
        like_pattern = f"{u}%"
        sql = (
            f"SELECT {select_str} FROM derivatives "
            f"WHERE TckrSymb LIKE ? "
            f"AND (SgmtNm = 'EQUITY CALL' OR SgmtNm = 'EQUITY PUT')"
        )
        rows = conn.execute(sql, (like_pattern,)).fetchall()

        if not rows:
            return {"status": "not_found", "underlying": u,
                    "error": f"no open positions for {u} in derivatives.db"}

        # Determine the reference date (most common RptDt across rows).
        refdate = ""
        if "RptDt" in all_cols and rows:
            dates = [r["RptDt"] for r in rows if r["RptDt"]]
            if dates:
                # Pick the most frequent date (in case of multi-date sync).
                from collections import Counter
                refdate = Counter(dates).most_common(1)[0][0]

        # ── Load instruments index (graceful: None if missing) ──────────
        instr_index = _load_instruments_index()

        # ── Build enriched detail rows + filter zero-position rows ──────
        from datetime import date as _date
        today = _date.today()

        detail: list[dict] = []
        for r in rows:
            oi = _to_int(r["OpnIntrst"]) if "OpnIntrst" in r.keys() else 0
            ttl_pos = _to_int(r["TtlPos"]) if "TtlPos" in r.keys() else 0
            # [v2 fix] OpnIntrst is empty in the CSV for most rows — fall back
            # to TtlPos (total position) so the OI KPIs + chart aren't all 0.
            if oi == 0 and ttl_pos > 0:
                oi = ttl_pos
            # Skip rows with all-zero positions (no open interest + no total).
            if oi == 0 and ttl_pos == 0:
                continue

            ticker = (r["TckrSymb"] or "").strip().upper()
            sgmt = (r["SgmtNm"] or "").strip().upper()
            opt_type = "CALL" if "CALL" in sgmt else "PUT" if "PUT" in sgmt else ""

            # Strike + expiration from the instruments join (or None).
            strike = None
            expiration = ""
            optn_style = ""
            crpn_nm = ""
            undrlyg = ""
            days_to_expiration = None
            if instr_index is not None:
                instr = instr_index.get(ticker)
                if instr:
                    strike = _to_float(instr.get("ExrcPric"))
                    expiration = (instr.get("XprtnDt") or "").strip()
                    optn_style = (instr.get("OptnStyle") or "").strip()
                    crpn_nm = (instr.get("CrpnNm") or "").strip()
                    undrlyg = (instr.get("UndrlygTckrSymb1") or "").strip()
                    if expiration:
                        try:
                            d_exp = _date.fromisoformat(expiration[:10])
                            days_to_expiration = (d_exp - today).days
                        except ValueError:
                            days_to_expiration = None

            detail.append({
                "ticker":              ticker,
                "type":                opt_type,
                "strike":              strike,
                "expiration":          expiration,
                "days_to_expiration":  days_to_expiration,
                "optn_style":          optn_style,
                "company":             crpn_nm,
                "underlying_ticker":   undrlyg,
                "oi":                  oi,
                "var_oi":              _to_int(r["VartnOpnIntrst"]) if "VartnOpnIntrst" in r.keys() else 0,
                "covered":             _to_int(r["CvrdQty"])        if "CvrdQty"        in r.keys() else 0,
                "blocked":             _to_int(r["TtlBlckdPos"])    if "TtlBlckdPos"    in r.keys() else 0,
                "uncovered":           _to_int(r["UcvrdQty"])       if "UcvrdQty"       in r.keys() else 0,
                "total":               ttl_pos,
                "holders":             _to_int(r["BrrwrQty"])       if "BrrwrQty"       in r.keys() else 0,
                "writers":             _to_int(r["LndrQty"])        if "LndrQty"        in r.keys() else 0,
                "forward":             _to_float(r["FwdPric"])      if "FwdPric"        in r.keys() else None,
            })

        if not detail:
            return {"status": "not_found", "underlying": u,
                    "error": f"no open positions (all zero) for {u}"}

        # ── Summary: CALL vs PUT totals ─────────────────────────────────
        def _sum(field: str, opt_type: str) -> int:
            return sum(d[field] for d in detail if d["type"] == opt_type)

        summary = {}
        for ot in ("CALL", "PUT"):
            oi_t = _sum("oi", ot)
            cov = _sum("covered", ot)
            blk = _sum("blocked", ot)
            unc = _sum("uncovered", ot)
            tot = _sum("total", ot)
            hld = _sum("holders", ot)
            wtr = _sum("writers", ot)
            summary[ot] = {
                "oi":         oi_t,
                "var_oi":     _sum("var_oi", ot),
                "covered":    cov,
                "blocked":    blk,
                "uncovered":  unc,
                "total":      tot,
                "holders":    hld,
                "writers":    wtr,
                "covered_pct":   (cov / tot * 100.0) if tot > 0 else 0.0,
                "uncovered_pct": (unc / tot * 100.0) if tot > 0 else 0.0,
            }

        # ── by_strike: aggregate OI per strike (for the bar chart) ──────
        strike_map: dict[float, dict] = {}
        for d in detail:
            if d["strike"] is None:
                continue
            s = d["strike"]
            if s not in strike_map:
                strike_map[s] = {"strike": s, "call_oi": 0, "put_oi": 0,
                                 "call_total": 0, "put_total": 0,
                                 "call_count": 0, "put_count": 0}
            bucket = strike_map[s]
            if d["type"] == "CALL":
                bucket["call_oi"]    += d["oi"]
                bucket["call_total"] += d["total"]
                bucket["call_count"] += 1
            elif d["type"] == "PUT":
                bucket["put_oi"]    += d["oi"]
                bucket["put_total"] += d["total"]
                bucket["put_count"] += 1
        by_strike = sorted(strike_map.values(), key=lambda b: b["strike"])

        return {
            "status":         "ok",
            "underlying":     u,
            "refdate":        refdate,
            "instruments_ok": instr_index is not None,
            "count":          len(detail),
            "summary":        summary,
            "by_strike":      by_strike,
            "detail":         detail,
        }
    finally:
        conn.close()


def lookup_option_positions(ticker: str = "") -> dict:
    """Look up open positions for a SINGLE option ticker.

    Lighter than open_positions() — fetches just one row from derivatives.db.
    Used by the Cadeia de Opções tab to enrich each chain row with
    OI / Coberta / Descoberta columns.

    Args:
        ticker: Option ticker (e.g. "PETRA201"). Required.

    Returns:
        {"status": "ok", "ticker": ..., "oi": N, "covered": N,
         "uncovered": N, "blocked": N, "total": N,
         "holders": N, "writers": N, "var_oi": N, "forward": float|None}

        Returns {"status": "not_found", ...} if the ticker isn't in
        derivatives.db or has no positions.
    """
    if not ticker:
        return {"status": "error", "error": "ticker is required"}

    t = ticker.strip().upper()

    try:
        conn = connect("derivatives", read_only=True)
    except FileNotFoundError as e:
        return {"status": "not_synced", "error": str(e)}
    except Exception as e:
        return {"status": "error", "error": f"{type(e).__name__}: {e}"}

    try:
        col_rows = conn.execute("PRAGMA table_info(derivatives)").fetchall()
        all_cols = {r["name"] for r in col_rows if r["name"] != "_ingested_at"}
        if "TckrSymb" not in all_cols:
            return {"status": "error",
                    "error": "derivatives table has no TckrSymb column"}

        wanted = ["TckrSymb", "OpnIntrst", "VartnOpnIntrst", "CvrdQty",
                  "TtlBlckdPos", "UcvrdQty", "TtlPos", "BrrwrQty", "LndrQty",
                  "FwdPric"]
        select_cols = [c for c in wanted if c in all_cols]
        select_str = ", ".join(select_cols)

        row = conn.execute(
            f"SELECT {select_str} FROM derivatives WHERE TckrSymb = ? LIMIT 1",
            (t,),
        ).fetchone()

        if not row:
            return {"status": "not_found", "ticker": t,
                    "error": f"no open positions for {t}"}

        return {
            "status":    "ok",
            "ticker":    t,
            "oi":        _to_int(row["OpnIntrst"])      if "OpnIntrst"      in row.keys() else 0,
            "var_oi":    _to_int(row["VartnOpnIntrst"]) if "VartnOpnIntrst" in row.keys() else 0,
            "covered":   _to_int(row["CvrdQty"])        if "CvrdQty"        in row.keys() else 0,
            "blocked":   _to_int(row["TtlBlckdPos"])    if "TtlBlckdPos"    in row.keys() else 0,
            "uncovered": _to_int(row["UcvrdQty"])       if "UcvrdQty"       in row.keys() else 0,
            "total":     _to_int(row["TtlPos"])         if "TtlPos"         in row.keys() else 0,
            "holders":   _to_int(row["BrrwrQty"])       if "BrrwrQty"       in row.keys() else 0,
            "writers":   _to_int(row["LndrQty"])        if "LndrQty"        in row.keys() else 0,
            "forward":   _to_float(row["FwdPric"])      if "FwdPric"        in row.keys() else None,
        }
    finally:
        conn.close()
