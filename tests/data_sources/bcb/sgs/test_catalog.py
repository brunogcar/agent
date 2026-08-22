"""tests/data_sources/bcb/sgs/test_catalog.py - SERIES_CATALOG + schema tests."""
from __future__ import annotations
from data_sources.bcb.sgs import catalog


def test_catalog_has_priority_series():
    codes = list(catalog.SERIES_CATALOG.keys())
    assert len(codes) == 11
    # 11 curated series covering the 4 macro categories (including TR 226).
    for code in [11, 12, 226, 432, 4389, 4390, 433, 189, 1, 4380, 1619]:
        assert code in codes, f"missing series {code}"


def test_catalog_has_series_226_tr():
    """v3 fix: series 226 (TR) was dropped in v2 - add it back."""
    assert 226 in catalog.SERIES_CATALOG
    name, freq, unit, category, desc = catalog.SERIES_CATALOG[226]
    assert "TR" in name
    assert freq == "daily"
    assert category == "Juros"


def test_catalog_entry_shape():
    for code, meta in catalog.SERIES_CATALOG.items():
        assert isinstance(meta, tuple) and len(meta) == 5, f"bad shape for {code}"
        name, freq, unit, category, desc = meta
        assert freq in {"daily", "monthly", "quarterly", "annual"}
        assert category in {"Juros", "Inflacao", "Cambio", "Atividade"}
        assert name and desc, f"empty name/desc for {code}"


def test_schema_creates_three_tables(tmp_path):
    import sqlite3
    conn = sqlite3.connect(str(tmp_path / "sgs.db"))
    catalog.ensure_schema(conn)
    tables = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    assert {"series_observations", "series_catalog", "sync_state"} <= tables
    # Catalog populated with all 11 series.
    n = conn.execute("SELECT COUNT(*) FROM series_catalog").fetchone()[0]
    assert n == 11
    conn.close()


def test_sync_state_uses_v1_schema(tmp_path):
    """v3 fix: sync_state uses (series_code, last_date, synced_at, row_count)
    instead of v2's (key, value, synced_at)."""
    import sqlite3
    conn = sqlite3.connect(str(tmp_path / "sgs.db"))
    catalog.ensure_schema(conn)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(sync_state)").fetchall()}
    assert {"series_code", "last_date", "synced_at", "row_count"} <= cols
    conn.close()


def test_drop_table_migrates_old_v1_db(tmp_path):
    """v3 fix: DROP TABLE IF EXISTS sync_state before CREATE ensures old v1
    DBs with a different sync_state shape get migrated."""
    import sqlite3
    db = tmp_path / "sgs.db"
    conn = sqlite3.connect(str(db))
    # Simulate an old v1 DB with the v2 schema (key/value/synced_at).
    conn.executescript("""
        CREATE TABLE series_observations (series_code INT, ref_date TEXT, value REAL);
        CREATE TABLE sync_state (key TEXT PRIMARY KEY, value TEXT, synced_at TEXT);
    """)
    conn.execute("INSERT INTO sync_state (key, value, synced_at) VALUES ('x','y','z')")
    conn.commit()
    # ensure_schema should DROP the old sync_state and CREATE the new one.
    catalog.ensure_schema(conn)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(sync_state)").fetchall()}
    assert "row_count" in cols  # new v1-schema column
    assert "value" not in cols  # old v2 column gone
    conn.close()
