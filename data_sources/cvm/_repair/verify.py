"""data_sources/cvm/_repair/verify.py — CVM data integrity verifier.

Run this after any CVM sync to confirm data integrity. Checks:
  1. No PENÚLTIMO rows (except 2009)
  2. No meses=12 rows in ITR with quarter-end dates
  3. CNPJ format consistency (all 14 plain digits)
  4. No duplicate empresa rows (same cnpj + ano)
  5. PETR4, VALE3, WEGE3 quarterly data is intact
  6. Year × meses breakdown

Usage:
  python -m data_sources.cvm._repair.verify
  python -m data_sources.cvm._repair.verify --itr
  python -m data_sources.cvm._repair.verify --dfp
"""
from __future__ import annotations

import argparse
import os
import sqlite3
import sys

from data_sources.cvm._db import dfp_db_path, itr_db_path

SPOT_CHECK_COMPANIES = {
    "PETR4": "33000167000101",   # PETROLEO BRASILEIRO S.A. PETROBRAS
    "VALE3": "33592510000154",   # VALE S.A.
    "WEGE3": "84429695000111",   # WEG S.A. (was 84153925000154 — wrong)
    "ITUB4": "60872504000123",   # ITAU UNIBANCO HOLDING S.A. (was 60701190000104 — wrong)
    "BBDC4": "60746948000112",   # BANCO BRADESCO S.A.
    "ABEV3": "07526557000100",   # AMBEV S.A. (was 07526555000100 — off by 2 digits)
}


def separator(title: str):
    print(f"\n{'─' * 60}")
    print(f"  {title}")
    print(f"{'─' * 60}")


def check_no_penultimo(conn, label: str):
    separator(f"{label}: PENÚLTIMO rows (should be 0 except 2009)")
    rows = conn.execute(
        "SELECT CASE WHEN data_fim_exerc LIKE '2009%' THEN '2009 (OK)' "
        "ELSE 'non-2009 (BAD)' END as category, "
        "COUNT(*) as cnt FROM contas WHERE ordem_exerc = 'PENÚLTIMO' "
        "GROUP BY category"
    ).fetchall()
    if not rows:
        print("  OK: No PENÚLTIMO rows found")
    else:
        for r in rows:
            status = "OK" if r[0] == "2009 (OK)" else "FAIL"
            print(f"  [{status}] {r['category']}: {r['cnt']:,} rows")
    empty = conn.execute(
        "SELECT COUNT(*) FROM contas WHERE ordem_exerc IS NULL OR ordem_exerc = ''"
    ).fetchone()[0]
    if empty > 0:
        print(f"  [WARN] {empty:,} rows have empty ordem_exerc")


def check_no_misstamped(conn, label: str):
    if label != "ITR":
        return
    separator(f"{label}: meses=12 flow rows at quarter-ends (should be 0)")
    # meses=12 at quarter-ends is CORRECT for BPA/BPP (balance sheet snapshots —
    # point-in-time, dt_ini is empty, compute_meses returns 12).
    # It's only a bug for FLOW statements (DRE/DFC/DVA) which have dt_ini set
    # and should be meses=3/6/9 at quarter-ends.
    rows = conn.execute(
        "SELECT data_fim_exerc, meses, grupo, COUNT(*) as cnt FROM contas "
        "WHERE meses = 12 AND data_fim_exerc IN "
        "('2025-03-31','2025-06-30','2025-09-30','2024-03-31','2024-06-30','2024-09-30') "
        "AND (grupo LIKE '%DRE%' OR grupo LIKE '%DFC%' OR grupo LIKE '%DVA%') "
        "GROUP BY data_fim_exerc, meses, grupo ORDER BY data_fim_exerc"
    ).fetchall()
    if not rows:
        print("  OK: No mis-stamped flow rows (BPA/BPP meses=12 at quarter-ends is normal)")
    else:
        print("  [FAIL] Found mis-stamped FLOW rows:")
        for r in rows:
            print(f"    {r['data_fim_exerc']} meses={r['meses']} grupo={r['grupo']}: {r['cnt']:,} rows")


def check_cnpj_format(conn, label: str):
    separator(f"{label}: CNPJ format consistency")
    rows = conn.execute(
        "SELECT CASE WHEN LENGTH(cnpj) = 14 AND cnpj NOT LIKE '%.%' "
        "AND cnpj NOT LIKE '%/%' THEN 'plain-14 (OK)' ELSE 'other (BAD)' END as fmt, "
        "COUNT(*) as cnt FROM empresas GROUP BY fmt"
    ).fetchall()
    for r in rows:
        status = "OK" if r[0] == "plain-14 (OK)" else "FAIL"
        print(f"  [{status}] {r['fmt']}: {r['cnt']:,}")


def check_no_duplicates(conn, label: str):
    separator(f"{label}: Duplicate empresa rows (same cnpj + ano)")
    rows = conn.execute(
        "SELECT cnpj, ano, COUNT(*) as cnt FROM empresas "
        "GROUP BY cnpj, ano HAVING cnt > 1 ORDER BY cnt DESC LIMIT 10"
    ).fetchall()
    if not rows:
        print("  OK: No duplicate empresa rows")
    else:
        print(f"  [FAIL] Found duplicates:")
        for r in rows:
            print(f"    CNPJ={r['cnpj']} ano={r['ano']}: {r['cnt']} rows")


def check_spot_companies(conn, label: str):
    if label != "ITR":
        return
    separator(f"{label}: Spot-check companies (2025 quarters)")
    for ticker, cnpj in SPOT_CHECK_COMPANIES.items():
        rows = conn.execute(
            "SELECT c.data_fim_exerc, c.meses, c.ordem_exerc, COUNT(*) as rows "
            "FROM contas c JOIN empresas e ON c.id_empresa = e.id "
            "WHERE e.cnpj = ? AND c.data_fim_exerc LIKE '2025%' "
            "GROUP BY c.data_fim_exerc, c.meses, c.ordem_exerc "
            "ORDER BY c.data_fim_exerc, c.meses",
            (cnpj,),
        ).fetchall()
        print(f"\n  {ticker} ({cnpj}):")
        if not rows:
            print("    [WARN] No 2025 data found")
            continue
        for r in rows:
            ordem_tag = r["ordem_exerc"] or "(empty)"
            status = "OK" if r["ordem_exerc"] == "ÚLTIMO" else "FAIL"
            print(
                f"    [{status}] {r['data_fim_exerc']} meses={r['meses']:2d} "
                f"ordem={ordem_tag:10s} rows={r['rows']:>5}"
            )


def check_year_meses(conn, label: str):
    separator(f"{label}: Year x meses distribution (recent years)")
    rows = conn.execute(
        "SELECT substr(data_fim_exerc, 1, 4) as yr, meses, COUNT(*) as rows "
        "FROM contas WHERE data_fim_exerc >= '2023-01-01' "
        "GROUP BY yr, meses ORDER BY yr, meses"
    ).fetchall()
    current_yr = None
    for r in rows:
        if r["yr"] != current_yr:
            if current_yr is not None:
                print()
            print(f"  {r['yr']}:", end="")
            current_yr = r["yr"]
        print(f"  m{r['meses']}={r['rows']:,}", end="")
    print()


def verify_db(db_path, label: str):
    if not os.path.exists(str(db_path)):
        print(f"\n[skip] {label} database not found at {db_path}")
        return
    print(f"\n{'=' * 60}")
    print(f"  Verifying {label}: {db_path}")
    print(f"{'=' * 60}")
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    check_no_penultimo(conn, label)
    check_no_misstamped(conn, label)
    check_cnpj_format(conn, label)
    check_no_duplicates(conn, label)
    check_spot_companies(conn, label)
    check_year_meses(conn, label)
    conn.close()


def main():
    parser = argparse.ArgumentParser(
        description="Verify CVM data integrity.",
    )
    parser.add_argument("--itr", action="store_true", help="Verify ITR only")
    parser.add_argument("--dfp", action="store_true", help="Verify DFP only")
    args = parser.parse_args()

    do_itr = args.itr or (not args.itr and not args.dfp)
    do_dfp = args.dfp or (not args.itr and not args.dfp)

    if do_itr:
        verify_db(itr_db_path(), "ITR")
    if do_dfp:
        verify_db(dfp_db_path(), "DFP")

    print(f"\n{'=' * 60}")
    print("  Verification complete.")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
