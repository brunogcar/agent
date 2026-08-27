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
      * [v2] Three value columns ("Ha 4 semanas", "1 sem", "Hoje") parsed to
        float at fetch time using parse_numeric() (handles "5,151%", "R$ 5,200",
        "US$ 76,200"). Stored as REAL in the DB.
      * Comparison column is mapped: up/down/flat ("up"/"down"/"flat").
      * Respondents count parsed as integer.

NO local database writes - this module only fetches + parses.
sync_engine.py stores parsed observations to focus.db.

CloudFront protection note: the boletim-focus page is fronted by
CloudFront and will reject requests with a non-browser User-Agent header.
We send the full Chrome 127 header set (CLOUDFRONT_HEADERS, which includes
Accept-Encoding) to match a real browser as closely as possible. This is
a DISTINCT variant from the BROWSER_HEADERS used by fluxo (which omits
Accept-Encoding).

[Phase 3, Commit 1] Refactored to inherit from `data_sources/ddm/_base/`
(BaseDDMFetcher). The shared _cache / _cache_lock / _concurrency_semaphore
scaffold + the cache-lookup + httpx.get + cache-write pattern now lives
in _base/fetcher_base.py; this module keeps only the parser functions
(which are NOT shared) + a thin fetch_focus_page() wrapper.
[v2] Values now parsed to float at fetch time (C2 fix). Added warning
logging when fallback paths are hit (W2 fix).
"""

from __future__ import annotations

import re
import sys

from data_sources.ddm._base.fetcher_base import CLOUDFRONT_HEADERS, BaseDDMFetcher
from data_sources.ddm._parsers import strip_html
from data_sources.ddm.focus.catalog import focus_url


class _Fetcher(BaseDDMFetcher):
    """Focus-specific fetcher config (SOURCE_NAME for log/error prefix)."""

    SOURCE_NAME = "focus"


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


def _warn(msg: str) -> None:
    """Log a warning to stderr (W2 fix — no more silent data loss)."""
    print(f"[ddm.focus WARNING] {msg}", file=sys.stderr, flush=True)


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


def _parse_numeric(value) -> float | None:
    """Parse a PT-BR formatted value to float (C2 fix — parse at fetch time).

    Handles:
      - "5,151%"      -> 5.151     (percentage, strip %)
      - "R$ 1.234,56" -> 1234.56   (PT-BR currency)
      - "R$ 5,200"    -> 5.2       (PT-BR currency)
      - "US$ -60,000" -> -60000.0  (US-style, comma = thousands)
      - "US$ 76,200"  -> 76200.0   (US-style)
      - "149"         -> 149.0     (plain number)
      - None / "" / "--" -> None

    Delegates to skills.ddm.focus.helpers.parse_numeric (same logic, kept
    in sync). The helpers version is used by the display layer; this one
    is used by the fetcher for DB storage.
    """
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    s = str(value).strip()
    if not s or s in ("--", "-"):
        return None
    # Strip % suffix -- focus wants the raw number, not the decimal form.
    if "%" in s:
        s = s.replace("%", "").strip()
    # US$ values use US-style formatting (comma = thousands).
    # Strip prefix + commas, then parse as float (handles negative sign).
    if "US$" in s:
        s = s.replace("US$", "").strip()
        s = s.replace(",", "")
        try:
            return float(s) if s else None
        except (ValueError, TypeError):
            return None
    # R$ / plain PT-BR values: delegate to the shared parser.
    from data_sources.ddm._parsers import parse_br_number
    return parse_br_number(s)


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
    text = strip_html(s)
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
        heading_text = strip_html(m.group(1))
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
        [{"year": 2026, "indicator": "IPCA", "four_weeks_ago": 5.151,
          "one_week_ago": 5.150, "today": 5.200,
          "comparison": "up", "respondents": 149}, ...]

    [v2] Values are parsed to float at fetch time (C2 fix). Previously
    stored as PT-BR strings ("5,151%", "R$ 5,200").
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
        # [W2 fix] Warn when falling back — could grab the wrong table.
        _warn("normal-table class not found, using fallback (first <table> on page)")
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
            # [W2 fix] Warn when skipping a table due to missing year.
            _warn(f"table at offset {table_start} skipped — no year heading found")
            continue

        # Extract <tbody> if present; otherwise parse the whole table body.
        body_match = re.search(r"<tbody[^>]*>([\s\S]*?)</tbody>", table_html)
        body_html = body_match.group(1) if body_match else table_html

        for tr in re.finditer(r"<tr[^>]*>([\s\S]*?)</tr>", body_html):
            cells = re.findall(r"<td[^>]*>([\s\S]*?)</td>", tr.group(1))
            if len(cells) < 6:
                # Header rows, malformed rows, or repeat-header rows.
                continue
            indicator = strip_html(cells[0])
            if not indicator:
                continue
            # Skip rows that look like header repeats (the first cell may
            # contain "Indicador" or the column-name string).
            if indicator.lower() in ("indicador", "indicador "):
                continue
            row = {
                "year":           year,
                "indicator":      indicator,
                "four_weeks_ago": _parse_numeric(strip_html(cells[1])),
                "one_week_ago":   _parse_numeric(strip_html(cells[2])),
                "today":          _parse_numeric(strip_html(cells[3])),
                "comparison":     _normalize_comparison(cells[4]),
                "respondents":    _parse_int(strip_html(cells[5])),
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

    The fetcher sends full browser-like headers (Chrome 127 on Windows,
    CLOUDFRONT_HEADERS variant with Accept-Encoding) to bypass the
    CloudFront WAF that guards the boletim-focus endpoint. The site
    rejects bare or identifying bot UAs with a 403, so we use a complete
    header set matching a real browser.
    """
    return _Fetcher.fetch_page(
        url=focus_url(),
        cache_key="page:focus",
        headers=CLOUDFRONT_HEADERS,
        slug=None,
        force=force,
    )


def clear_cache():
    """Clear the in-memory cache (thread-safe)."""
    _Fetcher.clear_cache()
