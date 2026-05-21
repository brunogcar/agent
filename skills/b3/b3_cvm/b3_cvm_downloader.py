"""
skills/b3/b3_cvm/b3_cvm_downloader.py
Deploy to: D:\mcp\agent\skills\b3\b3_cvm\b3_cvm_downloader.py

Network calls only. Downloads raw bytes and hands them to b3_cvm_parser.py.
No parsing logic here -- single responsibility.

=== B3 ISIN API FLOW ===
1. GET /IsinCall/GetTextDownload/
   Returns JSON: {"geralPt": {"id": 102014, "dataGeracao": "2026-05-19T..."}}
   "geralPt" = general file in Portuguese (complete, not daily delta)

2. base64(json.dumps(id)) -> encoded file ID
   e.g. json.dumps(102014) = "102014" -> base64 -> "MTAyMDE0"

3. GET /IsinCall/GetFileDownload/{encoded_id}
   Returns: ZIP file (PK magic bytes confirmed)
   Requires browser-like headers (Referer + Origin) -- 403 without them

=== DECISION: Browser headers required ===
B3's CDN checks Referer and Origin. Without them the API returns
"Host not in allowlist" (403). We send minimal browser-like headers.
User-Agent is checked too -- a blank UA also returns 403.

=== CVM DOWNLOAD ===
Simple GET, no auth, no special headers.
URL is stable and publicly documented in dados.cvm.gov.br.
File is ~1.5MB, updated daily.
"""

from __future__ import annotations

import base64
import json
import sys
from typing import Optional


# Browser-like headers required by B3 CDN
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

_B3_BASE = "https://sistemaswebb3-listados.b3.com.br"
_CVM_URL = "https://dados.cvm.gov.br/dados/CIA_ABERTA/CAD/DADOS/cad_cia_aberta.csv"


def download_b3_zip() -> bytes:
    """
    Download the B3 ISIN ZIP file. Returns raw bytes.

    Raises httpx.HTTPError on network failure.
    Raises ValueError if the response is not a ZIP.

    DECISION: Return raw bytes, not parsed data.
    The caller (b3_cvm.py mode_sync) passes bytes to b3_cvm_parser.parse_b3_zip().
    This keeps download and parse cleanly separated and independently testable.
    """
    import httpx

    # Step 1: get current file ID
    print("[b3_dl] Fetching B3 ISIN file index...", file=sys.stderr)
    resp = httpx.get(
        f"{_B3_BASE}/isinProxy/IsinCall/GetTextDownload/",
        headers=_B3_HEADERS,
        timeout=30,
        follow_redirects=True,
    )
    resp.raise_for_status()
    index    = resp.json()
    file_id  = index["geralPt"]["id"]
    gen_date = index["geralPt"].get("dataGeracao", "unknown")
    print(f"[b3_dl] B3 ISIN id={file_id} generated={gen_date}", file=sys.stderr)

    # Step 2: encode the integer ID (btoa(JSON.stringify(id)) in JS)
    encoded = base64.b64encode(json.dumps(file_id).encode()).decode()

    # Step 3: download ZIP
    print(f"[b3_dl] Downloading B3 ISIN ZIP (encoded={encoded})...", file=sys.stderr)
    resp2 = httpx.get(
        f"{_B3_BASE}/isinProxy/IsinCall/GetFileDownload/{encoded}",
        headers=_B3_HEADERS,
        timeout=120,
        follow_redirects=True,
    )
    resp2.raise_for_status()

    raw = resp2.content
    print(f"[b3_dl] Downloaded {len(raw):,} bytes | is_zip={raw[:2]==b'PK'}", file=sys.stderr)

    if raw[:2] != b"PK":
        # Not a ZIP -- could be an error page or plain text
        preview = raw[:200].decode("latin-1", errors="replace")
        raise ValueError(
            f"B3 GetFileDownload did not return a ZIP. "
            f"First 200 bytes: {preview!r}"
        )

    return raw


def download_cvm_register() -> bytes:
    """
    Download CVM cad_cia_aberta.csv. Returns raw bytes.

    Simple public GET -- no auth, no special headers.
    URL is stable (documented in dados.cvm.gov.br portal).

    DECISION: Return raw bytes. Encoding detection is in the parser
    (parse_cvm_register tries utf-8-sig, utf-8, latin-1 in order).
    """
    import httpx

    print("[b3_dl] Downloading CVM cad_cia_aberta.csv...", file=sys.stderr)
    resp = httpx.get(_CVM_URL, timeout=60, follow_redirects=True)
    resp.raise_for_status()
    raw = resp.content
    print(f"[b3_dl] Downloaded {len(raw):,} bytes (CVM)", file=sys.stderr)
    return raw
