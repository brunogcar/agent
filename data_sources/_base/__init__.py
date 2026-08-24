"""data_sources/_base/ — Cross-domain shared infrastructure.

[Phase 4 C1] Centralizes the SQLite catalog pattern (connect/db_path/data_dir)
that was duplicated across all 4 data_source domains (bcb, b3, cvm, ddm).

Domain-specific patterns (sync engines, fetchers, parsers) stay in their
respective domain folders — only the genuinely cross-domain plumbing
lives here.
"""
from data_sources._base.catalog import data_dir, db_path, connect

__all__ = ["data_dir", "db_path", "connect"]
