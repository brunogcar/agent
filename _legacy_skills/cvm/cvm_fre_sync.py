"""
skills/cvm/cvm_fre_sync.py
Deploy to: D:\\mcp\\agent\\skills\\cvm\\cvm_fre_sync.py

Downloader and parser for CVM FRE (Formulario de Referencia).
FRE = annual reference form filed by listed companies covering governance,
shareholder structure, executive compensation, capital structure, and more.

=== WHAT FRE IS ===
Filed annually (or on material changes) by all listed companies. Unlike IPE
(event index) or DFP/ITR (financial statements), FRE is a structured
disclosure form covering qualitative and quantitative company profile data.

=== ZIP STRUCTURE ===
Unlike IPE (1 ZIP -> 1 CSV), FRE ZIPs contain MANY CSVs:
  fre_cia_aberta_{year}.csv              <- FILING INDEX (always import)
  fre_cia_aberta_posicao_acionaria_{year}.csv        <- shareholder stakes
  fre_cia_aberta_distribuicao_capital_{year}.csv     <- free float / shareholder counts
  fre_cia_aberta_remuneracao_total_orgao_{year}.csv  <- board/exec compensation
  fre_cia_aberta_capital_social_{year}.csv           <- share count + capital value
  ... ~20+ other CSVs (auditors, board bios, related-party text, etc.)

DECISION: We import only the 5 most analytically useful CSVs into structured
tables. The other ~20 sections are text-heavy and low-value for programmatic
queries; they remain accessible via link_download (the full document URL).
This keeps fre.db lean and fast. Add more tables here if/when needed.

=== URL PATTERN ===
https://dados.cvm.gov.br/dados/CIA_ABERTA/DOC/FRE/DADOS/fre_cia_aberta_{year}.zip
One ZIP per year. Available from 2010 to present. Updated daily.
File size: ~15-50MB per year (much larger than IPE due to multiple CSVs).

=== DB SCHEMA (fre.db at memory_db/cvm/fre.db) ===

TABLE: documentos  <- from fre_cia_aberta_{year}.csv
  id_doc           INTEGER PRIMARY KEY  (ID_DOC from CVM, globally unique)
  cnpj             VARCHAR  (digits only, 14 chars)
  cd_cvm           INTEGER
  nome             VARCHAR
  categ_doc        VARCHAR  (FRE type category)
  dt_receb         VARCHAR  (YYYY-MM-DD, when CVM received it)
  dt_refer         VARCHAR  (YYYY-MM-DD, reference date)
  versao           INTEGER
  link_doc         VARCHAR  (download URL for full document)
  ano_origem       INTEGER

TABLE: posicao_acionaria  <- from fre_cia_aberta_posicao_acionaria_{year}.csv
  id               INTEGER PK AUTOINCREMENT
  cnpj             VARCHAR
  id_documento     INTEGER  (FK to documentos.id_doc)
  data_referencia  VARCHAR
  versao           INTEGER
  nome_companhia   VARCHAR
  acionista        VARCHAR  (shareholder name)
  cpf_cnpj_acionista VARCHAR
  tipo_pessoa      VARCHAR  (PF/PJ)
  nacionalidade    VARCHAR
  acionista_controlador VARCHAR  (S/N)
  participante_acordo_acionistas VARCHAR  (S/N)
  pct_on           REAL     (% ordinary shares)
  pct_pn           REAL     (% preferred shares)
  pct_total        REAL     (% total shares)
  qtd_on           INTEGER
  qtd_pn           INTEGER
  qtd_total        INTEGER
  UNIQUE(id_documento, cpf_cnpj_acionista)

TABLE: distribuicao_capital  <- from fre_cia_aberta_distribuicao_capital_{year}.csv
  id               INTEGER PK AUTOINCREMENT
  cnpj             VARCHAR
  id_documento     INTEGER
  data_referencia  VARCHAR
  versao           INTEGER
  nome_companhia   VARCHAR
  pct_on_circulacao     REAL  (% ON shares in float)
  pct_pn_circulacao     REAL  (% PN shares in float)
  pct_total_circulacao  REAL  (% total in float)
  qtd_on_circulacao     INTEGER
  qtd_pn_circulacao     INTEGER
  qtd_total_circulacao  INTEGER
  qtd_acionistas_pf     INTEGER  (# retail shareholders)
  qtd_acionistas_pj     INTEGER  (# institutional shareholders)
  qtd_acionistas_inst   INTEGER  (# institutional investors specifically)
  data_ultima_assembleia VARCHAR
  UNIQUE(id_documento)

TABLE: remuneracao_orgao  <- from fre_cia_aberta_remuneracao_total_orgao_{year}.csv
  id               INTEGER PK AUTOINCREMENT
  cnpj             VARCHAR
  id_documento     INTEGER
  data_referencia  VARCHAR
  versao           INTEGER
  nome_companhia   VARCHAR
  orgao            VARCHAR  (board/committee name)
  dt_ini_exercicio VARCHAR
  dt_fim_exercicio VARCHAR
  num_membros      REAL
  num_membros_remunerados REAL
  salario          REAL
  beneficios       REAL
  bonus            REAL
  participacao_resultados REAL
  baseada_acoes    REAL
  total_remuneracao REAL
  total_remuneracao_orgao REAL
  UNIQUE(id_documento, orgao, dt_ini_exercicio)

TABLE: capital_social  <- from fre_cia_aberta_capital_social_{year}.csv
  id               INTEGER PK AUTOINCREMENT
  cnpj             VARCHAR
  id_documento     INTEGER
  data_referencia  VARCHAR
  versao           INTEGER
  nome_companhia   VARCHAR
  tipo_capital     VARCHAR  (Subscrito/Integralizado)
  valor_capital    REAL     (BRL)
  qtd_acoes_on     INTEGER
  qtd_acoes_pn     INTEGER
  qtd_acoes_total  INTEGER
  data_aprovacao   VARCHAR
  UNIQUE(id_documento, tipo_capital)

TABLE: sync_state
  year             INTEGER PRIMARY KEY
  synced_at        TEXT
  rows_documentos  INTEGER
  rows_posicao     INTEGER
  rows_distrib     INTEGER
  rows_remuneracao INTEGER
  rows_capital     INTEGER
  duration_s       REAL

=== DECISION: ID_DOC as primary key for documentos ===
CVM assigns globally unique ID_DOC per filing. Using it as PK (not
AUTOINCREMENT) means re-syncing is idempotent -- same doc always maps to
same id. Section tables FK via id_documento -> documentos.id_doc.
ON CONFLICT(id_doc) DO UPDATE handles version corrections (VERSAO > 1).

=== DECISION: UNIQUE on section tables ===
Each section uses a natural dedup key (id_documento + discriminator).
This prevents duplicates from overlapping yearly ZIPs without requiring
a full delete-reload cycle. Same pattern as cvm_ipe_sync.py.
"""

from __future__ import annotations

import csv
import io
import os
import re
import sqlite3
import sys
import time
import zipfile
from datetime import datetime
from pathlib import Path


# ── Constants ─────────────────────────────────────────────────────────────────

CVM_BASE   = "https://dados.cvm.gov.br/dados/CIA_ABERTA/DOC/FRE/DADOS"
FIRST_YEAR = 2010   # FRE structured data available from 2010


# ── DB helpers ────────────────────────────────────────────────────────────────

def _fre_db_path() -> Path:
    """
    Resolve fre.db path. Checks MEMORY_ROOT env var first, then walks up
    from this file looking for memory_db/cvm/. Same pattern as cvm_ipe_sync.py.
    """
    memory_root = os.getenv("MEMORY_ROOT", "")
    if memory_root:
        return Path(memory_root) / "cvm" / "fre.db"
    here = Path(__file__).resolve().parent
    for _ in range(6):
        candidate = here / "memory_db" / "cvm" / "fre.db"
        if candidate.parent.exists():
            return candidate
        here = here.parent
    raise FileNotFoundError("Cannot locate memory_db/cvm/. Set MEMORY_ROOT in .env.")


def _connect_fre(read_only: bool = False) -> sqlite3.Connection:
    path = _fre_db_path()
    if read_only and not path.exists():
        raise FileNotFoundError(
            f"fre.db not found at {path}. Run sync() first."
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(
        f"file:{path}?mode=ro" if read_only else str(path),
        uri=read_only,
    )
    conn.row_factory = sqlite3.Row
    if not read_only:
        _ensure_schema(conn)
    return conn


def _ensure_schema(conn: sqlite3.Connection) -> None:
    """
    Create all tables. Idempotent via IF NOT EXISTS.
    Schema matches CVM column names documented in meta_fre_cia_aberta.zip.
    """
    conn.executescript("""
        -- Filing index: one row per FRE document filed with CVM
        -- id_doc is CVM's own globally-unique document ID -- used as PK
        -- so re-syncing is always safe (no orphan rows, no AUTOINCREMENT drift)
        CREATE TABLE IF NOT EXISTS documentos (
            id_doc       INTEGER PRIMARY KEY,
            cnpj         VARCHAR NOT NULL,
            cd_cvm       INTEGER DEFAULT 0,
            nome         VARCHAR,
            categ_doc    VARCHAR,
            dt_receb     VARCHAR,
            dt_refer     VARCHAR,
            versao       INTEGER DEFAULT 1,
            link_doc     VARCHAR,
            ano_origem   INTEGER
        );
        CREATE INDEX IF NOT EXISTS idx_fre_doc_cnpj    ON documentos(cnpj);
        CREATE INDEX IF NOT EXISTS idx_fre_doc_cd_cvm  ON documentos(cd_cvm);
        CREATE INDEX IF NOT EXISTS idx_fre_doc_dt_receb ON documentos(dt_receb);

        -- Shareholder structure: % ON/PN/Total per named shareholder
        -- Dedup: one row per (documento, shareholder CPF/CNPJ)
        -- Note: cpf_cnpj_acionista may be blank for foreign shareholders
        CREATE TABLE IF NOT EXISTS posicao_acionaria (
            id                       INTEGER PRIMARY KEY AUTOINCREMENT,
            cnpj                     VARCHAR NOT NULL,
            id_documento             INTEGER NOT NULL,
            data_referencia          VARCHAR,
            versao                   INTEGER,
            nome_companhia           VARCHAR,
            acionista                VARCHAR,
            cpf_cnpj_acionista       VARCHAR,
            tipo_pessoa              VARCHAR,
            nacionalidade            VARCHAR,
            acionista_controlador    VARCHAR,
            participante_acordo_acionistas VARCHAR,
            pct_on                   REAL,
            pct_pn                   REAL,
            pct_total                REAL,
            qtd_on                   INTEGER,
            qtd_pn                   INTEGER,
            qtd_total                INTEGER,
            UNIQUE(id_documento, cpf_cnpj_acionista, acionista)
        );
        CREATE INDEX IF NOT EXISTS idx_fre_pa_cnpj      ON posicao_acionaria(cnpj);
        CREATE INDEX IF NOT EXISTS idx_fre_pa_id_doc    ON posicao_acionaria(id_documento);

        -- Capital distribution: free float percentages + shareholder counts
        -- One row per documento (aggregate, not per-shareholder)
        CREATE TABLE IF NOT EXISTS distribuicao_capital (
            id                         INTEGER PRIMARY KEY AUTOINCREMENT,
            cnpj                       VARCHAR NOT NULL,
            id_documento               INTEGER NOT NULL,
            data_referencia            VARCHAR,
            versao                     INTEGER,
            nome_companhia             VARCHAR,
            pct_on_circulacao          REAL,
            pct_pn_circulacao          REAL,
            pct_total_circulacao       REAL,
            qtd_on_circulacao          INTEGER,
            qtd_pn_circulacao          INTEGER,
            qtd_total_circulacao       INTEGER,
            qtd_acionistas_pf          INTEGER,
            qtd_acionistas_pj          INTEGER,
            qtd_acionistas_inst        INTEGER,
            data_ultima_assembleia     VARCHAR,
            UNIQUE(id_documento)
        );
        CREATE INDEX IF NOT EXISTS idx_fre_dc_cnpj   ON distribuicao_capital(cnpj);

        -- Board/exec compensation: per-organ totals
        -- Organs: Diretoria Estatutaria, Conselho de Administracao, etc.
        -- UNIQUE on (documento, orgao, period) -- some docs have 3 years of history
        CREATE TABLE IF NOT EXISTS remuneracao_orgao (
            id                      INTEGER PRIMARY KEY AUTOINCREMENT,
            cnpj                    VARCHAR NOT NULL,
            id_documento            INTEGER NOT NULL,
            data_referencia         VARCHAR,
            versao                  INTEGER,
            nome_companhia          VARCHAR,
            orgao                   VARCHAR,
            dt_ini_exercicio        VARCHAR,
            dt_fim_exercicio        VARCHAR,
            num_membros             REAL,
            num_membros_remunerados REAL,
            salario                 REAL,
            beneficios              REAL,
            bonus                   REAL,
            participacao_resultados REAL,
            baseada_acoes           REAL,
            total_remuneracao       REAL,
            total_remuneracao_orgao REAL,
            UNIQUE(id_documento, orgao, dt_ini_exercicio)
        );
        CREATE INDEX IF NOT EXISTS idx_fre_rem_cnpj  ON remuneracao_orgao(cnpj);

        -- Capital structure: subscribed/paid-in capital + share counts
        -- tipo_capital distinguishes Subscrito vs Integralizado rows
        CREATE TABLE IF NOT EXISTS capital_social (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            cnpj             VARCHAR NOT NULL,
            id_documento     INTEGER NOT NULL,
            data_referencia  VARCHAR,
            versao           INTEGER,
            nome_companhia   VARCHAR,
            tipo_capital     VARCHAR,
            valor_capital    REAL,
            qtd_acoes_on     INTEGER,
            qtd_acoes_pn     INTEGER,
            qtd_acoes_total  INTEGER,
            data_aprovacao   VARCHAR,
            UNIQUE(id_documento, tipo_capital)
        );
        CREATE INDEX IF NOT EXISTS idx_fre_cap_cnpj  ON capital_social(cnpj);

        -- Tracks which years have been synced + row counts per table
        CREATE TABLE IF NOT EXISTS sync_state (
            year             INTEGER PRIMARY KEY,
            synced_at        TEXT NOT NULL,
            rows_documentos  INTEGER DEFAULT 0,
            rows_posicao     INTEGER DEFAULT 0,
            rows_distrib     INTEGER DEFAULT 0,
            rows_remuneracao INTEGER DEFAULT 0,
            rows_capital     INTEGER DEFAULT 0,
            duration_s       REAL DEFAULT 0
        );
    """)
    conn.commit()


# ── CNPJ normalization ────────────────────────────────────────────────────────

def _cnpj_digits(raw: str) -> str:
    """Strip formatting from CNPJ/CPF. Returns digits only, or '' if invalid."""
    digits = re.sub(r"\D", "", str(raw or ""))
    # CNPJ = 14 digits, CPF = 11 digits -- both valid in shareholder fields
    return digits if len(digits) in (11, 14) else digits


def _safe_float(val: str) -> float | None:
    """Parse numeric string from CVM CSVs. Returns None on blank/invalid."""
    if not val or not val.strip():
        return None
    try:
        # CVM uses period as decimal separator (standard CSV)
        return float(val.replace(",", ".").strip())
    except (ValueError, TypeError):
        return None


def _safe_int(val: str) -> int | None:
    """Parse integer string. Returns None on blank/invalid."""
    f = _safe_float(val)
    if f is None:
        return None
    return int(f)


# ── URL builder ───────────────────────────────────────────────────────────────

def url_for(year: int) -> str:
    """
    Build CVM FRE download URL for a given year.
    Pattern: .../FRE/DADOS/fre_cia_aberta_{year}.zip
    """
    return f"{CVM_BASE}/fre_cia_aberta_{year}.zip"


# ── Download ──────────────────────────────────────────────────────────────────

def download_zip(url: str, timeout: int = 120) -> bytes:
    """
    Download a FRE ZIP. Timeout is 120s (FRE ZIPs are 15-50MB, much larger
    than IPE's ~5MB). Uses httpx with follow_redirects=True.
    """
    import httpx
    print(f"[fre_sync] Downloading {url} ...", file=sys.stderr)
    t0   = time.time()
    resp = httpx.get(url, timeout=timeout, follow_redirects=True)
    resp.raise_for_status()
    elapsed = round(time.time() - t0, 1)
    print(f"[fre_sync] Downloaded {len(resp.content):,} bytes in {elapsed}s",
          file=sys.stderr)
    return resp.content


# ── CSV reader helper ─────────────────────────────────────────────────────────

def _read_csv_from_zip(zf: zipfile.ZipFile, name: str) -> list[dict]:
    """
    Read a CSV from an open ZipFile. Tries utf-8-sig, utf-8, latin-1, cp1252.
    Returns list of row dicts. Returns [] if file not in ZIP (graceful --
    older years may be missing some section CSVs).
    """
    if name not in zf.namelist():
        print(f"[fre_sync]   SKIP {name} (not in ZIP)", file=sys.stderr)
        return []

    raw_bytes = zf.read(name)
    content   = None
    for enc in ("utf-8-sig", "utf-8", "latin-1", "cp1252"):
        try:
            content = raw_bytes.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    if content is None:
        content = raw_bytes.decode("latin-1", errors="replace")

    reader = csv.DictReader(io.StringIO(content), delimiter=";")
    rows   = list(reader)
    print(f"[fre_sync]   {name}: {len(rows):,} rows", file=sys.stderr)
    return rows


# ── Section parsers ───────────────────────────────────────────────────────────

def _parse_documentos(rows: list[dict], year: int) -> list[dict]:
    """
    Parse fre_cia_aberta_{year}.csv -> documentos table.
    Columns (from meta_fre_cia_aberta.txt):
      CATEG_DOC, CD_CVM, CNPJ_CIA, DENOM_CIA, DT_RECEB, DT_REFER,
      ID_DOC, LINK_DOC, VERSAO
    """
    out = []
    for row in rows:
        id_doc = _safe_int(row.get("ID_DOC", ""))
        cnpj   = _cnpj_digits(row.get("CNPJ_CIA", ""))
        if not id_doc or not cnpj:
            continue
        out.append({
            "id_doc":    id_doc,
            "cnpj":      cnpj,
            "cd_cvm":    _safe_int(row.get("CD_CVM", "")) or 0,
            "nome":      row.get("DENOM_CIA", "").strip(),
            "categ_doc": row.get("CATEG_DOC", "").strip(),
            "dt_receb":  row.get("DT_RECEB", "").strip(),
            "dt_refer":  row.get("DT_REFER", "").strip(),
            "versao":    _safe_int(row.get("VERSAO", "")) or 1,
            "link_doc":  row.get("LINK_DOC", "").strip(),
            "ano_origem": year,
        })
    return out


def _parse_posicao_acionaria(rows: list[dict]) -> list[dict]:
    """
    Parse fre_cia_aberta_posicao_acionaria_{year}.csv.
    Key columns (from meta_fre_cia_aberta_posicao_acionaria.txt):
      CNPJ_Companhia, ID_Documento, Data_Referencia, Versao, Nome_Companhia,
      Acionista, CPF_CNPJ_Acionista, Tipo_Pessoa_Acionista, Nacionalidade,
      Acionista_Controlador, Participante_Acordo_Acionistas,
      Percentual_Acao_Ordinaria_Circulacao, Percentual_Acao_Preferencial_Circulacao,
      Percentual_Total_Acoes_Circulacao,
      Quantidade_Acao_Ordinaria_Circulacao, Quantidade_Acao_Preferencial_Circulacao,
      Quantidade_Total_Acoes_Circulacao
    """
    out = []
    for row in rows:
        id_doc = _safe_int(row.get("ID_Documento", ""))
        cnpj   = _cnpj_digits(row.get("CNPJ_Companhia", ""))
        if not id_doc:
            continue
        out.append({
            "cnpj":                         cnpj,
            "id_documento":                 id_doc,
            "data_referencia":              row.get("Data_Referencia", "").strip(),
            "versao":                       _safe_int(row.get("Versao", "")) or 1,
            "nome_companhia":               row.get("Nome_Companhia", "").strip(),
            "acionista":                    row.get("Acionista", "").strip(),
            "cpf_cnpj_acionista":           _cnpj_digits(row.get("CPF_CNPJ_Acionista", "")),
            "tipo_pessoa":                  row.get("Tipo_Pessoa_Acionista", "").strip(),
            "nacionalidade":                row.get("Nacionalidade", "").strip(),
            "acionista_controlador":        row.get("Acionista_Controlador", "").strip(),
            "participante_acordo_acionistas": row.get("Participante_Acordo_Acionistas", "").strip(),
            "pct_on":   _safe_float(row.get("Percentual_Acao_Ordinaria_Circulacao", "")),
            "pct_pn":   _safe_float(row.get("Percentual_Acao_Preferencial_Circulacao", "")),
            "pct_total":_safe_float(row.get("Percentual_Total_Acoes_Circulacao", "")),
            "qtd_on":   _safe_int(row.get("Quantidade_Acao_Ordinaria_Circulacao", "")),
            "qtd_pn":   _safe_int(row.get("Quantidade_Acao_Preferencial_Circulacao", "")),
            "qtd_total":_safe_int(row.get("Quantidade_Total_Acoes_Circulacao", "")),
        })
    return out


def _parse_distribuicao_capital(rows: list[dict]) -> list[dict]:
    """
    Parse fre_cia_aberta_distribuicao_capital_{year}.csv.
    Key columns (from meta_fre_cia_aberta_distribuicao_capital.txt):
      CNPJ_Companhia, ID_Documento, Data_Referencia, Versao, Nome_Companhia,
      Percentual_Acoes_Ordinarias_Circulacao, Percentual_Acoes_Preferenciais_Circulacao,
      Percentual_Total_Acoes_Circulacao,
      Quantidade_Acoes_Ordinarias_Circulacao, Quantidade_Acoes_Preferenciais_Circulacao,
      Quantidade_Total_Acoes_Circulacao,
      Quantidade_Acionistas_PF, Quantidade_Acionistas_PJ,
      Quantidade_Acionistas_Investidores_Institucionais,
      Data_Ultima_Assembleia
    """
    out = []
    for row in rows:
        id_doc = _safe_int(row.get("ID_Documento", ""))
        cnpj   = _cnpj_digits(row.get("CNPJ_Companhia", ""))
        if not id_doc:
            continue
        out.append({
            "cnpj":                  cnpj,
            "id_documento":          id_doc,
            "data_referencia":       row.get("Data_Referencia", "").strip(),
            "versao":                _safe_int(row.get("Versao", "")) or 1,
            "nome_companhia":        row.get("Nome_Companhia", "").strip(),
            "pct_on_circulacao":     _safe_float(row.get("Percentual_Acoes_Ordinarias_Circulacao", "")),
            "pct_pn_circulacao":     _safe_float(row.get("Percentual_Acoes_Preferenciais_Circulacao", "")),
            "pct_total_circulacao":  _safe_float(row.get("Percentual_Total_Acoes_Circulacao", "")),
            "qtd_on_circulacao":     _safe_int(row.get("Quantidade_Acoes_Ordinarias_Circulacao", "")),
            "qtd_pn_circulacao":     _safe_int(row.get("Quantidade_Acoes_Preferenciais_Circulacao", "")),
            "qtd_total_circulacao":  _safe_int(row.get("Quantidade_Total_Acoes_Circulacao", "")),
            "qtd_acionistas_pf":     _safe_int(row.get("Quantidade_Acionistas_PF", "")),
            "qtd_acionistas_pj":     _safe_int(row.get("Quantidade_Acionistas_PJ", "")),
            "qtd_acionistas_inst":   _safe_int(row.get("Quantidade_Acionistas_Investidores_Institucionais", "")),
            "data_ultima_assembleia":row.get("Data_Ultima_Assembleia", "").strip(),
        })
    return out


def _parse_remuneracao_orgao(rows: list[dict]) -> list[dict]:
    """
    Parse fre_cia_aberta_remuneracao_total_orgao_{year}.csv.
    Key columns (from meta_fre_cia_aberta_remuneracao_total_orgao.txt):
      CNPJ_Companhia, ID_Documento, Data_Referencia, Versao, Nome_Companhia,
      Orgao_Administracao, Data_Inicio_Exercicio_Social, Data_Fim_Exercicio_Social,
      Numero_Membros, Numero_Membros_Remunerados,
      Salario, Beneficios_Diretos_Indiretos, Bonus,
      Participacao_Resultados, Baseada_Acoes,
      Total_Remuneracao, Total_Remuneracao_Orgao
    """
    out = []
    for row in rows:
        id_doc = _safe_int(row.get("ID_Documento", ""))
        cnpj   = _cnpj_digits(row.get("CNPJ_Companhia", ""))
        if not id_doc:
            continue
        out.append({
            "cnpj":                    cnpj,
            "id_documento":            id_doc,
            "data_referencia":         row.get("Data_Referencia", "").strip(),
            "versao":                  _safe_int(row.get("Versao", "")) or 1,
            "nome_companhia":          row.get("Nome_Companhia", "").strip(),
            "orgao":                   row.get("Orgao_Administracao", "").strip(),
            "dt_ini_exercicio":        row.get("Data_Inicio_Exercicio_Social", "").strip(),
            "dt_fim_exercicio":        row.get("Data_Fim_Exercicio_Social", "").strip(),
            "num_membros":             _safe_float(row.get("Numero_Membros", "")),
            "num_membros_remunerados": _safe_float(row.get("Numero_Membros_Remunerados", "")),
            "salario":                 _safe_float(row.get("Salario", "")),
            "beneficios":              _safe_float(row.get("Beneficios_Diretos_Indiretos", "")),
            "bonus":                   _safe_float(row.get("Bonus", "")),
            "participacao_resultados": _safe_float(row.get("Participacao_Resultados", "")),
            "baseada_acoes":           _safe_float(row.get("Baseada_Acoes", "")),
            "total_remuneracao":       _safe_float(row.get("Total_Remuneracao", "")),
            "total_remuneracao_orgao": _safe_float(row.get("Total_Remuneracao_Orgao", "")),
        })
    return out


def _parse_capital_social(rows: list[dict]) -> list[dict]:
    """
    Parse fre_cia_aberta_capital_social_{year}.csv.
    Key columns (from meta_fre_cia_aberta_capital_social.txt):
      CNPJ_Companhia, ID_Documento, Data_Referencia, Versao, Nome_Companhia,
      Tipo_Capital, Valor_Capital,
      Quantidade_Acoes_Ordinarias, Quantidade_Acoes_Preferenciais,
      Quantidade_Total_Acoes, Data_Autorizacao_Aprovacao
    """
    out = []
    for row in rows:
        id_doc = _safe_int(row.get("ID_Documento", ""))
        cnpj   = _cnpj_digits(row.get("CNPJ_Companhia", ""))
        if not id_doc:
            continue
        out.append({
            "cnpj":            cnpj,
            "id_documento":    id_doc,
            "data_referencia": row.get("Data_Referencia", "").strip(),
            "versao":          _safe_int(row.get("Versao", "")) or 1,
            "nome_companhia":  row.get("Nome_Companhia", "").strip(),
            "tipo_capital":    row.get("Tipo_Capital", "").strip(),
            "valor_capital":   _safe_float(row.get("Valor_Capital", "")),
            "qtd_acoes_on":    _safe_int(row.get("Quantidade_Acoes_Ordinarias", "")),
            "qtd_acoes_pn":    _safe_int(row.get("Quantidade_Acoes_Preferenciais", "")),
            "qtd_acoes_total": _safe_int(row.get("Quantidade_Total_Acoes", "")),
            "data_aprovacao":  row.get("Data_Autorizacao_Aprovacao", "").strip(),
        })
    return out


# ── Parse dispatcher ──────────────────────────────────────────────────────────

def parse_zip(raw_bytes: bytes, year: int) -> dict:
    """
    Parse FRE ZIP for a given year. Returns dict of parsed rows per table.

    DECISION: We only import 5 of the ~20+ CSVs in the ZIP.
    The others (auditors, board bios, related-party narratives, etc.) are
    text-heavy and not useful for programmatic financial queries.
    They remain accessible via documentos.link_doc for full document download.

    Returns:
      {
        "documentos":           list[dict],
        "posicao_acionaria":    list[dict],
        "distribuicao_capital": list[dict],
        "remuneracao_orgao":    list[dict],
        "capital_social":       list[dict],
      }
    """
    if raw_bytes[:2] != b"PK":
        raise ValueError(f"Expected ZIP magic PK, got: {raw_bytes[:4]!r}")

    zf = zipfile.ZipFile(io.BytesIO(raw_bytes))
    print(f"[fre_sync] ZIP contains {len(zf.namelist())} files", file=sys.stderr)

    # DECISION: CSV names follow pattern fre_cia_aberta[_section]_{year}.csv
    # The main index has no section suffix.
    suffix = f"_{year}.csv"

    def _name(section: str = "") -> str:
        """Build expected CSV filename within ZIP."""
        if section:
            return f"fre_cia_aberta_{section}{suffix}"
        return f"fre_cia_aberta{suffix}"

    doc_rows   = _read_csv_from_zip(zf, _name())
    pa_rows    = _read_csv_from_zip(zf, _name("posicao_acionaria"))
    dc_rows    = _read_csv_from_zip(zf, _name("distribuicao_capital"))
    rem_rows   = _read_csv_from_zip(zf, _name("remuneracao_total_orgao"))
    cap_rows   = _read_csv_from_zip(zf, _name("capital_social"))

    return {
        "documentos":           _parse_documentos(doc_rows, year),
        "posicao_acionaria":    _parse_posicao_acionaria(pa_rows),
        "distribuicao_capital": _parse_distribuicao_capital(dc_rows),
        "remuneracao_orgao":    _parse_remuneracao_orgao(rem_rows),
        "capital_social":       _parse_capital_social(cap_rows),
    }


# ── Upsert helpers ────────────────────────────────────────────────────────────

def _upsert_documentos(conn: sqlite3.Connection, rows: list[dict]) -> int:
    """
    Upsert filing index. ON CONFLICT(id_doc) DO UPDATE so version corrections
    (higher VERSAO) overwrite older entries correctly.
    """
    if not rows:
        return 0
    sql = """
        INSERT INTO documentos
            (id_doc, cnpj, cd_cvm, nome, categ_doc, dt_receb, dt_refer,
             versao, link_doc, ano_origem)
        VALUES (?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(id_doc) DO UPDATE SET
            versao    = MAX(versao, excluded.versao),
            link_doc  = excluded.link_doc,
            dt_receb  = excluded.dt_receb,
            ano_origem= excluded.ano_origem
    """
    conn.executemany(sql, [
        (r["id_doc"], r["cnpj"], r["cd_cvm"], r["nome"], r["categ_doc"],
         r["dt_receb"], r["dt_refer"], r["versao"], r["link_doc"], r["ano_origem"])
        for r in rows
    ])
    conn.commit()
    return len(rows)


def _upsert_posicao(conn: sqlite3.Connection, rows: list[dict]) -> int:
    if not rows:
        return 0
    sql = """
        INSERT INTO posicao_acionaria
            (cnpj, id_documento, data_referencia, versao, nome_companhia,
             acionista, cpf_cnpj_acionista, tipo_pessoa, nacionalidade,
             acionista_controlador, participante_acordo_acionistas,
             pct_on, pct_pn, pct_total, qtd_on, qtd_pn, qtd_total)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(id_documento, cpf_cnpj_acionista, acionista) DO UPDATE SET
            pct_on    = excluded.pct_on,
            pct_pn    = excluded.pct_pn,
            pct_total = excluded.pct_total,
            qtd_on    = excluded.qtd_on,
            qtd_pn    = excluded.qtd_pn,
            qtd_total = excluded.qtd_total,
            versao    = MAX(versao, excluded.versao)
    """
    batch_size = 5_000
    total = 0
    for i in range(0, len(rows), batch_size):
        batch = rows[i:i + batch_size]
        conn.executemany(sql, [
            (r["cnpj"], r["id_documento"], r["data_referencia"], r["versao"],
             r["nome_companhia"], r["acionista"], r["cpf_cnpj_acionista"],
             r["tipo_pessoa"], r["nacionalidade"], r["acionista_controlador"],
             r["participante_acordo_acionistas"],
             r["pct_on"], r["pct_pn"], r["pct_total"],
             r["qtd_on"], r["qtd_pn"], r["qtd_total"])
            for r in batch
        ])
        total += len(batch)
    conn.commit()
    return total


def _upsert_distribuicao(conn: sqlite3.Connection, rows: list[dict]) -> int:
    if not rows:
        return 0
    sql = """
        INSERT INTO distribuicao_capital
            (cnpj, id_documento, data_referencia, versao, nome_companhia,
             pct_on_circulacao, pct_pn_circulacao, pct_total_circulacao,
             qtd_on_circulacao, qtd_pn_circulacao, qtd_total_circulacao,
             qtd_acionistas_pf, qtd_acionistas_pj, qtd_acionistas_inst,
             data_ultima_assembleia)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(id_documento) DO UPDATE SET
            pct_total_circulacao = excluded.pct_total_circulacao,
            qtd_acionistas_pf    = excluded.qtd_acionistas_pf,
            qtd_acionistas_pj    = excluded.qtd_acionistas_pj,
            versao               = MAX(versao, excluded.versao)
    """
    conn.executemany(sql, [
        (r["cnpj"], r["id_documento"], r["data_referencia"], r["versao"],
         r["nome_companhia"],
         r["pct_on_circulacao"], r["pct_pn_circulacao"], r["pct_total_circulacao"],
         r["qtd_on_circulacao"], r["qtd_pn_circulacao"], r["qtd_total_circulacao"],
         r["qtd_acionistas_pf"], r["qtd_acionistas_pj"], r["qtd_acionistas_inst"],
         r["data_ultima_assembleia"])
        for r in rows
    ])
    conn.commit()
    return len(rows)


def _upsert_remuneracao(conn: sqlite3.Connection, rows: list[dict]) -> int:
    if not rows:
        return 0
    sql = """
        INSERT INTO remuneracao_orgao
            (cnpj, id_documento, data_referencia, versao, nome_companhia,
             orgao, dt_ini_exercicio, dt_fim_exercicio,
             num_membros, num_membros_remunerados,
             salario, beneficios, bonus, participacao_resultados,
             baseada_acoes, total_remuneracao, total_remuneracao_orgao)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(id_documento, orgao, dt_ini_exercicio) DO UPDATE SET
            total_remuneracao_orgao = excluded.total_remuneracao_orgao,
            versao = MAX(versao, excluded.versao)
    """
    conn.executemany(sql, [
        (r["cnpj"], r["id_documento"], r["data_referencia"], r["versao"],
         r["nome_companhia"], r["orgao"], r["dt_ini_exercicio"], r["dt_fim_exercicio"],
         r["num_membros"], r["num_membros_remunerados"],
         r["salario"], r["beneficios"], r["bonus"],
         r["participacao_resultados"], r["baseada_acoes"],
         r["total_remuneracao"], r["total_remuneracao_orgao"])
        for r in rows
    ])
    conn.commit()
    return len(rows)


def _upsert_capital(conn: sqlite3.Connection, rows: list[dict]) -> int:
    if not rows:
        return 0
    sql = """
        INSERT INTO capital_social
            (cnpj, id_documento, data_referencia, versao, nome_companhia,
             tipo_capital, valor_capital,
             qtd_acoes_on, qtd_acoes_pn, qtd_acoes_total, data_aprovacao)
        VALUES (?,?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(id_documento, tipo_capital) DO UPDATE SET
            valor_capital  = excluded.valor_capital,
            qtd_acoes_total= excluded.qtd_acoes_total,
            versao         = MAX(versao, excluded.versao)
    """
    conn.executemany(sql, [
        (r["cnpj"], r["id_documento"], r["data_referencia"], r["versao"],
         r["nome_companhia"], r["tipo_capital"], r["valor_capital"],
         r["qtd_acoes_on"], r["qtd_acoes_pn"], r["qtd_acoes_total"],
         r["data_aprovacao"])
        for r in rows
    ])
    conn.commit()
    return len(rows)


# ── Public: sync ──────────────────────────────────────────────────────────────

def sync(
    years:        list[int] = None,
    full_history: bool      = False,
    force:        bool      = False,
) -> dict:
    """
    Download and import CVM FRE data into fre.db.

    Args:
        years:        Specific years. Default: current + prior year.
        full_history: All years from 2010. ~500MB+ download, 10-20 min.
        force:        Re-download even if already synced.

    TYPICAL USAGE:
        sync()                        # current + prior year (~30-60s)
        sync(years=[2022,2023,2024])  # specific years
        sync(full_history=True)       # all history (~15 min)

    NOTE: FRE ZIPs are 15-50MB each (vs IPE's ~5MB). Full history download
    is a serious commitment -- run overnight if syncing from 2010.
    """
    current_year = datetime.now().year

    if full_history:
        years = list(range(FIRST_YEAR, current_year + 1))
    elif years:
        years = [int(y) for y in years]
    else:
        years = [current_year - 1, current_year]

    print(f"[fre_sync] Syncing FRE for years: {years}", file=sys.stderr)

    try:
        conn = _connect_fre(read_only=False)
    except FileNotFoundError as e:
        return {"status": "error", "error": str(e)}

    t0_total     = time.time()
    years_synced = []
    years_skipped= []
    errors       = []
    totals       = {k: 0 for k in ("documentos", "posicao_acionaria",
                                    "distribuicao_capital", "remuneracao_orgao",
                                    "capital_social")}

    for year in sorted(years):
        if not force:
            existing = conn.execute(
                "SELECT synced_at, rows_documentos FROM sync_state WHERE year=?",
                (year,),
            ).fetchone()
            if existing:
                print(
                    f"[fre_sync] SKIP FRE {year} "
                    f"(synced {existing['synced_at']}, "
                    f"{existing['rows_documentos']:,} docs). "
                    "Use force=True to re-sync.",
                    file=sys.stderr,
                )
                years_skipped.append(year)
                continue

        t0 = time.time()
        try:
            raw    = download_zip(url_for(year))
            parsed = parse_zip(raw, year)

            n_doc  = _upsert_documentos(conn, parsed["documentos"])
            n_pa   = _upsert_posicao(conn,    parsed["posicao_acionaria"])
            n_dc   = _upsert_distribuicao(conn, parsed["distribuicao_capital"])
            n_rem  = _upsert_remuneracao(conn, parsed["remuneracao_orgao"])
            n_cap  = _upsert_capital(conn,    parsed["capital_social"])

            duration = round(time.time() - t0, 1)

            conn.execute("""
                INSERT OR REPLACE INTO sync_state
                    (year, synced_at, rows_documentos, rows_posicao,
                     rows_distrib, rows_remuneracao, rows_capital, duration_s)
                VALUES (?,?,?,?,?,?,?,?)
            """, (year, datetime.utcnow().isoformat(),
                  n_doc, n_pa, n_dc, n_rem, n_cap, duration))
            conn.commit()

            for k, v in zip(
                ("documentos","posicao_acionaria","distribuicao_capital",
                 "remuneracao_orgao","capital_social"),
                (n_doc, n_pa, n_dc, n_rem, n_cap),
            ):
                totals[k] += v

            years_synced.append(year)
            print(
                f"[fre_sync] FRE {year}: docs={n_doc:,} posicao={n_pa:,} "
                f"distrib={n_dc:,} remuneracao={n_rem:,} capital={n_cap:,} "
                f"in {duration}s",
                file=sys.stderr,
            )

        except Exception as e:
            import traceback
            err = f"FRE {year}: {type(e).__name__}: {e}"
            print(f"[fre_sync] ERROR {err}", file=sys.stderr)
            print(traceback.format_exc(), file=sys.stderr)
            errors.append(err)

    conn.close()

    total_duration = round(time.time() - t0_total, 1)
    status_val     = "success" if not errors else ("partial" if years_synced else "error")

    report = (
        f"=== FRE Sync Complete ===\n"
        f"Years synced   : {years_synced}\n"
        f"Years skipped  : {years_skipped}\n"
        f"documentos     : {totals['documentos']:,}\n"
        f"posicao_acionaria : {totals['posicao_acionaria']:,}\n"
        f"distribuicao_capital : {totals['distribuicao_capital']:,}\n"
        f"remuneracao_orgao : {totals['remuneracao_orgao']:,}\n"
        f"capital_social : {totals['capital_social']:,}\n"
        f"Duration       : {total_duration}s\n"
        f"Errors         : {len(errors)}\n"
    )
    if errors:
        report += "\n".join(f"  {e}" for e in errors)

    print(f"[fre_sync] {report}", file=sys.stderr)
    return {
        "status":        status_val,
        "years_synced":  years_synced,
        "years_skipped": years_skipped,
        "totals":        totals,
        "duration_s":    total_duration,
        "errors":        errors,
        "report":        report,
    }


# ── Public: status ────────────────────────────────────────────────────────────

def status() -> dict:
    """Show fre.db sync status and row counts per table."""
    try:
        conn = _connect_fre(read_only=True)
    except FileNotFoundError:
        return {"status": "not_synced",
                "message": "fre.db not found. Run sync() to populate."}
    try:
        counts = {}
        for tbl in ("documentos", "posicao_acionaria", "distribuicao_capital",
                    "remuneracao_orgao", "capital_social"):
            counts[tbl] = conn.execute(f"SELECT COUNT(*) FROM {tbl}").fetchone()[0]

        synced = conn.execute(
            "SELECT year, synced_at, rows_documentos FROM sync_state ORDER BY year"
        ).fetchall()
        years_list = [r["year"] for r in synced]

        # Date range from documentos
        dr = conn.execute(
            "SELECT MIN(dt_receb), MAX(dt_receb) FROM documentos"
        ).fetchone()

        conn.close()

        report = (
            f"=== FRE DB Status ===\n"
            f"Synced years     : {years_list}\n"
            f"documentos       : {counts['documentos']:,}\n"
            f"posicao_acionaria: {counts['posicao_acionaria']:,}\n"
            f"distribuicao_capital: {counts['distribuicao_capital']:,}\n"
            f"remuneracao_orgao: {counts['remuneracao_orgao']:,}\n"
            f"capital_social   : {counts['capital_social']:,}\n"
            f"Date range       : {dr[0]} to {dr[1]}\n"
        )
        return {
            "status":     "ok",
            "counts":     counts,
            "years":      years_list,
            "date_from":  dr[0],
            "date_to":    dr[1],
            "report":     report,
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}


# ── Public: query ─────────────────────────────────────────────────────────────

def query(
    company:   str  = "",
    section:   str  = "documentos",
    data_from: str  = "",
    data_to:   str  = "",
    limit:     int  = 20,
    cd_cvm:    int  = 0,
) -> dict:
    """
    Query FRE data for a company or date range.

    Args:
        company:   B3 ticker (PETR4), company name fragment, or CNPJ.
                   Resolved via bridge.db if available.
        section:   Which table to query. Options:
                     "documentos"           - filing index (default)
                     "posicao_acionaria"    - shareholder stakes
                     "distribuicao_capital" - free float + shareholder counts
                     "remuneracao_orgao"    - board/exec compensation
                     "capital_social"       - capital + share counts
        data_from: Start date YYYY-MM-DD for dt_receb (documentos) or
                   data_referencia (section tables).
        data_to:   End date YYYY-MM-DD.
        limit:     Max rows. Default: 20.
        cd_cvm:    Direct CD_CVM lookup on documentos table.

    DECISION: Query always resolves company -> cnpj via bridge first, then
    joins to the requested section via id_documento. This means you always
    get consistent company identification regardless of which section you query.
    """
    VALID_SECTIONS = {
        "documentos", "posicao_acionaria", "distribuicao_capital",
        "remuneracao_orgao", "capital_social",
    }
    if section not in VALID_SECTIONS:
        return {"status": "error",
                "error": f"Unknown section '{section}'. Options: {sorted(VALID_SECTIONS)}"}

    try:
        conn = _connect_fre(read_only=True)
    except FileNotFoundError as e:
        return {"status": "error", "error": str(e)}

    try:
        # Resolve company to cnpj
        cnpj_filter = ""
        if company:
            from skills.cvm._bridge import looks_like_ticker, resolve_via_bridge
            from skills.cvm._db import cnpj_digits as _cd

            raw_cnpj = _cd(company)
            if raw_cnpj:
                cnpj_filter = raw_cnpj
            elif looks_like_ticker(company):
                bridge = resolve_via_bridge(company.upper())
                # resolve_via_bridge returns (dfp_itr_ids, name) but we need cnpj
                # Look it up from documentos via cd_cvm from bridge
                from skills.cvm._db import connect_bridge
                bconn = connect_bridge()
                row = bconn.execute(
                    "SELECT cnpj FROM company_map WHERE ticker=? LIMIT 1",
                    (company.upper(),)
                ).fetchone()
                bconn.close()
                if row:
                    cnpj_filter = row["cnpj"]
                else:
                    # Fallback: search by name in documentos
                    cnpj_filter = None
            else:
                cnpj_filter = None  # will use LIKE on nome

        # Build query
        if section == "documentos":
            conditions, params = [], []
            if cnpj_filter:
                conditions.append("cnpj = ?")
                params.append(cnpj_filter)
            elif company and not cnpj_filter:
                conditions.append("upper(nome) LIKE ?")
                params.append(f"%{company.upper()}%")
            if cd_cvm:
                conditions.append("cd_cvm = ?")
                params.append(int(cd_cvm))
            if data_from:
                conditions.append("dt_receb >= ?")
                params.append(data_from)
            if data_to:
                conditions.append("dt_receb <= ?")
                params.append(data_to)
            where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
            rows = conn.execute(
                f"SELECT * FROM documentos {where} ORDER BY dt_receb DESC LIMIT ?",
                params + [limit],
            ).fetchall()

        else:
            # Section tables: resolve cnpj from documentos first
            conditions, params = [], []
            if cnpj_filter:
                conditions.append("s.cnpj = ?")
                params.append(cnpj_filter)
            elif company and not cnpj_filter:
                conditions.append("upper(s.nome_companhia) LIKE ?")
                params.append(f"%{company.upper()}%")
            if data_from:
                conditions.append("s.data_referencia >= ?")
                params.append(data_from)
            if data_to:
                conditions.append("s.data_referencia <= ?")
                params.append(data_to)
            where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
            rows = conn.execute(
                f"SELECT s.* FROM {section} s {where} "
                f"ORDER BY s.data_referencia DESC LIMIT ?",
                params + [limit],
            ).fetchall()

        results = [dict(r) for r in rows]

        if not results:
            return {
                "status": "not_found",
                "count":  0,
                "rows":   [],
                "report": f"No FRE {section} records found for the given filters.",
            }

        # Build human-readable report (first few rows, key fields)
        def _report_line(r: dict) -> str:
            if section == "documentos":
                return (f"{r.get('dt_receb','')}  {r.get('nome','')[:35]:<35}  "
                        f"{r.get('categ_doc','')[:20]:<20}  v{r.get('versao','')}")
            elif section == "posicao_acionaria":
                return (f"{r.get('data_referencia','')}  "
                        f"{r.get('acionista','')[:35]:<35}  "
                        f"total={r.get('pct_total',''):.2f}%")
            elif section == "distribuicao_capital":
                return (f"{r.get('data_referencia','')}  "
                        f"float={r.get('pct_total_circulacao',''):.1f}%  "
                        f"pf={r.get('qtd_acionistas_pf','')}")
            elif section == "remuneracao_orgao":
                return (f"{r.get('dt_fim_exercicio','')}  "
                        f"{r.get('orgao','')[:35]:<35}  "
                        f"total={r.get('total_remuneracao_orgao','')}")
            elif section == "capital_social":
                return (f"{r.get('data_referencia','')}  "
                        f"{r.get('tipo_capital',''):<15}  "
                        f"valor={r.get('valor_capital','')}")
            return str(r)

        report_lines = [
            f"=== FRE {section} ({len(results)} results) ===",
            f"Filters: company={company!r} section={section!r}",
            "",
        ]
        for r in results:
            try:
                report_lines.append(_report_line(r))
            except Exception:
                report_lines.append(str(r))

        return {
            "status": "success",
            "count":  len(results),
            "rows":   results,
            "report": "\n".join(report_lines),
        }

    except Exception as e:
        import traceback
        return {"status": "error", "error": str(e),
                "traceback": traceback.format_exc()}
    finally:
        conn.close()
