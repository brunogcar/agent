"""
patch_cvm_api.py
Deploy to: D:\mcp\agent\patch_cvm_api.py
Run:       python patch_cvm_api.py

Patches skills/cvm/cvm_api/cvm_api.py to:
  1. Replace inline _connect() with import from skills.cvm._db
  2. Add bridge ticker lookup at top of _resolve_company()

WHAT CHANGES:
  _connect()          -> wraps _db.connect_rapina() (same behavior, shared code)
  _resolve_company()  -> tries bridge first if input looks like a ticker,
                         then falls through to existing CNPJ/name logic unchanged

WHAT DOES NOT CHANGE:
  - CVM_DB_PATH import from cvm_api_catalog (still used in status mode)
  - normalize_cnpj, format_cnpj, real_value etc. (untouched)
  - All query functions (_query_*, mode_* etc.) -- zero changes
  - Return type of _resolve_company: still list[dict] with {id,cnpj,nome,ano}

DECISION: _resolve_company returns list[dict] in cvm_api (different from
cvm_dividends which returns tuple[list[int], str]). We preserve this
contract -- the bridge lookup adapts its result to match the existing shape.
"""

import ast
import sys
from pathlib import Path

TARGET = Path(__file__).parent / "skills" / "cvm" / "cvm_api" / "cvm_api.py"

# ── Patch 1: replace _connect() with shared _db wrapper ──────────────────────

OLD_CONNECT = '''def _connect() -> sqlite3.Connection:
    """
    Open rapina.db as read-only.
    Raises FileNotFoundError with a clear message if not found.

    DECISION: read-only URI mode (uri=True with ?mode=ro) prevents accidental
    writes and allows concurrent reads without WAL conflicts.
    rapina.db is updated externally by rapinav2 -- this skill never writes.
    """
    if not CVM_DB_PATH.exists():
        raise FileNotFoundError(
            f"rapina.db not found at {CVM_DB_PATH}. "
            f"Move it there: mkdir {CVM_DB_PATH.parent} && copy rapina.db {CVM_DB_PATH}"
        )
    uri = f"file:{CVM_DB_PATH}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    return conn'''

NEW_CONNECT = '''def _connect() -> sqlite3.Connection:
    """
    Open rapina.db read-only via shared _db helper.
    CVM_DB_PATH still used by status mode for file size reporting.

    DECISION: delegates to skills.cvm._db.connect_rapina() so all cvm skills
    use the same DB path resolution logic (MEMORY_ROOT env var or walk-up).
    Behavior is identical to the original -- read-only, Row factory.
    """
    from skills.cvm._db import connect_rapina
    return connect_rapina()'''

# ── Patch 2: add bridge lookup at top of _resolve_company() ──────────────────
# Original function resolves by CNPJ or name only.
# We add a ticker check BEFORE the existing logic -- if it looks like a ticker
# and the bridge resolves it, we build the same list[dict] shape from bridge data.
# If bridge unavailable or no match, fall through to original CNPJ/name logic.

OLD_RESOLVE = '''def _resolve_company(conn: sqlite3.Connection, query: str) -> list[dict]:
    """
    Find company records in empresas by CNPJ or name.
    Returns list of {id, cnpj, nome, ano} dicts for ALL years found.
    Multiple rows = same company across multiple years (expected).

    Resolution order:
      1. CNPJ match (strips formatting for comparison)
      2. Exact name match (case-insensitive)
      3. Partial name match

    DECISION: return ALL year rows so the caller can decide which years to use.
    Filtering to specific years happens in the query functions.
    """
    q = query.strip()
    rows: list[sqlite3.Row] = []'''

NEW_RESOLVE = '''def _resolve_company(conn: sqlite3.Connection, query: str) -> list[dict]:
    """
    Find company records in empresas by ticker, CNPJ, or name.
    Returns list of {id, cnpj, nome, ano} dicts for ALL years found.
    Multiple rows = same company across multiple years (expected).

    Resolution order:
      0. B3 ticker -> bridge.db (added v2: requires b3_cvm sync)
      1. CNPJ match (strips formatting for comparison)
      2. Exact name match (case-insensitive)
      3. Partial name match

    DECISION: bridge lookup prepended to existing logic.
    If bridge unavailable or ticker not found, falls through to CNPJ/name.
    Return shape unchanged: list[dict] with {id, cnpj, nome, ano}.
    """
    q = query.strip()

    # ── Path 0: B3 ticker -> bridge ───────────────────────────────────────────
    # DECISION: Import lazily -- bridge is optional enhancement.
    # If b3_cvm not installed or bridge not synced, silently skip.
    from skills.cvm._bridge import looks_like_ticker, resolve_via_bridge
    if looks_like_ticker(q):
        bridge = resolve_via_bridge(q.upper())
        if bridge is not None:
            rapina_ids, name = bridge
            if rapina_ids:
                # Fetch the actual empresas rows for these ids so the rest of
                # cvm_api works unchanged (it expects full Row objects with ano/cnpj)
                placeholders = ",".join("?" * len(rapina_ids))
                bridge_rows = conn.execute(
                    f"SELECT id, cnpj, nome, ano FROM empresas "
                    f"WHERE id IN ({placeholders}) ORDER BY ano",
                    rapina_ids,
                ).fetchall()
                if bridge_rows:
                    return [dict(r) for r in bridge_rows]
            # Bridge found ticker but no rapina data -- fall through to name search
            # using the CVM name from bridge as the query string
            if name and name != q:
                q = name  # search by CVM name instead of ticker

    rows: list[sqlite3.Row] = []'''


def apply_patch(path: Path, old: str, new: str, name: str) -> bool:
    content = path.read_text(encoding="utf-8")
    if old not in content:
        print(f"  SKIP {name}: old text not found (already patched?)")
        return False
    if content.count(old) > 1:
        print(f"  FAIL {name}: ambiguous -- appears {content.count(old)} times")
        return False
    patched = content.replace(old, new, 1)
    try:
        ast.parse(patched)
    except SyntaxError as e:
        print(f"  FAIL {name}: SyntaxError after patch: {e}")
        return False
    # Backup
    bak = path.with_suffix(".py.bak")
    import shutil
    shutil.copy2(path, bak)
    path.write_text(patched, encoding="utf-8")
    print(f"  OK   {name}")
    return True


def main():
    if not TARGET.exists():
        print(f"ERROR: {TARGET} not found")
        sys.exit(1)

    print(f"Patching {TARGET}")
    results = [
        apply_patch(TARGET, OLD_CONNECT,  NEW_CONNECT,  "replace _connect() with _db wrapper"),
        apply_patch(TARGET, OLD_RESOLVE,  NEW_RESOLVE,  "add bridge ticker lookup to _resolve_company"),
    ]

    failed = [r for r in results if r is False]
    if not failed:
        print("Done. cvm_api.py patched successfully.")
        print("Test with: skill(domain='cvm_api', mode='query', params='{\"company\":\"PETR4\"}')")
    else:
        print("Some patches failed -- check output above.")
        sys.exit(1)


if __name__ == "__main__":
    main()
