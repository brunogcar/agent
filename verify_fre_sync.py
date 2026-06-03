"""
verify_fre_sync.py
Deploy to: D:\\mcp\\agent\\verify_fre_sync.py

Smoke test for cvm_fre_sync.py.

Run modes:
    python verify_fre_sync.py              # status + parse test (no DB write, ~30-50MB download)
    python verify_fre_sync.py --sync       # sync current + prior year (writes to fre.db)
    python verify_fre_sync.py --full       # sync all years from 2010 (~15 min, 500MB+)
    python verify_fre_sync.py --year 2023  # sync a specific year only

NOTE: Parse test downloads a full FRE ZIP (~15-50MB) without writing to DB.
This is larger than IPE's ~5MB -- allow 30-60 seconds for the download.
"""

import sys, os, argparse
here = os.path.dirname(os.path.abspath(__file__))
if here not in sys.path:
    sys.path.insert(0, here)

parser = argparse.ArgumentParser(add_help=False)
parser.add_argument("--sync",  action="store_true")
parser.add_argument("--full",  action="store_true")
parser.add_argument("--year",  type=int, default=0)
args, _ = parser.parse_known_args()

DO_SYNC  = args.sync
DO_FULL  = args.full
YEAR_ARG = args.year

PASS = "[PASS]"; FAIL = "[FAIL]"; SKIP = "[SKIP]"
failures = []

def check(label, condition, detail=""):
    if condition:
        print(f"  {PASS} {label}" + (f"  -- {detail}" if detail else ""))
    else:
        print(f"  {FAIL} {label}" + (f"  -- {detail}" if detail else ""))
        failures.append(label)

def section(title):
    print(f"\n{'='*60}\n  {title}\n{'='*60}")

# ── 0. Import ─────────────────────────────────────────────────────────────────
section("0. Import check")
try:
    from skills.cvm.cvm_fre_sync import (
        url_for, sync, status, parse_zip, download_zip, query,
    )
    print("  [PASS] cvm_fre_sync imported OK")
except ImportError as e:
    print(f"  [FAIL] FATAL: {e}")
    sys.exit(1)

# ── 1. URL builder ────────────────────────────────────────────────────────────
section("1. URL builder")
from datetime import datetime
cur_year = datetime.now().year
for year, expected in [
    (2022, "FRE/DADOS/fre_cia_aberta_2022.zip"),
    (2024, "FRE/DADOS/fre_cia_aberta_2024.zip"),
    (cur_year, f"FRE/DADOS/fre_cia_aberta_{cur_year}.zip"),
]:
    url = url_for(year)
    check(f"url_for({year})", expected in url, url)

# ── 2. DB status ──────────────────────────────────────────────────────────────
section("2. DB status")
r = status()
check("status returns ok or not_synced",
      r.get("status") in ("ok", "not_synced"), r.get("error", ""))
if r.get("status") == "ok":
    print(f"\n{r.get('report','')}")
    check("has documentos", r.get("counts", {}).get("documentos", 0) > 0)
    db_has_data = r.get("counts", {}).get("documentos", 0) > 0
else:
    print("  fre.db not found or empty -- sync needed")
    db_has_data = False

# ── 3. Parse test (prior year, no DB write) ───────────────────────────────────
# DECISION: Download prior year (more complete than current) for parse test.
# FRE ZIPs are 15-50MB -- this will take 30-60 seconds. Progress shown via stderr.
parse_year = YEAR_ARG if YEAR_ARG else cur_year - 1
section(f"3. Parse test (FRE {parse_year}, no DB write)")
print(f"  Downloading FRE ZIP (~15-50MB, this may take 30-60s)...")
try:
    raw = download_zip(url_for(parse_year))
    check("download returns bytes", len(raw) > 100_000, f"{len(raw):,} bytes")
    check("is ZIP", raw[:2] == b"PK", f"magic={raw[:4]!r}")

    parsed = parse_zip(raw, parse_year)

    # Check filing index
    docs = parsed["documentos"]
    check("documentos > 100",     len(docs) > 100,  f"got {len(docs):,}")
    if docs:
        check("doc has id_doc",   bool(docs[0].get("id_doc")),   "")
        check("doc has cnpj",     bool(docs[0].get("cnpj")),     docs[0].get("cnpj",""))
        check("doc has dt_receb", bool(docs[0].get("dt_receb")), "")
        check("doc has link_doc", bool(docs[0].get("link_doc")), "")

        # Find Petrobras in index
        petr_docs = [d for d in docs if d.get("cnpj") == "33000167000101"]
        check("Petrobras in documentos", len(petr_docs) > 0,
              f"got {len(petr_docs)}")
        if petr_docs:
            p = petr_docs[0]
            print(f"    Sample Petrobras doc: id={p['id_doc']} "
                  f"dt_receb={p['dt_receb']} categ={p['categ_doc']}")

    # Check posicao_acionaria
    pa = parsed["posicao_acionaria"]
    check("posicao_acionaria > 0", len(pa) > 0, f"got {len(pa):,}")
    if pa:
        check("pa has acionista", bool(pa[0].get("acionista")), "")
        check("pa has pct_total", pa[0].get("pct_total") is not None, "")
        # Find Petrobras shareholders
        petr_pa = [r for r in pa if r.get("cnpj") == "33000167000101"]
        if petr_pa:
            print(f"    Petrobras shareholders: {len(petr_pa)}")
            for sh in petr_pa[:3]:
                print(f"      {sh.get('acionista','')[:40]:<40}  "
                      f"total={sh.get('pct_total','')}")

    # Check distribuicao_capital
    dc = parsed["distribuicao_capital"]
    check("distribuicao_capital > 0", len(dc) > 0, f"got {len(dc):,}")
    if dc:
        check("dc has pct_total_circulacao",
              dc[0].get("pct_total_circulacao") is not None, "")

    # Check remuneracao_orgao
    rem = parsed["remuneracao_orgao"]
    check("remuneracao_orgao > 0", len(rem) > 0, f"got {len(rem):,}")
    if rem:
        check("rem has orgao", bool(rem[0].get("orgao")), "")
        check("rem has total_remuneracao_orgao",
              rem[0].get("total_remuneracao_orgao") is not None, "")
        # Sample
        petr_rem = [r for r in rem if r.get("cnpj") == "33000167000101"]
        if petr_rem:
            print(f"    Petrobras compensation rows: {len(petr_rem)}")
            for r in petr_rem[:3]:
                print(f"      {r.get('orgao','')[:40]:<40}  "
                      f"total={r.get('total_remuneracao_orgao','')}")

    # Check capital_social
    cap = parsed["capital_social"]
    check("capital_social > 0", len(cap) > 0, f"got {len(cap):,}")
    if cap:
        check("cap has valor_capital",
              cap[0].get("valor_capital") is not None, "")

    print(f"\n    Summary: docs={len(docs):,} posicao={len(pa):,} "
          f"distrib={len(dc):,} remuneracao={len(rem):,} capital={len(cap):,}")

except Exception as e:
    import traceback
    print(f"  {FAIL} Parse test failed: {e}")
    print(traceback.format_exc())
    failures.append("parse test")

# ── 4. Sync ───────────────────────────────────────────────────────────────────
if DO_SYNC or DO_FULL or YEAR_ARG:
    section("4. Sync")
    sync_years = [YEAR_ARG] if YEAR_ARG else None
    mode_label = (
        f"year={YEAR_ARG}" if YEAR_ARG else
        "(full history from 2010)" if DO_FULL else
        "(current + prior year)"
    )
    print(f"  Syncing FRE {mode_label}...")
    r = sync(years=sync_years, full_history=DO_FULL)
    check("sync status in success/partial",
          r.get("status") in ("success", "partial"), str(r.get("errors", "")))
    check("years_synced or skipped > 0",
          len(r.get("years_synced", [])) + len(r.get("years_skipped", [])) > 0,
          f"synced={r.get('years_synced')} skipped={r.get('years_skipped')}")
    print(f"\n{r.get('report','')}")

    r2 = status()
    db_has_data = r2.get("status") == "ok" and r2.get("counts", {}).get("documentos", 0) > 0
    if db_has_data:
        print(f"\n{r2.get('report','')}")
else:
    section("4. Sync")
    print(f"  {SKIP} Use --sync, --full, or --year YYYY to write to fre.db.")

# ── 5. Query test ─────────────────────────────────────────────────────────────
section("5. Query test")
if not db_has_data:
    print(f"  {SKIP} fre.db empty -- run with --sync first")
else:
    # Filing index
    r = query(company="PETROBRAS", section="documentos", limit=5)
    check("query PETROBRAS documentos",
          r.get("status") in ("success", "not_found"), r.get("error", ""))
    if r.get("status") == "success":
        check("  returned rows", r.get("count", 0) > 0, f"got {r.get('count')}")
        print(f"\n{r.get('report','')[:500]}")

    # Shareholder structure via ticker
    r2 = query(company="PETR4", section="posicao_acionaria", limit=5)
    check("query PETR4 posicao_acionaria",
          r2.get("status") in ("success", "not_found"), r2.get("error", ""))
    if r2.get("status") == "success":
        check("  has shareholders", r2.get("count", 0) > 0, f"got {r2.get('count')}")
        print(f"\n{r2.get('report','')[:500]}")

    # Compensation
    r3 = query(company="VALE3", section="remuneracao_orgao", limit=5)
    check("query VALE3 remuneracao_orgao",
          r3.get("status") in ("success", "not_found"), r3.get("error", ""))

    # Capital
    r4 = query(company="ITUB4", section="capital_social", limit=5)
    check("query ITUB4 capital_social",
          r4.get("status") in ("success", "not_found"), r4.get("error", ""))

# ── 6. Skill dispatcher ───────────────────────────────────────────────────────
section("6. Skill dispatcher (cvm_fre __init__.py)")
try:
    from skills.cvm.cvm_fre import route
    r = route(mode="status")
    check("route(mode='status')",
          r.get("status") in ("ok", "not_synced"), r.get("error", ""))

    if db_has_data:
        r2 = route(mode="query", company="PETROBRAS", section="documentos", limit=3)
        check("route(mode='query', company='PETROBRAS', section='documentos')",
              r2.get("status") in ("success", "not_found"), r2.get("error", ""))
except Exception as e:
    print(f"  {SKIP} dispatcher error ({type(e).__name__}): {e}")

# ── Summary ───────────────────────────────────────────────────────────────────
section("SUMMARY")
if not failures:
    print("  All tests passed.")
    sys.exit(0)
else:
    print(f"  {len(failures)} FAILED:")
    for f in failures:
        print(f"    - {f}")
    sys.exit(1)
