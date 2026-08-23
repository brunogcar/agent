"""data_sources/ddm/_base/catalog_base.py -- Shared catalog infrastructure.

Common building blocks for all 7 DDM sub-domain catalogs (inflation, juros,
poupanca, acoes, dividends, fluxo, focus):

  - API_BASE constant (https://www.dadosdemercado.com.br).
  - ddm_data_dir() -- the memory_db/ddm/ base folder (creates it if missing).
    Byte-for-byte identical in all 7 catalogs before extraction.
  - connect(db_filename, source_name, read_only) -- open a SQLite connection.
    Identical 21-line body in all 7 catalogs before extraction; only the
    filename + the FileNotFoundError message string differed.
  - ensure_schema(conn, schema_sql, catalog, catalog_table) -- run the
    CREATE TABLE script, optionally populate a `<source>_catalog` metadata
    table from a CATALOG dict, then commit.
  - BaseDDMCatalog -- a thin config-driven class that bundles the above as
    classmethods so each source's catalog.py can declare its config as class
    attrs (DB_FILENAME, SOURCE_NAME, SCHEMA_SQL, INDEX_CATALOG,
    CATALOG_TABLE) and re-export `db_path` / `connect` / `ensure_schema` as
    module-level callables for backward compatibility.

What stays per-source (the genuine diff):
  - SCHEMA_SQL (different tables, columns, indexes).
  - INDEX_CATALOG / JUROS_CATALOG / POUPANCA_CATALOG (multi-page only).
  - URL helpers (index_url(slug) vs <src>_url() vs <SRC>_URL constant).

[Phase 3, Commit 1] Extracted from the 7 catalog.py files. See
phase3-investigate-ddm-base in worklog.md for the duplication analysis.
"""

from __future__ import annotations

API_BASE = "https://www.dadosdemercado.com.br"


def ddm_data_dir():
    """Return the DDM base data directory (creates it if missing).

    All DDM DBs live in the SAME base folder (memory_db/ddm/), not
    per-subdomain subfolders. So inflation.db, acoes.db, juros.db,
    poupanca.db, focus.db, fluxo.db, and dividends.db all sit side-by-side
    in memory_db/ddm/.

    Resolution order:
      1. core.config.cfg.memory_root / "ddm" (when set, mirrors bcb/sgs).
      2. cwd / "memory_db" / "ddm" (fallback).
    """
    from pathlib import Path
    try:
        from core.config import cfg
        memory_root = getattr(cfg, "memory_root", None)
    except Exception:
        memory_root = None
    if memory_root:
        d = Path(memory_root) / "ddm"
        d.mkdir(parents=True, exist_ok=True)
        return d
    d = Path.cwd() / "memory_db" / "ddm"
    d.mkdir(parents=True, exist_ok=True)
    return d


def connect(db_filename: str, source_name: str, read_only: bool = True):
    """Open a connection to <db_filename> in the DDM data dir.

    Args:
        db_filename: e.g. "inflation.db" (just the basename).
        source_name: e.g. "inflation" (for the FileNotFoundError message).
        read_only: True uses SQLite URI mode=ro (fails if DB missing).
                   False opens (or creates) the DB for writes.

    Returns a sqlite3.Connection with row_factory = sqlite3.Row.
    """
    import sqlite3
    path = ddm_data_dir() / db_filename
    if not path.exists():
        if read_only:
            raise FileNotFoundError(
                f"DDM {source_name} database not found at {path}. "
                f"Run sync first."
            )
        conn = sqlite3.connect(str(path))
    else:
        conn = sqlite3.connect(
            f"file:{path}?mode=ro" if read_only else str(path),
            uri=read_only,
        )
    conn.row_factory = sqlite3.Row
    return conn


def ensure_schema(
    conn,
    schema_sql: str,
    catalog: dict | None = None,
    catalog_table: str | None = None,
) -> None:
    """Create tables if they don't exist; optionally populate the catalog.

    Idempotent: CREATE TABLE IF NOT EXISTS is safe to re-run, and
    INSERT OR REPLACE refreshes metadata on every sync.

    Args:
        conn: an open SQLite connection (write mode).
        schema_sql: the SCHEMA_SQL constant from the per-source catalog.py.
        catalog: optional dict[slug, (name, category, description, unit)].
                 When provided, rows are INSERT-OR-REPLACEd into
                 <catalog_table>.
        catalog_table: optional table name (e.g. "index_catalog"). Required
                       when `catalog` is provided; ignored otherwise.
    """
    conn.executescript(schema_sql)
    if catalog and catalog_table:
        rows = [
            (slug, meta[0], meta[1], meta[2], meta[3])
            for slug, meta in catalog.items()
        ]
        conn.executemany(
            f"INSERT OR REPLACE INTO {catalog_table} "
            "(slug, name, category, description, unit) "
            "VALUES (?, ?, ?, ?, ?)",
            rows,
        )
    conn.commit()


class BaseDDMCatalog:
    """Config-driven base class for DDM sub-domain catalogs.

    Each source's catalog.py declares a subclass with class attrs:

        class _Catalog(BaseDDMCatalog):
            DB_FILENAME   = "inflation.db"
            SOURCE_NAME   = "inflation"
            SCHEMA_SQL    = SCHEMA_SQL     # defined at module level
            INDEX_CATALOG = INDEX_CATALOG  # multi-page only; {} otherwise
            CATALOG_TABLE = "index_catalog"  # multi-page only; "" otherwise

    and then re-exports the classmethods as module-level functions for
    backward compatibility:

        db_path       = _Catalog.db_path
        connect       = _Catalog.connect
        ensure_schema = _Catalog.ensure_schema

    The module-level `db_path` / `connect` / `ensure_schema` names are
    imported by sync_engine.py, status_reporter.py, query_engine.py, and
    skills/_freshness.py — so they MUST remain module-level callables.
    """

    DB_FILENAME: str = ""
    SOURCE_NAME: str = ""
    SCHEMA_SQL: str = ""
    INDEX_CATALOG: dict = {}
    CATALOG_TABLE: str = ""

    @classmethod
    def db_path(cls):
        """Return the path to <DB_FILENAME> in the DDM data dir."""
        return ddm_data_dir() / cls.DB_FILENAME

    @classmethod
    def connect(cls, read_only: bool = True):
        """Open a connection to <DB_FILENAME>.

        See module-level `connect()` for the read_only semantics.
        """
        return connect(cls.DB_FILENAME, cls.SOURCE_NAME, read_only)

    @classmethod
    def ensure_schema(cls, conn) -> None:
        """Create tables if they don't exist + populate the catalog table.

        Idempotent: safe to call on every connect-for-write.
        """
        ensure_schema(
            conn,
            cls.SCHEMA_SQL,
            cls.INDEX_CATALOG or None,
            cls.CATALOG_TABLE or None,
        )
