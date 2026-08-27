"""tests/data_sources/ddm/focus/test_fetcher.py - HTML parser tests.

No network access. Uses synthetic HTML that mirrors the DDM boletim-focus
page shape:
  - 4 <table class="normal-table"> blocks (one per target year)
  - Each table preceded by an <h2> or <h3> heading containing the year
  - 6 columns: Indicador | Ha 4 semanas | 1 sem | Hoje | Comp. | Resp.
  - Values are PT-BR formatted strings ("5,151%", "R$ 5,200")
  - Comparison column uses Unicode glyphs (up/down/=)

Verifies:
  - _parse_int parses plain integers + strips non-digit suffixes
  - _normalize_comparison maps glyphs -> "up"/"down"/"flat"/""
  - parse_focus_tables returns rows with the right year + fields
  - Year is correctly identified from preceding heading (h2 or h3)
  - Empty / malformed HTML is handled gracefully
"""
from __future__ import annotations

from data_sources.ddm.focus.fetcher import (
    _parse_int,
    _normalize_comparison,
    strip_html,
    _find_year_for_table,
    parse_focus_tables,
)


# ────────────────────────────────────────────────────────────────────────
# Sample HTML fragments
# ────────────────────────────────────────────────────────────────────────

SAMPLE_FOCUS_HTML = """
<html>
<head><title>Boletim Focus</title></head>
<body>
  <h1>Boletim Focus</h1>

  <h2>Expectativas de mercado para 2026</h2>
  <table class="normal-table">
    <thead>
      <tr>
        <th>Indicador</th>
        <th>Ha 4 semanas</th>
        <th>1 sem</th>
        <th>Hoje</th>
        <th>Comp.</th>
        <th>Resp.</th>
      </tr>
    </thead>
    <tbody>
      <tr>
        <td>IPCA</td>
        <td>5,151%</td>
        <td>5,150%</td>
        <td>5,200%</td>
        <td>\u25b2</td>
        <td>149</td>
      </tr>
      <tr>
        <td>PIB Total</td>
        <td>2,10%</td>
        <td>2,05%</td>
        <td>2,00%</td>
        <td>\u25bc</td>
        <td>140</td>
      </tr>
      <tr>
        <td>Cambio</td>
        <td>R$ 5,200</td>
        <td>R$ 5,250</td>
        <td>R$ 5,180</td>
        <td>=</td>
        <td>155</td>
      </tr>
    </tbody>
  </table>

  <h3>Expectativas para 2027</h3>
  <table class="normal-table">
    <thead>
      <tr>
        <th>Indicador</th><th>Ha 4 semanas</th><th>1 sem</th>
        <th>Hoje</th><th>Comp.</th><th>Resp.</th>
      </tr>
    </thead>
    <tbody>
      <tr>
        <td>IPCA</td>
        <td>4,00%</td>
        <td>4,10%</td>
        <td>4,05%</td>
        <td>=</td>
        <td>130</td>
      </tr>
      <tr>
        <td>Selic</td>
        <td>9,50%</td>
        <td>9,25%</td>
        <td>9,00%</td>
        <td>\u25bc</td>
        <td>120</td>
      </tr>
    </tbody>
  </table>
</body>
</html>
"""


# ────────────────────────────────────────────────────────────────────────
# Helper tests
# ────────────────────────────────────────────────────────────────────────

def test_parse_int_basic():
    assert _parse_int("149") == 149
    assert _parse_int("0") == 0
    assert _parse_int("1499") == 1499


def test_parse_int_strips_suffix():
    """Some respondents cells may render '149 resp.' -- strip the suffix."""
    assert _parse_int("149 resp.") == 149
    assert _parse_int("120 respondentes") == 120


def test_parse_int_dash_dash_is_none():
    assert _parse_int("--") is None
    assert _parse_int("") is None
    assert _parse_int(None) is None


def test_normalize_comparison_up_triangle():
    """Up triangle -> 'up'."""
    assert _normalize_comparison("\u25b2") == "up"
    assert _normalize_comparison(" \u25b2 ") == "up"


def test_normalize_comparison_down_triangle():
    """Down triangle -> 'down'."""
    assert _normalize_comparison("\u25bc") == "down"


def test_normalize_comparison_equals():
    """Equals sign -> 'flat'."""
    assert _normalize_comparison("=") == "flat"


def test_normalize_comparison_word_fallbacks():
    """Some pages render the glyph as 'Alta' / 'Baixa' / 'Estavel'."""
    assert _normalize_comparison("Alta") == "up"
    assert _normalize_comparison("Baixa") == "down"
    assert _normalize_comparison("Estavel") == "flat"


def test_normalize_comparison_empty_returns_empty():
    assert _normalize_comparison("") == ""
    assert _normalize_comparison(None) == ""
    assert _normalize_comparison("--") == ""


def test_strip_html_strips_anchor_and_tags():
    """Indicator names may be wrapped in <a href="/focus/ipca">IPCA</a>."""
    assert strip_html('<a href="/focus/ipca">IPCA</a>') == "IPCA"
    assert strip_html("  hello   world  ") == "hello world"
    assert strip_html("<b>Balanca</b>") == "Balanca"


# ────────────────────────────────────────────────────────────────────────
# _find_year_for_table tests
# ────────────────────────────────────────────────────────────────────────

def test_find_year_for_table_h2():
    """Find the year from the nearest preceding <h2>."""
    html = '<h2>Expectativas para 2026</h2><table class="normal-table">'
    pos = html.find('<table')
    assert _find_year_for_table(html, pos) == 2026


def test_find_year_for_table_h3():
    """Find the year from the nearest preceding <h3>."""
    html = '<h3>2027</h3><table class="normal-table">'
    pos = html.find('<table')
    assert _find_year_for_table(html, pos) == 2027


def test_find_year_for_table_returns_none_without_heading():
    """No preceding heading -> None."""
    html = '<table class="normal-table">'
    pos = html.find('<table')
    assert _find_year_for_table(html, pos) is None


def test_find_year_for_table_picks_nearest_heading():
    """When multiple headings precede a table, pick the nearest one."""
    html = ('<h2>2026</h2>some text<h2>2027</h2>'
            '<table class="normal-table">')
    pos = html.find('<table')
    assert _find_year_for_table(html, pos) == 2027


# ────────────────────────────────────────────────────────────────────────
# parse_focus_tables tests
# ────────────────────────────────────────────────────────────────────────

def test_parse_focus_tables_returns_rows_per_table():
    """The sample HTML has 2 tables -> 5 rows total (3 + 2)."""
    rows = parse_focus_tables(SAMPLE_FOCUS_HTML)
    assert len(rows) == 5


def test_parse_focus_tables_extracts_year_from_heading():
    """Year is correctly identified from the preceding heading."""
    rows = parse_focus_tables(SAMPLE_FOCUS_HTML)
    years = {r["year"] for r in rows}
    assert years == {2026, 2027}


def test_parse_focus_tables_year_assignment_per_row():
    """Each row carries the year of the table it came from."""
    rows = parse_focus_tables(SAMPLE_FOCUS_HTML)
    by_year = {}
    for r in rows:
        by_year.setdefault(r["year"], []).append(r["indicator"])
    assert by_year[2026] == ["IPCA", "PIB Total", "Cambio"]
    assert by_year[2027] == ["IPCA", "Selic"]


def test_parse_focus_tables_preserves_value_strings():
    """[v2] Values are now parsed to float at fetch time (C2 fix).

    Previously values were stored as PT-BR strings ("5,151%"). Now they're
    parsed to float (5.151) using _parse_numeric() — stored as REAL in DB.
    """
    rows = parse_focus_tables(SAMPLE_FOCUS_HTML)
    ipca_2026 = next(r for r in rows if r["year"] == 2026
                     and r["indicator"] == "IPCA")
    assert ipca_2026["four_weeks_ago"] == 5.151
    assert ipca_2026["one_week_ago"] == 5.150
    assert ipca_2026["today"] == 5.200
    assert ipca_2026["respondents"] == 149


def test_parse_focus_tables_preserves_currency_strings():
    """[v2] Currency values like 'R$ 5,200' parsed to float (5.2).

    Previously stored as PT-BR strings. Now parsed via _parse_numeric().
    """
    rows = parse_focus_tables(SAMPLE_FOCUS_HTML)
    cambio = next(r for r in rows if r["indicator"] == "Cambio")
    assert cambio["four_weeks_ago"] == 5.2
    assert cambio["today"] == 5.18


def test_parse_focus_tables_comparison_normalization():
    """Comparison column is normalized: up/down/flat."""
    rows = parse_focus_tables(SAMPLE_FOCUS_HTML)
    ipca = next(r for r in rows if r["year"] == 2026
                and r["indicator"] == "IPCA")
    assert ipca["comparison"] == "up"
    pib = next(r for r in rows if r["year"] == 2026
               and r["indicator"] == "PIB Total")
    assert pib["comparison"] == "down"
    cambio = next(r for r in rows if r["indicator"] == "Cambio")
    assert cambio["comparison"] == "flat"


def test_parse_focus_tables_empty_html():
    assert parse_focus_tables("") == []
    assert parse_focus_tables("<html><body>no tables</body></html>") == []


def test_parse_focus_tables_skips_malformed_rows():
    """Rows with fewer than 6 cells are skipped."""
    html = """
    <h2>2026</h2>
    <table class="normal-table">
      <tbody>
        <tr><td>IPCA</td><td>5,151%</td></tr>
        <tr><td>IPCA</td><td>5,151%</td><td>5,150%</td><td>5,200%</td>
            <td>\u25b2</td><td>149</td></tr>
      </tbody>
    </table>
    """
    rows = parse_focus_tables(html)
    assert len(rows) == 1
    assert rows[0]["indicator"] == "IPCA"


def test_parse_focus_tables_skips_header_repeat_rows():
    """Header-repeat rows (first cell == 'Indicador') are skipped."""
    html = """
    <h2>2026</h2>
    <table class="normal-table">
      <tbody>
        <tr><td>Indicador</td><td>Ha 4 semanas</td><td>1 sem</td>
            <td>Hoje</td><td>Comp.</td><td>Resp.</td></tr>
        <tr><td>IPCA</td><td>5,151%</td><td>5,150%</td><td>5,200%</td>
            <td>\u25b2</td><td>149</td></tr>
      </tbody>
    </table>
    """
    rows = parse_focus_tables(html)
    assert len(rows) == 1
    assert rows[0]["indicator"] == "IPCA"


def test_parse_focus_tables_handles_h3_year_heading():
    """Year can be in an <h3> instead of an <h2>."""
    rows = parse_focus_tables(SAMPLE_FOCUS_HTML)
    rows_2027 = [r for r in rows if r["year"] == 2027]
    assert len(rows_2027) == 2
    assert rows_2027[0]["indicator"] == "IPCA"
    assert rows_2027[1]["indicator"] == "Selic"
