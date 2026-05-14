#!/usr/bin/env python
"""
inspect_rapina_db_v2.py -- Targeted rapina.db inspection using correct schema.

Now we know: contas + empresas + isin are the three key tables.
This script answers the remaining questions needed to write the CVM skill:

  1. What grupo values exist? (maps to BPA/BPP/DRE/DFC/DVA)
  2. What does the account code hierarchy look like?
  3. How does ticker -> CNPJ -> id_empresa work?
  4. What does a full Petrobras DRE look like?
  5. What is the meses distribution? (3/6/9/12)
  6. What is the date range in contas?
  7. What account codes map to the "resumo" sheet fields?

Usage: python inspect_rapina_db_v2.py [optional: path/to/rapina.db]
"""

from __future__ import annotations
import sqlite3
import sys
from pathlib import Path


DB = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("D:/mcp/agent/memory_db/cvm/rapina.db")
conn = sqlite3.connect(str(DB))
conn.row_factory = sqlite3.Row


def q(sql, *args):
    return conn.execute(sql, args).fetchall()


def section(title):
    print(f"\n{'='*70}\n{title}\n{'='*70}")


# ── 1. grupo values ────────────────────────────────────────────────────────
section("1. DISTINCT grupo VALUES IN contas")
for row in q("SELECT grupo, COUNT(*) as cnt FROM contas GROUP BY grupo ORDER BY cnt DESC"):
    print(f"  {row['grupo']:40s} {row['cnt']:>10,}")

# ── 2. consolidado values ─────────────────────────────────────────────────
section("2. DISTINCT consolidado VALUES")
for row in q("SELECT consolidado, COUNT(*) as cnt FROM contas GROUP BY consolidado"):
    print(f"  consolidado={row['consolidado']}  rows={row['cnt']:,}")

# ── 3. meses distribution ────────────────────────────────────────────────
section("3. DISTINCT meses VALUES (period length)")
for row in q("SELECT meses, COUNT(*) as cnt FROM contas GROUP BY meses ORDER BY meses"):
    print(f"  meses={row['meses']:2d} ({['','','annual??','quarterly','','','','','','','','','annual'][min(row['meses'],12)]:10s})  rows={row['cnt']:,}")

# ── 4. date range ─────────────────────────────────────────────────────────
section("4. DATE RANGE IN contas")
for row in q("SELECT MIN(data_fim_exerc), MAX(data_fim_exerc), COUNT(DISTINCT data_fim_exerc) FROM contas"):
    print(f"  From: {row[0]}")
    print(f"  To:   {row[1]}")
    print(f"  Distinct dates: {row[2]}")

# ── 5. isin ticker lookup ────────────────────────────────────────────────
section("5. TICKER LOOKUP — PETR4, PETR3, VALE3")
for ticker in ("PETR4", "PETR3", "VALE3", "ITUB4", "WEGE3"):
    rows = q("SELECT * FROM isin WHERE ticker = ? LIMIT 3", ticker)
    if rows:
        for r in rows:
            print(f"  {ticker}: cnpj={r['cnpj']}  nome={r['nome']}")
    else:
        print(f"  {ticker}: NOT FOUND in isin")

# ── 6. empresas lookup by CNPJ ───────────────────────────────────────────
section("6. empresas LOOKUP — find Petrobras id")
# PETR4 CNPJ is 33.000.167/0001-01 (known)
# Try both formatted and unformatted
for cnpj in ("33.000.167/0001-01", "33000167000101", "33.000.167"):
    rows = q("SELECT * FROM empresas WHERE cnpj LIKE ? LIMIT 5", f"%{cnpj}%")
    if rows:
        for r in rows:
            print(f"  id={r['id']}  cnpj={r['cnpj']}  nome={r['nome']}  ano={r['ano']}")
        break

# ── 7. isin cnpj format ───────────────────────────────────────────────────
section("7. isin CNPJ FORMAT (first 10 rows)")
for r in q("SELECT * FROM isin WHERE ticker NOT LIKE '000%' LIMIT 10"):
    print(f"  ticker={r['ticker']:10s}  cnpj={r['cnpj']:20s}  nome={r['nome'][:40]}")

# ── 8. empresas CNPJ format ───────────────────────────────────────────────
section("8. empresas CNPJ FORMAT (first 10 rows)")
for r in q("SELECT * FROM empresas LIMIT 10"):
    print(f"  id={r['id']:6}  cnpj={r['cnpj']:25s}  nome={r['nome'][:40]}")

# ── 9. contas for id_empresa=1 (CAMIL) to understand structure ───────────
section("9. contas STRUCTURE — id_empresa=1, all grupos, most recent date")
latest = q("SELECT MAX(data_fim_exerc) FROM contas WHERE id_empresa=1")[0][0]
print(f"  Latest date for empresa 1: {latest}")
for r in q("""
    SELECT grupo, COUNT(*) as cnt, MIN(codigo), MAX(codigo)
    FROM contas WHERE id_empresa=1 AND data_fim_exerc=?
    GROUP BY grupo
""", latest):
    print(f"  grupo={r['grupo']:10s}  rows={r['cnt']:4}  codes={r[2]}..{r[3]}")

# ── 10. DRE sample for empresa 1 ─────────────────────────────────────────
section("10. DRE SAMPLE — empresa 1, most recent annual (meses=12)")
for r in q("""
    SELECT codigo, descr, valor, escala, meses, data_fim_exerc
    FROM contas
    WHERE id_empresa=1 AND grupo='DRE' AND meses=12
    ORDER BY data_fim_exerc DESC, codigo
    LIMIT 20
"""):
    val_real = r['valor'] * r['escala']
    print(f"  {r['codigo']:12s}  {r['descr'][:35]:35s}  {val_real:>20,.0f}  {r['data_fim_exerc']}")

# ── 11. Account code top-levels across all companies ──────────────────────
section("11. TOP-LEVEL ACCOUNT CODES (codigo length <= 4) by grupo")
for r in q("""
    SELECT grupo, codigo, descr, COUNT(DISTINCT id_empresa) as companies
    FROM contas
    WHERE LENGTH(codigo) <= 4
    GROUP BY grupo, codigo, descr
    ORDER BY grupo, codigo
    LIMIT 60
"""):
    print(f"  {r['grupo']:8s}  {r['codigo']:10s}  {r['descr'][:40]:40s}  ({r['companies']} cos)")

# ── 12. Find Petrobras via empresas search ────────────────────────────────
section("12. SEARCH empresas FOR PETROBRAS")
for r in q("SELECT * FROM empresas WHERE nome LIKE '%PETRO%' ORDER BY ano DESC LIMIT 10"):
    print(f"  id={r['id']:6}  cnpj={r['cnpj']}  nome={r['nome']}  ano={r['ano']}")

# ── 13. Full Petrobras DRE if found ──────────────────────────────────────
section("13. PETROBRAS FINANCIAL DATA (if found)")
petro = q("SELECT id FROM empresas WHERE nome LIKE '%PETROBRAS%' ORDER BY ano DESC LIMIT 1")
if petro:
    pid = petro[0]['id']
    print(f"  Using id_empresa={pid}")
    for r in q("""
        SELECT grupo, codigo, descr, valor, escala, meses, data_fim_exerc, consolidado
        FROM contas
        WHERE id_empresa=? AND meses=12 AND consolidado=1
        ORDER BY data_fim_exerc DESC, grupo, codigo
        LIMIT 30
    """, pid):
        val_real = r['valor'] * r['escala']
        print(f"  {r['grupo']:8s}  {r['codigo']:12s}  {r['descr'][:30]:30s}  {val_real:>20,.0f}  {r['data_fim_exerc']}")
else:
    print("  Petrobras not found by name -- checking isin table")
    for r in q("SELECT * FROM isin WHERE ticker='PETR4' LIMIT 3"):
        print(f"  isin: {dict(r)}")

# ── 14. How id_empresa links to empresas ────────────────────────────────
section("14. contas id_empresa DISTINCT COUNT vs empresas")
cnt_contas = q("SELECT COUNT(DISTINCT id_empresa) FROM contas")[0][0]
cnt_emp    = q("SELECT COUNT(*) FROM empresas")[0][0]
print(f"  Distinct id_empresa in contas: {cnt_contas:,}")
print(f"  Rows in empresas: {cnt_emp:,}")
print(f"  Note: empresas has one row per company per year (ano column)")
print(f"  So same company may have multiple ids across years")

# ── 15. Resumo candidates ────────────────────────────────────────────────
section("15. RESUMO ACCOUNT CODES (key fundamentals)")
# These are the codes rapinav2 uses for the 'resumo' sheet
# Standard CVM account codes for the key financials
resumo_codes = [
    ("3.11", "Resultado Bruto"),
    ("3.05", "EBIT / Resultado Operacional"),
    ("3.01", "Receita Liquida"),
    ("3.11.01", "Resultado Bruto"),
    ("6.01", "Caixa Operacional"),
    ("1",    "Ativo Total"),
    ("2",    "Passivo Total"),
    ("2.03", "Patrimonio Liquido"),
    ("2.01", "Passivo Circulante"),
    ("2.02", "Passivo Nao Circulante"),
]
for code, label in resumo_codes:
    cnt = q("SELECT COUNT(DISTINCT id_empresa) FROM contas WHERE codigo=?", code)[0][0]
    if cnt > 0:
        sample = q("SELECT descr FROM contas WHERE codigo=? LIMIT 1", code)
        descr = sample[0]['descr'] if sample else "?"
        print(f"  {code:12s}  {label:30s}  found in {cnt:,} companies  descr='{descr}'")
    else:
        print(f"  {code:12s}  {label:30s}  NOT FOUND")

conn.close()
print("\n" + "="*70)
print("DONE")
print("="*70)
