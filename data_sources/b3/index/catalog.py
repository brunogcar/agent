"""data_sources/b3/index/catalog.py -- Schema + index catalog for B3 indices.

B3 indexProxy API: fetches index composition (constituents + weights).
URL: https://sistemaswebb3-listados.b3.com.br/indexProxy/indexCall/GetPortfolioDay/{base64}
Payload: {"language":"en-us","pageNumber":1,"pageSize":200,"index":"IBOV","segment":"1"}

Indices update quarterly (4 times/year) but the API always returns the
CURRENT composition. This catalog stores ALL available indices (26) but
only 5 are marked active for sync. More can be activated by setting
active=1 in INDEX_CATALOG.

Storage: memory_db/b3/index.db
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

API_BASE = "https://sistemaswebb3-listados.b3.com.br/indexProxy/indexCall/GetPortfolioDay"

# All 26 B3 indices. active=True marks the 5 we sync by default.
# Tuple: (name, description, active)
INDEX_CATALOG: dict[str, tuple[str, str, bool]] = {
    "IBOV":   ("Indice Bovespa", "Principal indice do mercado acionario brasileiro", True),
    "SMLL":   ("Indice Small Cap", "Acoes de menor capitalizacao com boa liquidez", True),
    "BDRX":   ("Indice BDRX", "BDRs nao patrocinados negociados na B3", True),
    "IFIX":   ("Indice de Fundos Imobiliarios", "Principal indice de FIIs da B3", True),
    "IDIV":   ("Indice Dividendos", "Acoes com maior distribuicao de dividendos", True),
    "AGFS":   ("Indice Agronegocio Free Float", "Empresas do agronegocio com free float relevante", False),
    "GPTW":   ("Indice GPTW B3", "Empresas certificadas pelo Great Place to Work", False),
    "IBEE":   ("Indice de Eficiencia Energetica", "Empresas com destaque em eficiencia energetica", False),
    "IBEP":   ("Indice de Energia Eletrica", "Companhias do setor de energia eletrica", False),
    "IBEW":   ("Indice de Energia Eletrica Weighted", "Versao ponderada do indice de energia eletrica", False),
    "IBHB":   ("Indice Holding Brasil", "Empresas caracterizadas como holdings", False),
    "IBLV":   ("Indice de Baixa Volatilidade", "Acoes com menor oscilacao historica", False),
    "IBRA":   ("Indice Brasil Amplo", "Ampla representatividade do mercado brasileiro", False),
    "IBRX":   ("Indice Brasil 100", "As 100 acoes mais negociadas da B3", False),
    "IBRX50": ("Indice Brasil 50", "As 50 acoes mais negociadas da B3", False),
    "IBSD":   ("Indice Sustentabilidade Diversificada", "Empresas com boas praticas ESG", False),
    "ICO2":   ("Indice Carbono Eficiente", "Empresas com menor emissao de carbono", False),
    "ICON":   ("Indice de Consumo", "Empresas do setor de consumo", False),
    "IDVR":   ("Indice de Diversidade", "Empresas com diversidade e inclusao", False),
    "IFIL":   ("Indice Fundos Imobiliarios Liquidos", "FIIs com maior liquidez", False),
    "IMAT":   ("Indice de Materiais Basicos", "Empresas de mineracao e siderurgia", False),
    "IMOB":   ("Indice Imobiliario", "Empresas do setor imobiliario", False),
    "INDX":   ("Indice do Setor Industrial", "Empresas industriais", False),
    "ISE":    ("Indice de Sustentabilidade Empresarial", "Empresas com melhores praticas ESG", False),
    "UTIL":   ("Indice de Utilidade Publica", "Empresas de energia, agua e saneamento", False),
}

ACTIVE_INDICES = [k for k, v in INDEX_CATALOG.items() if v[2]]
ALL_INDICES = list(INDEX_CATALOG.keys())

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS index_catalog (
    code        TEXT PRIMARY KEY,
    name        TEXT,
    description TEXT,
    active      INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS index_constituents (
    index_code      TEXT NOT NULL,
    ticker          TEXT NOT NULL,
    company_name    TEXT,
    type            TEXT,
    theorical_qty   INTEGER,
    participation   REAL,
    rank            INTEGER,
    ref_date        TEXT NOT NULL,
    synced_at       TEXT,
    PRIMARY KEY (index_code, ticker, ref_date)
);

CREATE INDEX IF NOT EXISTS idx_const_index ON index_constituents(index_code);
CREATE INDEX IF NOT EXISTS idx_const_ticker ON index_constituents(ticker);
CREATE INDEX IF NOT EXISTS idx_const_date ON index_constituents(ref_date);

CREATE TABLE IF NOT EXISTS sync_state (
    index_code  TEXT PRIMARY KEY,
    last_date   TEXT,
    synced_at   TEXT,
    row_count   INTEGER
);
"""


def _db_dir() -> Path:
    try:
        from core.config import cfg
        memory_root = getattr(cfg, "memory_root", None)
        if memory_root:
            d = Path(memory_root) / "b3"
            d.mkdir(parents=True, exist_ok=True)
            return d
    except Exception:
        pass
    d = Path.cwd() / "memory_db" / "b3"
    d.mkdir(parents=True, exist_ok=True)
    return d


def db_path() -> Path:
    return _db_dir() / "index.db"


def connect(read_only: bool = True) -> sqlite3.Connection:
    path = db_path()
    if not path.exists():
        if read_only:
            raise FileNotFoundError(f"Index database not found at {path}. Run sync first.")
        path.parent.mkdir(parents=True, exist_ok=True)
    if read_only:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    else:
        conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    return conn


def ensure_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA_SQL)
    for code, (name, desc, active) in INDEX_CATALOG.items():
        conn.execute(
            "INSERT OR REPLACE INTO index_catalog (code, name, description, active) VALUES (?, ?, ?, ?)",
            (code, name, desc, 1 if active else 0),
        )
    conn.commit()


def build_index_url(index_code: str, page_size: int = 200) -> str:
    import base64
    import json
    payload = json.dumps({
        "language": "en-us",
        "pageNumber": 1,
        "pageSize": page_size,
        "index": index_code,
        "segment": "1",
    })
    b64 = base64.b64encode(payload.encode()).decode()
    return f"{API_BASE}/{b64}"
