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
"""

from __future__ import annotations

import re
import sys
import threading
import time
from datetime import datetime, timezone

import httpx

from data_sources.ddm.acoes.catalog import acoes_url

# 5-minute cache TTL. Stock prices change intraday but the auto-sync guard
# already enforces a 24h freshness window; the in-memory cache prevents
# redundant fetches within a single dashboard run.
_CACHE_TTL = 300

_cache: dict[str, tuple[object, float]] = {}

# Thread-safety primitives (mirror ddm/inflation fetcher):
#   _cache_lock             - guards all reads/writes to the _cache dict
#   _concurrency_semaphore  - caps in-flight HTTP requests
_cache_lock = threading.Lock()
_concurrency_semaphore = threading.Semaphore(5)


def _progress(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _today_date() -> str:
    """Return today's date as YYYY-MM-DD (local)."""
    return datetime.now().strftime("%Y-%m-%d")


def _strip_html(s: str) -> str:
    """Strip all HTML tags from a string and collapse whitespace."""
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", s)).strip()


def _parse_br_int(s: str) -> int | None:
    """Parse a PT-BR formatted integer ('52.792.400') -> 52792400.

    PT-BR uses '.' as the thousands separator. Returns None for empty
    strings, '--', or unparseable inputs.
    """
    if s is None:
        return None
    s = s.strip()
    if not s or s == "--":
        return None
    cleaned = s.replace(".", "").replace(" ", "")
    try:
        return int(cleaned)
    except (ValueError, TypeError):
        return None


def _parse_br_number(s: str) -> float | None:
    """Parse a PT-BR formatted number ('44,30') -> 44.30.

    PT-BR uses ',' as the decimal separator. Returns None for empty
    strings, '--', or unparseable inputs. Handles negative numbers
    ('-1,16' -> -1.16).
    """
    if s is None:
        return None
    s = s.strip()
    if not s or s == "--":
        return None
    try:
        return float(s.replace(",", "."))
    except (ValueError, TypeError):
        return None


def _parse_variation(s: str) -> float | None:
    """Parse a signed PT-BR percentage ('+2,78%' or '-10,85%') -> 2.78 / -10.85.

    DDM renders variation with:
      - A leading sign ('+' or '-')
      - PT-BR comma decimal ('2,78')
      - A trailing percent sign ('%')

    Returns None for empty strings, '--', or unparseable inputs.
    """
    if s is None:
        return None
    s = s.strip()
    if not s or s == "--":
        return None
    # Strip the trailing '%' sign (if present).
    s = s.replace("%", "").strip()
    # The sign + comma-decimal format is handled by _parse_br_number.
    return _parse_br_number(s)


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
        ticker = _strip_html(cells[0])
        name = _strip_html(cells[1])
        negocios = _parse_br_int(_strip_html(cells[2]))
        last_price = _parse_br_number(_strip_html(cells[3]))
        variation = _parse_variation(_strip_html(cells[4]))

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
    cache_key = "page:acoes"

    with _cache_lock:
        if not force and cache_key in _cache:
            data, ts = _cache[cache_key]
            if time.time() - ts < _CACHE_TTL:
                return data

    url = acoes_url()
    headers = {
        "Accept": "text/html,application/xhtml+xml",
        "User-Agent": "Mozilla/5.0 (compatible; ddm-fetcher/1.0)",
    }

    _progress(f"[ddm.acoes] Fetching acoes page ({url})")

    with _concurrency_semaphore:
        try:
            resp = httpx.get(url, headers=headers, timeout=30, follow_redirects=True)
            resp.raise_for_status()
        except httpx.HTTPError as e:
            return {"status": "error", "error": f"ddm.acoes: {e}"}

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
