"""
verify_b3_cvm_bridge.py -- Smoke test for the B3-CVM identity bridge.

Run from repo root:
    python verify_b3_cvm_bridge.py

What this tests:
  1. Bridge sync (downloads B3 ISIN + CVM CSV, builds bridge.db)
  2. Ticker lookup: PETR4, VALE3, ITUB4
  3. CNPJ lookup: Petrobras CNPJ
  4. Name resolve: "PETROBRAS", "VALE", "ITAU"
  5. Tickers mode: all tickers for Petrobras CNPJ
  6. cvm_dividends via ticker (bridge integration)
  7. cvm_shareholders via ticker (bridge integration)
  8. Bridge status after sync

DECISION: This script hits the network (B3 + CVM downloads).
It should be run manually after deployment, not in CI.
Estimated time: 15-30 seconds for first sync.

Exit code:
  0 = all tests passed
  1 = one or more tests failed (details printed to stdout)
"""

import sys
import os

# ── Make sure we can import from skills/ ──────────────────────────────────────
# When run from repo root, skills/ is already on the path.
# When run from a subdirectory, add parent to sys.path.
here = os.path.dirname(os.path.abspath(__file__))
if here not in sys.path:
    sys.path.insert(0, here)


# ── Test runner ───────────────────────────────────────────────────────────────

PASS = "  [PASS]"
FAIL = "  [FAIL]"
SKIP = "  [SKIP]"

failures = []


def check(label: str, condition: bool, detail: str = "") -> None:
    if condition:
        print(f"{PASS} {label}")
    else:
        print(f"{FAIL} {label}" + (f" -- {detail}" if detail else ""))
        failures.append(label)


def section(title: str) -> None:
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


# ── 1. Bridge sync ────────────────────────────────────────────────────────────

section("1. Bridge sync (hits network)")

try:
    from skills.b3.b3_cvm.b3_cvm import mode_sync, mode_status
    print("  Importing b3_cvm... OK")
except ImportError as e:
    print(f"  FATAL: Cannot import b3_cvm: {e}")
    sys.exit(1)

print("  Running mode_sync() -- downloading B3 ISIN + CVM CSV...")
sync_result = mode_sync()

check("sync status == success",
      sync_result.get("status") == "success",
      sync_result.get("error", ""))

check("B3 rows > 1000",
      sync_result.get("b3_rows", 0) > 1000,
      f"got {sync_result.get('b3_rows', 0)}")

check("CVM rows > 100",
      sync_result.get("cvm_rows", 0) > 100,
      f"got {sync_result.get('cvm_rows', 0)}")

check("bridge_total > 1000",
      sync_result.get("bridge_total", 0) > 1000,
      f"got {sync_result.get('bridge_total', 0)}")

check("at least some CVM matches",
      sync_result.get("with_cvm", 0) > 100,
      f"got {sync_result.get('with_cvm', 0)}")

check("at least some rapina matches",
      sync_result.get("with_rapina", 0) > 0,
      f"got {sync_result.get('with_rapina', 0)}")

print(f"\n  Sync report:\n{sync_result.get('report', '(no report)')}")


# ── 2. Ticker lookup ──────────────────────────────────────────────────────────

section("2. Ticker lookup")

from skills.b3.b3_cvm.b3_cvm import mode_lookup

for ticker in ("PETR4", "VALE3", "ITUB4", "BBAS3"):
    r = mode_lookup(ticker=ticker)
    ok = r.get("status") == "success"
    check(
        f"lookup ticker={ticker}",
        ok,
        r.get("error", "") if not ok else
        f"cnpj={r.get('cnpj','')} cd_cvm={r.get('cd_cvm',0)} rapina_ids={len(r.get('rapina_ids',[]))}",
    )
    if ok:
        check(f"  {ticker} has CNPJ", bool(r.get("cnpj")), r.get("cnpj", "empty"))
        check(f"  {ticker} has CD_CVM", r.get("cd_cvm", 0) > 0, str(r.get("cd_cvm")))
        print(f"  {ticker}: {r.get('denom_social','')} -- tickers: {[t['ticker'] for t in r.get('tickers',[])]}")


# ── 3. CNPJ lookup ────────────────────────────────────────────────────────────

section("3. CNPJ lookup")

# Petrobras CNPJ
petr_cnpj = "33000167000101"
r = mode_lookup(cnpj=petr_cnpj)
check("lookup by CNPJ (Petrobras)",
      r.get("status") == "success",
      r.get("error", ""))
if r.get("status") == "success":
    check("  CNPJ lookup returns PETR tickers",
          any("PETR" in t["ticker"] for t in r.get("tickers", [])),
          str([t["ticker"] for t in r.get("tickers", [])]))


# ── 4. Name resolve ───────────────────────────────────────────────────────────

section("4. Name resolve")

from skills.b3.b3_cvm.b3_cvm import mode_resolve

for query in ("PETROBRAS", "VALE", "ITAU"):
    r = mode_resolve(query=query)
    check(
        f"resolve '{query}'",
        r.get("status") == "success" and r.get("count", 0) > 0,
        r.get("error", f"count={r.get('count',0)}"),
    )
    if r.get("status") == "success":
        first = r["companies"][0]
        print(f"  '{query}' -> {first['denom_social']} (CNPJ: {first['cnpj']})")


# ── 5. Tickers mode ───────────────────────────────────────────────────────────

section("5. Tickers mode")

from skills.b3.b3_cvm.b3_cvm import mode_tickers

r = mode_tickers(query="PETROBRAS")
check("tickers for PETROBRAS",
      r.get("status") == "success" and r.get("count", 0) > 1,
      f"count={r.get('count',0)}")
if r.get("status") == "success":
    tickers_found = [t["ticker"] for t in r.get("tickers", [])]
    print(f"  Petrobras tickers: {tickers_found}")
    check("  PETR3 in tickers", "PETR3" in tickers_found, str(tickers_found))
    check("  PETR4 in tickers", "PETR4" in tickers_found, str(tickers_found))


# ── 6. cvm_dividends via ticker ───────────────────────────────────────────────

section("6. cvm_dividends with ticker (bridge integration)")

try:
    from skills.cvm.cvm_dividends.cvm_dividends import cvm_dividends

    r = cvm_dividends(ticker="PETR4", mode="status")
    check("cvm_dividends(ticker='PETR4') status",
          r.get("status") in ("success", "not_found"),
          r.get("error", ""))

    if r.get("status") == "success":
        check("  company name contains PETRO",
              "PETRO" in r.get("company", "").upper(),
              r.get("company", ""))
        check("  rapina_ids populated",
              len(r.get("ids", [])) > 0,
              f"ids={r.get('ids',[])}")
        print(f"  Report preview:\n{r.get('report','')[:400]}")
    else:
        print(f"  Not found (rapina.db may not have data for PETR4): {r.get('error','')}")

except ImportError as e:
    print(f"  {SKIP} cvm_dividends not importable: {e}")


# ── 7. cvm_shareholders via ticker ────────────────────────────────────────────

section("7. cvm_shareholders with ticker (bridge integration)")

try:
    from skills.cvm.cvm_shareholders.cvm_shareholders import cvm_shareholders

    r = cvm_shareholders(ticker="VALE3", mode="status")
    check("cvm_shareholders(ticker='VALE3') status",
          r.get("status") in ("success", "not_found"),
          r.get("error", ""))

    if r.get("status") == "success":
        check("  company name contains VALE",
              "VALE" in r.get("company", "").upper(),
              r.get("company", ""))
        print(f"  Report preview:\n{r.get('report','')[:400]}")
    else:
        print(f"  Not found (rapina.db may not have VALE3): {r.get('error','')}")

except ImportError as e:
    print(f"  {SKIP} cvm_shareholders not importable: {e}")


# ── 8. Bridge status ──────────────────────────────────────────────────────────

section("8. Bridge status after sync")

r = mode_status()
check("status after sync is ok", r.get("status") == "ok", r.get("error", ""))
if r.get("status") == "ok":
    print(r.get("report", ""))


# ── Summary ───────────────────────────────────────────────────────────────────

section("SUMMARY")

if not failures:
    print("  All tests passed.")
    sys.exit(0)
else:
    print(f"  {len(failures)} test(s) FAILED:")
    for f in failures:
        print(f"    - {f}")
    sys.exit(1)
