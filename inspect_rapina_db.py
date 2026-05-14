#!/usr/bin/env python
"""
inspect_rapina_db.py -- Discover rapina.db schema and sample data.

Run this BEFORE writing the CVM skill so we know exactly what tables,
columns, and data formats rapinav2 uses.

Usage:
  python inspect_rapina_db.py                         # default path
  python inspect_rapina_db.py D:/path/to/rapina.db    # custom path

Output: prints schema + sample rows for every table, then a PETR4/PETROBRAS
lookup to show exactly what a query looks like.
"""

from __future__ import annotations
import json
import sqlite3
import sys
from pathlib import Path


def main():
    db_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("D:/mcp/agent/memory_db/cvm/rapina.db")

    if not db_path.exists():
        print(f"ERROR: rapina.db not found at {db_path}")
        print("Move it there first, or pass the path as an argument:")
        print("  python inspect_rapina_db.py E:/Downloads/rapina/v2/.dados/rapina.db")
        return 1

    print(f"Opening: {db_path} ({db_path.stat().st_size / 1024 / 1024:.1f} MB)\n")
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    # ── 1. All tables ─────────────────────────────────────────────────────────
    tables = [r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    ).fetchall()]

    print("=" * 70)
    print(f"TABLES ({len(tables)} total)")
    print("=" * 70)
    for t in tables:
        count = conn.execute(f"SELECT COUNT(*) FROM [{t}]").fetchone()[0]
        print(f"  {t:40s} {count:>10,} rows")

    # ── 2. Schema for each table ───────────────────────────────────────────────
    print("\n" + "=" * 70)
    print("SCHEMAS")
    print("=" * 70)
    for t in tables:
        cols = conn.execute(f"PRAGMA table_info([{t}])").fetchall()
        print(f"\n[{t}]")
        for c in cols:
            print(f"  {c['name']:35s} {c['type']:15s} {'NOT NULL' if c['notnull'] else 'nullable'} {'PK' if c['pk'] else ''}")

    # ── 3. Sample rows from each table ────────────────────────────────────────
    print("\n" + "=" * 70)
    print("SAMPLE DATA (3 rows per table)")
    print("=" * 70)
    for t in tables:
        print(f"\n[{t}]")
        try:
            rows = conn.execute(f"SELECT * FROM [{t}] LIMIT 3").fetchall()
            if rows:
                keys = rows[0].keys()
                print("  " + " | ".join(f"{k[:20]}" for k in keys))
                print("  " + "-" * min(120, len(" | ".join(f"{k[:20]}" for k in keys))))
                for row in rows:
                    print("  " + " | ".join(f"{str(row[k])[:20]}" for k in keys))
            else:
                print("  (empty)")
        except Exception as e:
            print(f"  ERROR: {e}")

    # ── 4. Company lookup — find PETROBRAS / PETR4 ───────────────────────────
    print("\n" + "=" * 70)
    print("PETROBRAS LOOKUP (key company for testing)")
    print("=" * 70)

    # Try common table/column names rapinav2 might use
    search_queries = [
        ("SELECT * FROM empresa WHERE nome LIKE '%PETRO%' LIMIT 5", "empresa.nome"),
        ("SELECT * FROM company WHERE name LIKE '%PETRO%' LIMIT 5", "company.name"),
        ("SELECT * FROM cia_aberta WHERE DENOM_CIA LIKE '%PETRO%' LIMIT 5", "cia_aberta"),
        ("SELECT DISTINCT CD_CVM, DENOM_CIA FROM dfp WHERE DENOM_CIA LIKE '%PETRO%' LIMIT 5", "dfp"),
        ("SELECT DISTINCT CD_CVM, DENOM_CIA FROM itr WHERE DENOM_CIA LIKE '%PETRO%' LIMIT 5", "itr"),
        ("SELECT * FROM companies WHERE ticker LIKE '%PETR%' OR name LIKE '%PETRO%' LIMIT 5", "companies"),
    ]

    for q, label in search_queries:
        try:
            rows = conn.execute(q).fetchall()
            if rows:
                print(f"\n  Found via '{label}':")
                for row in rows:
                    print(f"    {dict(row)}")
        except Exception:
            pass

    # ── 5. Find the main financial data table ────────────────────────────────
    print("\n" + "=" * 70)
    print("FINANCIAL DATA STRUCTURE")
    print("=" * 70)

    # Look for tables with typical CVM column names
    cvm_cols = {"CD_CVM", "CNPJ_CIA", "DT_REFER", "VL_CONTA", "DS_CONTA", "CD_CONTA"}
    for t in tables:
        cols = {c["name"].upper() for c in conn.execute(f"PRAGMA table_info([{t}])").fetchall()}
        overlap = cvm_cols & cols
        if len(overlap) >= 3:
            print(f"\n  Table '{t}' has CVM columns: {overlap}")
            # Get date range
            try:
                dates = conn.execute(
                    f"SELECT MIN(DT_REFER), MAX(DT_REFER), COUNT(DISTINCT DT_REFER) "
                    f"FROM [{t}]"
                ).fetchone()
                print(f"    Date range: {dates[0]} to {dates[1]} ({dates[2]} distinct dates)")
            except Exception:
                pass
            # Get distinct ORDEM_EXERC or period types if present
            for col in ["ORDEM_EXERC", "GRUPO_DFP", "ESCALA_MOEDA"]:
                try:
                    vals = conn.execute(
                        f"SELECT DISTINCT {col} FROM [{t}] LIMIT 10"
                    ).fetchall()
                    print(f"    {col}: {[r[0] for r in vals]}")
                except Exception:
                    pass

    # ── 6. Full sample for one company/year ──────────────────────────────────
    print("\n" + "=" * 70)
    print("FULL PETROBRAS SAMPLE (one period, one statement type)")
    print("=" * 70)

    # Try to get a slice of Petrobras DRE data
    petro_queries = [
        """SELECT * FROM dfp
           WHERE DENOM_CIA LIKE '%PETRO%'
           AND GRUPO_DFP = 'DF Consolidado - Demonstração do Resultado'
           ORDER BY DT_REFER DESC LIMIT 10""",
        """SELECT * FROM financials
           WHERE company LIKE '%PETRO%'
           ORDER BY year DESC LIMIT 10""",
        """SELECT * FROM report
           WHERE name LIKE '%PETRO%'
           ORDER BY period DESC LIMIT 10""",
    ]

    for q in petro_queries:
        try:
            rows = conn.execute(q).fetchall()
            if rows:
                print(f"\n  Query: {q[:80]}...")
                for row in rows[:5]:
                    print(f"  {dict(row)}")
                break
        except Exception:
            pass

    conn.close()

    print("\n" + "=" * 70)
    print("DONE — paste this output to Claude to design the CVM skill")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(main())
