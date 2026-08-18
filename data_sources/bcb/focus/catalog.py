"""data_sources/bcb/focus/catalog.py -- Schema + indicator catalog for BCB Focus.

BCB Focus = Boletim Focus (weekly market expectations survey). Public, free,
no auth. The Olinda OData API exposes per-indicator market expectations:
median, mean, min, max + respondent count.

API: https://olinda.bcb.gov.br/olinda/servico/Expectativas/versao/v1/odata/
  - ExpectativaMercadoMensais  (monthly expectations, e.g. IPCA for 08/2028)
  - ExpectativasMercadoAnuais  (annual expectations, e.g. Selic for 2026)

OData query params:
  - $filter=Indicador eq 'IPCA'
  - $orderby=Data desc
  - $top=N
  - $format=json

Response fields (per row):
  Indicador            -- 'IPCA', 'Selic', 'PIB', 'Cambio'
  Data                 -- YYYY-MM-DD (date the expectation was made)
  DataReferencia       -- '2026' (annual) or '08/2028' (monthly)
  Media, Mediana       -- central tendency
  Minimo, Maximo       -- range
  numeroRespondentes   -- survey participant count
  baseCalculo          -- 0 (current month) or 1 (next month onward)

Storage: memory_db/bcb/focus.db
"""

from __future__ import annotations

API_BASE = (
    "https://olinda.bcb.gov.br/olinda/servico/Expectativas/versao/v1/odata"
)

# Curated indicator catalog. Tuple shape:
#   (indicador, frequency, description, unit_hint)
#   frequency in {monthly, annual}
#   unit_hint is a display hint (raw values are plain floats; the report
#   layer formats them per the indicator convention).
INDICATOR_CATALOG: dict[str, tuple[str, str, str, str]] = {
    "IPCA":  ("IPCA",  "monthly", "Inflacao - IPCA mensal (% no mes)",         "%"),
    "Selic": ("Selic", "annual",  "Juros - Meta Selic (% a.a.)",               "% a.a."),
    "Câmbio":("Câmbio","monthly", "Cambio - USD/BRL (R$ por dolar, fim mes)",  "R$"),
}

# Endpoints per frequency. Each maps to a single Olinda entity set.
ENDPOINTS: dict[str, str] = {
    "monthly": "ExpectativaMercadoMensais",
    "annual":  "ExpectativasMercadoAnuais",
}

# All indicators we sync, with their default frequency (some indicators
# are available in both monthly + annual — we sync the primary one).
DEFAULT_INDICATORS: list[tuple[str, str]] = [
    ("IPCA",   "monthly"),
    ("Selic",  "annual"),
    ("Câmbio", "monthly"),
]


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS expectations_monthly (
    indicador            TEXT NOT NULL,
    data                 TEXT NOT NULL,        -- YYYY-MM-DD (date expectation was made)
    data_referencia      TEXT NOT NULL,        -- 'MM/YYYY' for monthly
    media                REAL,
    mediana              REAL,
    minimo               REAL,
    maximo               REAL,
    numero_respondentes INTEGER,
    base_calculo         INTEGER,
    synced_at            TEXT,
    PRIMARY KEY (indicador, data, data_referencia, base_calculo)
);

CREATE INDEX IF NOT EXISTS idx_exp_monthly_ind ON expectations_monthly(indicador);
CREATE INDEX IF NOT EXISTS idx_exp_monthly_ref ON expectations_monthly(data_referencia);
CREATE INDEX IF NOT EXISTS idx_exp_monthly_date ON expectations_monthly(data);

CREATE TABLE IF NOT EXISTS expectations_annual (
    indicador            TEXT NOT NULL,
    data                 TEXT NOT NULL,        -- YYYY-MM-DD (date expectation was made)
    data_referencia      TEXT NOT NULL,        -- 'YYYY' for annual
    media                REAL,
    mediana              REAL,
    minimo               REAL,
    maximo               REAL,
    numero_respondentes INTEGER,
    base_calculo         INTEGER,
    synced_at            TEXT,
    PRIMARY KEY (indicador, data, data_referencia)
);

CREATE INDEX IF NOT EXISTS idx_exp_annual_ind ON expectations_annual(indicador);
CREATE INDEX IF NOT EXISTS idx_exp_annual_ref ON expectations_annual(data_referencia);
CREATE INDEX IF NOT EXISTS idx_exp_annual_date ON expectations_annual(data);

CREATE TABLE IF NOT EXISTS sync_state (
    indicador   TEXT PRIMARY KEY,
    frequency   TEXT,
    last_date   TEXT,
    synced_at   TEXT,
    row_count   INTEGER
);
"""


def bcb_data_dir():
    """Return the BCB data directory (creates it if missing)."""
    from pathlib import Path
    try:
        from core.config import cfg
        memory_root = getattr(cfg, "memory_root", None)
    except Exception:
        memory_root = None
    if memory_root:
        d = Path(memory_root) / "bcb"
        d.mkdir(parents=True, exist_ok=True)
        return d
    d = Path.cwd() / "memory_db" / "bcb"
    d.mkdir(parents=True, exist_ok=True)
    return d


def db_path():
    """Return the path to focus.db."""
    return bcb_data_dir() / "focus.db"


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
                f"Focus database not found at {path}. Run sync first."
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
    """Create tables if they don't exist."""
    conn.executescript(SCHEMA_SQL)
    conn.commit()


def endpoint_url(frequency: str) -> str:
    """Build the Olinda OData endpoint URL for a frequency."""
    entity = ENDPOINTS.get(frequency)
    if not entity:
        raise ValueError(f"Unknown frequency: {frequency!r}")
    return f"{API_BASE}/{entity}"
