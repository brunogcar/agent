"""data_sources/cvm/_repair/normalize_cnpj.py — One-time: normalize CNPJ + merge duplicates.

The sync engines have normalized CNPJ to 14 plain digits at ingest since
v1.2.1 via `data_sources.cvm._db.cnpj_digits()`. This script fixes
databases synced before that fix, which contain a mix of:
  - Dotted format: "33.000.167/0001-01" (18 chars)
  - Plain format:  "33000167000101"      (14 digits)

This caused duplicate empresa rows (same company, two CNPJ formats) and
unreliable CNPJ-based lookups.

Usage:
  python -m data_sources.cvm._repair.normalize_cnpj
  python -m data_sources.cvm._repair.normalize_cnpj --dfp
  python -m data_sources.cvm._repair.normalize_cnpj --dry-run

WHY MERGE BEFORE NORMALIZE
--------------------------
The empresas table has UNIQUE(cnpj, ano). If we normalize CNPJ format
first (UPDATE dotted→plain), the UPDATE fails with "UNIQUE constraint
failed" because the plain-format row already exists.

Fix: merge duplicates first (using normalized CNPJ to detect them),
delete the duplicates, THEN normalize the remaining rows (no collisions
possible).
"""
from __future__ import annotations

import argparse
import os
import sqlite3
import sys

from data_sources.cvm._db import cnpj_digits, dfp_db_path, itr_db_path


def normalize_db(db_path, label: str, dry_run: bool = False):
    """Normalize CNPJ and merge duplicates in one database.

    Order of operations (critical — see module docstring):
      1. Build id→normalized_cnpj mapping in memory
      2. Group rows by (normalized_cnpj, ano) to find duplicates
      3. Merge duplicates: move contas to primary (lowest id), delete others
      4. Normalize CNPJ format on remaining rows (safe — no duplicates left)
    """
    print(f"\n{'─' * 60}")
    print(f"  {label}: {db_path}")
    print(f"{'─' * 60}")

    if not os.path.exists(str(db_path)):
        print(f"  [skip] Database not found")
        return

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    # --- Step 1: Load all empresas and compute normalized CNPJ ---
    rows = conn.execute("SELECT id, cnpj, nome, ano FROM empresas ORDER BY id").fetchall()
    print(f"  Empresas: {len(rows):,}")

    id_to_norm: dict[int, str] = {}
    groups: dict[tuple[str, int], list[int]] = {}

    for row in rows:
        norm = cnpj_digits(row["cnpj"])
        id_to_norm[row["id"]] = norm
        key = (norm, row["ano"])
        groups.setdefault(key, []).append(row["id"])

    needs_format_fix = sum(1 for r in rows if id_to_norm[r["id"]] != r["cnpj"])
    print(f"  CNPJ format needs normalization: {needs_format_fix:,}")

    dup_groups = {k: v for k, v in groups.items() if len(v) > 1}
    print(f"  Duplicate (normalized_cnpj, ano) groups: {len(dup_groups):,}")

    if dup_groups:
        total_dupe_rows = sum(len(v) - 1 for v in dup_groups.values())
        print(f"  Duplicate rows to merge: {total_dupe_rows:,}")
        if dry_run:
            for i, ((norm, ano), ids) in enumerate(sorted(dup_groups.items())[:5]):
                print(f"    cnpj={norm} ano={ano} ids={ids}")
            if len(dup_groups) > 5:
                print(f"    ... and {len(dup_groups) - 5} more")

    if dry_run:
        conn.close()
        return

    # --- Step 2: Merge duplicates (delete colliding, move rest, delete dup rows) ---
    # When DFP/ITR was re-synced with force=True before normalization, INSERT OR REPLACE
    # wrote identical contas rows under BOTH the dotted-CNPJ empresa and plain-CNPJ
    # empresa. A direct UPDATE id_empresa=primary WHERE id_empresa=dup would hit
    # UNIQUE constraint on (id_empresa, codigo, consolidado, data_ini_exerc, data_fim_exerc).
    # Fix: delete rows from dup that already exist in primary (identical data anyway),
    # then move the remaining non-colliding rows.
    merged_count = 0
    contas_deleted_colliding = 0
    contas_moved = 0
    for (norm, ano), ids in dup_groups.items():
        ids.sort()
        primary_id = ids[0]
        duplicate_ids = ids[1:]

        for dup_id in duplicate_ids:
            # Step 2a: Delete colliding rows from dup (they already exist in primary)
            deleted = conn.execute(
                """DELETE FROM contas WHERE id_empresa = ?
                   AND EXISTS (
                       SELECT 1 FROM contas c2
                       WHERE c2.id_empresa = ?
                         AND c2.codigo = contas.codigo
                         AND c2.consolidado = contas.consolidado
                         AND COALESCE(c2.data_ini_exerc, '') = COALESCE(contas.data_ini_exerc, '')
                         AND c2.data_fim_exerc = contas.data_fim_exerc
                   )""",
                (dup_id, primary_id),
            ).rowcount
            contas_deleted_colliding += deleted

            # Step 2b: Move remaining (non-colliding) rows to primary
            moved = conn.execute(
                "UPDATE contas SET id_empresa = ? WHERE id_empresa = ?",
                (primary_id, dup_id),
            ).rowcount
            contas_moved += moved

            # Step 2c: Delete the now-empty duplicate empresa row
            conn.execute("DELETE FROM empresas WHERE id = ?", (dup_id,))
            merged_count += 1

    conn.commit()
    print(f"  Merged {merged_count:,} duplicate empresa rows")
    print(f"  Deleted {contas_deleted_colliding:,} colliding contas (already in primary)")
    print(f"  Moved {contas_moved:,} contas rows to primary empresa")

    # --- Step 3: Normalize CNPJ format on remaining rows ---
    normalized_count = 0
    remaining = conn.execute("SELECT id, cnpj FROM empresas").fetchall()
    for row in remaining:
        original = row["cnpj"]
        normalized = cnpj_digits(original)
        if normalized != original:
            conn.execute(
                "UPDATE empresas SET cnpj = ? WHERE id = ?",
                (normalized, row["id"]),
            )
            normalized_count += 1

    conn.commit()
    print(f"  CNPJ format normalized: {normalized_count:,}")

    final_count = conn.execute("SELECT COUNT(*) FROM empresas").fetchone()[0]
    print(f"  Final empresa count: {final_count:,}")

    conn.close()


def main():
    parser = argparse.ArgumentParser(
        description="One-time CNPJ normalization + duplicate merge for DFP/ITR databases.",
    )
    parser.add_argument("--dfp", action="store_true", help="Normalize DFP only")
    parser.add_argument("--itr", action="store_true", help="Normalize ITR only")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report without making changes",
    )
    args = parser.parse_args()

    do_dfp = args.dfp or (not args.dfp and not args.itr)
    do_itr = args.itr or (not args.dfp and not args.itr)

    print(f"{'=' * 60}")
    print(f"  CVM CNPJ Normalization (one-time repair)")
    print(f"  Databases: {', '.join(filter(None, ['DFP' if do_dfp else None, 'ITR' if do_itr else None]))}")
    print(f"  Dry run: {args.dry_run}")
    print(f"{'=' * 60}")

    if do_dfp:
        normalize_db(dfp_db_path(), "DFP", args.dry_run)
    if do_itr:
        normalize_db(itr_db_path(), "ITR", args.dry_run)


if __name__ == "__main__":
    main()
