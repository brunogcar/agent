"""data_sources/cvm/bridge/isin_fetcher.py -- B3 ISIN ZIP fallback for CNPJ resolution.

FALLBACK ROLE
-------------
The primary bridge path is: ticker -> dividends API (codeCVM) -> CAD (cd_cvm -> CNPJ).
This module provides the FALLBACK when the primary fails:

  ticker -> dividends.db.cash_dividends.isin_code (or instruments.db ISIN)
         -> ISIN ZIP (isin -> cnpj)         <-- this module
         -> CAD (cnpj -> cd_cvm + names)

The ISIN ZIP is downloaded from B3's ISIN service (sistemaswebb3-listados.b3.com.br).
It contains EMISSOR.TXT (issuer_code -> cnpj) + NUMERACA.TXT (isin -> issuer_code),
which join to produce {isin: cnpj} — 300k+ entries covering ALL B3 instruments.

CACHING
-------
The parsed index is cached in memory_db/b3/isin_index.db (SQLite, ~15MB).
A sync_state row tracks the download date. If the cache is < 24h old, the
download is skipped. This avoids re-downloading the 6.9MB ZIP on every lookup.

API CONFIRMED ALIVE 2026-07-23:
  GET /isinProxy/IsinCall/GetTextDownload/  -> JSON {geralPt: {id, dataGeracao}}
  GET /isinProxy/IsinCall/GetFileDownload/{base64(id)}  -> ZIP (PK magic bytes)
  Requires browser-like headers (Referer + Origin) or 403.
"""

from __future__ import annotations

import base64
import csv
import io
import json
import re
import sqlite3
import sys
import zipfile
from datetime import datetime, timedelta
from pathlib import Path

import httpx

from core.tracer import tracer

# ── Constants ────────────────────────────────────────────────────────────────

_B3_BASE = "https://sistemaswebb3-listados.b3.com.br"

_B3_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept":          "application/json, text/plain, */*",
    "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
    "Referer":         "https://sistemaswebb3-listados.b3.com.br/isinPage",
    "Origin":          "https://sistemaswebb3-listados.b3.com.br",
}

# Cache validity: re-download if older than this
_CACHE_TTL_HOURS = 24


def _progress(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


# ── Path ─────────────────────────────────────────────────────────────────────

def _b3_data_dir() -> Path:
    """Return the B3 data directory (shared with dividends, api)."""
    from core.config import cfg
    memory_root = getattr(cfg, "memory_root", None)
    if memory_root:
        d = Path(memory_root) / "b3"
        d.mkdir(parents=True, exist_ok=True)
        return d
    d = Path.cwd() / "memory_db" / "b3"
    d.mkdir(parents=True, exist_ok=True)
    return d


def isin_db_path() -> Path:
    """Return the path to the ISIN index cache database."""
    return _b3_data_dir() / "isin_index.db"


def _connect(read_only: bool = True) -> sqlite3.Connection:
    path = isin_db_path()
    if not path.exists():
        if read_only:
            raise FileNotFoundError(
                f"ISIN index not found at {path}. Run isin_fetcher.sync() first."
            )
        conn = sqlite3.connect(str(path))
    else:
        conn = sqlite3.connect(
            f"file:{path}?mode=ro" if read_only else str(path),
            uri=read_only,
        )
    conn.row_factory = sqlite3.Row
    return conn


def _ensure_schema(conn: sqlite3.Connection) -> None:
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS isin_cnpj (
            isin TEXT PRIMARY KEY,
            cnpj TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_isin_cnpj ON isin_cnpj(cnpj);

        CREATE TABLE IF NOT EXISTS sync_state (
            key         TEXT PRIMARY KEY,
            value       TEXT,
            synced_at   TEXT
        );
    """)
    conn.commit()


# ── Download ─────────────────────────────────────────────────────────────────

def _download_zip() -> bytes:
    """Download the B3 ISIN ZIP. Returns raw bytes.

    Two-step flow:
      1. GET /isinProxy/IsinCall/GetTextDownload/ -> JSON {geralPt: {id: N}}
      2. base64(json.dumps(N)) -> encoded
      3. GET /isinProxy/IsinCall/GetFileDownload/{encoded} -> ZIP bytes
    """
    _progress("[isin] Fetching B3 ISIN file index...")

    # Step 1: get current file ID
    resp = httpx.get(
        f"{_B3_BASE}/isinProxy/IsinCall/GetTextDownload/",
        headers=_B3_HEADERS,
        timeout=30,
        follow_redirects=True,
    )
    resp.raise_for_status()
    index = resp.json()
    file_id = index["geralPt"]["id"]
    gen_date = index["geralPt"].get("dataGeracao", "unknown")
    _progress(f"[isin] B3 ISIN id={file_id} generated={gen_date}")

    # Step 2: encode
    encoded = base64.b64encode(json.dumps(file_id).encode()).decode()

    # Step 3: download ZIP
    _progress(f"[isin] Downloading B3 ISIN ZIP ({encoded})...")
    resp2 = httpx.get(
        f"{_B3_BASE}/isinProxy/IsinCall/GetFileDownload/{encoded}",
        headers=_B3_HEADERS,
        timeout=120,
        follow_redirects=True,
    )
    resp2.raise_for_status()

    raw = resp2.content
    if raw[:2] != b"PK":
        preview = raw[:200].decode("latin-1", errors="replace")
        raise ValueError(
            f"B3 GetFileDownload did not return a ZIP. First 200 bytes: {preview!r}"
        )

    _progress(f"[isin] Downloaded {len(raw):,} bytes")
    return raw


# ── Parse ────────────────────────────────────────────────────────────────────

def _cnpj(raw: str) -> str:
    """Strip non-digits. Return 14-char string or '' if wrong length."""
    if not raw:
        return ""
    digits = re.sub(r"\D", "", str(raw))
    return digits if len(digits) == 14 else ""


def _parse_emissor(raw_bytes: bytes) -> dict[str, str]:
    """Parse EMISSOR.TXT -> {issuer_code: cnpj}. ~67k entries."""
    content = raw_bytes.decode("latin-1", errors="replace")
    result: dict[str, str] = {}
    for line in content.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            cols = [c.strip('"') for c in next(csv.reader([line]))]
        except Exception:
            continue
        if len(cols) < 3:
            continue
        code = cols[0].strip()
        cnpj = _cnpj(cols[2].strip())
        if code and cnpj:
            result[code] = cnpj
    return result


def _parse_numeraca(raw_bytes: bytes, emissor_index: dict[str, str]) -> dict[str, str]:
    """Parse NUMERACA.TXT -> {isin: cnpj}. ~300k entries."""
    content = raw_bytes.decode("latin-1", errors="replace")
    result: dict[str, str] = {}
    for line in content.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            cols = [c.strip('"') for c in next(csv.reader([line]))]
        except Exception:
            continue
        if len(cols) < 4:
            continue
        isin = cols[2].strip()
        issuer_code = cols[3].strip()
        if not isin or len(isin) < 10:
            continue
        cnpj = emissor_index.get(issuer_code, "")
        if cnpj:
            result[isin] = cnpj
    return result


def _parse_zip(raw_bytes: bytes) -> dict[str, str]:
    """Unzip + parse EMISSOR + NUMERACA -> {isin: cnpj}."""
    if raw_bytes[:2] != b"PK":
        raise ValueError(f"Expected ZIP (PK magic), got: {raw_bytes[:4]!r}")

    zf = zipfile.ZipFile(io.BytesIO(raw_bytes))
    names = zf.namelist()
    _progress(f"[isin] ZIP entries: {names}")

    emissor_name = next((n for n in names if "EMISSOR" in n.upper()), None)
    numeraca_name = next((n for n in names if "NUMERACA" in n.upper()), None)

    if not emissor_name:
        raise ValueError(f"EMISSOR.TXT not found in ZIP. Entries: {names}")
    if not numeraca_name:
        raise ValueError(f"NUMERACA.TXT not found in ZIP. Entries: {names}")

    emissor_index = _parse_emissor(zf.read(emissor_name))
    _progress(f"[isin] EMISSOR: {len(emissor_index):,} issuer->cnpj entries")

    isin_cnpj = _parse_numeraca(zf.read(numeraca_name), emissor_index)
    _progress(f"[isin] NUMERACA: {len(isin_cnpj):,} isin->cnpj entries")
    return isin_cnpj


# ── Sync (download + cache) ──────────────────────────────────────────────────

def sync(force: bool = False, trace_id: str = "") -> dict:
    """Download the B3 ISIN ZIP and populate isin_index.db cache.

    Args:
        force: Re-download even if cache is fresh.
        trace_id: Tracer ID.

    Returns:
        Dict with sync status + entry count.
    """
    tid = trace_id or ""
    now = datetime.now()
    now_iso = now.isoformat()

    # Check cache freshness
    if not force and _cache_is_fresh():
        conn = _connect(read_only=True)
        try:
            count = conn.execute("SELECT COUNT(*) as n FROM isin_cnpj").fetchone()["n"]
            return {"status": "skipped", "reason": "cache fresh (<24h)",
                    "entries": count, "synced_at": _get_cache_date()}
        except Exception:
            pass  # cache corrupt, re-download
        finally:
            conn.close()

    tracer.step(tid, "isin_sync", "Downloading B3 ISIN ZIP")

    # Download
    try:
        raw = _download_zip()
    except Exception as e:
        return {"status": "error", "error": f"download failed: {e}"}

    # Parse
    try:
        isin_cnpj = _parse_zip(raw)
    except Exception as e:
        return {"status": "error", "error": f"parse failed: {e}"}

    # Store in isin_index.db
    conn = _connect(read_only=False)
    _ensure_schema(conn)
    try:
        conn.execute("DELETE FROM isin_cnpj")
        # Batch insert
        rows = list(isin_cnpj.items())
        conn.executemany(
            "INSERT INTO isin_cnpj (isin, cnpj) VALUES (?, ?)", rows,
        )
        conn.execute(
            "INSERT OR REPLACE INTO sync_state (key, value, synced_at) "
            "VALUES ('last_sync', ?, ?)",
            (now_iso, now_iso),
        )
        conn.execute(
            "INSERT OR REPLACE INTO sync_state (key, value, synced_at) "
            "VALUES ('entry_count', ?, ?)",
            (str(len(rows)), now_iso),
        )
        conn.commit()
    finally:
        conn.close()

    _progress(f"[isin] Cached {len(isin_cnpj):,} isin->cnpj entries in isin_index.db")
    return {
        "status": "ok", "entries": len(isin_cnpj), "synced_at": now_iso,
    }


def _cache_is_fresh() -> bool:
    """Check if isin_index.db exists and was synced < 24h ago."""
    path = isin_db_path()
    if not path.exists():
        return False
    try:
        conn = _connect(read_only=True)
        row = conn.execute(
            "SELECT value FROM sync_state WHERE key='last_sync'"
        ).fetchone()
        conn.close()
        if not row:
            return False
        last = datetime.fromisoformat(row["value"])
        return (datetime.now() - last) < timedelta(hours=_CACHE_TTL_HOURS)
    except Exception:
        return False


def _get_cache_date() -> str:
    """Return the last sync timestamp from the cache."""
    try:
        conn = _connect(read_only=True)
        row = conn.execute(
            "SELECT value FROM sync_state WHERE key='last_sync'"
        ).fetchone()
        conn.close()
        return row["value"] if row else ""
    except Exception:
        return ""


# ── Lookup ───────────────────────────────────────────────────────────────────

def lookup_isin(isin: str) -> str | None:
    """Look up a single ISIN -> CNPJ. Returns 14-digit CNPJ or None."""
    if not isin:
        return None
    try:
        conn = _connect(read_only=True)
    except FileNotFoundError:
        return None
    try:
        row = conn.execute(
            "SELECT cnpj FROM isin_cnpj WHERE isin=?", (isin.strip().upper(),),
        ).fetchone()
        return row["cnpj"] if row else None
    except Exception:
        return None
    finally:
        conn.close()


def status() -> dict:
    """Show ISIN index cache status."""
    path = isin_db_path()
    if not path.exists():
        return {"status": "not_synced",
                "message": "ISIN index not cached. Run isin_fetcher.sync() first."}
    try:
        conn = _connect(read_only=True)
        count = conn.execute("SELECT COUNT(*) as n FROM isin_cnpj").fetchone()["n"]
        last = conn.execute(
            "SELECT value FROM sync_state WHERE key='last_sync'"
        ).fetchone()
        conn.close()
        return {
            "status": "ok",
            "path": str(path),
            "db_size_mb": round(path.stat().st_size / (1024 * 1024), 1),
            "entries": count,
            "last_sync": last["value"] if last else "",
            "fresh": _cache_is_fresh(),
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}
