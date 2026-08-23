"""data_sources/ddm/fluxo/fetcher.py -- HTTP fetcher + HTML parser for DDM Fluxo.

Handles:
  - HTTP GET to www.dadosdemercado.com.br/fluxo (no auth, no JS)
  - Server-rendered HTML response cached 5 min (single cache key, thread-safe Lock)
  - Regex-based parser (no BeautifulSoup dependency):
      * parse_fluxo_table(html) - list of dicts per ref_date
  - Boundary normalizations:
      * Date: "19/08/2026" -> "2026-08-19" (DD/MM/YYYY -> YYYY-MM-DD)
      * Value: "-1.582,35 mi" -> -1582.35 (strip "mi", remove dots,
        replace comma with dot, keep sign)
      * Value: "1.029,81 mi" -> 1029.81
      * Value: "42,36 mi" -> 42.36
      * Value: "-9,31 mi" -> -9.31

NO local database writes - this module only fetches + parses.
sync_engine.py stores parsed observations to fluxo.db.

CloudFront protection note: the /fluxo page is fronted by CloudFront and
will reject requests with a non-browser User-Agent header. We send the
full Chrome 127 header set (User-Agent + Accept + Accept-Language +
Connection + Upgrade-Insecure-Requests) to match a real browser as
closely as possible. NOTE: this is the BROWSER_HEADERS variant (without
Accept-Encoding), distinct from CLOUDFRONT_HEADERS used by focus.

[Phase 3, Commit 1] Refactored to inherit from `data_sources/ddm/_base/`
(BaseDDMFetcher). The shared _cache / _cache_lock / _concurrency_semaphore
scaffold + the cache-lookup + httpx.get + cache-write pattern now lives
in _base/fetcher_base.py; this module keeps only the parser functions
(which are NOT shared) + a thin fetch_fluxo_page() wrapper.
"""

from __future__ import annotations

import re

from data_sources.ddm._base.fetcher_base import BROWSER_HEADERS, BaseDDMFetcher
from data_sources.ddm._parsers import (
    parse_br_date_iso,
    parse_br_number,
    strip_html,
)
from data_sources.ddm.fluxo.catalog import fluxo_url


class _Fetcher(BaseDDMFetcher):
    """Fluxo-specific fetcher config (SOURCE_NAME for log/error prefix)."""

    SOURCE_NAME = "fluxo"


def parse_fluxo_table(html: str) -> list[dict]:
    """Parse the single fluxo table from the /fluxo page.

    The table is `<table class="normal-table" id="flow">` with 6 columns:
        Data | Estrangeiro | Institucional | Pessoa fisica |
        Inst. Financeira | Outros

    Returns a list of dicts (in source order - newest first, DESC by date):
        [{"ref_date": "2026-08-19",
          "estrangeiro": -1582.35,
          "institucional": 1029.81,
          "pessoa_fisica": 42.36,
          "inst_financeira": 519.49,
          "outros": -9.31}, ...]

    Values are parsed to floats (millions of R$). Dates are normalized to
    ISO YYYY-MM-DD at parse time. Header rows and malformed rows are
    skipped (rows with fewer than 6 cells, or rows where the first cell
    is the literal "Data" header label).
    """
    if not html:
        return []

    # Find the <table class="normal-table"> block. The class attribute can
    # appear in any position relative to other attributes, so we use a
    # permissive regex. The /fluxo page has exactly one such table.
    table_match = re.search(
        r'<table[^>]*class="[^"]*normal-table[^"]*"[^>]*>([\s\S]*?)</table>',
        html,
    )
    if not table_match:
        # Fallback: any <table> with id="flow" or any <table> at all.
        table_match = re.search(
            r'<table[^>]*id="flow"[^>]*>([\s\S]*?)</table>',
            html,
        )
    if not table_match:
        return []

    table_html = table_match.group(0)

    # Extract <tbody> if present; otherwise parse the whole table body.
    body_match = re.search(r"<tbody[^>]*>([\s\S]*?)</tbody>", table_html)
    body_html = body_match.group(1) if body_match else table_html

    rows: list[dict] = []
    for tr in re.finditer(r"<tr[^>]*>([\s\S]*?)</tr>", body_html):
        cells = re.findall(r"<td[^>]*>([\s\S]*?)</td>", tr.group(1))
        if len(cells) < 6:
            # Header rows, malformed rows, or repeat-header rows.
            continue
        date_str = strip_html(cells[0])
        if not date_str:
            continue
        # Skip the header row (first cell == "Data").
        if date_str.lower() in ("data", "data "):
            continue
        ref_date = parse_br_date_iso(date_str)
        if not ref_date:
            continue
        row = {
            "ref_date":        ref_date,
            "estrangeiro":     parse_br_number(cells[1]),
            "institucional":   parse_br_number(cells[2]),
            "pessoa_fisica":   parse_br_number(cells[3]),
            "inst_financeira": parse_br_number(cells[4]),
            "outros":          parse_br_number(cells[5]),
        }
        rows.append(row)

    return rows


def fetch_fluxo_page(force: bool = False) -> dict:
    """Fetch the HTML page for /fluxo.

    Args:
        force: Bypass cache.

    Returns:
        {"status": "ok", "html": <str>, "synced_at": <iso>}
        On error: {"status": "error", "error": <str>}

    The fetcher sends full browser-like headers (Chrome 127 on Windows,
    BROWSER_HEADERS variant without Accept-Encoding) to bypass the
    CloudFront WAF that guards the fluxo endpoint. The site rejects bare
    or identifying bot UAs with a 403, so we use a complete header set
    matching a real browser.
    """
    return _Fetcher.fetch_page(
        url=fluxo_url(),
        cache_key="page:fluxo",
        headers=BROWSER_HEADERS,
        slug=None,
        force=force,
    )


def clear_cache():
    """Clear the in-memory cache (thread-safe)."""
    _Fetcher.clear_cache()
