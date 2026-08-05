"""tests/data_sources/b3/index/conftest.py -- Test fixtures for B3 index tests."""
import sqlite3
from pathlib import Path
import pytest


@pytest.fixture
def index_db(tmp_path, monkeypatch):
    """Create a temp index.db with test data."""
    db = tmp_path / "index.db"
    conn = sqlite3.connect(str(db))
    conn.executescript("""
        CREATE TABLE index_catalog (
            code TEXT PRIMARY KEY, name TEXT, description TEXT, active INTEGER DEFAULT 0
        );
        CREATE TABLE index_constituents (
            index_code TEXT NOT NULL, ticker TEXT NOT NULL, company_name TEXT,
            type TEXT, theorical_qty INTEGER, participation REAL, rank INTEGER,
            ref_date TEXT NOT NULL, synced_at TEXT,
            PRIMARY KEY (index_code, ticker, ref_date)
        );
        CREATE TABLE sync_state (
            index_code TEXT PRIMARY KEY, last_date TEXT, synced_at TEXT, row_count INTEGER
        );
        INSERT INTO index_catalog VALUES ('IBOV','Indice Bovespa','Principal indice',1);
        INSERT INTO index_catalog VALUES ('SMLL','Indice Small Cap','Small caps',1);
        INSERT INTO index_constituents VALUES ('IBOV','PETR4','PETROBRAS','ON NM',1000000,10.5,1,'2024-01-15','2024-01-15T10:00:00');
        INSERT INTO index_constituents VALUES ('IBOV','VALE3','VALE','ON NM',800000,8.3,2,'2024-01-15','2024-01-15T10:00:00');
        INSERT INTO index_constituents VALUES ('SMLL','PETR4','PETROBRAS','ON NM',500000,5.2,3,'2024-01-15','2024-01-15T10:00:00');
        INSERT INTO sync_state VALUES ('IBOV','2024-01-15','2024-01-15T10:00:00',2);
        INSERT INTO sync_state VALUES ('SMLL','2024-01-15','2024-01-15T10:00:00',1);
    """)
    conn.commit()
    conn.close()

    monkeypatch.setattr("data_sources.b3.index.catalog.db_path", lambda: db)
    return db
