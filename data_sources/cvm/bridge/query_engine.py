"""data_sources/cvm/bridge/query_engine.py -- Query the B3-CVM bridge.

Read-only queries against bridge.db:
  - lookup(ticker/cnpj/cd_cvm)  -- resolve any identifier to the full identity record
  - status()                    -- bridge.db stats (total, with cnpj, last sync)
  - resolve(query)              -- fuzzy name search across denom_social/denom_comerc/trading_name
"""

from __future__ import annotations

from data_sources.cvm.bridge.catalog import connect, db_path


def lookup(ticker: str = "", cnpj: str = "", cd_cvm: str = "") -> dict:
    """Resolve a ticker, CNPJ, or CD_CVM to the full bridge identity record.

    Exactly one of ticker/cnpj/cd_cvm should be provided.

    Returns:
        {status: "ok", ticker, cd_cvm, cnpj, denom_social, ...}
        {status: "not_found", error: "..."}
        {status: "not_synced", message: "..."}
    """
    if not ticker and not cnpj and not cd_cvm:
        return {"status": "error",
                "error": "Provide ticker, cnpj, or cd_cvm"}

    try:
        conn = connect(read_only=True)
    except FileNotFoundError as e:
        return {"status": "not_synced", "message": str(e)}

    try:
        from data_sources.cvm._db import cnpj_digits

        row = None
        if ticker:
            row = conn.execute(
                "SELECT * FROM ticker_map WHERE ticker=? LIMIT 1",
                (ticker.strip().upper(),),
            ).fetchone()
        elif cnpj:
            cn = cnpj_digits(cnpj)
            if cn:
                row = conn.execute(
                    "SELECT * FROM ticker_map WHERE cnpj=? LIMIT 1", (cn,),
                ).fetchone()
        else:  # cd_cvm
            row = conn.execute(
                "SELECT * FROM ticker_map WHERE cd_cvm=? LIMIT 1",
                (str(cd_cvm).strip(),),
            ).fetchone()

        if not row:
            ident = ticker or cnpj or cd_cvm
            return {"status": "not_found",
                    "error": f"'{ident}' not found in bridge.db. "
                             f"Run mode='sync' with this ticker first."}

        return {"status": "ok", **dict(row)}
    except Exception as e:
        return {"status": "error", "error": str(e)}
    finally:
        conn.close()


def status() -> dict:
    """Show bridge.db stats: total tickers, with cnpj, with cd_cvm, last sync."""
    path = db_path()
    if not path.exists():
        return {"status": "not_synced",
                "message": "bridge.db not found. Run mode='sync' first."}

    try:
        conn = connect(read_only=True)
    except FileNotFoundError:
        return {"status": "not_synced", "message": "bridge.db not found."}

    try:
        total = conn.execute("SELECT COUNT(*) as n FROM ticker_map").fetchone()["n"]
        with_cnpj = conn.execute(
            "SELECT COUNT(*) as n FROM ticker_map WHERE cnpj != ''"
        ).fetchone()["n"]
        with_cvm = conn.execute(
            "SELECT COUNT(*) as n FROM ticker_map WHERE cd_cvm != ''"
        ).fetchone()["n"]
        linked = conn.execute(
            "SELECT COUNT(*) as n FROM sync_log WHERE action='linked'"
        ).fetchone()["n"]
        no_cad = conn.execute(
            "SELECT COUNT(*) as n FROM sync_log WHERE action='no_cad'"
        ).fetchone()["n"]

        last = conn.execute(
            "SELECT * FROM sync_log ORDER BY id DESC LIMIT 1"
        ).fetchone()

        return {
            "status": "ok",
            "path": str(path),
            "db_size_kb": round(path.stat().st_size / 1024, 1),
            "total_tickers": total,
            "with_cnpj": with_cnpj,
            "with_cd_cvm": with_cvm,
            "cnpj_coverage_pct": round(with_cnpj / total * 100, 1) if total else 0,
            "log": {"linked": linked, "no_cad": no_cad},
            "last_sync": {
                "synced_at": last["synced_at"] if last else "",
                "ticker": last["ticker"] if last else "",
                "action": last["action"] if last else "",
            } if last else None,
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}
    finally:
        conn.close()


def resolve(query: str = "", limit: int = 10) -> dict:
    """Fuzzy name search across trading_name, denom_social, denom_comerc.

    Args:
        query: Name fragment (>= 2 chars).
        limit: Max results. Default 10.

    Returns:
        {status: "ok", query, count, matches: [...]}
        {status: "not_found", query, error: "..."}
    """
    if not query or len(query.strip()) < 2:
        return {"status": "error", "error": "query must be >= 2 characters"}

    try:
        conn = connect(read_only=True)
    except FileNotFoundError as e:
        return {"status": "not_synced", "message": str(e)}

    try:
        q = f"%{query.upper()}%"
        rows = conn.execute(
            "SELECT * FROM ticker_map "
            "WHERE UPPER(trading_name) LIKE ? OR UPPER(denom_social) LIKE ? "
            "OR UPPER(denom_comerc) LIKE ? "
            "ORDER BY CASE WHEN UPPER(trading_name) LIKE ? THEN 0 ELSE 1 END, ticker "
            "LIMIT ?",
            (q, q, q, q, limit),
        ).fetchall()

        if not rows:
            return {"status": "not_found", "query": query,
                    "error": f"No bridge entries matching '{query}'"}

        return {
            "status": "ok", "query": query, "count": len(rows),
            "matches": [dict(r) for r in rows],
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}
    finally:
        conn.close()
