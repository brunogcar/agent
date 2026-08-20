"""tests/data_sources/ddm/poupanca/test_fetcher.py - HTML parser tests.

No network access. Uses synthetic HTML that mirrors the DDM poupanca page
shape:
  - 1 <table> block per page (id="index-values")
  - Header: year corner + Jan..Dez (12 columns, NO "Ano")
  - Body rows: <td>year</td> + <td data-value="...">...</td> x12

Verifies:
  - _parse_br_number handles comma decimal + '--' -> None
  - parse_matrix_only returns years + month labels (12 only, no "Ano") +
    matrix
  - flatten_matrix_to_observations derives month_value + acumulado_no_ano +
    acumulado_12m from the matrix correctly using SUM (NOT AVERAGE - this
    is the KEY difference from juros).

The SUM-not-AVERAGE distinction is critical: poupanca monthly yield is a
percentage return, so summing produces the cumulative return. Juros uses
AVERAGE because the monthly cell is a daily rate quoted as annualized %.
"""
from __future__ import annotations

from data_sources.ddm.poupanca.fetcher import (
    _parse_br_number,
    _parse_data_value,
    parse_matrix_only,
    flatten_matrix_to_observations,
)


# ────────────────────────────────────────────────────────────────────────
# Sample HTML fragments
# ────────────────────────────────────────────────────────────────────────

# Poupanca page shape: only ONE table (the matrix). Header has year-corner +
# Jan..Dez (12 columns, NO "Ano"). Some cells are missing (--) for the
# current year (Aug-Dec 2026 not yet published).
#
# Values are realistic poupanca monthly yields (typically ~0.5-0.7%/month).
SAMPLE_POUPANCA_HTML = """
<table id="index-values">
  <thead>
    <tr>
      <th>Ano</th><th>Jan</th><th>Fev</th><th>Mar</th>
      <th>Abr</th><th>Mai</th><th>Jun</th><th>Jul</th>
      <th>Ago</th><th>Set</th><th>Out</th><th>Nov</th>
      <th>Dez</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <td>2026</td>
      <td class="right" data-value="0.67">0,67%</td>
      <td class="right" data-value="0.65">0,65%</td>
      <td class="right" data-value="0.62">0,62%</td>
      <td class="right" data-value="0.58">0,58%</td>
      <td class="right" data-value="0.58">0,58%</td>
      <td class="right" data-value="0.58">0,58%</td>
      <td class="right" data-value="0.58">0,58%</td>
      <td class="right">--</td>
      <td class="right">--</td>
      <td class="right">--</td>
      <td class="right">--</td>
      <td class="right">--</td>
    </tr>
    <tr>
      <td>2025</td>
      <td class="right" data-value="0.55">0,55%</td>
      <td class="right" data-value="0.56">0,56%</td>
      <td class="right" data-value="0.58">0,58%</td>
      <td class="right" data-value="0.60">0,60%</td>
      <td class="right" data-value="0.62">0,62%</td>
      <td class="right" data-value="0.65">0,65%</td>
      <td class="right" data-value="0.67">0,67%</td>
      <td class="right" data-value="0.70">0,70%</td>
      <td class="right" data-value="0.72">0,72%</td>
      <td class="right" data-value="0.73">0,73%</td>
      <td class="right" data-value="0.74">0,74%</td>
      <td class="right" data-value="0.75">0,75%</td>
    </tr>
  </tbody>
</table>
"""


# ────────────────────────────────────────────────────────────────────────
# Helper tests
# ────────────────────────────────────────────────────────────────────────

def test_parse_br_number_basic():
    assert _parse_br_number("0,67") == 0.67
    assert _parse_br_number("-0,12") == -0.12
    assert _parse_br_number("0,75") == 0.75


def test_parse_br_number_dash_dash_is_none():
    """Boundary contract: '--' is the DDM missing-value marker."""
    assert _parse_br_number("--") is None
    assert _parse_br_number("") is None
    assert _parse_br_number(None) is None


def test_parse_data_value_attribute():
    td = '<td class="right" data-value="0.67">0,67%</td>'
    assert _parse_data_value(td) == 0.67


def test_parse_data_value_dash_dash_is_none():
    td = '<td class="right">--</td>'
    assert _parse_data_value(td) is None


# ────────────────────────────────────────────────────────────────────────
# Matrix parser tests
# ────────────────────────────────────────────────────────────────────────

def test_parse_matrix_only_years_desc():
    result = parse_matrix_only(SAMPLE_POUPANCA_HTML)
    assert result["years"] == [2026, 2025]


def test_parse_matrix_only_header_no_ano():
    """Poupanca matrix has 12 month columns - NO 'Ano' (no acumulado column)."""
    result = parse_matrix_only(SAMPLE_POUPANCA_HTML)
    months = result["months"]
    assert "Ano" not in months
    assert months == ["Jan", "Fev", "Mar", "Abr", "Mai", "Jun",
                      "Jul", "Ago", "Set", "Out", "Nov", "Dez"]


def test_parse_matrix_only_data_values():
    result = parse_matrix_only(SAMPLE_POUPANCA_HTML)
    row_2026 = result["matrix"][2026]
    assert row_2026["Jan"] == 0.67
    assert row_2026["Jul"] == 0.58
    # Aug-Dec 2026 are missing ("--").
    assert row_2026["Ago"] is None
    assert row_2026["Dez"] is None
    # 2025 has all 12 months.
    row_2025 = result["matrix"][2025]
    assert row_2025["Dez"] == 0.75


def test_parse_matrix_only_empty_html():
    result = parse_matrix_only("")
    assert result == {"years": [], "months": [], "matrix": {}}


def test_parse_matrix_only_strips_stray_ano_column():
    """Defensive: if a page accidentally ships an 'Ano' final column,
    the parser must filter it out (poupanca pages shouldn't have one but
    we want to be resilient)."""
    html = """
    <table id="index-values">
      <thead><tr><th>Ano</th><th>Jan</th><th>Fev</th><th>Ano</th></tr></thead>
      <tbody>
        <tr><td>2026</td>
            <td data-value="0.67">0,67%</td>
            <td data-value="0.65">0,65%</td>
            <td data-value="999.0">999,00%</td></tr>
      </tbody>
    </table>
    """
    result = parse_matrix_only(html)
    # Only canonical month labels kept.
    assert result["months"] == ["Jan", "Fev"]
    assert result["matrix"][2026]["Jan"] == 0.67
    assert result["matrix"][2026]["Fev"] == 0.65
    # Stray "Ano" column was filtered out (NOT stored under "Ano" key).
    assert "Ano" not in result["matrix"][2026]


# ────────────────────────────────────────────────────────────────────────
# flatten_matrix_to_observations tests
# ────────────────────────────────────────────────────────────────────────

def test_flatten_matrix_to_observations_sorts_ascending():
    """Flattened series must be sorted ASC by ref_date (oldest first)."""
    result = parse_matrix_only(SAMPLE_POUPANCA_HTML)
    obs = flatten_matrix_to_observations(result)
    ref_dates = [o["ref_date"] for o in obs]
    assert ref_dates == sorted(ref_dates)
    assert ref_dates[0] == "2025-01"
    assert ref_dates[-1] == "2026-07"


def test_flatten_matrix_to_observations_skips_missing_cells():
    """Cells with '--' (None) must NOT appear in the flattened series."""
    result = parse_matrix_only(SAMPLE_POUPANCA_HTML)
    obs = flatten_matrix_to_observations(result)
    ref_dates = [o["ref_date"] for o in obs]
    # 12 months in 2025 + 7 months in 2026 = 19 observations.
    assert len(obs) == 19
    # Aug-Dec 2026 (None cells) must not appear.
    for missing in ("2026-08", "2026-09", "2026-10", "2026-11", "2026-12"):
        assert missing not in ref_dates


def test_flatten_matrix_to_observations_month_value():
    """month_value = the cell value (monthly yield %)."""
    result = parse_matrix_only(SAMPLE_POUPANCA_HTML)
    obs = flatten_matrix_to_observations(result)
    by_date = {o["ref_date"]: o for o in obs}
    assert by_date["2025-01"]["month_value"] == 0.55
    assert by_date["2026-07"]["month_value"] == 0.58


def test_flatten_matrix_to_observations_acumulado_no_ano_uses_SUM():
    """acumulado_no_ano = SUM (NOT AVERAGE) of all months in same year UP
    TO that month (year-to-date cumulative return).

    For Jan/2025: only Jan/2025 -> acumulado_no_ano = 0.55.
    For Jul/2025: SUM(Jan..Jul 2025) = 0.55+0.56+0.58+0.60+0.62+0.65+0.67.
    For Jan/2026: only Jan/2026 (NEW year resets the YTD SUM).
    """
    result = parse_matrix_only(SAMPLE_POUPANCA_HTML)
    obs = flatten_matrix_to_observations(result)
    by_date = {o["ref_date"]: o for o in obs}

    # Jan/2025: only itself.
    assert by_date["2025-01"]["acumulado_no_ano"] == 0.55
    # Jul/2025: SUM of Jan..Jul 2025 (NOT average!).
    expected_jul = 0.55 + 0.56 + 0.58 + 0.60 + 0.62 + 0.65 + 0.67
    assert abs(by_date["2025-07"]["acumulado_no_ano"] - expected_jul) < 1e-9
    # Jan/2026: only Jan/2026 (NEW year resets the YTD SUM).
    assert by_date["2026-01"]["acumulado_no_ano"] == 0.67


def test_flatten_matrix_to_observations_acumulado_12m_uses_SUM_full_window():
    """acumulado_12m for the 12th month = SUM (NOT AVERAGE) of the last 12
    months.

    For Dec/2025: SUM(Jan..Dez 2025) = sum of all 12 cells in 2025.
    """
    result = parse_matrix_only(SAMPLE_POUPANCA_HTML)
    obs = flatten_matrix_to_observations(result)
    by_date = {o["ref_date"]: o for o in obs}

    vals_2025 = [0.55, 0.56, 0.58, 0.60, 0.62, 0.65,
                 0.67, 0.70, 0.72, 0.73, 0.74, 0.75]
    expected_dec_2025 = sum(vals_2025)
    assert abs(by_date["2025-12"]["acumulado_12m"] - expected_dec_2025) < 1e-9


def test_flatten_matrix_to_observations_acumulado_12m_uses_SUM_short_window():
    """acumulado_12m for the first 11 months uses available months (not None)
    and uses SUM (NOT AVERAGE).

    For Jan/2025: window = [Jan/2025] only -> acumulado_12m = 0.55.
    For Feb/2025: window = [Jan, Feb] -> SUM = 0.55+0.56.
    """
    result = parse_matrix_only(SAMPLE_POUPANCA_HTML)
    obs = flatten_matrix_to_observations(result)
    by_date = {o["ref_date"]: o for o in obs}

    assert by_date["2025-01"]["acumulado_12m"] == 0.55
    assert abs(by_date["2025-02"]["acumulado_12m"] - (0.55 + 0.56)) < 1e-9


def test_flatten_matrix_to_observations_acumulado_12m_crosses_year_boundary():
    """acumulado_12m for Jan/2026 = SUM(Feb..Dec 2025 + Jan 2026) = 11 months
    of 2025 + 1 month of 2026 (SUM, NOT AVERAGE)."""
    result = parse_matrix_only(SAMPLE_POUPANCA_HTML)
    obs = flatten_matrix_to_observations(result)
    by_date = {o["ref_date"]: o for o in obs}

    vals_feb_to_dec_2025 = [0.56, 0.58, 0.60, 0.62, 0.65,
                            0.67, 0.70, 0.72, 0.73, 0.74, 0.75]
    expected_jan_2026 = sum(vals_feb_to_dec_2025) + 0.67
    assert abs(by_date["2026-01"]["acumulado_12m"] - expected_jan_2026) < 1e-9


def test_flatten_matrix_to_observations_does_NOT_use_average():
    """Critical regression test: poupanca MUST use SUM, NOT AVERAGE.

    If someone accidentally copies the juros fetcher (which uses AVERAGE),
    this test will catch it: for Jul/2025, AVERAGE would be ~0.604 but SUM
    is ~4.23. The values are very different - no floating-point wiggle room.
    """
    result = parse_matrix_only(SAMPLE_POUPANCA_HTML)
    obs = flatten_matrix_to_observations(result)
    by_date = {o["ref_date"]: o for o in obs}

    # Jul/2025 SUM of Jan..Jul 2025.
    expected_sum = 0.55 + 0.56 + 0.58 + 0.60 + 0.62 + 0.65 + 0.67
    # Jul/2025 AVERAGE would be expected_sum / 7.
    expected_avg = expected_sum / 7

    actual = by_date["2025-07"]["acumulado_no_ano"]
    assert abs(actual - expected_sum) < 1e-9, (
        f"Expected SUM={expected_sum}, got {actual} "
        f"(looks like AVERAGE={expected_avg}?)"
    )
    # And explicitly NOT equal to the average.
    assert abs(actual - expected_avg) > 0.5


def test_flatten_matrix_to_observations_empty_matrix():
    assert flatten_matrix_to_observations({}) == []
    assert flatten_matrix_to_observations(
        {"years": [], "months": [], "matrix": {}}) == []
