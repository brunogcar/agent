"""data_sources/ddm/dividends/fetcher.py -- HTTP fetcher + HTML parser for DDM Dividends.

Handles:
  - HTTP GET to www.dadosdemercado.com.br/agenda-de-dividendos (no auth, no JS)
  - Server-rendered HTML response cached 5 min (single key, thread-safe Lock)
  - Regex-based parser (no BeautifulSoup dependency):
      * parse_dividends_table(html)  -> list of dividend dicts
  - Boundary normalizations:
      * "0,017250"   -> 0.017250   (Brazilian comma decimal -> float)
      * "01/07/2026" -> "2026-07-01" (DD/MM/YYYY -> YYYY-MM-DD)
      * "BBDC3"      -> "BBDC3"    (text inside <a> tag)
      * "Dividendo"  -> "Dividendo" (plain text)
      * "JCP"        -> "JCP"      (plain text)

DDM dividends page shape (single table, class="normal-table"):
  <table class="normal-table">
    <thead><tr><th>Codigo</th><th>Tipo</th><th>Valor (R$)</th>
               <th>Registro</th><th>Ex</th><th>Pagamento</th></tr></thead>
    <tbody>
      <tr>
        <td><strong><a href="/acoes/bbdc3">BBDC3</a></strong></td>
        <td>Dividendo</td>
        <td>0,017250</td>
        <td>01/07/2026</td>
        <td>02/07/2026</td>
        <td>03/08/2026</td>
      </tr>
      ...
    </tbody>
  </table>

NO local database writes - this module only fetches + parses.
sync_engine.py stores parsed rows to dividends.db.
"""

from __future__ import annotations

import re
import sys
import threading
import time
from datetime import datetime, timezone

import httpx

from data_sources.ddm._parsers import (
    parse_br_date_iso,
    parse_br_number,
    strip_html,
)
from data_sources.ddm.dividends.catalog import DIVIDENDS_URL

# 5-minute cache TTL. DDM publishes the dividend agenda on a rolling basis;
# 5 min is well within the freshness window. Single-key cache (one page).
_CACHE_TTL = 300

_cache: dict[str, tuple[object, float]] = {}

# Thread-safety primitives (mirror bcb/sgs + ddm/juros + ddm/poupanca):
#   _cache_lock             - guards all reads/writes to the _cache dict
#   _concurrency_semaphore  - caps in-flight HTTP requests (conservative)
_cache_lock = threading.Lock()
_concurrency_semaphore = threading.Semaphore(5)


def _progress(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _extract_ticker(td: str) -> str:
    """Extract the ticker code from a Codigo cell.

    DDM wraps the ticker in a <strong><a href="/acoes/bbdc3">BBDC3</a></strong>
    structure. Falls back to stripping HTML if the <a> tag is missing.
    """
    if not td:
        return ""
    # Prefer the <a> tag's inner text (canonical ticker form).
    m = re.search(r"<a[^>]*>([^<]+)</a>", td)
    if m:
        return m.group(1).strip()
    return strip_html(td)


def parse_dividends_table(html: str) -> list[dict]:
    """Parse the dividend agenda table (class="normal-table").

    Returns a list of dicts (one per row):
      [{"ticker": "BBDC3", "tipo": "Dividendo", "value": 0.017250,
        "record_date": "2026-07-01", "ex_date": "2026-07-02",
        "payment_date": "2026-08-03"}, ...]

    Skips rows that don't have 6 cells or don't have a parseable ticker.

    Order: rows are returned in the SAME order they appear on the page
    (DDM lists upcoming events chronologically by record_date ASC).
    """
    if not html:
        return []

    # Find the dividends table by class. Fallback: first <table> on the page.
    m = re.search(
        r'<table[^>]*class="[^"]*normal-table[^"]*"[^>]*>([\s\S]*?)</table>',
        html,
    )
    if m:
        table = m.group(0)
    else:
        tables = re.findall(r"<table[^>]*>[\s\S]*?</table>", html)
        if not tables:
            return []
        table = tables[0]

    # Body rows only (skip thead).
    body_match = re.search(r"<tbody[^>]*>([\s\S]*?)</tbody>", table)
    body_html = body_match.group(1) if body_match else table

    rows: list[dict] = []
    for tr in re.finditer(r"<tr[^>]*>([\s\S]*?)</tr>", body_html):
        cells = re.findall(r"<td[^>]*>([\s\S]*?)</td>", tr.group(1))
        if len(cells) < 6:
            continue

        ticker = _extract_ticker(cells[0])
        if not ticker:
            continue

        tipo = strip_html(cells[1])
        value = parse_br_number(strip_html(cells[2]))
        record_date = parse_br_date_iso(strip_html(cells[3]))
        ex_date = parse_br_date_iso(strip_html(cells[4]))
        payment_date = parse_br_date_iso(strip_html(cells[5]))

        rows.append({
            "ticker":       ticker,
            "tipo":         tipo,
            "value":        value,
            "record_date":  record_date,
            "ex_date":      ex_date,
            "payment_date": payment_date,
        })

    return rows


def fetch_dividends_page(force: bool = False) -> dict:
    """Fetch the dividend agenda HTML page.

    Args:
        force: Bypass cache.

    Returns:
        {"status": "ok", "html": <str>, "synced_at": <iso>}
        On error: {"status": "error", "error": <msg>}
    """
    cache_key = "page:dividends"

    with _cache_lock:
        if not force and cache_key in _cache:
            data, ts = _cache[cache_key]
            if time.time() - ts < _CACHE_TTL:
                return data

    headers = {
        "Accept": "text/html,application/xhtml+xml",
        "User-Agent": "Mozilla/5.0 (compatible; ddm-fetcher/1.0)",
    }

    _progress(f"[ddm.dividends] Fetching agenda-de-dividendos ({DIVIDENDS_URL})")

    with _concurrency_semaphore:
        try:
            resp = httpx.get(DIVIDENDS_URL, headers=headers,
                             timeout=30, follow_redirects=True)
            resp.raise_for_status()
        except httpx.HTTPError as e:
            return {"status": "error",
                    "error": f"ddm.dividends: {e}"}

    html = resp.text
    result = {
        "status":    "ok",
        "html":      html,
        "synced_at": _now_iso(),
    }

    with _cache_lock:
        _cache[cache_key] = (result, time.time())
    return result


def clear_cache():
    """Clear the in-memory cache (thread-safe)."""
    with _cache_lock:
        _cache.clear()
