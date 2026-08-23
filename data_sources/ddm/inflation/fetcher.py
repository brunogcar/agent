"""data_sources/ddm/inflation/fetcher.py -- HTTP fetcher + HTML parser for DDM.

Handles:
  - HTTP GET to www.dadosdemercado.com.br/indices/{slug} (no auth, no JS)
  - Server-rendered HTML response cached 5 min (per slug, thread-safe Lock)
  - Regex-based parser (no BeautifulSoup dependency):
      * parse_historical_table(html) -- DESC monthly rows -> ascending obs list
      * parse_monthly_matrix(html)   -- year x month matrix dict
  - Boundary normalizations:
      * "Jul/2026" -> "2026-07"  (ref_date)
      * "0,41"     -> 0.41       (Brazilian comma decimal)
      * "--"       -> None       (missing values)

NO local database writes - this module only fetches + parses.
sync_engine.py stores parsed observations to inflation.db.
"""

from __future__ import annotations

import re
import sys
import threading
import time
from datetime import datetime, timezone

import httpx

from data_sources.ddm._parsers import (
    parse_br_number,
    parse_mes_ano,
    strip_html,
)
from data_sources.ddm.inflation.catalog import index_url

# 5-minute cache TTL. DDM publishes monthly series once per month, so 5 min
# is well within the freshness window. Cache is per-slug.
_CACHE_TTL = 300

_cache: dict[str, tuple[object, float]] = {}

# Thread-safety primitives (mirror bcb/sgs fetcher):
#   _cache_lock             - guards all reads/writes to the _cache dict
#   _concurrency_semaphore  - caps in-flight HTTP requests (DDM has no
#                             documented rate limit; this is conservative)
_cache_lock = threading.Lock()
_concurrency_semaphore = threading.Semaphore(5)


def _progress(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_data_value(td: str) -> float | None:
    """Extract the data-value attribute from a <td data-value="..."> cell.

    DDM matrix cells look like: <td class="right" data-value="0.41">0,41%</td>
    The data-value attribute is the canonical numeric form (dot decimal).
    Falls back to parsing the cell text if the attribute is missing.
    """
    if not td:
        return None
    m = re.search(r'data-value="([^"]+)"', td)
    if m:
        val = m.group(1).strip()
        if val == "--" or val == "":
            return None
        try:
            return float(val)
        except (ValueError, TypeError):
            return None
    # Fallback: strip HTML + parse the cell text.
    text = re.sub(r"<[^>]+>", "", td).strip()
    text = text.replace("%", "").strip()
    return parse_br_number(text)


def parse_historical_table(html: str) -> list[dict]:
    """Parse the historical monthly table (2nd <table> on the page).

    DDM index pages have 2 tables:
      1. Monthly matrix (id="index-values") - year x month grid
      2. Historical monthly (class "normal-table") - DESC rows with
         columns: Mes/Ano | Indice do mes (%) | Acumulado no ano (%) |
                  Acumulado 12 meses (%)

    Returns a list of dicts sorted ASCENDING by ref_date:
      [{"ref_date": "2026-07", "month_value": 0.41,
        "year_acumulado": 3.12, "acumulado_12m": 5.88}, ...]
    """
    if not html:
        return []
    tables = re.findall(r"<table[^>]*>[\s\S]*?</table>", html)
    if len(tables) < 2:
        return []
    table = tables[1]

    rows: list[dict] = []
    for tr in re.finditer(r"<tr[^>]*>([\s\S]*?)</tr>", table):
        cells = re.findall(r"<td[^>]*>([\s\S]*?)</td>", tr.group(1))
        if len(cells) < 4:
            continue
        cleaned = [strip_html(c) for c in cells[:4]]
        ref_date = parse_mes_ano(cleaned[0])
        if not ref_date:
            continue
        rows.append({
            "ref_date":        ref_date,
            "month_value":     parse_br_number(cleaned[1]),
            "year_acumulado":  parse_br_number(cleaned[2]),
            "acumulado_12m":   parse_br_number(cleaned[3]),
        })

    # DDM rows are DESC (Jul/2026, Jun/2026, ...) - reverse to ASC.
    rows.reverse()
    return rows


def parse_monthly_matrix(html: str) -> dict:
    """Parse the monthly matrix table (1st <table>, id="index-values").

    Rows = years, Columns = Jan..Dez + "Ano" (year acumulado).

    Returns:
        {"years": [<int>, ...],
         "months": ["Jan", "Fev", ..., "Dez", "Ano"],
         "matrix": {<year_int>: {"Jan": <float|None>, ..., "Ano": <float|None>}}}

    Missing cells are stored as None.
    """
    if not html:
        return {"years": [], "months": [], "matrix": {}}

    # Find the matrix table by id (fallback: first <table>).
    m = re.search(r'<table[^>]*id="index-values"[^>]*>([\s\S]*?)</table>', html)
    if m:
        table = m.group(0)
    else:
        tables = re.findall(r"<table[^>]*>[\s\S]*?</table>", html)
        if not tables:
            return {"years": [], "months": [], "matrix": {}}
        table = tables[0]

    # Parse header row.
    header_match = re.search(r"<thead[^>]*>([\s\S]*?)</thead>", table)
    months: list[str] = []
    if header_match:
        header_tr = re.search(r"<tr[^>]*>([\s\S]*?)</tr>", header_match.group(1))
        if header_tr:
            for th in re.findall(r"<th[^>]*>([\s\S]*?)</th>", header_tr.group(1)):
                months.append(strip_html(th))
    if not months:
        # Fallback: take the first <tr> in the table as the header.
        first_tr = re.search(r"<tr[^>]*>([\s\S]*?)</tr>", table)
        if first_tr:
            for cell in re.findall(r"<t[h|d][^>]*>([\s\S]*?)</t[h|d]>", first_tr.group(1)):
                months.append(strip_html(cell))

    # Parse body rows.
    body_match = re.search(r"<tbody[^>]*>([\s\S]*?)</tbody>", table)
    body_html = body_match.group(1) if body_match else table

    years: list[int] = []
    matrix: dict[int, dict[str, float | None]] = {}
    for tr in re.finditer(r"<tr[^>]*>([\s\S]*?)</tr>", body_html):
        cells = re.findall(r"<td[^>]*>([\s\S]*?)</td>", tr.group(1))
        if not cells:
            continue
        # First cell = year (string).
        year_str = strip_html(cells[0])
        try:
            year = int(year_str)
        except (ValueError, TypeError):
            continue
        row: dict[str, float | None] = {}
        for i, cell in enumerate(cells[1:], start=1):
            label = months[i] if i < len(months) else f"col{i}"
            row[label] = _parse_data_value(cell)
        years.append(year)
        matrix[year] = row

    # Sort years descending (DDM shows newest year first).
    years.sort(reverse=True)
    return {"years": years, "months": months, "matrix": matrix}


def fetch_index_page(slug: str, force: bool = False) -> dict:
    """Fetch the HTML page for an index.

    Args:
        slug:  DDM index slug (e.g. 'igp-m').
        force: Bypass cache.

    Returns:
        {"status": "ok", "slug": <str>, "html": <str>, "synced_at": <iso>}
    """
    cache_key = f"page:{slug}"

    with _cache_lock:
        if not force and cache_key in _cache:
            data, ts = _cache[cache_key]
            if time.time() - ts < _CACHE_TTL:
                return data

    url = index_url(slug)
    headers = {
        "Accept": "text/html,application/xhtml+xml",
        "User-Agent": "Mozilla/5.0 (compatible; ddm-fetcher/1.0)",
    }

    _progress(f"[ddm.inflation] Fetching index page {slug} ({url})")

    with _concurrency_semaphore:
        try:
            resp = httpx.get(url, headers=headers, timeout=30, follow_redirects=True)
            resp.raise_for_status()
        except httpx.HTTPError as e:
            return {"status": "error", "slug": slug,
                    "error": f"ddm.inflation: {e}"}

    html = resp.text
    result = {
        "status":    "ok",
        "slug":      slug,
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
