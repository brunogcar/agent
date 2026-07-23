"""
skills/b3/b3_cvm/b3_cvm_parser.py
Deploy to: D:\mcp\agent\skills\b3\b3_cvm\b3_cvm_parser.py

Parses the two B3 ZIP files and CVM CSV into Python dicts.
No network calls here -- only bytes-in, list[dict]-out.
Called exclusively by b3_cvm_downloader.py.

=== B3 ZIP STRUCTURE (confirmed 2026-05-20) ===
ZIP contains three files:
  EMISSOR.TXT   -- 68,624 rows, comma+quote delimited, no header
                   col[0] issuer_code  "0001"
                   col[1] name         "PETROLEO BRASILEIRO..."
                   col[2] cnpj         "33000167000101"   (digits only, 14 chars)
                   col[3] date         "20180630"

  NUMERACA.TXT  -- 281,635 rows, comma+quote delimited, no header, 45 cols
                   col[1] status       "A" (Ativo) or "N" (Inativo)
                   col[2] isin         "BRPETRACNPR6"
                   col[3] issuer_code  "0002"  <- joins EMISSOR col[0]
                   col[4] cfi_code     "EPNNPR" (NOT the ticker -- this is CFI)
                   col[20] inst_type   "CTF", "ACN", "4V", "5A" etc.

  Leiame.pdf    -- documentation, ignored

  DECISION: col[4] is CFI code, NOT the trading ticker (TckrSymb).
  We confirmed: PETR4 is found in instruments.db via ISIN join, not here.
  NUMERACA is used ONLY to get ISIN -> CNPJ mapping via EMISSOR join.
  The actual ticker comes from instruments.db (b3_api's database).

=== EQUITY FILTER (instruments.db, applied in b3_cvm.py) ===
  SgmtNm='CASH' AND MktNm='EQUITY-CASH' AND SctyCtgyNm IN ('SHARES','UNIT')
  This gives main equities (PETR4, VALE3) and units (KLBN11).
  No odd lots (ODD LOT), no block trades (Equity Block Trading Lot),
  no derivatives, no futures.

=== CVM cad_cia_aberta.csv ===
  Semicolon-delimited, ~2,673 rows (2026-05 count).
  Encoding: UTF-8-BOM or latin-1 (try both).
  Key columns: CD_CVM | CNPJ_CIA | DENOM_SOCIAL | DENOM_COMERC | SIT | TP_MERC | SETOR_ATIV
  CNPJ_CIA is punctuated ("33.000.167/0001-01") -- normalize with _cnpj().
"""

from __future__ import annotations

import csv
import io
import re
import sys
import zipfile
from typing import Optional


# ── CNPJ normalization (local copy -- avoids circular import from cvm/_db.py) ─
# DECISION: Duplicate _cnpj() here rather than importing from skills.cvm._db.
# b3_cvm_parser.py is a b3/ skill file and should not depend on cvm/ internals.
# The function is trivial (one line) so duplication cost is negligible.

def _cnpj(raw: str) -> str:
    """Strip non-digits. Return 14-char string or '' if wrong length."""
    if not raw:
        return ""
    digits = re.sub(r"\D", "", str(raw))
    return digits if len(digits) == 14 else ""


# ── EMISSOR.TXT parser ────────────────────────────────────────────────────────

def parse_emissor(raw_bytes: bytes) -> dict[str, str]:
    """
    Parse EMISSOR.TXT from B3 ZIP.
    Returns {issuer_code: cnpj} dict. ~68k entries.

    Format: comma+quote, no header, 4 columns:
      col[0] issuer_code (zero-padded 4-digit string)
      col[1] name
      col[2] cnpj (14 digits, no punctuation)
      col[3] date YYYYMMDD

    DECISION: We only store issuer_code -> cnpj.
    The name is already in instruments.db (CrpnNm column).
    Storing the full name here would duplicate data and add no value.

    ENCODING: latin-1. EMISSOR.TXT confirmed latin-1 from inspection.
    Company names contain accented Portuguese characters (Ã, Ç, É etc.)
    that are encoded as single bytes in latin-1.
    """
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

    print(f"[b3_parser] EMISSOR: {len(result):,} issuer->cnpj entries", file=sys.stderr)
    return result


# ── NUMERACA.TXT parser ───────────────────────────────────────────────────────

def parse_numeraca(raw_bytes: bytes, emissor_index: dict[str, str]) -> dict[str, str]:
    """
    Parse NUMERACA.TXT and return {isin: cnpj} mapping.

    NUMERACA has 281k rows covering ALL B3 instruments (funds, bonds,
    equities, options, futures). We do NOT filter here -- we build the
    complete ISIN->CNPJ index and let b3_cvm.py filter by instrument type
    using instruments.db (SgmtNm/MktNm/SctyCtgyNm).

    DECISION: Return all ISINs, not just equities.
    The equity filter happens in b3_cvm.py when joining with instruments.db.
    This keeps the parser simple and the index reusable for future skills
    (e.g. b3_fii could use the same ISIN->CNPJ index for FII funds).

    Format: comma+quote, no header, 45 columns:
      col[1]  status       "A" or "N"
      col[2]  isin         "BRPETRACNPR6"
      col[3]  issuer_code  "0234" -- joins to emissor_index

    NOTE: col[4] is CFI code (EPNNPR, ESVUFR, OPESPS etc.), NOT ticker.
    The trading ticker (PETR4) comes from instruments.db, not NUMERACA.
    """
    content = raw_bytes.decode("latin-1", errors="replace")
    result: dict[str, str] = {}
    no_cnpj = 0
    skipped = 0

    for line in content.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            cols = [c.strip('"') for c in next(csv.reader([line]))]
        except Exception:
            skipped += 1
            continue
        if len(cols) < 4:
            continue

        isin        = cols[2].strip()
        issuer_code = cols[3].strip()

        if not isin or len(isin) < 10:
            continue

        cnpj = emissor_index.get(issuer_code, "")
        if cnpj:
            result[isin] = cnpj
        else:
            no_cnpj += 1

    print(
        f"[b3_parser] NUMERACA: {len(result):,} isin->cnpj | "
        f"no_cnpj={no_cnpj:,} | skipped={skipped:,}",
        file=sys.stderr,
    )
    return result


# ── CVM cad_cia_aberta.csv parser ─────────────────────────────────────────────

def parse_cvm_register(raw_bytes: bytes) -> list[dict]:
    """
    Parse CVM cad_cia_aberta.csv into list of dicts.

    Returns list of dicts with keys:
      cnpj, cd_cvm, denom_social, denom_comerc, sit, tp_merc, setor_ativ

    ENCODING: Try UTF-8-BOM first (CVM uses BOM on some files), then latin-1.

    SEMICOLON DELIMITER: CVM uses semicolons because Brazil uses comma as
    the decimal separator -- semicolons are the PT-BR CSV convention.

    DECISION: Include ALL companies (ATIVO, CANCELADO, SUSPENSO).
    dfp_itr.db has historical data for cancelled companies (merged/acquired).
    The 'sit' column lets callers filter if they only want active ones.
    """
    content = None
    for encoding in ("utf-8-sig", "utf-8", "latin-1", "cp1252"):
        try:
            content = raw_bytes.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    if content is None:
        content = raw_bytes.decode("latin-1", errors="replace")

    lines = content.splitlines()
    if not lines:
        return []

    # Parse header to get column positions by name
    headers = [h.strip() for h in lines[0].split(";")]
    col_idx = {h: i for i, h in enumerate(headers)}

    def _get(parts: list[str], name: str) -> str:
        idx = col_idx.get(name, -1)
        if idx < 0 or idx >= len(parts):
            return ""
        return parts[idx].strip()

    rows = []
    for line in lines[1:]:
        line = line.strip()
        if not line:
            continue
        parts = line.split(";")
        cnpj_raw   = _get(parts, "CNPJ_CIA")
        cd_cvm_raw = _get(parts, "CD_CVM") or "0"
        try:
            cd_cvm = int(cd_cvm_raw)
        except ValueError:
            cd_cvm = 0

        rows.append({
            "cnpj":         _cnpj(cnpj_raw),
            "cd_cvm":       cd_cvm,
            "denom_social": _get(parts, "DENOM_SOCIAL"),
            "denom_comerc": _get(parts, "DENOM_COMERC"),
            "sit":          _get(parts, "SIT"),
            "tp_merc":      _get(parts, "TP_MERC"),
            "setor_ativ":   _get(parts, "SETOR_ATIV"),
        })

    print(f"[b3_parser] CVM register: {len(rows):,} rows", file=sys.stderr)
    return rows


# ── ZIP dispatcher ────────────────────────────────────────────────────────────

def parse_b3_zip(raw_bytes: bytes) -> dict[str, str]:
    """
    Unzip B3 ISIN ZIP and return {isin: cnpj} mapping.

    Orchestrates: unzip -> parse_emissor -> parse_numeraca -> return index.
    Callers (b3_cvm_downloader.py) just pass raw ZIP bytes and get the index.

    DECISION: Return only {isin: cnpj} dict, not the raw EMISSOR/NUMERACA rows.
    The downstream join (instruments.db -> isin_cnpj_index) only needs this
    mapping. Keeping the intermediate data in memory is wasteful for 281k rows.

    ZIP ENTRY SELECTION:
      EMISSOR.TXT  -- must be read first (builds the issuer_code->cnpj index)
      NUMERACA.TXT -- read second (uses emissor index to resolve CNPJs)
      Leiame.pdf   -- ignored
    """
    if raw_bytes[:2] != b"PK":
        raise ValueError(
            f"Expected ZIP (PK magic), got: {raw_bytes[:4]!r}. "
            "B3 GetFileDownload should always return a ZIP."
        )

    zf = zipfile.ZipFile(io.BytesIO(raw_bytes))
    names = zf.namelist()
    print(f"[b3_parser] ZIP entries: {names}", file=sys.stderr)

    # Find EMISSOR and NUMERACA (case-insensitive, in case B3 changes casing)
    emissor_name  = next((n for n in names if "EMISSOR"  in n.upper()), None)
    numeraca_name = next((n for n in names if "NUMERACA" in n.upper()), None)

    if not emissor_name:
        raise ValueError(f"EMISSOR.TXT not found in ZIP. Entries: {names}")
    if not numeraca_name:
        raise ValueError(f"NUMERACA.TXT not found in ZIP. Entries: {names}")

    emissor_bytes  = zf.read(emissor_name)
    numeraca_bytes = zf.read(numeraca_name)

    emissor_index  = parse_emissor(emissor_bytes)
    isin_cnpj      = parse_numeraca(numeraca_bytes, emissor_index)

    return isin_cnpj
