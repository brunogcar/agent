"""data_sources/ddm/focus/fetcher.py -- HTTP fetcher + HTML parser for DDM Focus.

Handles:
  - HTTP GET to www.dadosdemercado.com.br/boletim-focus (no auth, no JS)
  - Server-rendered HTML response cached 5 min (single cache key, thread-safe Lock)
  - Regex-based parser (no BeautifulSoup dependency):
      * parse_focus_tables(html) - list of dicts per (year, indicator) pair
  - Boundary normalizations:
      * Year is identified from the nearest preceding heading (<h2> or <h3>)
        that contains a 4-digit year (e.g. "2026").
      * Indicator name is the first cell of each row.
      * three value columns ("Ha 4 semanas", "1 sem", "Hoje") preserved
        verbatim as PT-BR strings ("5,151%", "R$ 5,200").
      * Comparison column is mapped: up/down/flat ("up"/"down"/"flat").
      * Respondents count parsed as integer.

NO local database writes - this module only fetches + parses.
sync_engine.py stores parsed observations to focus.db.

CloudFront protection note: the boletim-focus page is fronted by
CloudFront and will reject requests with a non-browser User-Agent header.
We send the full Chrome 127 header set (User-Agent + Accept + Accept-Language
+ Accept-Encoding + Connection + Upgrade-Insecure-Requests) to match a real
browser as closely as possible. This mirrors the headers used by the existing
DDM scrapers but is more comprehensive (the CloudFront WAF rules on this
endpoint are stricter than the /acoes and /indices endpoints).
"""

from __future__ import annotations

import re
import sys
import threading
import time
from datetime import datetime, timezone

import httpx

from data_sources.ddm.focus.catalog import focus_url

# 5-minute cache TTL. Focus is published weekly (Friday afternoons BRT),
# so 5 min is well within the freshness window. Cache is single-key (one
# page only, unlike inflation/juros which have per-slug caches).
_CACHE_TTL = 300

_cache: dict[str, tuple[object, float]] = {}

# Thread-safety primitives (mirror ddm/acoes fetcher):
#   _cache_lock             - guards all reads/writes to the _cache dict
#   _concurrency_semaphore  - caps in-flight HTTP requests
_cache_lock = threading.Lock()
_concurrency_semaphore = threading.Semaphore(5)

# Full browser-like headers (Chrome 127 on Windows). CloudFront's WAF on
# the /boletim-focus endpoint rejects bare or identifying bot UAs, so we
# send the complete set of browser headers to look like a real browser.
_BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/127.0.0.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;q=0.9,"
        "image/webp,*/*;q=0.8"
    ),
    "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
}

# Comparison-symbol -> normalized string mapping. The Focus page renders
# the Comp. column with one of three Unicode glyphs:
#   up    -- "BLACK UP-POINTING TRIANGLE"
#   down  -- "BLACK DOWN-POINTING TRIANGLE"
#   flat  -- "EQUALS SIGN"
_COMPARISON_MAP = {
    "up": "up",
    "down": "down",
    "flat": "flat",
}


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


def _parse_int(s: str) -> int | None:
    """Parse a plain integer ('149') -> 149.

    Returns None for empty strings, '--', or unparseable inputs. The
    respondents column is a plain integer (no PT-BR thousands separators
    observed in production), so this is a simple int() call with safety.
    """
    if s is None:
        return None
    s = s.strip()
    if not s or s == "--":
        return None
    try:
        return int(s)
    except (ValueError, TypeError):
        # Some respondents counts are formatted like "149 resp." -- strip
        # any non-digit suffix and retry.
        digits = re.match(r"(\d+)", s)
        if digits:
            return int(digits.group(1))
        return None


def _normalize_comparison(s: str) -> str:
    """Map a raw comparison cell to one of {"up", "down", "flat", ""}.

    The Comp. column on the Focus page uses Unicode triangle glyphs:
        up   -> "\u25b2" (BLACK UP-POINTING TRIANGLE)
        down -> "\u25bc" (BLACK DOWN-POINTING TRIANGLE)
        flat -> "="      (EQUALS SIGN)

    Any unrecognized cell (empty, '--', missing) returns "".
    """
    if not s:
        return ""
    text = _strip_html(s)
    if not text:
        return ""
    if "\u25b2" in text or text.lower() == "up":
        return _COMPARISON_MAP["up"]
    if "\u25bc" in text or text.lower() == "down":
        return _COMPARISON_MAP["down"]
    if text == "=" or text.lower() == "flat":
        return _COMPARISON_MAP["flat"]
    # Some pages render the glyph as the bare word "Alta" / "Baixa" / "Estavel".
    if "alta" in text.lower():
        return _COMPARISON_MAP["up"]
    if "baixa" in text.lower():
        return _COMPARISON_MAP["down"]
    if "estavel" in text.lower() or "est\u00e1vel" in text.lower():
        return _COMPARISON_MAP["flat"]
    return ""


def _find_year_for_table(html: str, table_start: int) -> int | None:
    """Find the year for a table by scanning backwards for the nearest
    preceding heading (<h2> or <h3>) containing a 4-digit year.

    Args:
        html:        The full page HTML.
        table_start: Character offset of the table's opening <table tag.

    Returns:
        The 4-digit year as int, or None if no heading is found.
    """
    # Search the slice of HTML *before* this table for any <h2>...</h2> or
    # <h3>...</h3> containing a 4-digit year. Take the LAST one before
    # the table (nearest preceding heading).
    prefix = html[:table_start]
    # Match <h[23][^>]*>...YYYY...</h[23]> non-greedily.
    matches = list(re.finditer(
        r"<h[23][^>]*>([\s\S]*?)</h[23]>",
        prefix,
    ))
    if not matches:
        # Fallback: look at the page title / first heading anywhere.
        return None
    # Walk matches in reverse (most recent first).
    for m in reversed(matches):
        heading_text = _strip_html(m.group(1))
        year_match = re.search(r"(20\d{2})", heading_text)
        if year_match:
            try:
                return int(year_match.group(1))
            except ValueError:
                continue
    return None


def parse_focus_tables(html: str) -> list[dict]:
    """Parse the 4 yearly tables from the Boletim Focus page.

    Each table is `<table class="normal-table">` with 6 columns:
        Indicador | Ha 4 semanas | 1 sem | Hoje | Comp. | Resp.

    The year for each table is identified by the nearest preceding heading
    (`<h2>` or `<h3>`) that contains a 4-digit year (e.g. "2026"). This is
    robust to layout shifts: DDM may swap the table order, add/remove
    intermediate divs, or wrap tables in <section> tags.

    Returns a list of dicts (in table-row order):
        [{"year": 2026, "indicator": "IPCA", "four_weeks_ago": "5,151%",
          "one_week_ago": "5,150%", "today": "5,200%",
          "comparison": "up", "respondents": 149}, ...]

    Values are preserved as PT-BR strings ("5,151%", "R$ 5,200") so the
    dashboard can render them verbatim without reformatting. The
    `respondents` field is parsed to int (it is a plain count). The
    `comparison` field is normalized to one of "up" / "down" / "flat" / "".
    """
    if not html:
        return []

    # Find all <table ... class="normal-table" ...>...</table> blocks.
    # The class attribute can appear in any position relative to other
    # attributes, so we use a permissive regex.
    table_matches = list(re.finditer(
        r'<table[^>]*class="[^"]*normal-table[^"]*"[^>]*>([\s\S]*?)</table>',
        html,
    ))
    # Fallback: if the class-attribute pattern missed (e.g. class with single
    # quotes or extra attributes), try a more permissive scan.
    if not table_matches:
        table_matches = list(re.finditer(
            r"<table[^>]*>[\s\S]*?</table>",
            html,
        ))

    rows: list[dict] = []
    for tm in table_matches:
        table_html = tm.group(0)
        table_start = tm.start()
        year = _find_year_for_table(html, table_start)
        if year is None:
            # Without a year we cannot key the row, so skip.
            continue

        # Extract <tbody> if present; otherwise parse the whole table body.
        body_match = re.search(r"<tbody[^>]*>([\s\S]*?)</tbody>", table_html)
        body_html = body_match.group(1) if body_match else table_html

        for tr in re.finditer(r"<tr[^>]*>([\s\S]*?)</tr>", body_html):
            cells = re.findall(r"<td[^>]*>([\s\S]*?)</td>", tr.group(1))
            if len(cells) < 6:
                # Header rows, malformed rows, or repeat-header rows.
                continue
            indicator = _strip_html(cells[0])
            if not indicator:
                continue
            # Skip rows that look like header repeats (the first cell may
            # contain "Indicador" or the column-name string).
            if indicator.lower() in ("indicador", "indicador "):
                continue
            row = {
                "year":           year,
                "indicator":      indicator,
                "four_weeks_ago": _strip_html(cells[1]),
                "one_week_ago":   _strip_html(cells[2]),
                "today":          _strip_html(cells[3]),
                "comparison":     _normalize_comparison(cells[4]),
                "respondents":    _parse_int(_strip_html(cells[5])),
            }
            rows.append(row)

    return rows


def fetch_focus_page(force: bool = False) -> dict:
    """Fetch the HTML page for /boletim-focus.

    Args:
        force: Bypass cache.

    Returns:
        {"status": "ok", "html": <str>, "synced_at": <iso>}
        On error: {"status": "error", "error": <str>}

    The fetcher sends full browser-like headers (Chrome 127 on Windows) to
    bypass the CloudFront WAF that guards the boletim-focus endpoint. The
    site rejects bare or identifying bot UAs with a 403, so we use a
    complete header set matching a real browser.
    """
    cache_key = "page:focus"

    with _cache_lock:
        if not force and cache_key in _cache:
            data, ts = _cache[cache_key]
            if time.time() - ts < _CACHE_TTL:
                return data

    url = focus_url()

    _progress(f"[ddm.focus] Fetching boletim-focus page ({url})")

    with _concurrency_semaphore:
        try:
            resp = httpx.get(url, headers=_BROWSER_HEADERS, timeout=30,
                             follow_redirects=True)
            resp.raise_for_status()
        except httpx.HTTPError as e:
            return {"status": "error", "error": f"ddm.focus: {e}"}

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
