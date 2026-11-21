"""tools/migrations/rekey_itr_snapshots.py — [v1.7.1] ITR snapshot re-key.

THE BUG
-------
ITR BPA/BPP rows are point-in-time snapshots: DT_INI_EXERC is empty, so
compute_meses() returns 12 for ALL of them — including the Mar/Jun/Sep
quarter-end filings. Consequences in any itr.db synced before v1.7.1:

  1. Every quarter's balance lands in the same (year → meses=12) bucket,
     so Q1/Q2/Q3 snapshots overwrite each other (last write wins).
  2. Every consumer that looks for quarter buckets — financials
     fetchers._snap(), the bpa/* and bpp/* calculation engines — finds
     nothing at meses 3/6/9 and carries the prior year-end DFP value
     forward. Quarterly balance sheets, TTM balanço, Altman Z, liquidity
     and debt ratios all rendered Dec-31(Y−1) values for Q1–Q3.

THE FIX
-------
A filing's own flow rows (DRE/DFC/DVA — which DO have DT_INI_EXERC) define
its period: a filing with a 3/6/9-month DRE is that quarter's filing, and
its BPA/BPP rows belong in the same bucket. Fiscal-year filers (quarter
ends in May/Aug/Nov) are handled for free — the flow months, not the
calendar month, drive the bucket. Dec-31 ITR filings (flow meses=12) keep
their snapshots at 12.

This migration applies the same re-key the v1.7.1 sync engine now performs
per year — to ALL historical rows at once — then bumps
``PRAGMA user_version`` to 2 (the marker the WebUI pre-flight reads) and
clears the engine cache (fingerprints are MAX(versao)+MAX(data_fim_exerc),
which this migration does not change — without the wipe, cached engine
results would keep serving the collapsed balances).

USAGE (from the repo root)
--------------------------
    python -m tools.migrations.rekey_itr_snapshots             # dry-run report
    python -m tools.migrations.rekey_itr_snapshots --apply     # do it
    python -m tools.migrations.rekey_itr_snapshots --apply --batch 250000

Close the WebUI (and any running sync) before --apply: the batched writes
take the write lock, and the engine-cache wipe needs the file unlocked.
The UPDATE only touches the meses INTEGER of matching snapshot rows — no
inserts, no deletes, meses is not part of the contas primary key — so the
risk profile is minimal. A WAL checkpoint runs at the end to fold the -wal
file back into the DB.
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
import time

# user_version marker written when the re-key has been applied (also set by
# the v1.7.1+ ITR sync engine on every successful store). The WebUI
# pre-flight warns when itr.db reports less than this.
REKEY_VERSION = 2


def _connect(path, *, read_only: bool = False) -> sqlite3.Connection:
    uri = f"file:{path}?mode=ro" if read_only else f"file:{path}?mode=rw"
    conn = sqlite3.connect(uri, uri=True, timeout=30,
                           isolation_level=None)  # autocommit — batch commits
    conn.row_factory = sqlite3.Row
    return conn


def _analyze(conn: sqlite3.Connection) -> dict:
    """Count mis-keyed snapshots and how many the flow map can fix."""
    print("  scanning contas (one full pass — this is the slow part)…")
    t0 = time.time()

    # Filing → flow-period map, materialized once with an index so the
    # per-row lookup in the UPDATE is O(log n) instead of a table scan.
    conn.execute(
        """CREATE TEMP TABLE flow_map AS
           SELECT id_empresa, data_fim_exerc, MAX(meses) AS meses
           FROM contas
           WHERE data_ini_exerc != '' AND data_ini_exerc IS NOT NULL
             AND meses IN (3, 6, 9)
           GROUP BY id_empresa, data_fim_exerc""")
    conn.execute(
        "CREATE UNIQUE INDEX temp.idx_flow_map ON flow_map(id_empresa, data_fim_exerc)")

    stats = {"snapshots_total": 0, "miskeyed": 0, "fixable": 0, "by_month": {}}

    cur = conn.execute(
        """SELECT substr(data_fim_exerc, 6, 2) AS mes, COUNT(*) AS n,
                  SUM(EXISTS (SELECT 1 FROM flow_map f
                              WHERE f.id_empresa = contas.id_empresa
                                AND f.data_fim_exerc = contas.data_fim_exerc)) AS fixable
           FROM contas
           WHERE (data_ini_exerc = '' OR data_ini_exerc IS NULL)
             AND meses = 12
           GROUP BY mes ORDER BY mes""")
    for r in cur:
        n = int(r["n"] or 0)
        stats["snapshots_total"] += n
        stats["by_month"][r["mes"]] = {"rows": n, "fixable": int(r["fixable"] or 0)}
        # Quarter-end months are the mis-keyed ones (Dec stays 12 — correct).
        if r["mes"] != "12":
            stats["miskeyed"] += n
            stats["fixable"] += int(r["fixable"] or 0)

    stats["scan_secs"] = time.time() - t0
    return stats


def _apply(conn: sqlite3.Connection, batch: int) -> int:
    """Re-key snapshots in rowid batches. Returns rows updated."""
    lo, hi = conn.execute("SELECT MIN(rowid), MAX(rowid) FROM contas").fetchone()
    if lo is None:
        return 0
    total_span = (hi - lo) + 1
    updated = 0
    t0 = time.time()
    pos = lo
    n_batches = 0
    while pos <= hi:
        cur = conn.execute(
            """UPDATE contas SET meses = (
                   SELECT f.meses FROM flow_map f
                   WHERE f.id_empresa = contas.id_empresa
                     AND f.data_fim_exerc = contas.data_fim_exerc)
               WHERE rowid >= ? AND rowid < ?
                 AND (data_ini_exerc = '' OR data_ini_exerc IS NULL)
                 AND meses = 12
                 AND EXISTS (SELECT 1 FROM flow_map f
                             WHERE f.id_empresa = contas.id_empresa
                               AND f.data_fim_exerc = contas.data_fim_exerc)""",
            (pos, pos + batch))
        if cur.rowcount and cur.rowcount > 0:
            updated += cur.rowcount
        pos += batch
        n_batches += 1
        done = min(pos - lo, total_span)
        pct = done * 100.0 / max(total_span, 1)
        sys.stdout.write(
            f"\r  {done:,}/{total_span:,} rowids ({pct:5.1f}%) — {updated:,} rows re-keyed")
        sys.stdout.flush()
    print(f"\n  done in {time.time() - t0:.1f}s ({n_batches} batches)")
    return updated


def _clear_engine_cache() -> None:
    """Wipe engine_cache.db (fingerprints don't change with this migration,
    so cached engine results must go or they keep serving collapsed values)."""
    try:
        from data_sources._cache import db_path as cache_db_path
        path = cache_db_path()
    except Exception as e:  # noqa: BLE001 — advisory step
        print(f"  [warn] engine cache location unavailable ({e}) — "
              f"delete memory_db/cache/engine_cache.db manually")
        return
    if not path.exists():
        print("  engine cache: no engine_cache.db — nothing to clear")
        return
    try:
        conn = sqlite3.connect(path, timeout=10)
        try:
            for tbl in ("engine_cache", "engine_periods", "engine_cache_meta"):
                conn.execute(f"DELETE FROM {tbl}")
            conn.commit()
        finally:
            conn.close()
        print("  engine cache cleared (engine_cache, engine_periods, engine_cache_meta)")
    except sqlite3.Error as e:
        print(f"  [warn] engine cache locked ({e}) — close the WebUI and "
              f"delete memory_db/cache/engine_cache.db, then restart")


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Re-key ITR BPA/BPP snapshot rows to their filing's quarter "
                    "(fixes quarterly balanços for DBs synced before v1.7.1).")
    ap.add_argument("--apply", action="store_true",
                    help="perform the re-key (default: dry-run report only)")
    ap.add_argument("--batch", type=int, default=500_000,
                    help="rowid span per UPDATE transaction (default: 500000)")
    args = ap.parse_args()

    from data_sources.cvm._db import itr_db_path
    path = itr_db_path()
    if not path.exists():
        print(f"itr.db not found: {path}")
        return 1

    conn = _connect(path)
    try:
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        print(f"itr.db: {path}")
        print(f"  size: {path.stat().st_size / 1e9:.2f} GB")
        print(f"  PRAGMA user_version = {version} "
              f"({'re-key marker present' if version >= REKEY_VERSION else 'pre-v1.7.1 (no marker)'})")

        stats = _analyze(conn)
        print(f"  scan took {stats['scan_secs']:.1f}s")
        print(f"  snapshot rows at meses=12: {stats['snapshots_total']:,}")
        print(f"  mis-keyed (non-Dec quarter ends): {stats['miskeyed']:,} "
              f"— fixable via flow map: {stats['fixable']:,}")
        print("  by data_fim month:")
        for mes, d in sorted(stats["by_month"].items()):
            tag = " (year-end — correct)" if mes == "12" else ""
            print(f"    {mes}: {d['rows']:>10,} rows, {d['fixable']:>10,} fixable{tag}")

        if not args.apply:
            print("\nDRY-RUN — nothing written. Re-run with --apply to re-key "
                  f"{stats['fixable']:,} rows, bump user_version to {REKEY_VERSION} "
                  "and clear the engine cache.")
            return 0

        if stats["fixable"] == 0 and version >= REKEY_VERSION:
            print("\nNothing to do — DB already re-keyed.")
            return 0

        print("\nApplying re-key…")
        updated = _apply(conn, max(args.batch, 10_000))
        conn.execute(f"PRAGMA user_version = {REKEY_VERSION}")
        print(f"  user_version → {REKEY_VERSION}")

        # Fold the -wal back into the main file (best-effort).
        try:
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            print("  WAL checkpointed")
        except sqlite3.Error as e:  # noqa: BLE001 — advisory
            print(f"  [warn] WAL checkpoint skipped ({e})")

        print(f"\nRe-keyed {updated:,} snapshot rows. Next: clear the engine cache…")
        _clear_engine_cache()
        print("Done. Restart the WebUI (in-memory caches die with the process) — "
              "quarterly balanços now show real Mar/Jun/Sep period-end values.")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
