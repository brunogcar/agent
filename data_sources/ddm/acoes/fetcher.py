"""data_sources/ddm/acoes/fetcher.py -- HTTP fetcher + HTML parser for DDM Acoes.

Handles:
  - HTTP GET to www.dadosdemercado.com.br/acoes (no auth, no JS)
  - Server-rendered HTML response cached 5 min (single cache key, thread-safe Lock)
  - Regex-based parser (no BeautifulSoup dependency):
      * parse_stocks_table(html) - list of stock dicts (ticker, name,
        negocios, last_price, variation)
  - Boundary normalizations:
      * "52.792.400" -> 52792400  (PT-BR thousands, dot separator)
      * "44,30"      -> 44.30     (PT-BR decimal, comma separator)
      * "+2,78%"     -> 2.78      (signed percentage, comma decimal)
      * "-10,85%"    -> -10.85    (negative variation)

NO local database writes - this module only fetches + parses.
sync_engine.py stores parsed stocks to acoes.db.

[Phase 3, Commit 1] Refactored to inherit from `data_sources/ddm/_base/`
(BaseDDMFetcher). The shared _cache / _cache_lock / _concurrency_semaphore
scaffold + the cache-lookup + httpx.get + cache-write pattern now lives
in _base/fetcher_base.py; this module keeps only the parser functions
(which are NOT shared) + a thin fetch_acoes_page() wrapper.
"""

from __future__ import annotations

import re

from data_sources.ddm._base.fetcher_base import BOT_HEADERS, BaseDDMFetcher
from data_sources.ddm._parsers import (
    parse_br_int,
    parse_br_number,
    parse_br_percentage,
    strip_html,
)
from data_sources.ddm.acoes.catalog import acoes_url


class _Fetcher(BaseDDMFetcher):
    """Acoes-specific fetcher config (SOURCE_NAME for log/error prefix)."""

    SOURCE_NAME = "acoes"


def parse_stocks_table(html: str) -> list[dict]:
    """Parse the stocks table from the acoes page.

    The page has exactly one table with id="stocks" (class="normal-table"):
      <table class="normal-table" id="stocks">
        <thead><tr>
          <th>Ticker</th><th>Nome</th><th>Negocios</th>
          <th>Ultima (R$)</th><th>Variacao</th>
        </tr></thead>
        <tbody>
          <tr>
            <td><a href="/acoes/petr4">PETR4</a></td>
            <td>Petrobras</td>
            <td>52.792.400</td>
            <td>44,30</td>
            <td>+2,78%</td>
          </tr>
          ...
        </tbody>
      </table>

    Returns a list of dicts (in the order they appear on the page - DDM
    pre-sorts by Negocios DESC):
      [{"ticker": "PETR4", "name": "Petrobras", "negocios": 52792400,
        "last_price": 44.30, "variation": 2.78}, ...]

    Missing values become None.
    """
    if not html:
        return []

    # Find the stocks table by id="stocks".
    m = re.search(r'<table[^>]*id="stocks"[^>]*>([\s\S]*?)</table>', html)
    if m:
        table = m.group(0)
    else:
        # Fallback: any "normal-table" class.
        m = re.search(r'<table[^>]*class="normal-table"[^>]*>([\s\S]*?)</table>', html)
        if m:
            table = m.group(0)
        else:
            # Last resort: first table on the page.
            tables = re.findall(r"<table[^>]*>[\s\S]*?</table>", html)
            if not tables:
                return []
            table = tables[0]

    # Extract <tbody> if present; otherwise parse the whole table body.
    body_match = re.search(r"<tbody[^>]*>([\s\S]*?)</tbody>", table)
    body_html = body_match.group(1) if body_match else table

    rows: list[dict] = []
    for tr in re.finditer(r"<tr[^>]*>([\s\S]*?)</tr>", body_html):
        cells = re.findall(r"<td[^>]*>([\s\S]*?)</td>", tr.group(1))
        if len(cells) < 5:
            continue
        ticker = strip_html(cells[0])
        name = strip_html(cells[1])
        negocios = parse_br_int(strip_html(cells[2]))
        last_price = parse_br_number(strip_html(cells[3]))
        variation = parse_br_percentage(strip_html(cells[4]))

        if not ticker:
            # Skip rows without a ticker (malformed / header repeat).
            continue

        rows.append({
            "ticker":     ticker,
            "name":       name,
            "negocios":   negocios,
            "last_price": last_price,
            "variation":  variation,
        })

    return rows


def fetch_acoes_page(force: bool = False) -> dict:
    """Fetch the HTML page for /acoes.

    Args:
        force: Bypass cache.

    Returns:
        {"status": "ok", "html": <str>, "synced_at": <iso>}
        On error: {"status": "error", "error": <str>}
    """
    return _Fetcher.fetch_page(
        url=acoes_url(),
        cache_key="page:acoes",
        headers=BOT_HEADERS,
        slug=None,
        force=force,
    )


def clear_cache():
    """Clear the in-memory cache (thread-safe)."""
    _Fetcher.clear_cache()
