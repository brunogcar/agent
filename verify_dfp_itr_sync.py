"""
verify_dfp_itr_sync.py
Deploy to: D:\mcp\agent\verify_dfp_itr_sync.py

Smoke test for cvm_dfp_itr_sync.py downloader.

Run modes:
    python verify_dfp_itr_sync.py                # status + quick parse test (no download)
    python verify_dfp_itr_sync.py --sync-dfp     # download DFP current+prior year
    python verify_dfp_itr_sync.py --sync-itr     # download ITR current+prior year
    python verify_dfp_itr_sync.py --sync-all     # DFP + ITR current+prior year
    python verify_dfp_itr_sync.py --full-history # WARNING: ~2GB, ~10 min

Tests:
  0. Import check
  1. URL builder sanity
  2. DB status (existing dfp_itr.db from rapinav2)
  3. Parse test (download ONE small file, parse, don't write to DB)
  4. Sync (if flag given)
  5. Query test (Petrobras DVA via ticker PETR4)
"""

import sys, os
here = os.path.dirname(os.path.abspath(__file__))
if here not in sys.path:
    sys.path.insert(0, here)

SYNC_DFP     = "--sync-dfp"     in sys.argv
SYNC_ITR     = "--sync-itr"     in sys.argv
SYNC_ALL     = "--sync-all"     in sys.argv
FULL_HISTORY = "--full-history" in sys.argv

if SYNC_ALL:
    SYNC_DFP = SYNC_ITR = True

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
    from skills.cvm.cvm_dfp_itr_sync import (
        url_for, sync, status, parse_zip, download_zip,
        _connect_dfp_itr, _compute_meses,
    )
    print("  [PASS] cvm_dfp_itr_sync imported OK")
except ImportError as e:
    print(f"  [FAIL] FATAL: {e}")
    sys.exit(1)

# ── 1. URL builder ────────────────────────────────────────────────────────────
section("1. URL builder")
from datetime import datetime
cur_year = datetime.now().year

for form, year, expected_frag in [
    ("DFP", 2024, "DFP/DADOS/dfp_cia_aberta_2024.zip"),
    ("ITR", 2025, "ITR/DADOS/itr_cia_aberta_2025.zip"),
    ("DFP", cur_year, f"DFP/DADOS/dfp_cia_aberta_{cur_year}.zip"),
]:
    url = url_for(form, year)
    check(f"url_for({form},{year})", expected_frag in url, url)

# ── 2. meses computation ──────────────────────────────────────────────────────
section("2. meses computation")
for dt_ini, dt_fim, expected in [
    ("2024-01-01", "2024-03-31", 3),   # Q1
    ("2024-01-01", "2024-06-30", 6),   # H1
    ("2024-01-01", "2024-09-30", 9),   # 9M
    ("2024-01-01", "2024-12-31", 12),  # annual DFP
    ("2023-10-01", "2024-09-30", 12),  # non-Dec fiscal year
]:
    result = _compute_meses(dt_ini, dt_fim)
    check(f"meses({dt_ini}->{dt_fim})=={expected}", result==expected, f"got {result}")

# ── 3. DB status (existing data from rapinav2) ────────────────────────────────
section("3. DB status (existing dfp_itr.db)")
r = status()
check("status returns ok or not_found",
      r.get("status") in ("ok", "not_found"), r.get("error",""))
if r.get("status") == "ok":
    print(f"\n{r.get('report','')}")
    check("has empresas rows", r.get("empresas",0) > 0, f"got {r.get('empresas',0)}")
    check("has contas rows",   r.get("contas",0) > 0,   f"got {r.get('contas',0)}")
    db_has_data = r.get("contas",0) > 0
else:
    print(f"  dfp_itr.db not found or empty -- sync needed")
    db_has_data = False

# ── 4. Parse test (download 1 file, parse only, no DB write) ──────────────────
section("4. Parse test (download DFP current year, no DB write)")
print("  Downloading ONE file to test parser (~5-20MB)...")
try:
    raw   = download_zip(url_for("DFP", cur_year))
    check("download returns bytes", len(raw) > 1000, f"{len(raw):,} bytes")
    check("is ZIP", raw[:2] == b"PK", f"magic={raw[:4]!r}")

    rows  = parse_zip(raw, "DFP", cur_year)
    check("parsed > 1000 rows",    len(rows) > 1000,   f"got {len(rows):,}")
    check("has CNPJ field",        bool(rows[0].get("cnpj")),  str(rows[0].get("cnpj","")))
    check("has codigo field",      bool(rows[0].get("codigo")), str(rows[0].get("codigo","")))
    check("has valor field",       "valor" in rows[0],  "")
    check("has escala field",      "escala" in rows[0], "")
    check("has data_fim_exerc",    bool(rows[0].get("data_fim_exerc")), "")
    check("meses in 3/6/9/12/15",  rows[0].get("meses") in (3,6,9,12,15), str(rows[0].get("meses")))

    # Check Petrobras is in the data
    petr_rows = [r for r in rows if "PETROBRAS" in r.get("nome","").upper()
                                  or "33000167000101" in r.get("cnpj","").replace(".","").replace("/","").replace("-","")]
    check("Petrobras found in parsed rows",
          len(petr_rows) > 0, f"got {len(petr_rows)} rows")
    if petr_rows:
        sample = petr_rows[0]
        print(f"    Sample: cnpj={sample['cnpj']} codigo={sample['codigo']} "
              f"grupo={sample['grupo']} valor={sample['valor']} escala={sample['escala']} "
              f"data_fim={sample['data_fim_exerc']} meses={sample['meses']}")

except Exception as e:
    print(f"  {FAIL} Parse test failed: {type(e).__name__}: {e}")
    failures.append("parse test")

# ── 5. Sync (only if flag given) ──────────────────────────────────────────────
if SYNC_DFP or SYNC_ITR:
    section("5. Sync")
    forms = []
    if SYNC_DFP: forms.append("DFP")
    if SYNC_ITR: forms.append("ITR")

    for form in forms:
        print(f"\n  Syncing {form} {'(full history)' if FULL_HISTORY else '(current+prior year)'}...")
        r = sync(form=form, full_history=FULL_HISTORY)
        check(f"sync {form} status in success/partial",
              r.get("status") in ("success","partial"), r.get("errors",""))
        check(f"sync {form} years_synced > 0",
              len(r.get("years_synced",[])) > 0 or len(r.get("years_skipped",[])) > 0,
              f"synced={r.get('years_synced')} skipped={r.get('years_skipped')}")
        print(f"\n{r.get('report','')}")
else:
    section("5. Sync")
    print(f"  {SKIP} No sync flag. Use --sync-dfp, --sync-itr, or --sync-all to download.")

# ── 6. Query test (Petrobras DVA via ticker) ──────────────────────────────────
section("6. Query test via cvm_dfp_itr skill")
if not db_has_data:
    print(f"  {SKIP} dfp_itr.db empty -- run with --sync-dfp first")
else:
    try:
        from skills.cvm.cvm_dfp_itr.cvm_dfp_itr import mode_query
        r = mode_query(company="PETROBRAS", grupo="DVA", anos=[2024], consolidado=1)
        check("query PETROBRAS DVA",
              r.get("status") in ("success","not_found"), r.get("error",""))
        if r.get("status") == "success":
            rows = r.get("data",[])
            check("DVA rows returned", len(rows) > 0, f"got {len(rows)}")
            print(f"    Sample row: {rows[0] if rows else '(none)'}")
    except Exception as e:
        print(f"  {SKIP} mode_query error ({type(e).__name__}): {e}")

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
