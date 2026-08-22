"""data_sources/ddm/focus/catalog.py -- Schema + URL helpers for DDM Focus.

DDM Focus = Brazilian Boletim Focus (market expectations survey) scraped from
dadosdemercado.com.br/boletim-focus. The page exposes 4 yearly tables (one
per target year: 2026, 2027, 2028, 2029), each `<table class="normal-table">`
with the same 6-column shape:

    Indicador | Ha 4 semanas | 1 sem | Hoje | Comp. | Resp.

Values are PT-BR formatted strings preserved verbatim from the source:
    - "5,151%"      -- percent with comma decimal
    - "R$ 5,200"    -- currency with PT-BR thousands + decimal
    - "149"         -- respondent count (integer)
    - Comp. column  -- one of three glyphs: up/down/flat

Unlike the other DDM sub-domains (inflation / juros / poupanca / acoes),
Focus is a single-page snapshot, not a per-index historical series. There
is NO catalog of indices: the 4 year-tables each carry 12-13 indicator
rows (IPCA, PIB Total, Cambio, Selic, etc.) which are discovered at parse
time. The DB stores each (year, indicator, ref_date) combination so a
history of focus snapshots is preserved across syncs.

Storage: memory_db/ddm/focus.db (per-subdomain DB in the DDM base folder,
mirroring ddm/acoes.db + ddm/juros.db + ddm/poupanca.db side-by-side layout).
"""

from __future__ import annotations

API_BASE = "https://www.dadosdemercado.com.br"

# Canonical URL for the Boletim Focus page. Single page, no slug substitution.
FOCUS_URL = f"{API_BASE}/boletim-focus"


# Schema: focus_observations holds one row per (year, indicator, ref_date).
# ref_date is the YYYY-MM-DD of the sync (Focus is weekly; DDM does not
# expose a publication-date column on the page itself, so the sync date is
# the closest proxy for the bulletin's reference week).
#
# All numeric values are stored as TEXT strings preserving the source format
# ("5,151%", "R$ 5,200"). Downstream consumers (charts, KPIs) parse the
# strings into floats on demand. This mirrors the acoes variation-pattern
# but is even more permissive: Focus mixes percentage, currency, and
# integer-count columns in the same snapshot, so keeping the original
# string form avoids lossy conversions.
SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS focus_observations (
    year            INTEGER NOT NULL,
    indicator       TEXT NOT NULL,
    four_weeks_ago  TEXT,
    one_week_ago    TEXT,
    today           TEXT,
    comparison      TEXT,
    respondents     INTEGER,
    ref_date        TEXT,
    synced_at       TEXT,
    PRIMARY KEY (year, indicator, ref_date)
);

CREATE INDEX IF NOT EXISTS idx_focus_year      ON focus_observations(year);
CREATE INDEX IF NOT EXISTS idx_focus_indicator ON focus_observations(indicator);
CREATE INDEX IF NOT EXISTS idx_focus_ref_date  ON focus_observations(ref_date);

CREATE TABLE IF NOT EXISTS sync_state (
    slug          TEXT PRIMARY KEY,     -- always 'focus' for this subdomain
    last_date     TEXT,                 -- most recent ref_date synced (YYYY-MM-DD)
    synced_at     TEXT,                 -- ISO timestamp of the sync
    row_count     INTEGER               -- number of rows synced
);
"""


def ddm_data_dir():
    """Return the DDM base data directory (creates it if missing).

    All DDM DBs live in the SAME base folder (memory_db/ddm/), not
    per-subdomain subfolders. So inflation.db, acoes.db, juros.db,
    poupanca.db, and focus.db all sit side-by-side in memory_db/ddm/.
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


def db_path():
    """Return the path to focus.db."""
    return ddm_data_dir() / "focus.db"


def connect(read_only: bool = True):
    """Open a connection to focus.db.

    read_only=True uses the SQLite URI mode=ro (fails if DB missing).
    read_only=False opens (or creates) the DB for writes.
    """
    import sqlite3
    path = db_path()
    if not path.exists():
        if read_only:
            raise FileNotFoundError(
                f"DDM focus database not found at {path}. Run sync first."
            )
        conn = sqlite3.connect(str(path))
    else:
        conn = sqlite3.connect(
            f"file:{path}?mode=ro" if read_only else str(path),
            uri=read_only,
        )
    conn.row_factory = sqlite3.Row
    return conn


def ensure_schema(conn):
    """Create tables if they don't exist.

    Idempotent: CREATE TABLE IF NOT EXISTS is safe to re-run.
    """
    conn.executescript(SCHEMA_SQL)
    conn.commit()


def focus_url() -> str:
    """Return the canonical Boletim Focus URL."""
    return FOCUS_URL
