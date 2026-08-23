"""tests/data_sources/ddm/inflation/test_fetcher.py - HTML parser tests.

No network access. Uses synthetic HTML that mirrors the DDM page shape:
  - 2 <table> blocks per page
  - Table 1: id="index-values" monthly matrix (year x month)
  - Table 2: class="normal-table" historical monthly (DESC rows)

Verifies:
  - parse_mes_ano normalizes 'Jul/2026' -> '2026-07'
  - parse_br_number handles comma decimal + '--' -> None
  - parse_historical_table returns ASC rows with all 4 fields
  - parse_monthly_matrix extracts year list + month labels + matrix dict
"""
from __future__ import annotations

from data_sources.ddm.inflation.fetcher import (
    parse_br_number,
    parse_mes_ano,
    _parse_data_value,
    parse_historical_table,
    parse_monthly_matrix,
)


# ────────────────────────────────────────────────────────────────────────
# Sample HTML fragments
# ────────────────────────────────────────────────────────────────────────

SAMPLE_MATRIX_HTML = """
<table id="index-values">
  <thead>
    <tr>
      <th>Ano</th><th>Jan</th><th>Fev</th><th>Mar</th>
      <th>Abr</th><th>Mai</th><th>Jun</th><th>Jul</th>
      <th>Ago</th><th>Set</th><th>Out</th><th>Nov</th>
      <th>Dez</th><th>Ano</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <td>2026</td>
      <td class="right" data-value="0.41">0,41%</td>
      <td class="right" data-value="0.78">0,78%</td>
      <td class="right" data-value="0.55">0,55%</td>
      <td class="right" data-value="0.32">0,32%</td>
      <td class="right" data-value="-0.12">-0,12%</td>
      <td class="right" data-value="0.18">0,18%</td>
      <td class="right" data-value="-1.16">-1,16%</td>
      <td class="right">--</td>
      <td class="right">--</td>
      <td class="right">--</td>
      <td class="right">--</td>
      <td class="right">--</td>
      <td class="right" data-value="0.94">0,94%</td>
    </tr>
    <tr>
      <td>2025</td>
      <td class="right" data-value="0.42">0,42%</td>
      <td class="right" data-value="0.80">0,80%</td>
      <td class="right" data-value="0.56">0,56%</td>
      <td class="right" data-value="0.30">0,30%</td>
      <td class="right" data-value="0.05">0,05%</td>
      <td class="right" data-value="0.22">0,22%</td>
      <td class="right" data-value="-0.99">-0,99%</td>
      <td class="right" data-value="0.10">0,10%</td>
      <td class="right" data-value="0.45">0,45%</td>
      <td class="right" data-value="0.33">0,33%</td>
      <td class="right" data-value="0.48">0,48%</td>
      <td class="right" data-value="0.62">0,62%</td>
      <td class="right" data-value="4.36">4,36%</td>
    </tr>
  </tbody>
</table>
"""

SAMPLE_HISTORICAL_HTML = """
<table class="normal-table">
  <thead>
    <tr>
      <th>Mes/Ano</th>
      <th>Indice do mes (%)</th>
      <th>Acumulado no ano (%)</th>
      <th>Acumulado 12 meses (%)</th>
    </tr>
  </thead>
  <tbody>
    <tr><td>Jul/2026</td><td>-1,16</td><td>0,94</td><td>5,88</td></tr>
    <tr><td>Jun/2026</td><td>0,18</td><td>2,13</td><td>7,03</td></tr>
    <tr><td>Mai/2026</td><td>-0,12</td><td>1,94</td><td>8,21</td></tr>
    <tr><td>Abr/2026</td><td>0,32</td><td>2,06</td><td>8,66</td></tr>
  </tbody>
</table>
"""

SAMPLE_PAGE_HTML = SAMPLE_MATRIX_HTML + "\n" + SAMPLE_HISTORICAL_HTML


# ────────────────────────────────────────────────────────────────────────
# Helper tests
# ────────────────────────────────────────────────────────────────────────

def test_parse_mes_ano_basic():
    assert parse_mes_ano("Jul/2026") == "2026-07"
    assert parse_mes_ano("Jan/2025") == "2025-01"
    assert parse_mes_ano("Dez/2024") == "2024-12"


def test_parse_mes_ano_invalid():
    assert parse_mes_ano("") == ""
    assert parse_mes_ano("garbage") == ""
    assert parse_mes_ano("13/2026") == ""  # not a 3-letter month abbreviation


def test_parse_br_number_basic():
    assert parse_br_number("0,41") == 0.41
    assert parse_br_number("-1,16") == -1.16
    assert parse_br_number("3,12") == 3.12


def test_parse_br_number_dash_dash_is_none():
    """Boundary contract: '--' is the DDM missing-value marker."""
    assert parse_br_number("--") is None
    assert parse_br_number("") is None
    assert parse_br_number(None) is None


def test_parse_data_value_attribute():
    td = '<td class="right" data-value="0.41">0,41%</td>'
    assert _parse_data_value(td) == 0.41


def test_parse_data_value_dash_dash_is_none():
    td = '<td class="right">--</td>'
    assert _parse_data_value(td) is None


# ────────────────────────────────────────────────────────────────────────
# Historical-table parser tests
# ────────────────────────────────────────────────────────────────────────

def test_parse_historical_table_returns_ascending():
    """DDM rows are DESC (Jul/2026 first); parser must reverse to ASC."""
    rows = parse_historical_table(SAMPLE_PAGE_HTML)
    assert len(rows) == 4
    ref_dates = [r["ref_date"] for r in rows]
    assert ref_dates == ["2026-04", "2026-05", "2026-06", "2026-07"]


def test_parse_historical_table_fields():
    rows = parse_historical_table(SAMPLE_PAGE_HTML)
    latest = rows[-1]  # Jul/2026 after ascending sort
    assert latest["ref_date"] == "2026-07"
    assert latest["month_value"] == -1.16
    assert latest["year_acumulado"] == 0.94
    assert latest["acumulado_12m"] == 5.88


def test_parse_historical_table_empty_html():
    assert parse_historical_table("") == []
    assert parse_historical_table("<html><body>no tables</body></html>") == []


def test_parse_historical_table_single_table_returns_empty():
    """Parser expects >= 2 tables; a page with only 1 returns []."""
    assert parse_historical_table(SAMPLE_MATRIX_HTML) == []


# ────────────────────────────────────────────────────────────────────────
# Monthly-matrix parser tests
# ────────────────────────────────────────────────────────────────────────

def test_parse_monthly_matrix_years_desc():
    result = parse_monthly_matrix(SAMPLE_PAGE_HTML)
    assert result["years"] == [2026, 2025]


def test_parse_monthly_matrix_header():
    result = parse_monthly_matrix(SAMPLE_PAGE_HTML)
    # First header cell is "Ano" (year label).
    assert result["months"][0] == "Ano"
    # Last header cell is also "Ano" (year acumulado).
    assert result["months"][-1] == "Ano"
    # Middle cells are Jan..Dez.
    assert result["months"][1:13] == ["Jan", "Fev", "Mar", "Abr", "Mai",
                                      "Jun", "Jul", "Ago", "Set", "Out",
                                      "Nov", "Dez"]


def test_parse_monthly_matrix_data_values():
    result = parse_monthly_matrix(SAMPLE_PAGE_HTML)
    row_2026 = result["matrix"][2026]
    assert row_2026["Jan"] == 0.41
    assert row_2026["Jul"] == -1.16
    # Aug-Dec 2026 are missing ("--").
    assert row_2026["Ago"] is None
    assert row_2026["Dez"] is None
    # Final "Ano" column = year acumulado.
    assert row_2026["Ano"] == 0.94


def test_parse_monthly_matrix_empty_html():
    result = parse_monthly_matrix("")
    assert result == {"years": [], "months": [], "matrix": {}}
