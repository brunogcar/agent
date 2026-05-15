#!/usr/bin/env python
"""
inspect_rapina_dividends.py -- What dividend/shareholder data exists in rapina.db?

Checks:
  1. fre table contents (we know it's 0 rows but check columns anyway)
  2. DVA accounts -- dividends often appear here
  3. DRE accounts -- JCP (Juros sobre Capital Proprio) appears in DRE
  4. BPP accounts -- dividends payable, retained earnings, equity breakdown
  5. isin table -- what data is actually there
  6. Any account description containing "dividend", "JCP", "lucro", "acionista"

Usage: python inspect_rapina_dividends.py [path/to/rapina.db]
"""

import sqlite3, sys
from pathlib import Path

DB = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("D:/mcp/agent/memory_db/cvm/rapina.db")
conn = sqlite3.connect(str(DB))
conn.row_factory = sqlite3.Row

def q(sql, *args): return conn.execute(sql, args).fetchall()
def section(t): print(f"\n{'='*70}\n{t}\n{'='*70}")

# 1. fre table
section("1. FRE TABLE")
print(f"  Rows: {q('SELECT COUNT(*) FROM fre')[0][0]}")
cols = q("PRAGMA table_info(fre)")
print(f"  Columns: {[c['name'] for c in cols]}")

# 2. isin table -- what's actually useful there
section("2. ISIN TABLE SAMPLE (non-fund rows)")
rows = q("""
    SELECT key, ticker, cnpj, nome FROM isin
    WHERE LENGTH(ticker) = 5
    AND ticker GLOB '[A-Z][A-Z][A-Z][A-Z][0-9]*'
    LIMIT 20
""")
for r in rows:
    print(f"  ticker={r['ticker']:8s}  cnpj={r['cnpj']:20s}  nome={r['nome'][:40]}")

# 3. DVA accounts -- dividends/JCP appear here
section("3. DVA ACCOUNTS SAMPLE (all distinct descriptions)")
rows = q("""
    SELECT DISTINCT codigo, descr, COUNT(DISTINCT id_empresa) as companies
    FROM contas WHERE grupo='DVA'
    GROUP BY codigo, descr
    ORDER BY codigo
    LIMIT 40
""")
for r in rows:
    print(f"  {r['codigo']:15s}  {r['descr'][:50]:50s}  ({r['companies']} cos)")

# 4. Dividend-related account descriptions anywhere
section("4. DIVIDEND/JCP KEYWORD SEARCH IN contas.descr")
keywords = ['dividend', 'divid', 'jcp', 'juros sobre capital', 'lucros e dividend',
            'remuneracao', 'acionista', 'distribui']
for kw in keywords:
    rows = q(f"""
        SELECT DISTINCT grupo, codigo, descr, COUNT(DISTINCT id_empresa) as cos
        FROM contas WHERE LOWER(descr) LIKE ?
        GROUP BY grupo, codigo, descr
        ORDER BY cos DESC
        LIMIT 5
    """, f"%{kw}%")
    if rows:
        print(f"\n  Keyword: '{kw}'")
        for r in rows:
            print(f"    {r['grupo']:6s}  {r['codigo']:15s}  {r['descr'][:50]}  ({r['cos']} cos)")

# 5. BPP equity breakdown -- retained earnings, dividends payable
section("5. BPP EQUITY ACCOUNTS (codigo starts with 2.03)")
rows = q("""
    SELECT DISTINCT codigo, descr, COUNT(DISTINCT id_empresa) as cos
    FROM contas WHERE grupo='BPP' AND codigo LIKE '2.03%'
    GROUP BY codigo, descr ORDER BY codigo
    LIMIT 30
""")
for r in rows:
    print(f"  {r['codigo']:20s}  {r['descr'][:50]:50s}  ({r['cos']} cos)")

# 6. DRE accounts with JCP / interest on equity
section("6. DRE ACCOUNTS WITH JCP/INTEREST KEYWORDS")
rows = q("""
    SELECT DISTINCT codigo, descr, COUNT(DISTINCT id_empresa) as cos
    FROM contas WHERE grupo='DRE'
    AND (LOWER(descr) LIKE '%juros%' OR LOWER(descr) LIKE '%jcp%'
         OR LOWER(descr) LIKE '%capital proprio%')
    GROUP BY codigo, descr ORDER BY cos DESC LIMIT 20
""")
for r in rows:
    print(f"  {r['codigo']:15s}  {r['descr'][:60]:60s}  ({r['cos']} cos)")

# 7. DMPL table check -- equity statement has dividend/retained earnings detail
section("7. DMPL GROUP (Demonstracao Mutacoes Patrimonio Liquido)")
cnt = q("SELECT COUNT(*) FROM contas WHERE grupo='DMPL'")[0][0]
print(f"  DMPL rows in contas: {cnt}")
if cnt > 0:
    rows = q("""
        SELECT DISTINCT codigo, descr, COUNT(DISTINCT id_empresa) as cos
        FROM contas WHERE grupo='DMPL'
        GROUP BY codigo, descr ORDER BY codigo LIMIT 20
    """)
    for r in rows:
        print(f"  {r['codigo']:20s}  {r['descr'][:50]}  ({r['cos']} cos)")

# 8. Petrobras DVA -- actual dividend values
section("8. PETROBRAS DVA SAMPLE (dividends paid to shareholders)")
petro = q("SELECT id FROM empresas WHERE nome LIKE '%PETROBRAS%' ORDER BY ano DESC LIMIT 1")
if petro:
    pid = petro[0]['id']
    rows = q("""
        SELECT codigo, descr, valor*escala as val_real, data_fim_exerc, meses
        FROM contas
        WHERE id_empresa=? AND grupo='DVA' AND meses=12
        ORDER BY data_fim_exerc DESC, codigo
        LIMIT 30
    """, pid)
    for r in rows:
        print(f"  {r['codigo']:15s}  {r['descr'][:40]:40s}  {r['val_real']:>20,.0f}  {r['data_fim_exerc']}")

# 9. Summary of what's available
section("9. SUMMARY -- DISTINCT grupos IN contas")
for r in q("SELECT grupo, COUNT(*) as rows, COUNT(DISTINCT id_empresa) as cos FROM contas GROUP BY grupo ORDER BY rows DESC"):
    print(f"  {r['grupo']:10s}  {r['rows']:>12,} rows  {r['cos']:>6,} companies")

conn.close()
print("\n" + "="*70 + "\nDONE\n" + "="*70)
