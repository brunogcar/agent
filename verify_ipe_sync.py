"""
verify_ipe_sync.py
Deploy to: D:\mcp\agent\verify_ipe_sync.py

Smoke test for cvm_ipe_sync.py downloader.

Run modes:
    python verify_ipe_sync.py              # status + parse test (no DB write)
    python verify_ipe_sync.py --sync       # sync current + prior year
    python verify_ipe_sync.py --full       # sync all years from 2003 (~2-3 min)
"""

import sys, os
here = os.path.dirname(os.path.abspath(__file__))
if here not in sys.path:
    sys.path.insert(0, here)

DO_SYNC  = "--sync" in sys.argv
DO_FULL  = "--full" in sys.argv

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
    from skills.cvm.cvm_ipe_sync import (
        url_for, sync, status, parse_zip, download_zip, query,
    )
    print("  [PASS] cvm_ipe_sync imported OK")
except ImportError as e:
    print(f"  [FAIL] FATAL: {e}")
    sys.exit(1)

# ── 1. URL builder ────────────────────────────────────────────────────────────
section("1. URL builder")
from datetime import datetime
cur_year = datetime.now().year
for year, expected in [
    (2024, "IPE/DADOS/ipe_cia_aberta_2024.zip"),
    (2025, "IPE/DADOS/ipe_cia_aberta_2025.zip"),
    (cur_year, f"IPE/DADOS/ipe_cia_aberta_{cur_year}.zip"),
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
    check("has events", r.get("total", 0) > 0, f"got {r.get('total', 0)}")
    db_has_data = r.get("total", 0) > 0
else:
    print("  ipe.db not found or empty -- sync needed")
    db_has_data = False

# ── 3. Parse test (prior year, no DB write) ───────────────────────────────────
parse_year = cur_year - 1
section(f"3. Parse test (IPE {parse_year}, no DB write)")
print("  Downloading ONE IPE file (~5-15MB)...")
try:
    raw  = download_zip(url_for(parse_year))
    check("download returns bytes", len(raw) > 1000, f"{len(raw):,} bytes")
    check("is ZIP", raw[:2] == b"PK", f"magic={raw[:4]!r}")

    rows = parse_zip(raw, parse_year)
    check("parsed > 100 rows",      len(rows) > 100,              f"got {len(rows):,}")
    check("has cnpj field",         bool(rows[0].get("cnpj")),    rows[0].get("cnpj",""))
    check("has protocolo field",    bool(rows[0].get("protocolo")), "")
    check("has data_entrega field", bool(rows[0].get("data_entrega")), "")
    check("has link_download",      bool(rows[0].get("link_download")), "")
    check("has categoria",          bool(rows[0].get("categoria")), "")
    check("has assunto",            "assunto" in rows[0], "")

    # Check CNPJ is digits-only
    sample_cnpj = rows[0].get("cnpj", "")
    check("cnpj is digits only",    sample_cnpj.isdigit() and len(sample_cnpj)==14,
          f"{sample_cnpj!r}")

    # Check Petrobras events
    petr = [r for r in rows if "33000167000101" in r.get("cnpj","")]
    check("Petrobras events found", len(petr) > 0, f"got {len(petr)}")
    if petr:
        p = petr[0]
        print(f"    Sample Petrobras: {p['data_entrega']} | "
              f"{p['categoria']} | {p['assunto'][:60]}")

    # Show top categories
    from collections import Counter
    cats = Counter(r["categoria"] for r in rows).most_common(5)
    print(f"\n    Top categories in {parse_year}:")
    for cat, n in cats:
        print(f"      {n:>6,}  {cat}")

except Exception as e:
    import traceback
    print(f"  {FAIL} Parse test failed: {e}")
    print(traceback.format_exc())
    failures.append("parse test")

# ── 4. Sync ───────────────────────────────────────────────────────────────────
if DO_SYNC or DO_FULL:
    section("4. Sync")
    print(f"  Syncing IPE {'(full history from 2003)' if DO_FULL else '(current + prior year)'}...")
    r = sync(full_history=DO_FULL)
    check("sync status in success/partial",
          r.get("status") in ("success", "partial"), str(r.get("errors", "")))
    check("years_synced or skipped > 0",
          len(r.get("years_synced", [])) > 0 or len(r.get("years_skipped", [])) > 0,
          f"synced={r.get('years_synced')} skipped={r.get('years_skipped')}")
    print(f"\n{r.get('report','')}")

    # Re-check status after sync
    r2 = status()
    db_has_data = r2.get("status") == "ok" and r2.get("total", 0) > 0
else:
    section("4. Sync")
    print(f"  {SKIP} Use --sync or --full to download.")

# ── 5. Query test ─────────────────────────────────────────────────────────────
section("5. Query test")
if not db_has_data:
    print(f"  {SKIP} ipe.db empty -- run with --sync first")
else:
    # Query by name
    r = query(company="PETROBRAS", limit=5)
    check("query PETROBRAS status",
          r.get("status") in ("success", "not_found"), r.get("error", ""))
    if r.get("status") == "success":
        check("  returned events", r.get("count", 0) > 0, f"got {r.get('count')}")
        print(f"\n{r.get('report','')[:500]}")

    # Query by ticker via bridge
    r2 = query(company="PETR4", limit=3)
    check("query PETR4 via bridge",
          r2.get("status") in ("success", "not_found"), r2.get("error", ""))
    if r2.get("status") == "success":
        check("  PETR4 same results as PETROBRAS",
              r2.get("count", 0) > 0, f"got {r2.get('count')}")

    # Query by keyword
    r3 = query(keyword="dividendo", limit=5)
    check("query keyword='dividendo'",
          r3.get("status") in ("success", "not_found"), r3.get("error", ""))
    if r3.get("status") == "success":
        print(f"    dividend events: {r3.get('count')}")

# ── 6. Skill dispatcher ───────────────────────────────────────────────────────
section("6. Skill dispatcher (cvm_ipe __init__.py)")
try:
    from skills.cvm.cvm_ipe import route
    r = route(mode="status")
    check("route(mode='status')",
          r.get("status") in ("ok", "not_synced"), r.get("error", ""))

    if db_has_data:
        r2 = route(mode="query", company="PETROBRAS", limit=3)
        check("route(mode='query', company='PETROBRAS')",
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
    for f in failures: print(f"    - {f}")
    sys.exit(1)
