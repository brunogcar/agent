"""
skills/b3/b3_cvm/b3_cvm.py
Deploy to: D:\mcp\agent\skills\b3\b3_cvm\b3_cvm.py

Mode dispatchers and public helper functions.
Network + parsing logic split into:
  b3_cvm_downloader.py  -- HTTP downloads only
  b3_cvm_parser.py      -- bytes -> dicts parsing only

=== BRIDGE.DB SCHEMA (managed by skills/cvm/_db.py connect_bridge()) ===
company_map table -- one row per (ticker, isin):
  ticker       -- B3 trading symbol e.g. "PETR4"
  isin         -- e.g. "BRPETRACNPR6"
  b3_name      -- CrpnNm from instruments.db
  sgmt         -- SgmtNm: "CASH"
  catg         -- SctyCtgyNm: "SHARES" or "UNIT"
  spec_cd      -- SpcfctnCd: "PN N2", "ON NM" etc.
  gov_level    -- CorpGovnLvlNm: "NIVEL 2", "NOVO MERCADO" etc.
  mkt_cap      -- MktCptlstn in BRL
  cnpj         -- 14 digits, universal join key
  cd_cvm       -- CVM integer code
  denom_social -- CVM official name
  denom_comerc -- CVM commercial name
  sit          -- ATIVO / CANCELADO / SUSPENSO
  tp_merc      -- BOVESPA / BALCAO etc.
  setor_ativ   -- economic sector
  dfp_itr_ids   -- JSON array of dfp_itr empresa.id ints
  synced_at    -- ISO timestamp

=== JOIN LOGIC ===
instruments.db (local) -> TckrSymb + ISIN + company info
B3 ISIN ZIP (download) -> ISIN -> CNPJ  (via EMISSOR+NUMERACA join)
CVM CSV (download)     -> CNPJ -> CD_CVM + names + status
dfp_itr.db (local)      -> CNPJ -> [empresa_ids]
"""

from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from skills.cvm._db import (
    connect_bridge, build_dfp_itr_cnpj_index,
    cnpj_digits, bridge_path,
)


# ── instruments.db path ───────────────────────────────────────────────────────

def _instruments_path() -> Path:
    import os
    memory_root = os.getenv("MEMORY_ROOT", "")
    if memory_root:
        p = Path(memory_root) / "b3" / "instruments.db"
        if p.exists():
            return p
    here = Path(__file__).resolve().parent
    for _ in range(6):
        p = here / "memory_db" / "b3" / "instruments.db"
        if p.exists():
            return p
        here = here.parent
    raise FileNotFoundError(
        "instruments.db not found. "
        "Run skill(domain='b3_api', mode='sync') to populate it."
    )


def _connect_instruments():
    import sqlite3
    path = _instruments_path()
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


# ── Mode: sync ────────────────────────────────────────────────────────────────

def mode_sync() -> dict:
    """
    Build or rebuild bridge.db from four local/remote sources.

    Steps:
      a. Load instruments.db filtered to CASH/EQUITY-CASH/SHARES+UNIT
      b. Download B3 ISIN ZIP -> parse -> {isin: cnpj}
      c. Download CVM CSV     -> parse -> {cnpj: cvm_row}
      d. Build dfp_itr index   -> {cnpj: [empresa_ids]}
      e. Join all on CNPJ, UPSERT into bridge.db
      f. Log to sync_log

    EQUITY FILTER: SgmtNm='CASH' AND MktNm='EQUITY-CASH' AND SctyCtgyNm IN ('SHARES','UNIT')
    Excludes: odd lots, block trades, derivatives, futures, forwards.
    The bridge is for equity identity resolution only.
    """
    from skills.b3.b3_cvm.b3_cvm_downloader import download_b3_zip, download_cvm_register
    from skills.b3.b3_cvm.b3_cvm_parser import parse_b3_zip, parse_cvm_register

    t0      = time.time()
    now_iso = datetime.now(timezone.utc).isoformat()

    # a. instruments.db
    print("[b3_cvm] Loading instruments.db...", file=sys.stderr)
    try:
        ic = _connect_instruments()
        inst_rows = ic.execute("""
            SELECT TckrSymb, ISIN, CrpnNm, SgmtNm, MktNm, SctyCtgyNm,
                   SpcfctnCd, CorpGovnLvlNm, MktCptlstn
            FROM instruments
            WHERE SgmtNm = 'CASH'
              AND MktNm  = 'EQUITY-CASH'
              AND SctyCtgyNm IN ('SHARES', 'UNIT')
        """).fetchall()
        ic.close()
    except Exception as e:
        return {"status": "error", "error": f"instruments.db: {e}", "step": "instruments"}

    print(f"[b3_cvm] instruments: {len(inst_rows):,} equity rows", file=sys.stderr)

    # b. B3 ISIN ZIP
    try:
        isin_cnpj = parse_b3_zip(download_b3_zip())
    except Exception as e:
        return {"status": "error", "error": f"B3 ZIP: {e}", "step": "b3_zip"}

    # c. CVM CSV
    try:
        cvm_rows = parse_cvm_register(download_cvm_register())
    except Exception as e:
        return {"status": "error", "error": f"CVM CSV: {e}", "step": "cvm_csv"}

    cvm_by_cnpj: dict[str, dict] = {}
    for row in cvm_rows:
        c = row["cnpj"]
        if not c:
            continue
        existing = cvm_by_cnpj.get(c)
        if existing is None or (
            row.get("sit") == "ATIVO" and existing.get("sit") != "ATIVO"
        ):
            cvm_by_cnpj[c] = row

    # d. dfp_itr index
    dfp_itr_index = build_dfp_itr_cnpj_index()

    # e. join + upsert
    conn        = connect_bridge(read_only=False)
    matched_cvm = 0
    matched_rap = 0
    no_cnpj     = 0

    try:
        for row in inst_rows:
            ticker = row["TckrSymb"]
            isin   = row["ISIN"] or ""
            cnpj   = isin_cnpj.get(isin, "") if isin else ""

            if not cnpj:
                no_cnpj += 1

            cvm        = cvm_by_cnpj.get(cnpj, {}) if cnpj else {}
            dfp_itr_ids = dfp_itr_index.get(cnpj, []) if cnpj else []
            if cvm:
                matched_cvm += 1
            if dfp_itr_ids:
                matched_rap += 1

            conn.execute("""
                INSERT INTO company_map
                    (ticker, isin, b3_name, sgmt, catg, spec_cd, gov_level,
                     mkt_cap, cnpj, cd_cvm, denom_social, denom_comerc,
                     sit, tp_merc, setor_ativ, dfp_itr_ids, synced_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(ticker, isin) DO UPDATE SET
                    b3_name=excluded.b3_name, sgmt=excluded.sgmt,
                    catg=excluded.catg, spec_cd=excluded.spec_cd,
                    gov_level=excluded.gov_level, mkt_cap=excluded.mkt_cap,
                    cnpj=excluded.cnpj, cd_cvm=excluded.cd_cvm,
                    denom_social=excluded.denom_social,
                    denom_comerc=excluded.denom_comerc,
                    sit=excluded.sit, tp_merc=excluded.tp_merc,
                    setor_ativ=excluded.setor_ativ,
                    dfp_itr_ids=excluded.dfp_itr_ids, synced_at=excluded.synced_at
            """, (
                ticker, isin,
                row["CrpnNm"] or "", row["SgmtNm"] or "", row["SctyCtgyNm"] or "",
                row["SpcfctnCd"] or "", row["CorpGovnLvlNm"] or "",
                row["MktCptlstn"] or 0,
                cnpj,
                cvm.get("cd_cvm", 0),    cvm.get("denom_social", ""),
                cvm.get("denom_comerc", ""), cvm.get("sit", ""),
                cvm.get("tp_merc", ""),  cvm.get("setor_ativ", ""),
                json.dumps(dfp_itr_ids),  now_iso,
            ))

        conn.commit()

        total       = conn.execute("SELECT COUNT(*) FROM company_map").fetchone()[0]
        with_cvm    = conn.execute("SELECT COUNT(*) FROM company_map WHERE cd_cvm > 0").fetchone()[0]
        with_dfp_itr = conn.execute("SELECT COUNT(*) FROM company_map WHERE dfp_itr_ids != '[]'").fetchone()[0]
        duration    = round(time.time() - t0, 1)

        conn.execute("""
            INSERT INTO sync_log
                (synced_at, instruments, isin_cnpj, cvm_rows, bridge_rows,
                 matched_cvm, matched_rap, duration_s, notes)
            VALUES (?,?,?,?,?,?,?,?,?)
        """, (now_iso, len(inst_rows), len(isin_cnpj), len(cvm_rows),
              total, matched_cvm, matched_rap, duration, f"no_cnpj={no_cnpj}"))
        conn.commit()

    finally:
        conn.close()

    cvm_pct    = round(with_cvm    / total * 100, 1) if total else 0
    dfp_itr_pct = round(with_dfp_itr / total * 100, 1) if total else 0

    report = (
        f"=== B3-CVM Bridge Sync Complete ===\n"
        f"Duration         : {duration}s\n"
        f"Instruments rows : {len(inst_rows):,} (CASH/EQUITY-CASH)\n"
        f"ISIN->CNPJ index : {len(isin_cnpj):,}\n"
        f"CVM register     : {len(cvm_rows):,}\n"
        f"Bridge total     : {total:,} tickers\n"
        f"With CVM data    : {with_cvm:,} ({cvm_pct}%)\n"
        f"With dfp_itr data : {with_dfp_itr:,} ({dfp_itr_pct}%)\n"
        f"No CNPJ in ZIP   : {no_cnpj:,}\n"
        f"Synced at        : {now_iso}\n"
    )
    print(f"[b3_cvm] {report}", file=sys.stderr)
    return {
        "status": "success",
        "instruments": len(inst_rows), "isin_cnpj": len(isin_cnpj),
        "cvm_rows": len(cvm_rows), "bridge_total": total,
        "with_cvm": with_cvm, "with_dfp_itr": with_dfp_itr,
        "no_cnpj": no_cnpj, "cvm_pct": cvm_pct, "dfp_itr_pct": dfp_itr_pct,
        "duration_s": duration, "synced_at": now_iso, "report": report,
    }


# ── Mode: status ──────────────────────────────────────────────────────────────

def mode_status() -> dict:
    path = bridge_path()
    if not path.exists():
        return {"status": "not_synced",
                "message": "bridge.db not found. Run skill(domain='b3_cvm', mode='sync')."}
    try:
        conn        = connect_bridge(read_only=True)
        total       = conn.execute("SELECT COUNT(*) FROM company_map").fetchone()[0]
        with_cvm    = conn.execute("SELECT COUNT(*) FROM company_map WHERE cd_cvm > 0").fetchone()[0]
        with_dfp_itr = conn.execute("SELECT COUNT(*) FROM company_map WHERE dfp_itr_ids != '[]'").fetchone()[0]
        shares      = conn.execute("SELECT COUNT(*) FROM company_map WHERE catg='SHARES'").fetchone()[0]
        units       = conn.execute("SELECT COUNT(*) FROM company_map WHERE catg='UNIT'").fetchone()[0]
        last_log    = conn.execute("SELECT * FROM sync_log ORDER BY id DESC LIMIT 1").fetchone()
        conn.close()

        last_sync = last_log["synced_at"] if last_log else "never"
        duration  = last_log["duration_s"] if last_log else 0
        age_warn  = ""
        if last_log and last_log["synced_at"]:
            try:
                age_days = (datetime.now(timezone.utc) - datetime.fromisoformat(last_log["synced_at"])).days
                if age_days > 7:
                    age_warn = f" [{age_days}d old -- consider re-syncing]"
            except Exception:
                pass

        report = (
            f"=== B3-CVM Bridge Status ===\n"
            f"Last sync        : {last_sync}{age_warn}\n"
            f"Sync duration    : {duration}s\n"
            f"Total tickers    : {total:,} (SHARES={shares:,} UNIT={units:,})\n"
            f"With CVM data    : {with_cvm:,} ({round(with_cvm/total*100,1) if total else 0}%)\n"
            f"With dfp_itr data : {with_dfp_itr:,} ({round(with_dfp_itr/total*100,1) if total else 0}%)\n"
            f"Bridge file      : {path}\n"
        )
        return {
            "status": "ok", "last_sync": last_sync, "total": total,
            "shares": shares, "units": units,
            "with_cvm": with_cvm, "with_dfp_itr": with_dfp_itr,
            "bridge_path": str(path), "report": report,
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}


# ── Mode: lookup ──────────────────────────────────────────────────────────────

def mode_lookup(ticker: str = "", cnpj: str = "", cd_cvm: int = 0) -> dict:
    """Resolve company by ticker, CNPJ, or CD_CVM to full identity record."""
    if not ticker and not cnpj and not cd_cvm:
        return {"status": "error", "error": "Provide ticker, cnpj, or cd_cvm"}
    try:
        conn = connect_bridge(read_only=True)
    except FileNotFoundError as e:
        return {"status": "error", "error": str(e)}
    try:
        if ticker:
            row = conn.execute(
                "SELECT * FROM company_map WHERE upper(ticker)=? LIMIT 1",
                (ticker.upper(),),
            ).fetchone()
            if not row:
                return {"status": "not_found",
                        "error": f"Ticker '{ticker}' not found. Run mode='sync' first."}
            query_cnpj = row["cnpj"]
        elif cnpj:
            query_cnpj = cnpj_digits(cnpj)
            row = conn.execute(
                "SELECT * FROM company_map WHERE cnpj=? LIMIT 1", (query_cnpj,),
            ).fetchone()
            if not row:
                return {"status": "not_found", "error": f"CNPJ '{cnpj}' not found"}
        else:
            row = conn.execute(
                "SELECT * FROM company_map WHERE cd_cvm=? LIMIT 1", (int(cd_cvm),),
            ).fetchone()
            if not row:
                return {"status": "not_found", "error": f"CD_CVM {cd_cvm} not found"}
            query_cnpj = row["cnpj"]

        all_rows = conn.execute(
            "SELECT ticker, isin, b3_name, sgmt, catg, spec_cd, gov_level, mkt_cap "
            "FROM company_map WHERE cnpj=? ORDER BY ticker", (query_cnpj,),
        ).fetchall()

        tickers    = [{"ticker": r["ticker"], "isin": r["isin"], "name": r["b3_name"],
                       "sgmt": r["sgmt"], "catg": r["catg"], "spec": r["spec_cd"],
                       "gov": r["gov_level"], "mkt_cap": r["mkt_cap"]}
                      for r in all_rows]
        dfp_itr_ids = json.loads(row["dfp_itr_ids"] or "[]")
        ticker_str = ", ".join(t["ticker"] for t in tickers)

        result = {
            "status": "success",
            "cnpj": row["cnpj"], "cd_cvm": row["cd_cvm"],
            "denom_social": row["denom_social"], "denom_comerc": row["denom_comerc"],
            "b3_name": row["b3_name"], "sit": row["sit"],
            "tp_merc": row["tp_merc"], "setor_ativ": row["setor_ativ"],
            "gov_level": row["gov_level"],
            "tickers": tickers, "dfp_itr_ids": dfp_itr_ids,
            "synced_at": row["synced_at"],
        }
        result["report"] = (
            f"Company    : {row['denom_social'] or row['b3_name']}\n"
            f"Commercial : {row['denom_comerc']}\n"
            f"CNPJ       : {row['cnpj']}\n"
            f"CD_CVM     : {row['cd_cvm']}\n"
            f"Governance : {row['gov_level']}\n"
            f"Tickers    : {ticker_str}\n"
            f"Status CVM : {row['sit']}\n"
            f"Sector     : {row['setor_ativ']}\n"
            f"dfp_itr_ids : {len(dfp_itr_ids)} rows\n"
        )
        return result
    except Exception as e:
        import traceback
        return {"status": "error",
                "error": f"{type(e).__name__}: {e}\n{traceback.format_exc()}"}
    finally:
        conn.close()


# ── Mode: resolve ─────────────────────────────────────────────────────────────

def mode_resolve(query: str = "") -> dict:
    """Fuzzy name search across bridge.db. Returns up to 10 companies."""
    if not query or len(query.strip()) < 2:
        return {"status": "error", "error": "query must be >= 2 characters"}
    try:
        conn = connect_bridge(read_only=True)
    except FileNotFoundError as e:
        return {"status": "error", "error": str(e)}
    try:
        q = f"%{query.upper()}%"
        cnpj_rows = conn.execute("""
            SELECT DISTINCT cnpj FROM company_map
            WHERE upper(denom_social) LIKE ? OR upper(denom_comerc) LIKE ?
               OR upper(b3_name)      LIKE ?
            ORDER BY CASE WHEN upper(denom_social) LIKE ? THEN 0 ELSE 1 END, denom_social
            LIMIT 10
        """, (q, q, q, q)).fetchall()

        companies = []
        for (cnpj,) in cnpj_rows:
            rep = conn.execute(
                "SELECT * FROM company_map WHERE cnpj=? LIMIT 1", (cnpj,)
            ).fetchone()
            if not rep:
                continue
            ticks = conn.execute(
                "SELECT ticker, isin, catg FROM company_map WHERE cnpj=? ORDER BY ticker",
                (cnpj,),
            ).fetchall()
            companies.append({
                "cnpj": rep["cnpj"], "cd_cvm": rep["cd_cvm"],
                "denom_social": rep["denom_social"], "denom_comerc": rep["denom_comerc"],
                "b3_name": rep["b3_name"], "sit": rep["sit"],
                "gov_level": rep["gov_level"], "setor_ativ": rep["setor_ativ"],
                "tickers": [{"ticker": r["ticker"], "isin": r["isin"], "catg": r["catg"]}
                            for r in ticks],
                "dfp_itr_ids": json.loads(rep["dfp_itr_ids"] or "[]"),
            })

        if not companies:
            return {"status": "not_found", "query": query,
                    "error": f"No companies found matching '{query}'"}

        lines = [f"=== Companies matching '{query}' ===", ""]
        for c in companies:
            tstr = " / ".join(t["ticker"] for t in c["tickers"])
            lines += [c["denom_social"] or c["b3_name"],
                      f"  CNPJ:{c['cnpj']}  CD_CVM:{c['cd_cvm']}  Gov:{c['gov_level']}",
                      f"  Tickers: {tstr}  Status:{c['sit']}",
                      f"  dfp_itr_ids: {len(c['dfp_itr_ids'])} rows", ""]
        return {"status": "success", "query": query, "count": len(companies),
                "companies": companies, "report": "\n".join(lines)}
    except Exception as e:
        return {"status": "error", "error": str(e)}
    finally:
        conn.close()


# ── Mode: tickers ─────────────────────────────────────────────────────────────

def mode_tickers(query: str = "") -> dict:
    """List all B3 tickers for a company (name fragment or CNPJ)."""
    if not query:
        return {"status": "error", "error": "query is required"}
    try:
        conn = connect_bridge(read_only=True)
    except FileNotFoundError as e:
        return {"status": "error", "error": str(e)}
    try:
        c = cnpj_digits(query)
        if c:
            rows = conn.execute(
                "SELECT ticker, isin, b3_name, catg, spec_cd, gov_level, cnpj, cd_cvm "
                "FROM company_map WHERE cnpj=? ORDER BY ticker", (c,)
            ).fetchall()
        else:
            q     = f"%{query.upper()}%"
            cnpjs = conn.execute(
                "SELECT DISTINCT cnpj FROM company_map "
                "WHERE upper(denom_social) LIKE ? OR upper(b3_name) LIKE ? LIMIT 5",
                (q, q),
            ).fetchall()
            rows = []
            for (cn,) in cnpjs:
                rows += conn.execute(
                    "SELECT ticker, isin, b3_name, catg, spec_cd, gov_level, cnpj, cd_cvm "
                    "FROM company_map WHERE cnpj=? ORDER BY ticker", (cn,)
                ).fetchall()

        if not rows:
            return {"status": "not_found", "query": query,
                    "error": f"No tickers found for '{query}'"}

        tickers = [dict(r) for r in rows]
        lines   = [f"=== Tickers for '{query}' ===", ""]
        for t in tickers:
            lines.append(f"  {t['ticker']:<10} {t['isin']:<18} "
                         f"{t['catg']:<8} {t['spec_cd']:<12} {t['gov_level']}")
        lines.append(f"\nTotal: {len(tickers)}")
        return {"status": "success", "query": query, "count": len(tickers),
                "tickers": tickers, "report": "\n".join(lines)}
    except Exception as e:
        return {"status": "error", "error": str(e)}
    finally:
        conn.close()


# ── Public helpers (imported by cvm_* skills) ─────────────────────────────────

def resolve_by_ticker(ticker: str) -> Optional[dict]:
    r = mode_lookup(ticker=ticker)
    return r if r.get("status") == "success" else None

def resolve_by_cnpj(cnpj: str) -> Optional[dict]:
    r = mode_lookup(cnpj=cnpj)
    return r if r.get("status") == "success" else None

def resolve_by_cd_cvm(cd_cvm: int) -> Optional[dict]:
    r = mode_lookup(cd_cvm=cd_cvm)
    return r if r.get("status") == "success" else None
