"""data_sources/b3/cotahist_derivatives/__init__.py -- Derivatives sub-domain manifest.

Derivatives data from COTAHIST (options, term, forward) stored in the same
cotahist.db as a separate `cotahist_derivatives` table. Populated during
the standard COTAHIST sync (the sync engine writes to both tables in one pass).
"""
from __future__ import annotations

MANIFEST = {
    "sub_domain": "cotahist_derivatives",
    "description": (
        "B3 COTAHIST derivatives data: options (calls/puts), term, forward. "
        "Stored in cotahist.db as a separate table. Populated during sync."
    ),
    "source": "B3 COTAHIST annual ZIP files (same as equities — BDI-filtered)",
    "storage": "cotahist.db (shared with equities table)",
    "bdi_codes": [78, 82, 83, 84, 26],
    "modes": ["options_chain", "available_maturities", "put_call_ratio", "volume_by_strike"],
}

from data_sources.b3.cotahist_derivatives import query_engine  # noqa: F401
from data_sources.b3.cotahist_derivatives import status_reporter  # noqa: F401
