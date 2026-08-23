"""tests/data_sources/ddm/dividends/test_fetcher.py - HTML parser tests.

No network access. Uses synthetic HTML that mirrors the DDM dividends page
shape:
  - 1 <table class="normal-table"> block
  - Header: Codigo | Tipo | Valor (R$) | Registro | Ex | Pagamento (6 cols)
  - Body rows: <td><strong><a href="/acoes/bbdc3">BBDC3</a></strong></td>
               + 5 plain-text <td> cells

Verifies:
  - parse_br_number handles comma decimal + '--' -> None
  - parse_br_date_iso converts DD/MM/YYYY -> YYYY-MM-DD
  - parse_dividends_table returns rows with the right shape + types
  - parse_dividends_table handles empty HTML + missing <a> tag fallback
"""
from __future__ import annotations

from data_sources.ddm.dividends.fetcher import (
    parse_br_number, parse_br_date_iso, _extract_ticker,
    parse_dividends_table,
)


# ────────────────────────────────────────────────────────────────────────
# Sample HTML fragments
# ────────────────────────────────────────────────────────────────────────

# DDM dividends page shape: 1 table (class="normal-table"). Header has
# 6 columns: Codigo | Tipo | Valor (R$) | Registro | Ex | Pagamento.
# Body rows wrap the ticker in <strong><a href="/acoes/bbdc3">BBDC3</a></strong>.
SAMPLE_DIVIDENDS_HTML = """
<table class="normal-table">
  <thead>
    <tr>
      <th>Codigo</th><th>Tipo</th><th>Valor (R$)</th>
      <th>Registro</th><th>Ex</th><th>Pagamento</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <td><strong><a href="/acoes/bbdc3">BBDC3</a></strong></td>
      <td>Dividendo</td>
      <td>0,017250</td>
      <td>01/07/2026</td>
      <td>02/07/2026</td>
      <td>03/08/2026</td>
    </tr>
    <tr>
      <td><strong><a href="/acoes/petr4">PETR4</a></strong></td>
      <td>JCP</td>
      <td>7,960000</td>
      <td>15/06/2026</td>
      <td>16/06/2026</td>
      <td>30/07/2026</td>
    </tr>
    <tr>
      <td><strong><a href="/acoes/vale3">VALE3</a></strong></td>
      <td>Dividendo</td>
      <td>0,006000</td>
      <td>10/12/2026</td>
      <td>11/12/2026</td>
      <td>15/01/2027</td>
    </tr>
  </tbody>
</table>
"""


SAMPLE_DIVIDENDS_HTML_NO_A_TAG = """
<table class="normal-table">
  <tbody>
    <tr>
      <td><strong>ITUB4</strong></td>
      <td>Dividendo</td>
      <td>0,500000</td>
      <td>05/03/2026</td>
      <td>06/03/2026</td>
      <td>10/04/2026</td>
    </tr>
  </tbody>
</table>
"""


# ────────────────────────────────────────────────────────────────────────
# Helper tests
# ────────────────────────────────────────────────────────────────────────

def test_parse_br_number_basic():
    assert parse_br_number("0,017250") == 0.017250
    assert parse_br_number("7,960000") == 7.96
    assert parse_br_number("0,006") == 0.006


def test_parse_br_number_dash_dash_is_none():
    """Boundary contract: '--' is the DDM missing-value marker."""
    assert parse_br_number("--") is None
    assert parse_br_number("") is None
    assert parse_br_number(None) is None


def test_parse_br_date_basic():
    """DD/MM/YYYY -> YYYY-MM-DD."""
    assert parse_br_date_iso("01/07/2026") == "2026-07-01"
    assert parse_br_date_iso("15/06/2026") == "2026-06-15"
    assert parse_br_date_iso("10/12/2026") == "2026-12-10"


def test_parse_br_date_invalid():
    """Unparseable inputs return empty string.

    Note: the shared parser also accepts ISO YYYY-MM-DD as passthrough
    (returns the same string), so '2026-07-01' is NOT treated as invalid.
    """
    assert parse_br_date_iso("") == ""
    assert parse_br_date_iso(None) == ""
    assert parse_br_date_iso("2026-07-01") == "2026-07-01"  # ISO passthrough
    assert parse_br_date_iso("not-a-date") == ""


def test_extract_ticker_from_anchor():
    """Ticker extracted from <a href="/acoes/bbdc3">BBDC3</a>."""
    td = '<strong><a href="/acoes/bbdc3">BBDC3</a></strong>'
    assert _extract_ticker(td) == "BBDC3"


def test_extract_ticker_fallback_no_anchor():
    """When the <a> tag is missing, fall back to stripped HTML text."""
    td = '<strong>ITUB4</strong>'
    assert _extract_ticker(td) == "ITUB4"


# ────────────────────────────────────────────────────────────────────────
# parse_dividends_table tests
# ────────────────────────────────────────────────────────────────────────

def test_parse_dividends_table_returns_3_rows():
    result = parse_dividends_table(SAMPLE_DIVIDENDS_HTML)
    assert len(result) == 3


def test_parse_dividends_table_row_shape():
    """Each row has all 6 fields: ticker, tipo, value, record_date, ex_date,
    payment_date."""
    result = parse_dividends_table(SAMPLE_DIVIDENDS_HTML)
    first = result[0]
    assert set(first.keys()) == {
        "ticker", "tipo", "value",
        "record_date", "ex_date", "payment_date",
    }


def test_parse_dividends_table_first_row_values():
    """Verify the BBDC3 row has the right values."""
    result = parse_dividends_table(SAMPLE_DIVIDENDS_HTML)
    first = result[0]
    assert first["ticker"] == "BBDC3"
    assert first["tipo"] == "Dividendo"
    assert first["value"] == 0.017250
    assert first["record_date"] == "2026-07-01"
    assert first["ex_date"] == "2026-07-02"
    assert first["payment_date"] == "2026-08-03"


def test_parse_dividends_table_jcp_row():
    """The PETR4 row is JCP with value 7.96."""
    result = parse_dividends_table(SAMPLE_DIVIDENDS_HTML)
    petr4 = next(r for r in result if r["ticker"] == "PETR4")
    assert petr4["tipo"] == "JCP"
    assert petr4["value"] == 7.96


def test_parse_dividends_table_value_range_extremes():
    """The smallest value (0.006) and largest value (7.96) round-trip
    through the parser without losing precision."""
    result = parse_dividends_table(SAMPLE_DIVIDENDS_HTML)
    values = [r["value"] for r in result]
    assert min(values) == 0.006
    assert max(values) == 7.96


def test_parse_dividends_table_no_a_tag_fallback():
    """When the ticker cell has no <a> tag, _extract_ticker falls back to
    stripped HTML text."""
    result = parse_dividends_table(SAMPLE_DIVIDENDS_HTML_NO_A_TAG)
    assert len(result) == 1
    assert result[0]["ticker"] == "ITUB4"


def test_parse_dividends_table_empty_html():
    """Empty HTML returns an empty list."""
    assert parse_dividends_table("") == []


def test_parse_dividends_table_no_table_returns_empty():
    """HTML without a <table> tag returns an empty list."""
    assert parse_dividends_table("<html><body>no table here</body></html>") == []


def test_parse_dividends_table_skips_short_rows():
    """Rows with fewer than 6 cells are skipped."""
    html = """
    <table class="normal-table">
      <tbody>
        <tr>
          <td><a href="/acoes/bbdc3">BBDC3</a></td>
          <td>Dividendo</td>
          <td>0,017250</td>
        </tr>
        <tr>
          <td><strong><a href="/acoes/petr4">PETR4</a></strong></td>
          <td>JCP</td>
          <td>7,960000</td>
          <td>15/06/2026</td>
          <td>16/06/2026</td>
          <td>30/07/2026</td>
        </tr>
      </tbody>
    </table>
    """
    result = parse_dividends_table(html)
    assert len(result) == 1
    assert result[0]["ticker"] == "PETR4"


def test_parse_dividends_table_finds_table_by_class():
    """When multiple <table> tags exist, the one with class 'normal-table'
    is preferred."""
    html = """
    <table class="other-table">
      <tbody><tr><td>not this one</td></tr></tbody>
    </table>
    <table class="normal-table">
      <tbody>
        <tr>
          <td><a href="/acoes/bbdc3">BBDC3</a></td>
          <td>Dividendo</td>
          <td>0,017250</td>
          <td>01/07/2026</td>
          <td>02/07/2026</td>
          <td>03/08/2026</td>
        </tr>
      </tbody>
    </table>
    """
    result = parse_dividends_table(html)
    assert len(result) == 1
    assert result[0]["ticker"] == "BBDC3"
