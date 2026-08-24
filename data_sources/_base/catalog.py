"""data_sources/_base/catalog.py — Cross-domain SQLite catalog helpers.

Shared infrastructure for all data_source domains (bcb, b3, cvm, ddm).
Centralizes the connect/db_path/data_dir pattern that was duplicated
across 4 domains (7+ copies of the same 18-line connect() function).

[Phase 4 C1] Extracted per code review — the catalog layer is the only
genuinely cross-domain concern (SQLite connection plumbing). Sync/fetcher
patterns stay domain-specific (DDM scrapes HTML, CVM downloads ZIPs, etc.).

[Phase 4 C4] Adopted by all 4 domains (DDM, BCB, B3, CVM). The per-domain
`*_data_dir()` / `*_db_path()` / `connect_*()` helpers are now thin
wrappers that delegate to `data_dir(domain)` / `connect(...)` here.

Functions:
  - data_dir(domain)     -> Path  (memory_db/<domain>/ via cfg.memory_root)
  - db_path(domain, filename) -> Path
  - connect(path, source_name, read_only=True) -> sqlite3.Connection
"""
from __future__ import annotations

import sqlite3
from pathlib import Path


def data_dir(domain: str) -> Path:
    """Return the data directory for a domain.

    Resolution order:
      1. ``core.config.cfg.memory_root / <domain>`` (canonical — always set
         in production via ``MEMORY_ROOT`` env var, defaults to
         ``<agent_root>/memory_db``).
      2. ``cwd / "memory_db" / <domain>`` (fallback when ``core.config``
         can't be imported — e.g. standalone scripts without the agent
         package on sys.path).

    Creates the directory if it doesn't exist (idempotent — safe to call on
    every read or write path).

    [Phase 4 C4 bugfix] Previously this consulted a ``MEMORY_DB_ROOT`` env
    var that was never set anywhere in the repo — meaning tests that
    patched ``cfg.memory_root = tmp_path`` were silently ignored by this
    function. Now it consults ``cfg.memory_root`` (the same source every
    domain already uses), so the resolution chain is unified across DDM /
    BCB / B3 / CVM.
    """
    try:
        from core.config import cfg
        memory_root = getattr(cfg, "memory_root", None)
    except Exception:
        memory_root = None
    if memory_root:
        d = Path(memory_root) / domain
        d.mkdir(parents=True, exist_ok=True)
        return d
    d = Path.cwd() / "memory_db" / domain
    d.mkdir(parents=True, exist_ok=True)
    return d


def db_path(domain: str, filename: str) -> Path:
    """Return the path to <domain>/<filename> in the data root."""
    return data_dir(domain) / filename


def connect(path: Path, source_name: str, read_only: bool = True) -> sqlite3.Connection:
    """Open a SQLite connection with the standard mode=ro pattern.

    Args:
        path:        Full path to the .db file.
        source_name: Human-readable name for error messages (e.g. "sgs").
        read_only:   True uses SQLite URI mode=ro (fails if DB missing).
                     False opens (or creates) the DB for writes.

    Returns a sqlite3.Connection with row_factory = sqlite3.Row.
    """
    if not path.exists():
        if read_only:
            raise FileNotFoundError(
                f"{source_name} database not found at {path}. Run sync first."
            )
        # For write mode, create the parent dir if needed.
        path.parent.mkdir(parents=True, exist_ok=True)

    if read_only:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    else:
        conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    return conn
