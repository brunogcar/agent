"""data_sources/cvm/bridge/sync_engine.py -- Build bridge.db entries per ticker.

THE SYNC FLOW (per the user's design: "check if already fetched, if not run
it, then update bridge.db")

For each ticker:
  1. Check bridge.db -- if ticker already mapped AND not force -> skip
  2. Ensure dividends data exists -- call b3.dividends.sync (which checks its
     own sync_state and fetches from the API only if needed)
  3. Read code_cvm from dividends.company_info (the ticker -> cd_cvm link)
  4. If no code_cvm -> log 'no_cvm', store partial row (ticker only), continue
  5. CAD lookup by cd_cvm -> CNPJ + official names + status + sector
  6. If CAD miss -> log 'no_cad', store ticker + cd_cvm (cnpj empty), continue
  7. UPSERT bridge.db ticker_map with the full identity record
  8. Log 'linked' to sync_log

DESIGN NOTES
------------
- The bridge REUSES b3.dividends.sync_engine.sync for the API call. It does
  NOT duplicate the HTTP fetch logic. The dividends sync already caches via
  sync_state, so re-syncing the same ticker is a no-op (returns 'skipped').
- The bridge REUSES cvm.cad.query_engine.lookup for the cd_cvm -> CNPJ join.
  No new CAD parsing logic.
- If cad.db doesn't exist or is empty, the bridge still stores ticker + cd_cvm.
  The resolver (_bridge.py) can fall back to cd_cvm for DFP/ITR queries
  (empresas.cd_cvm column) even without CNPJ.
- force=True re-fetches dividends AND re-joins CAD (useful after a CAD refresh).

NO INSTRUMENTS DEPENDENCY
-------------------------
This engine never reads instruments.db. Tickers are provided explicitly by the
caller. If you want to bridge all tickers from a partial instruments sync, pass
them as a list: params='{"tickers":["PETR4","VALE3",...]}'.
"""

from __future__ import annotations

import sys
from datetime import datetime
from typing import Any

from data_sources.cvm._db import cnpj_digits
from data_sources.cvm.bridge.catalog import connect, ensure_schema


def _progress(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def _now() -> str:
    return datetime.now().isoformat()


# ── Public entry point ───────────────────────────────────────────────────────

def sync(
    ticker: str = "",
    tickers: list[str] | None = None,
    force: bool = False,
    trace_id: str = "",
) -> dict:
    """Sync one or more tickers into the bridge.

    Args:
        ticker: Single ticker (e.g., "PETR4"). Ignored if `tickers` is given.
        tickers: List of tickers. Takes precedence over `ticker`.
        force: Re-fetch dividends AND re-join CAD even if already bridged.
        trace_id: Tracer ID (forwarded to dividends sync).

    Returns:
        For a single ticker: the per-ticker result dict.
        For multiple tickers: {"status": "ok", "results": {ticker: result, ...}, ...}
    """
    # Normalize to a list of uppercased tickers
    if tickers:
        targets = [t.strip().upper() for t in tickers if t and t.strip()]
    elif ticker:
        targets = [ticker.strip().upper()]
    else:
        return {"status": "error",
                "error": "Provide ticker (single) or tickers (list)."}

    if not targets:
        return {"status": "error", "error": "No valid tickers provided."}

    # Single ticker -- return the per-ticker result directly
    if len(targets) == 1:
        return _sync_one(targets[0], force=force, trace_id=trace_id)

    # Multiple tickers -- aggregate
    results: dict[str, dict] = {}
    linked = skipped = errors = 0
    for tkr in targets:
        r = _sync_one(tkr, force=force, trace_id=trace_id)
        results[tkr] = r
        st = r.get("status")
        if st == "ok":
            linked += 1
        elif st == "skipped":
            skipped += 1
        else:
            errors += 1

    return {
        "status": "ok",
        "total": len(targets),
        "linked": linked,
        "skipped": skipped,
        "errors": errors,
        "results": results,
    }


# ── Per-ticker sync ──────────────────────────────────────────────────────────

def _sync_one(ticker: str, force: bool, trace_id: str) -> dict:
    """Sync a single ticker: check bridge -> ensure dividends -> CAD join -> upsert."""
    now = _now()

    # 1. Check bridge.db -- skip if already mapped (unless force)
    try:
        conn = connect(read_only=False)
        ensure_schema(conn)
    except Exception as e:
        return {"status": "error", "ticker": ticker,
                "error": f"bridge.db open failed: {e}", "step": "open"}

    try:
        if not force:
            existing = conn.execute(
                "SELECT * FROM ticker_map WHERE ticker=?", (ticker,),
            ).fetchone()
            if existing:
                return {
                    "status": "skipped",
                    "ticker": ticker,
                    "reason": "already in bridge",
                    "cd_cvm": existing["cd_cvm"],
                    "cnpj": existing["cnpj"],
                }

        # 2. Ensure dividends data (sync checks its own cache)
        cd_cvm, trading_name, div_status, div_detail = _ensure_dividends(
            ticker, force=force, trace_id=trace_id,
        )

        # 3. No codeCVM -> try ISIN fallback (dividends DB isin -> ISIN ZIP -> CNPJ -> CAD)
        if not cd_cvm:
            _progress(f"[bridge] {ticker}: no codeCVM from dividends, trying ISIN fallback...")
            fallback = _try_isin_fallback(ticker, trace_id=trace_id)
            if fallback.get("cnpj"):
                # ISIN fallback got a CNPJ -> CAD lookup by cnpj
                cnpj = fallback["cnpj"]
                cad_row = _cad_lookup_by_cnpj(cnpj)
                if cad_row:
                    cd_cvm = cad_row.get("CD_CVM", "")
                    _upsert(conn, ticker, issuing=ticker[:4], cd_cvm=cd_cvm,
                            trading_name=trading_name, cnpj=cnpj,
                            denom_social=cad_row.get("DENOM_SOCIAL", ""),
                            denom_comerc=cad_row.get("DENOM_COMERC", ""),
                            sit=cad_row.get("SIT", ""),
                            setor_ativ=cad_row.get("SETOR_ATIV", ""),
                            tp_merc=cad_row.get("TP_MERC", ""), now=now)
                    _log(conn, now, ticker, "linked_isin", cd_cvm, cnpj,
                         f"via ISIN fallback: {fallback.get('isin','')}")
                    conn.commit()
                    _progress(f"[bridge] {ticker}: ISIN fallback linked cnpj={cnpj} cd_cvm={cd_cvm}")
                    return {
                        "status": "ok", "ticker": ticker, "cd_cvm": cd_cvm,
                        "cnpj": cnpj, "source": "isin_fallback",
                        "denom_social": cad_row.get("DENOM_SOCIAL", ""),
                        "trading_name": trading_name,
                        "sit": cad_row.get("SIT", ""),
                    }
                # ISIN got CNPJ but CAD miss -- store ticker + cnpj, log 'no_cad'
                _upsert(conn, ticker, issuing=ticker[:4], cd_cvm="",
                        trading_name=trading_name, cnpj=cnpj,
                        denom_social="", denom_comerc="",
                        sit="", setor_ativ="", tp_merc="", now=now)
                _log(conn, now, ticker, "no_cad", "", cnpj,
                     f"via ISIN fallback, cnpj={cnpj} not in cad.db")
                conn.commit()
                return {
                    "status": "ok", "ticker": ticker, "cd_cvm": "",
                    "cnpj": cnpj, "source": "isin_fallback",
                    "warning": "ISIN resolved CNPJ but CAD miss",
                    "trading_name": trading_name,
                }
            # ISIN fallback also failed -> store partial row, log 'no_cvm'
            _upsert(conn, ticker, issuing=ticker[:4], cd_cvm="",
                    trading_name=trading_name, cnpj="",
                    denom_social="", denom_comerc="",
                    sit="", setor_ativ="", tp_merc="", now=now)
            _log(conn, now, ticker, "no_cvm", "", "",
                 f"{div_detail}; isin_fallback: {fallback.get('detail','')}")
            conn.commit()
            return {
                "status": "error", "ticker": ticker,
                "error": "no codeCVM from dividends and ISIN fallback failed",
                "step": "dividends+isin", "dividends_status": div_status,
                "isin_detail": fallback.get("detail", ""),
            }

        # 4. CAD lookup by cd_cvm
        cad_row = _cad_lookup(cd_cvm)

        if cad_row is None:
            # CAD miss -- store ticker + cd_cvm, log 'no_cad'
            _upsert(conn, ticker, issuing=ticker[:4], cd_cvm=cd_cvm,
                    trading_name=trading_name, cnpj="",
                    denom_social="", denom_comerc="",
                    sit="", setor_ativ="", tp_merc="", now=now)
            _log(conn, now, ticker, "no_cad", cd_cvm, "",
                 f"cd_cvm={cd_cvm} not found in cad.db (stale or unregistered)")
            conn.commit()
            _progress(f"[bridge] {ticker}: cd_cvm={cd_cvm} but not in CAD (stored partial)")
            return {
                "status": "ok", "ticker": ticker, "cd_cvm": cd_cvm,
                "cnpj": "", "warning": "cd_cvm not in cad.db (partial bridge entry)",
                "trading_name": trading_name,
            }

        # 5. Full success -- UPSERT with CAD data
        cnpj = cnpj_digits(cad_row.get("CNPJ_CIA", ""))
        _upsert(conn, ticker, issuing=ticker[:4], cd_cvm=cd_cvm,
                trading_name=trading_name, cnpj=cnpj,
                denom_social=cad_row.get("DENOM_SOCIAL", ""),
                denom_comerc=cad_row.get("DENOM_COMERC", ""),
                sit=cad_row.get("SIT", ""),
                setor_ativ=cad_row.get("SETOR_ATIV", ""),
                tp_merc=cad_row.get("TP_MERC", ""), now=now)
        _log(conn, now, ticker, "linked", cd_cvm, cnpj,
             f"{cad_row.get('DENOM_SOCIAL', '')}")
        conn.commit()

        _progress(f"[bridge] {ticker}: cd_cvm={cd_cvm} cnpj={cnpj} linked")
        return {
            "status": "ok", "ticker": ticker, "cd_cvm": cd_cvm,
            "cnpj": cnpj,
            "denom_social": cad_row.get("DENOM_SOCIAL", ""),
            "trading_name": trading_name,
            "sit": cad_row.get("SIT", ""),
        }
    except Exception as e:
        import traceback
        try:
            _log(conn, now, ticker, "error", "", "", f"{type(e).__name__}: {e}")
            conn.commit()
        except Exception:
            pass
        return {"status": "error", "ticker": ticker,
                "error": f"{type(e).__name__}: {e}",
                "traceback": traceback.format_exc()}
    finally:
        conn.close()


# ── Dividends integration ────────────────────────────────────────────────────

def _ensure_dividends(ticker: str, force: bool, trace_id: str):
    """Ensure dividends data exists for ticker; return (code_cvm, trading_name, status, detail).

    Calls b3.dividends.sync (which checks sync_state and fetches only if needed).
    Then reads company_info.code_cvm from dividends.db.
    """
    from data_sources.b3.dividends.sync_engine import sync as sync_dividends
    from data_sources.b3.dividends.query_engine import company_info as div_company_info

    try:
        result = sync_dividends(ticker=ticker, force=force, trace_id=trace_id)
    except Exception as e:
        return "", "", "error", f"dividends sync raised: {e}"

    st = result.get("status")
    if st == "error":
        return "", "", st, f"dividends: {result.get('error', 'unknown')}"

    # 'ok' or 'skipped' -- company_info should exist either way
    try:
        info = div_company_info(ticker=ticker)
    except Exception as e:
        return "", "", "error", f"company_info query raised: {e}"

    if info.get("status") != "ok":
        return "", "", st, f"company_info: {info.get('status', 'unknown')}"

    row = info.get("info", {})
    code_cvm = (row.get("code_cvm") or "").strip()
    trading_name = (row.get("trading_name") or "").strip()
    return code_cvm, trading_name, st, ""


# ── CAD integration ──────────────────────────────────────────────────────────

def _cad_lookup(cd_cvm: str) -> dict | None:
    """Look up a company in cad.db by cd_cvm. Returns the row dict or None."""
    from data_sources.cvm.cad.query_engine import lookup as cad_lookup

    try:
        result = cad_lookup(cd_cvm=cd_cvm, full=False)
    except FileNotFoundError:
        return None
    except Exception:
        return None

    if result.get("status") != "ok":
        return None

    company = result.get("company")
    if not company:
        return None
    return company


def _cad_lookup_by_cnpj(cnpj: str) -> dict | None:
    """Look up a company in cad.db by CNPJ. Returns the row dict or None.

    Used by the ISIN fallback path (which resolves CNPJ first, then needs
    cd_cvm + names from CAD).
    """
    if not cnpj:
        return None
    from data_sources.cvm.cad.query_engine import lookup as cad_lookup

    try:
        result = cad_lookup(cnpj=cnpj, full=False)
    except FileNotFoundError:
        return None
    except Exception:
        return None

    if result.get("status") != "ok":
        return None

    company = result.get("company")
    if not company:
        return None
    return company


# ── ISIN fallback ────────────────────────────────────────────────────────────

def _try_isin_fallback(ticker: str, trace_id: str = "") -> dict:
    """ISIN fallback: ticker -> dividends.db isin -> ISIN ZIP -> CNPJ.

    Called when the primary path (dividends API -> codeCVM) fails.
    Uses the ISIN stored in dividends.db.cash_dividends (from a prior dividends
    sync) to look up the CNPJ via the B3 ISIN ZIP index.

    Returns:
        {"cnpj": "33000167000101", "isin": "BRPETRACNPR6"} on success
        {"cnpj": "", "detail": "..."} on failure
    """
    # 1. Get ISIN from dividends.db (cash_dividends table)
    isin = _get_isin_from_dividends(ticker)
    if not isin:
        return {"cnpj": "", "detail": "no ISIN in dividends.db for this ticker"}

    # 2. Ensure ISIN index is cached (downloads ZIP if stale/missing)
    from data_sources.cvm.bridge import isin_fetcher
    try:
        sync_result = isin_fetcher.sync(trace_id=trace_id)
    except Exception as e:
        return {"cnpj": "", "isin": isin,
                "detail": f"isin_fetcher.sync raised: {e}"}

    if sync_result.get("status") == "error":
        return {"cnpj": "", "isin": isin,
                "detail": f"isin index sync: {sync_result.get('error','')}"}

    # 3. Look up ISIN -> CNPJ
    cnpj = isin_fetcher.lookup_isin(isin)
    if not cnpj:
        return {"cnpj": "", "isin": isin,
                "detail": f"ISIN {isin} not found in B3 ISIN index"}

    return {"cnpj": cnpj, "isin": isin}


def _get_isin_from_dividends(ticker: str) -> str:
    """Get the first ISIN for a ticker from dividends.db.cash_dividends.

    Returns the ISIN string or "" if no dividends data exists.
    """
    try:
        from data_sources.b3.dividends.query_engine import dividends as div_query
        result = div_query(ticker=ticker, limit=1)
    except Exception:
        return ""
    if result.get("status") != "ok":
        return ""
    divs = result.get("dividends", [])
    if not divs:
        return ""
    return (divs[0].get("isin_code") or "").strip()


# ── DB helpers ───────────────────────────────────────────────────────────────

def _upsert(conn, ticker, issuing, cd_cvm, trading_name, cnpj,
            denom_social, denom_comerc, sit, setor_ativ, tp_merc, now):
    """UPSERT a ticker_map row."""
    conn.execute(
        "INSERT INTO ticker_map "
        "(ticker, issuing, cd_cvm, trading_name, cnpj, denom_social, "
        " denom_comerc, sit, setor_ativ, tp_merc, synced_at) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?) "
        "ON CONFLICT(ticker) DO UPDATE SET "
        "  issuing=excluded.issuing, cd_cvm=excluded.cd_cvm, "
        "  trading_name=excluded.trading_name, cnpj=excluded.cnpj, "
        "  denom_social=excluded.denom_social, denom_comerc=excluded.denom_comerc, "
        "  sit=excluded.sit, setor_ativ=excluded.setor_ativ, "
        "  tp_merc=excluded.tp_merc, synced_at=excluded.synced_at",
        (ticker, issuing, cd_cvm, trading_name, cnpj, denom_social,
         denom_comerc, sit, setor_ativ, tp_merc, now),
    )


def _log(conn, synced_at, ticker, action, cd_cvm, cnpj, detail):
    """Insert a sync_log row."""
    conn.execute(
        "INSERT INTO sync_log (synced_at, ticker, action, cd_cvm, cnpj, detail) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (synced_at, ticker, action, cd_cvm, cnpj, detail),
    )
