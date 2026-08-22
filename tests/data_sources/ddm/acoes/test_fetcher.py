"""tests/data_sources/ddm/acoes/test_fetcher.py - HTML parser tests.

No network access. Uses synthetic HTML that mirrors the DDM acoes page shape:
  - 1 <table id="stocks"> with 5 columns: Ticker | Nome | Negocios |
    Ultima (R$) | Variacao
  - Ticker cell contains <a href="/acoes/petr4">PETR4</a>
  - Negocios uses PT-BR thousands ("52.792.400")
  - Ultima uses PT-BR decimal ("44,30")
  - Variacao has a sign + comma decimal + "%" ("+2,78%" / "-10,85%")

Verifies:
  - _parse_br_int handles PT-BR thousands
  - _parse_br_number handles PT-BR comma decimal
  - _parse_variation handles sign + comma decimal + %
  - parse_stocks_table returns rows in page order with all 5 fields
"""
from __future__ import annotations

from data_sources.ddm.acoes.fetcher import (
    _parse_br_int,
    _parse_br_number,
    _parse_variation,
    parse_stocks_table,
)


# ────────────────────────────────────────────────────────────────────────
# Sample HTML fragments
# ────────────────────────────────────────────────────────────────────────

SAMPLE_ACOES_HTML = """
<table class="normal-table" id="stocks">
  <thead>
    <tr>
      <th>Ticker</th>
      <th>Nome</th>
      <th>Negocios</th>
      <th>Ultima (R$)</th>
      <th>Variacao</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <td><a href="/acoes/petr4">PETR4</a></td>
      <td>Petrobras</td>
      <td>52.792.400</td>
      <td>44,30</td>
      <td>+2,78%</td>
    </tr>
    <tr>
      <td><a href="/acoes/vale3">VALE3</a></td>
      <td>Vale</td>
      <td>38.412.100</td>
      <td>61,45</td>
      <td>-1,32%</td>
    </tr>
    <tr>
      <td><a href="/acoes/itub4">ITUB4</a></td>
      <td>Itau Unibanco</td>
      <td>25.100.500</td>
      <td>33,20</td>
      <td>+0,45%</td>
    </tr>
  </tbody>
</table>
"""


# ────────────────────────────────────────────────────────────────────────
# Helper tests
# ────────────────────────────────────────────────────────────────────────

def test_parse_br_int_basic():
    assert _parse_br_int("52.792.400") == 52792400
    assert _parse_br_int("1.000") == 1000
    assert _parse_br_int("42") == 42


def test_parse_br_int_dash_dash_is_none():
    assert _parse_br_int("--") is None
    assert _parse_br_int("") is None
    assert _parse_br_int(None) is None


def test_parse_br_number_basic():
    assert _parse_br_number("44,30") == 44.30
    assert _parse_br_number("-1,16") == -1.16
    assert _parse_br_number("0,00") == 0.0


def test_parse_br_number_dash_dash_is_none():
    assert _parse_br_number("--") is None
    assert _parse_br_number("") is None
    assert _parse_br_number(None) is None


def test_parse_variation_signed():
    assert _parse_variation("+2,78%") == 2.78
    assert _parse_variation("-10,85%") == -10.85
    assert _parse_variation("+0,00%") == 0.0


def test_parse_variation_strips_pct_only():
    """Without a sign, + is assumed (parseFloat handles it)."""
    assert _parse_variation("2,78%") == 2.78


def test_parse_variation_dash_dash_is_none():
    assert _parse_variation("--") is None
    assert _parse_variation("") is None
    assert _parse_variation(None) is None


# ────────────────────────────────────────────────────────────────────────
# parse_stocks_table tests
# ────────────────────────────────────────────────────────────────────────

def test_parse_stocks_table_returns_rows_in_page_order():
    """DDM pre-sorts by Negocios DESC; parser must preserve page order."""
    rows = parse_stocks_table(SAMPLE_ACOES_HTML)
    assert len(rows) == 3
    tickers = [r["ticker"] for r in rows]
    assert tickers == ["PETR4", "VALE3", "ITUB4"]


def test_parse_stocks_table_fields():
    rows = parse_stocks_table(SAMPLE_ACOES_HTML)
    petr4 = rows[0]
    assert petr4["ticker"] == "PETR4"
    assert petr4["name"] == "Petrobras"
    assert petr4["negocios"] == 52792400
    assert petr4["last_price"] == 44.30
    assert petr4["variation"] == 2.78


def test_parse_stocks_table_negative_variation():
    rows = parse_stocks_table(SAMPLE_ACOES_HTML)
    vale3 = rows[1]
    assert vale3["variation"] == -1.32


def test_parse_stocks_table_strips_anchor_tag():
    """Ticker is inside <a href="/acoes/petr4">PETR4</a> — must extract 'PETR4'."""
    rows = parse_stocks_table(SAMPLE_ACOES_HTML)
    assert rows[0]["ticker"] == "PETR4"
    assert "<a" not in rows[0]["ticker"]


def test_parse_stocks_table_empty_html():
    assert parse_stocks_table("") == []
    assert parse_stocks_table("<html><body>no tables</body></html>") == []


def test_parse_stocks_table_falls_back_to_normal_table_class():
    """If id='stocks' is missing, fall back to the first 'normal-table'."""
    html = """
    <table class="normal-table">
      <thead><tr><th>Ticker</th><th>Nome</th><th>Negocios</th><th>Ultima (R$)</th><th>Variacao</th></tr></thead>
      <tbody>
        <tr><td><a href="/acoes/abcd4">ABCD4</a></td><td>Abcd</td><td>1.000</td><td>10,00</td><td>+1,00%</td></tr>
      </tbody>
    </table>
    """
    rows = parse_stocks_table(html)
    assert len(rows) == 1
    assert rows[0]["ticker"] == "ABCD4"


def test_parse_stocks_table_skips_malformed_rows():
    """Rows with fewer than 5 cells are skipped."""
    html = """
    <table id="stocks">
      <tbody>
        <tr><td>PETR4</td><td>Petrobras</td></tr>
        <tr><td><a href="/acoes/petr4">PETR4</a></td><td>Petrobras</td><td>52.792.400</td><td>44,30</td><td>+2,78%</td></tr>
      </tbody>
    </table>
    """
    rows = parse_stocks_table(html)
    assert len(rows) == 1
    assert rows[0]["ticker"] == "PETR4"
