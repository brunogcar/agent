"""data_sources/ddm/juros/fetcher.py -- HTTP fetcher + HTML parser for DDM Juros.

Handles:
  - HTTP GET to www.dadosdemercado.com.br/indices/{slug} (no auth, no JS)
  - Server-rendered HTML response cached 5 min (per slug, thread-safe Lock)
  - Regex-based parser (no BeautifulSoup dependency):
      * parse_matrix_only(html)              -- year x month matrix dict
                                                (NO "Ano" column - 12 months only)
      * flatten_matrix_to_observations(m)    -- DERIVE the historical series
  - Boundary normalizations:
      * "Jul" (cell label) -> "07"        (ref_date month component)
      * "0,41"             -> 0.41        (Brazilian comma decimal)
      * "--"               -> None        (missing values)

Unlike inflation pages, juros pages do NOT ship a historical monthly table.
The matrix is the ONLY data source. The historical series (month_value,
media_no_ano, media_12m) is DERIVED from the matrix at parse time:

  - month_value   = cell value (daily rate % for that month)
  - media_no_ano  = AVERAGE of all months in same year UP TO that month
                    (year-to-date average)
  - media_12m     = AVERAGE of the last 12 months (rolling)

These match the Google Sheet formulas:
  - "Media no ano (%)":     AVERAGE(FILTER(B:B, YEAR(A:A)=YEAR(d), A:A<=d))
  - "Media 12 meses (%)":   AVERAGE(FILTER(B:B, A:A<=d, A:A>=d-365))

NO local database writes - this module only fetches + parses.
sync_engine.py stores derived observations to juros.db.

[Phase 3, Commit 1] Refactored to inherit from `data_sources/ddm/_base/`
(BaseDDMFetcher). The shared _cache / _cache_lock / _concurrency_semaphore
scaffold + the cache-lookup + httpx.get + cache-write pattern now lives
in _base/fetcher_base.py; this module keeps only the parser functions
(which are NOT shared) + a thin fetch_juros_page() wrapper.
"""

from __future__ import annotations

import re
from statistics import mean

from data_sources.ddm._base.fetcher_base import BOT_HEADERS, BaseDDMFetcher
from data_sources.ddm._parsers import (
    parse_br_number,
    strip_html,
)
from data_sources.ddm.juros.catalog import index_url


class _Fetcher(BaseDDMFetcher):
    """Juros-specific fetcher config (SOURCE_NAME for log/error prefix)."""

    SOURCE_NAME = "juros"


# Portuguese month abbreviations used by DDM in the matrix header.
_MONTHS_PT = {
    "Jan": "01", "Fev": "02", "Mar": "03", "Abr": "04",
    "Mai": "05", "Jun": "06", "Jul": "07", "Ago": "08",
    "Set": "09", "Out": "10", "Nov": "11", "Dez": "12",
}

# Canonical month order (used to filter non-month columns out of the matrix).
_MONTH_ORDER = ["Jan", "Fev", "Mar", "Abr", "Mai", "Jun",
                "Jul", "Ago", "Set", "Out", "Nov", "Dez"]


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


def parse_matrix_only(html: str) -> dict:
    """Parse the monthly matrix table (the ONLY table on a DDM juros page).

    Selic / CDI / Meta-Selic pages ship just 1 table with id="index-values":
      Rows = years, Columns = Jan..Dez (12 columns only, NO "Ano" column).

    Returns:
        {"years":  [<int>, ...],                  # newest year first
         "months": ["Jan", "Fev", ..., "Dez"],    # 12 entries, no "Ano"
         "matrix": {<year_int>: {"Jan": <float|None>, ..., "Dez": <float|None>}}}

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

    # Strip the leading year-label column (DDM uses an empty <th></th> corner
    # OR a labeled "Ano" header for the year column). Keep ONLY the 12
    # canonical month labels (Jan..Dez). Filter out any non-month labels
    # (e.g. "Ano" if it accidentally slipped in - juros pages shouldn't
    # have one, but be defensive).
    cleaned_months: list[str] = []
    for label in months:
        if label in _MONTH_ORDER:
            cleaned_months.append(label)
    if not cleaned_months:
        cleaned_months = list(_MONTH_ORDER)

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
        # Walk the remaining cells and place them under the next month label
        # in cleaned_months. Skip non-canonical columns defensively.
        for i, cell in enumerate(cells[1:], start=0):
            if i >= len(cleaned_months):
                break
            label = cleaned_months[i]
            row[label] = _parse_data_value(cell)
        years.append(year)
        matrix[year] = row

    # Sort years descending (DDM shows newest year first).
    years.sort(reverse=True)
    return {"years": years, "months": cleaned_months, "matrix": matrix}


def flatten_matrix_to_observations(matrix: dict) -> list[dict]:
    """DERIVE the historical series from the monthly matrix.

    The juros pages do NOT ship a historical table - only the year x month
    matrix. This function flattens the matrix into a sorted list of monthly
    observations and computes the two derived averages:

      - month_value   = cell value (daily rate % for that month)
      - media_no_ano  = AVERAGE of all months in the same year UP TO that
                        month (year-to-date average).
                        Matches: AVERAGE(FILTER(B:B, YEAR(A:A)=YEAR(d), A:A<=d))
      - media_12m     = AVERAGE of the last 12 months INCLUDING the current
                        month (rolling 12-month average).
                        Matches: AVERAGE(FILTER(B:B, A:A<=d, A:A>=d-365))

    For the first 11 months of the catalog (no full 12-month window yet),
    media_12m uses the available months (NOT None) - this matches the
    Google Sheet formula which averages whatever rows match the filter
    (could be fewer than 12 at the start of the series).

    Returns a list of dicts sorted ASCENDING by ref_date:
      [{"ref_date": "YYYY-MM", "month_value": <float|None>,
        "media_no_ano": <float|None>, "media_12m": <float|None>}, ...]
    """
    if not matrix:
        return []

    years_all = matrix.get("years") or []
    matrix_data = matrix.get("matrix") or {}
    months = matrix.get("months") or list(_MONTH_ORDER)

    # Build a flat list of (ref_date, month_value) sorted ASC.
    # Iterate years ascending so the rolling average sees the right order.
    flat: list[tuple[str, float | None]] = []
    for year in sorted(years_all):
        row = matrix_data.get(year, {})
        for mon in _MONTH_ORDER:
            if mon not in months:
                continue
            # Skip cells that are missing (None) - they don't exist in the
            # timeline yet (e.g. Aug-Dec 2026 if today is Jul/2026).
            val = row.get(mon)
            if val is None:
                continue
            mm = _MONTHS_PT.get(mon, "")
            if not mm:
                continue  # unknown month abbreviation — skip row
            flat.append((f"{year}-{mm}", val))

    if not flat:
        return []

    # Sort ascending by ref_date (year-asc, then month-asc).
    flat.sort(key=lambda x: x[0])

    observations: list[dict] = []
    for i, (ref_date, val) in enumerate(flat):
        year_str = ref_date.split("-")[0]

        # media_no_ano: average of all months in same year UP TO this one.
        same_year_vals: list[float] = []
        for j in range(i + 1):
            prev_date, prev_val = flat[j]
            if prev_date.startswith(f"{year_str}-") and prev_val is not None:
                same_year_vals.append(prev_val)
        media_no_ano = mean(same_year_vals) if same_year_vals else None

        # media_12m: average of the last 12 months INCLUDING current.
        # Slice the flat list to [max(0, i-11), i+1] and average all non-None.
        window_start = max(0, i - 11)
        window_vals: list[float] = []
        for j in range(window_start, i + 1):
            _, w_val = flat[j]
            if w_val is not None:
                window_vals.append(w_val)
        media_12m = mean(window_vals) if window_vals else None

        observations.append({
            "ref_date":     ref_date,
            "month_value":  val,
            "media_no_ano": media_no_ano,
            "media_12m":    media_12m,
        })

    return observations


def fetch_juros_page(slug: str, force: bool = False) -> dict:
    """Fetch the HTML page for an index.

    Args:
        slug:  DDM juros slug (e.g. 'selic').
        force: Bypass cache.

    Returns:
        {"status": "ok", "slug": <str>, "html": <str>, "synced_at": <iso>}
    """
    return _Fetcher.fetch_page(
        url=index_url(slug),
        cache_key=f"page:{slug}",
        headers=BOT_HEADERS,
        slug=slug,
        force=force,
    )


def clear_cache():
    """Clear the in-memory cache (thread-safe)."""
    _Fetcher.clear_cache()
