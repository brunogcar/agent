"""data_sources/cvm/_meses.py -- Shared meses (months) computation for CVM data.

The `meses` field is NOT a column in the CVM CSV. It is computed from
DT_INI_EXERC + DT_FIM_EXERC. This module mirrors rapinav2's monthsDiff()
function (https://github.com/dude333/rapinav2) — the original Go implementation
that this data source is based on.

WHAT meses MEANS
----------------
  meses=3   → Q1 cumulative (Jan→Mar, ITR)
  meses=6   → H1 cumulative (Jan→Jun, ITR)
  meses=9   → 9M cumulative (Jan→Sep, ITR)
  meses=12  → Annual flow (Jan→Dec, DFP) OR balance-sheet snapshot (BPA/BPP)
  meses=15  → 15-month transition period (rare, DFP)

BPA/BPP (balance sheet) rows have DT_INI_EXERC="" (empty) because they are
point-in-time snapshots, not period flows. For these, meses defaults to 12.

FLOW VS SNAPSHOT
----------------
  Flow statements (DRE, DFC, DVA, DMPL) have DT_INI_EXERC != "".
  Snapshot statements (BPA, BPP) have DT_INI_EXERC == "".

This distinction is critical for the query layer: flow values are cumulative
over a period, snapshot values are point-in-time. The trimestral transformation
(T4 = annual − 9M) only applies to flows; snapshots are taken as-is.
"""

from __future__ import annotations

from datetime import date


def compute_meses(dt_ini: str, dt_fim: str) -> int:
    """Compute the number of months in a CVM reporting period.

    Mirrors rapinav2's monthsDiff() (pkg/contabil/contabil_cvm_dfp.go:353-387).

    Args:
        dt_ini: DT_INI_EXERC from CVM CSV (ISO format "YYYY-MM-DD").
                Empty string "" for BPA/BPP snapshots.
        dt_fim: DT_FIM_EXERC from CVM CSV (ISO format "YYYY-MM-DD").

    Returns:
        Number of months (inclusive). Values: 3, 6, 9, 12, 15, or other.
        Returns 12 for empty dt_ini (BPA/BPP snapshots).
        Returns 0 for invalid dates (caller should drop these rows).

    Examples:
        >>> compute_meses("", "2023-12-31")
        12  # BPA/BPP snapshot
        >>> compute_meses("2023-01-01", "2023-03-31")
        3   # ITR Q1
        >>> compute_meses("2023-01-01", "2023-06-30")
        6   # ITR H1
        >>> compute_meses("2023-01-01", "2023-09-30")
        9   # ITR 9M
        >>> compute_meses("2023-01-01", "2023-12-31")
        12  # DFP annual
        >>> compute_meses("2023-01-01", "2024-03-31")
        15  # 15-month transition
        >>> compute_meses("2023-07-01", "2024-06-30")
        12  # Non-calendar fiscal year (Jul→Jun)
    """
    # BPA/BPP snapshots: DT_INI_EXERC is empty → default to 12 months
    if not dt_ini or not dt_ini.strip():
        return 12

    try:
        ini = date.fromisoformat(dt_ini[:10])
        fim = date.fromisoformat(dt_fim[:10])
    except (ValueError, TypeError):
        return 0  # invalid dates — caller should drop

    # rapinav2 formula: (anoF - anoI) * 12 - mesI + mesF + 1
    # The +1 makes it inclusive: Jan→Mar = 3 - 1 + 1 = 3 months (not 2)
    meses = (fim.year - ini.year) * 12 - ini.month + fim.month + 1
    return meses


def is_snapshot(dt_ini: str) -> bool:
    """Check if a row is a balance-sheet snapshot (BPA/BPP).

    Snapshot rows have DT_INI_EXERC == "" (empty).
    Flow rows (DRE, DFC, DVA, DMPL) have DT_INI_EXERC != "".
    """
    return not dt_ini or not dt_ini.strip()


def is_flow(dt_ini: str) -> bool:
    """Check if a row is a flow statement (DRE, DFC, DVA, DMPL).

    Flow rows have DT_INI_EXERC != "" (non-empty).
    """
    return not is_snapshot(dt_ini)


def should_keep_row(ordem_exerc: str, dt_fim: str) -> bool:
    """Filter rows by ORDEM_EXERC.

    rapinav2 keeps only:
    - ORDEM_EXERC == "ÚLTIMO" (current-year value)
    - ORDEM_EXERC == "PENÚLTIMO" AND DT_FIM_EXERC starts with "2009"
      (the 2009 backfill trick — CVM DFP starts in 2010, so 2009 data
      only exists as PENÚLTIMO in the 2010 filing)

    All other PENÚLTIMO rows are comparative prior-year columns that would
    create duplicate data (prior year already stored from its own ÚLTIMO).

    Args:
        ordem_exerc: ORDEM_EXERC from CVM CSV ("ÚLTIMO" or "PENÚLTIMO").
        dt_fim: DT_FIM_EXERC from CVM CSV (ISO format "YYYY-MM-DD").

    Returns:
        True if the row should be kept, False if it should be dropped.
    """
    if not ordem_exerc:
        return True  # defensive — keep if unknown

    ordem = ordem_exerc.strip().upper()
    if ordem == "ÚLTIMO" or ordem == "ULTIMO":
        return True
    if ordem == "PENÚLTIMO" or ordem == "PENULTIMO":
        # Keep only 2009 backfill
        return dt_fim.startswith("2009") if dt_fim else False
    return False  # unknown ORDEM_EXERC — drop


def is_valid_meses(meses: int) -> bool:
    """Check if meses is a valid reporting period.

    rapinav2 drops rows where meses % 3 != 0 (invalid period).
    Valid: 3, 6, 9, 12, 15, 18, ... (multiples of 3).
    Invalid: 0, 1, 2, 4, 5, 7, 8, 10, 11, 13, 14, ...
    """
    return meses > 0 and meses % 3 == 0
