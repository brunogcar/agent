"""
verify_b3_cvm_bridge.py -- Smoke test for the B3-CVM identity bridge.

Deploy to: D:\mcp\agent\verify_b3_cvm_bridge.py

Run from repo root:
    python verify_b3_cvm_bridge.py           # full test including sync
    python verify_b3_cvm_bridge.py --no-sync # skip sync, test lookup only

FIXES vs v1:
  - Removed bad imports: 'annual'/'equity_structure' are mode strings, not functions
  - Calls cvm_dividends(mode='annual') and cvm_shareholders(mode='minority') correctly
  - bridge_has_data gate: skips lookup tests when sync produced 0 CVM matches
  - Added --no-sync flag for faster iteration when bridge.db already exists
  - Added sections 9-11: cvm_dividends, cvm_shareholders, resolve_by_* helpers
"""

import sys, os

here = os.path.dirname(os.path.abspath(__file__))
if here not in sys.path:
    sys.path.insert(0, here)

NO_SYNC = "--no-sync" in sys.argv

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

def skip_section(title, reason):
    print(f"\n{'='*60}\n  {SKIP} {title}: {reason}\n{'='*60}")

# ── 0. Import check ───────────────────────────────────────────────────────────
section("0. Import check")
try:
    from skills.b3.b3_cvm.b3_cvm import (
        mode_sync, mode_status, mode_lookup, mode_resolve, mode_tickers,
        resolve_by_ticker, resolve_by_cnpj, resolve_by_cd_cvm, is_ticker,
    )
    print("  [PASS] skills.b3.b3_cvm.b3_cvm imported OK")
except ImportError as e:
    print(f"  [FAIL] FATAL: {e}"); sys.exit(1)

# ── 1. is_ticker heuristic ────────────────────────────────────────────────────
section("1. is_ticker() heuristic")
for s, expected in [
    ("PETR4", True), ("VALE3", True), ("TAEE11", True), ("PETR4F", True),
    ("PETROBRAS", False), ("33000167000101", False), ("ABCD", False), ("petr4", True),
]:
    check(f"is_ticker({s!r})=={expected}", is_ticker(s)==expected, f"got {is_ticker(s)}")

# ── 2. Bridge sync ────────────────────────────────────────────────────────────
if NO_SYNC:
    skip_section("2. Bridge sync", "--no-sync"); sync_result = {"status": "skipped"}
else:
    section("2. Bridge sync (downloads B3 ISIN ZIP + CVM CSV)")
    print("  Running mode_sync()...")
    sync_result = mode_sync()
    check("sync status==success", sync_result.get("status")=="success", sync_result.get("error",""))
    check("B3 rows > 1000",       sync_result.get("b3_rows",0) > 1000,    f"got {sync_result.get('b3_rows',0)}")
    check("CVM rows > 100",       sync_result.get("cvm_rows",0) > 100,    f"got {sync_result.get('cvm_rows',0)}")
    check("bridge_total > 1000",  sync_result.get("bridge_total",0) > 1000, f"got {sync_result.get('bridge_total',0)}")
    check("B3+CVM matches > 100", sync_result.get("with_cvm",0) > 100,    f"got {sync_result.get('with_cvm',0)} -- CNPJ col missing if 0")
    check("B3+rapina > 0",        sync_result.get("with_rapina",0) > 0,   f"got {sync_result.get('with_rapina',0)}")
    if sync_result.get("status") == "success":
        print(f"\n  Sync summary:")
        for line in sync_result.get("report","").splitlines(): print(f"    {line}")

# ── 3. Bridge status ──────────────────────────────────────────────────────────
section("3. Bridge status")
r = mode_status()
check("status in ok/not_synced", r.get("status") in ("ok","not_synced"), r.get("error",""))
if r.get("status") == "ok":
    for line in r.get("report","").splitlines(): print(f"    {line}")
bridge_has_data = r.get("status") == "ok" and r.get("with_cvm",0) > 0

# ── 4. Ticker lookup ──────────────────────────────────────────────────────────
if not bridge_has_data:
    skip_section("4-8. Lookups", "bridge has no CVM data (check CNPJ column parsing)")
else:
    section("4. Ticker lookup")
    for ticker in ("PETR4", "VALE3", "ITUB4", "BBAS3"):
        r = mode_lookup(ticker=ticker)
        ok = r.get("status") == "success"
        check(f"lookup ticker={ticker}", ok, r.get("error","") if not ok else "")
        if ok:
            check(f"  {ticker} cnpj not empty", bool(r.get("cnpj")), r.get("cnpj","(empty)"))
            check(f"  {ticker} cd_cvm > 0", r.get("cd_cvm",0) > 0, str(r.get("cd_cvm")))
            print(f"    {ticker}: {r.get('denom_social','')} | tickers={[t['ticker'] for t in r.get('tickers',[])]}")

    section("5. CNPJ lookup")
    r = mode_lookup(cnpj="33000167000101")
    check("lookup Petrobras CNPJ", r.get("status")=="success", r.get("error",""))
    if r.get("status") == "success":
        found = [t["ticker"] for t in r.get("tickers",[])]
        check("  has PETR3", "PETR3" in found, str(found))
        check("  has PETR4", "PETR4" in found, str(found))
        check("  has rapina_ids", len(r.get("rapina_ids",[]))>0, str(r.get("rapina_ids",[])[:3]))

    section("6. CD_CVM lookup")
    r = mode_lookup(cd_cvm=9512)
    check("lookup cd_cvm=9512 (Petrobras)", r.get("status")=="success", r.get("error",""))
    if r.get("status") == "success":
        check("  cnpj==33000167000101", r.get("cnpj")=="33000167000101", r.get("cnpj",""))

    section("7. Name resolve")
    for query in ("PETROBRAS", "VALE", "ITAU"):
        r = mode_resolve(query=query)
        ok = r.get("status")=="success" and r.get("count",0)>0
        check(f"resolve '{query}'", ok, r.get("error","") if not ok else f"{r.get('count')} found")
        if ok:
            c = r["companies"][0]
            print(f"    '{query}' -> {c['denom_social']} (CD_CVM:{c['cd_cvm']})")

    section("8. Tickers mode")
    r = mode_tickers(query="PETROBRAS")
    check("tickers for PETROBRAS > 1", r.get("status")=="success" and r.get("count",0)>1, f"count={r.get('count',0)}")
    if r.get("status") == "success":
        found = [t["ticker"] for t in r.get("tickers",[])]
        print(f"    Petrobras tickers: {found}")
        check("  PETR3 present", "PETR3" in found, str(found))
        check("  PETR4 present", "PETR4" in found, str(found))

# ── 9. cvm_dividends ──────────────────────────────────────────────────────────
section("9. cvm_dividends bridge integration")
try:
    from skills.cvm.cvm_dividends.cvm_dividends import cvm_dividends

    r = cvm_dividends(ticker="PETROBRAS", mode="status")
    check("cvm_dividends(ticker='PETROBRAS', mode='status')",
          r.get("status") in ("success","not_found"), r.get("error",""))
    if r.get("status") == "success":
        print(f"    Company: {r.get('company')} | ids: {len(r.get('ids',[]))}")
        print(f"    Report: {r.get('report','')[:250]}")

    if bridge_has_data:
        r2 = cvm_dividends(ticker="PETR4", mode="status")
        check("cvm_dividends(ticker='PETR4') via bridge",
              r2.get("status") in ("success","not_found"), r2.get("error",""))
        if r2.get("status")=="success" and r.get("status")=="success":
            check("  PETR4 and PETROBRAS resolve same company",
                  r2.get("company")==r.get("company"),
                  f"{r2.get('company')} vs {r.get('company')}")

    r3 = cvm_dividends(ticker="PETROBRAS", mode="annual", periods=3)
    check("cvm_dividends mode='annual'",
          r3.get("status") in ("success","not_found"), r3.get("error",""))
    if r3.get("status") == "success":
        print(f"    Annual: {r3.get('report','')[:300]}")

    r4 = cvm_dividends(ticker="PETROBRAS", mode="cash_paid", periods=3)
    check("cvm_dividends mode='cash_paid'",
          r4.get("status") in ("success","not_found"), r4.get("error",""))

    r5 = cvm_dividends(ticker="PETROBRAS", mode="declared", periods=3)
    check("cvm_dividends mode='declared'",
          r5.get("status") in ("success","not_found"), r5.get("error",""))

except ImportError as e:
    print(f"  {SKIP} cvm_dividends not importable: {e}")

# ── 10. cvm_shareholders ──────────────────────────────────────────────────────
section("10. cvm_shareholders bridge integration")
try:
    from skills.cvm.cvm_shareholders.cvm_shareholders import cvm_shareholders

    r = cvm_shareholders(ticker="PETROBRAS", mode="status")
    check("cvm_shareholders(ticker='PETROBRAS', mode='status')",
          r.get("status") in ("success","not_found"), r.get("error",""))
    if r.get("status") == "success":
        print(f"    Company: {r.get('company')}")
        print(f"    Report: {r.get('report','')[:300]}")

    if bridge_has_data:
        r2 = cvm_shareholders(ticker="VALE3", mode="status")
        check("cvm_shareholders(ticker='VALE3') via bridge",
              r2.get("status") in ("success","not_found"), r2.get("error",""))

    r3 = cvm_shareholders(ticker="PETROBRAS", mode="equity_structure", periods=3)
    check("cvm_shareholders mode='equity_structure'",
          r3.get("status") in ("success","not_found"), r3.get("error",""))

    r4 = cvm_shareholders(ticker="PETROBRAS", mode="minority", periods=3)
    check("cvm_shareholders mode='minority'",
          r4.get("status") in ("success","not_found"), r4.get("error",""))

except ImportError as e:
    print(f"  {SKIP} cvm_shareholders not importable: {e}")

# ── 11. resolve_by_* helpers ─────────────────────────────────────────────────
if not bridge_has_data:
    skip_section("11. resolve_by_* helpers", "bridge has no CVM data")
else:
    section("11. resolve_by_* helper functions")
    r = resolve_by_ticker("PETR4")
    check("resolve_by_ticker('PETR4') not None", r is not None)
    if r: check("  has rapina_ids", len(r.get("rapina_ids",[]))>0)

    r2 = resolve_by_cnpj("33000167000101")
    check("resolve_by_cnpj('33000167000101') not None", r2 is not None)

    r3 = resolve_by_cd_cvm(9512)
    check("resolve_by_cd_cvm(9512) not None", r3 is not None)

    r4 = resolve_by_ticker("XXXX9")
    check("resolve_by_ticker('XXXX9') returns None", r4 is None, f"got {r4}")

# ── Summary ───────────────────────────────────────────────────────────────────
section("SUMMARY")
if not failures:
    print("  All tests passed.")
    sys.exit(0)
else:
    print(f"  {len(failures)} test(s) FAILED:")
    for f in failures: print(f"    - {f}")
    if not bridge_has_data:
        print("\n  TIP: CNPJ column not extracted from B3 file.")
        print("  Check the [b3_cvm] DEBUG lines above for the raw sample row.")
        print("  The column name containing CNPJ may differ from expected.")
    sys.exit(1)
