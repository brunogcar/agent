"""data_sources/cvm/_repair/purge_penultimo.py — One-time: purge PENÚLTIMO rows.

The sync engines have filtered PENÚLTIMO at ingest since v1.0 via
`data_sources.cvm._meses.should_keep_row()`. This script cleans up
legacy rows from databases synced before that fix or re-synced with
`force=True` (INSERT OR REPLACE doesn't delete old rows).

Deletes all contas rows where ordem_exerc = 'PENÚLTIMO', except for
2009 backfill data (the only source of 2009 annual figures, since CVM
didn't publish a 2009 DFP).

Usage:
  python -m data_sources.cvm._repair.purge_penultimo --vacuum
  python -m data_sources.cvm._repair.purge_penultimo --dfp --vacuum
  python -m data_sources.cvm._repair.purge_penultimo --dry-run
"""
from __future__ import annotations

import argparse
import os
import sqlite3
import sys

from data_sources.cvm._db import cnpj_digits, dfp_db_path, itr_db_path  # noqa: F401


def purge_db(db_path, label: str, dry_run: bool = False, vacuum: bool = False):
    """Purge PENÚLTIMO rows from one database."""
    print(f"\n{'─' * 60}")
    print(f"  {label}: {db_path}")
    print(f"{'─' * 60}")

    if not os.path.exists(str(db_path)):
        print(f"  [skip] Database not found")
        return

    size_before = os.path.getsize(str(db_path)) / 1024 / 1024
    print(f"  Size before: {size_before:.1f} MB")

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    total_before = conn.execute("SELECT COUNT(*) FROM contas").fetchone()[0]
    penultimo_total = conn.execute(
        "SELECT COUNT(*) FROM contas WHERE ordem_exerc = 'PENÚLTIMO'"
    ).fetchone()[0]
    penultimo_2009 = conn.execute(
        "SELECT COUNT(*) FROM contas WHERE ordem_exerc = 'PENÚLTIMO' "
        "AND data_fim_exerc LIKE '2009%'"
    ).fetchone()[0]
    penultimo_to_delete = penultimo_total - penultimo_2009

    print(f"  Total contas rows:      {total_before:>10,}")
    print(f"  PENÚLTIMO rows:         {penultimo_total:>10,}")
    print(f"    └─ 2009 (keep):       {penultimo_2009:>10,}")
    print(f"    └─ to delete:         {penultimo_to_delete:>10,}")

    if dry_run:
        print(f"  [dry-run] No rows deleted.")
        conn.close()
        return

    if penultimo_to_delete > 0:
        print(f"  Deleting {penultimo_to_delete:,} rows...")
        conn.execute(
            "DELETE FROM contas WHERE ordem_exerc = 'PENÚLTIMO' "
            "AND data_fim_exerc NOT LIKE '2009%'"
        )
        conn.commit()
        print(f"  Done.")

    total_after = conn.execute("SELECT COUNT(*) FROM contas").fetchone()[0]
    print(f"  Total contas after:     {total_after:>10,}")
    print(f"  Removed:                {total_before - total_after:>10,}")

    if vacuum:
        print(f"  Running VACUUM...")
        conn.execute("VACUUM")
        size_after = os.path.getsize(str(db_path)) / 1024 / 1024
        print(f"  Size after:  {size_after:.1f} MB")
        print(f"  Saved:       {size_before - size_after:.1f} MB")
    else:
        print(f"  Run with --vacuum to reclaim disk space.")

    conn.close()


def main():
    parser = argparse.ArgumentParser(
        description="One-time purge of legacy PENÚLTIMO rows from DFP/ITR databases.",
    )
    parser.add_argument("--dfp", action="store_true", help="Purge DFP only")
    parser.add_argument("--itr", action="store_true", help="Purge ITR only")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report counts without deleting",
    )
    parser.add_argument(
        "--vacuum",
        action="store_true",
        help="Run VACUUM after deletion to reclaim disk space",
    )
    args = parser.parse_args()

    do_dfp = args.dfp or (not args.dfp and not args.itr)
    do_itr = args.itr or (not args.dfp and not args.itr)

    print(f"{'=' * 60}")
    print(f"  CVM PENÚLTIMO Purge (one-time repair)")
    print(f"  Databases: {', '.join(filter(None, ['DFP' if do_dfp else None, 'ITR' if do_itr else None]))}")
    print(f"  Dry run: {args.dry_run}")
    print(f"{'=' * 60}")

    if do_dfp:
        purge_db(dfp_db_path(), "DFP", args.dry_run, args.vacuum)
    if do_itr:
        purge_db(itr_db_path(), "ITR", args.dry_run, args.vacuum)


if __name__ == "__main__":
    main()
