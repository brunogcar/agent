"""tests/data_sources/ddm/juros/test_fetcher.py - HTML parser tests.

No network access. Uses synthetic HTML that mirrors the DDM juros page shape:
  - 1 <table> block per page (id="index-values")
  - Header: year corner + Jan..Dez (12 columns, NO "Ano")
  - Body rows: <td>year</td> + <td data-value="...">...</td> x12

Verifies:
  - _parse_br_number handles comma decimal + '--' -> None
  - parse_matrix_only returns years + month labels (12 only, no "Ano") + matrix
  - flatten_matrix_to_observations derives month_value + media_no_ano +
    media_12m from the matrix correctly
"""
from __future__ import annotations

from data_sources.ddm.juros.fetcher import (
    _parse_br_number,
    _parse_data_value,
    parse_matrix_only,
    flatten_matrix_to_observations,
)


# ────────────────────────────────────────────────────────────────────────
# Sample HTML fragments
# ────────────────────────────────────────────────────────────────────────

# Juros page shape: only ONE table (the matrix). Header has year-corner +
# Jan..Dez (12 columns, NO "Ano"). Some cells are missing (--) for the
# current year (Aug-Dec 2026 not yet published).
SAMPLE_JUROS_HTML = """
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
      <td class="right" data-value="13.15">13,15%</td>
      <td class="right" data-value="12.85">12,85%</td>
      <td class="right" data-value="11.25">11,25%</td>
      <td class="right" data-value="10.50">10,50%</td>
      <td class="right" data-value="10.50">10,50%</td>
      <td class="right" data-value="10.50">10,50%</td>
      <td class="right" data-value="10.50">10,50%</td>
      <td class="right">--</td>
      <td class="right">--</td>
      <td class="right">--</td>
      <td class="right">--</td>
      <td class="right">--</td>
    </tr>
    <tr>
      <td>2025</td>
      <td class="right" data-value="12.15">12,15%</td>
      <td class="right" data-value="12.25">12,25%</td>
      <td class="right" data-value="11.75">11,75%</td>
      <td class="right" data-value="11.25">11,25%</td>
      <td class="right" data-value="11.25">11,25%</td>
      <td class="right" data-value="11.25">11,25%</td>
      <td class="right" data-value="11.25">11,25%</td>
      <td class="right" data-value="11.25">11,25%</td>
      <td class="right" data-value="11.25">11,25%</td>
      <td class="right" data-value="11.75">11,75%</td>
      <td class="right" data-value="12.25">12,25%</td>
      <td class="right" data-value="12.75">12,75%</td>
    </tr>
  </tbody>
</table>
"""


# ────────────────────────────────────────────────────────────────────────
# Helper tests
# ────────────────────────────────────────────────────────────────────────

def test_parse_br_number_basic():
    assert _parse_br_number("13,15") == 13.15
    assert _parse_br_number("-1,16") == -1.16
    assert _parse_br_number("12,75") == 12.75


def test_parse_br_number_dash_dash_is_none():
    """Boundary contract: '--' is the DDM missing-value marker."""
    assert _parse_br_number("--") is None
    assert _parse_br_number("") is None
    assert _parse_br_number(None) is None


def test_parse_data_value_attribute():
    td = '<td class="right" data-value="13.15">13,15%</td>'
    assert _parse_data_value(td) == 13.15


def test_parse_data_value_dash_dash_is_none():
    td = '<td class="right">--</td>'
    assert _parse_data_value(td) is None


# ────────────────────────────────────────────────────────────────────────
# Matrix parser tests
# ────────────────────────────────────────────────────────────────────────

def test_parse_matrix_only_years_desc():
    result = parse_matrix_only(SAMPLE_JUROS_HTML)
    assert result["years"] == [2026, 2025]


def test_parse_matrix_only_header_no_ano():
    """Juros matrix has 12 month columns - NO 'Ano' (no acumulado column)."""
    result = parse_matrix_only(SAMPLE_JUROS_HTML)
    months = result["months"]
    assert "Ano" not in months
    assert months == ["Jan", "Fev", "Mar", "Abr", "Mai", "Jun",
                      "Jul", "Ago", "Set", "Out", "Nov", "Dez"]


def test_parse_matrix_only_data_values():
    result = parse_matrix_only(SAMPLE_JUROS_HTML)
    row_2026 = result["matrix"][2026]
    assert row_2026["Jan"] == 13.15
    assert row_2026["Jul"] == 10.50
    # Aug-Dec 2026 are missing ("--").
    assert row_2026["Ago"] is None
    assert row_2026["Dez"] is None
    # 2025 has all 12 months.
    row_2025 = result["matrix"][2025]
    assert row_2025["Dez"] == 12.75


def test_parse_matrix_only_empty_html():
    result = parse_matrix_only("")
    assert result == {"years": [], "months": [], "matrix": {}}


def test_parse_matrix_only_strips_stray_ano_column():
    """Defensive: if a page accidentally ships an 'Ano' final column,
    the parser must filter it out (juros pages shouldn't have one but
    we want to be resilient)."""
    html = """
    <table id="index-values">
      <thead><tr><th>Ano</th><th>Jan</th><th>Fev</th><th>Ano</th></tr></thead>
      <tbody>
        <tr><td>2026</td>
            <td data-value="13.15">13,15%</td>
            <td data-value="12.85">12,85%</td>
            <td data-value="999.0">999,00%</td></tr>
      </tbody>
    </table>
    """
    result = parse_matrix_only(html)
    # Only canonical month labels kept.
    assert result["months"] == ["Jan", "Fev"]
    assert result["matrix"][2026]["Jan"] == 13.15
    assert result["matrix"][2026]["Fev"] == 12.85
    # Stray "Ano" column was filtered out (NOT stored under "Ano" key).
    assert "Ano" not in result["matrix"][2026]


# ────────────────────────────────────────────────────────────────────────
# flatten_matrix_to_observations tests
# ────────────────────────────────────────────────────────────────────────

def test_flatten_matrix_to_observations_sorts_ascending():
    """Flattened series must be sorted ASC by ref_date (oldest first)."""
    result = parse_matrix_only(SAMPLE_JUROS_HTML)
    obs = flatten_matrix_to_observations(result)
    ref_dates = [o["ref_date"] for o in obs]
    assert ref_dates == sorted(ref_dates)
    assert ref_dates[0] == "2025-01"
    assert ref_dates[-1] == "2026-07"


def test_flatten_matrix_to_observations_skips_missing_cells():
    """Cells with '--' (None) must NOT appear in the flattened series."""
    result = parse_matrix_only(SAMPLE_JUROS_HTML)
    obs = flatten_matrix_to_observations(result)
    ref_dates = [o["ref_date"] for o in obs]
    # 12 months in 2025 + 7 months in 2026 = 19 observations.
    assert len(obs) == 19
    # Aug-Dec 2026 (None cells) must not appear.
    for missing in ("2026-08", "2026-09", "2026-10", "2026-11", "2026-12"):
        assert missing not in ref_dates


def test_flatten_matrix_to_observations_month_value():
    """month_value = the cell value (daily rate %)."""
    result = parse_matrix_only(SAMPLE_JUROS_HTML)
    obs = flatten_matrix_to_observations(result)
    by_date = {o["ref_date"]: o for o in obs}
    assert by_date["2025-01"]["month_value"] == 12.15
    assert by_date["2026-07"]["month_value"] == 10.50


def test_flatten_matrix_to_observations_media_no_ano():
    """media_no_ano = AVG of all months in same year UP TO that month.

    For Jan/2025: only Jan/2025 -> media_no_ano = 12.15.
    For Jul/2025: avg(Jan..Jul 2025) = (12.15+12.25+11.75+11.25+11.25+
                                       11.25+11.25)/7.
    """
    result = parse_matrix_only(SAMPLE_JUROS_HTML)
    obs = flatten_matrix_to_observations(result)
    by_date = {o["ref_date"]: o for o in obs}

    # Jan/2025: only itself.
    assert by_date["2025-01"]["media_no_ano"] == 12.15
    # Jul/2025: avg of Jan..Jul 2025.
    expected_jul = (12.15 + 12.25 + 11.75 + 11.25 + 11.25 +
                    11.25 + 11.25) / 7
    assert abs(by_date["2025-07"]["media_no_ano"] - expected_jul) < 1e-9
    # Jan/2026: only Jan/2026 (NEW year resets the YTD average).
    assert by_date["2026-01"]["media_no_ano"] == 13.15


def test_flatten_matrix_to_observations_media_12m_full_window():
    """media_12m for the 12th month = avg of the last 12 months.

    For Dec/2025: avg(Jan..Dez 2025) = mean of all 12 cells in 2025.
    """
    result = parse_matrix_only(SAMPLE_JUROS_HTML)
    obs = flatten_matrix_to_observations(result)
    by_date = {o["ref_date"]: o for o in obs}

    vals_2025 = [12.15, 12.25, 11.75, 11.25, 11.25, 11.25,
                 11.25, 11.25, 11.25, 11.75, 12.25, 12.75]
    expected_dec_2025 = sum(vals_2025) / 12
    assert abs(by_date["2025-12"]["media_12m"] - expected_dec_2025) < 1e-9


def test_flatten_matrix_to_observations_media_12m_short_window():
    """media_12m for the first 11 months uses available months (not None).

    For Jan/2025: window = [Jan/2025] only -> media_12m = 12.15.
    For Feb/2025: window = [Jan, Feb] -> avg = (12.15+12.25)/2.
    """
    result = parse_matrix_only(SAMPLE_JUROS_HTML)
    obs = flatten_matrix_to_observations(result)
    by_date = {o["ref_date"]: o for o in obs}

    assert by_date["2025-01"]["media_12m"] == 12.15
    assert abs(by_date["2025-02"]["media_12m"] - (12.15 + 12.25) / 2) < 1e-9


def test_flatten_matrix_to_observations_media_12m_crosses_year_boundary():
    """media_12m for Jan/2026 = avg(Feb..Dec 2025 + Jan 2026) = 11 months
    of 2025 + 1 month of 2026."""
    result = parse_matrix_only(SAMPLE_JUROS_HTML)
    obs = flatten_matrix_to_observations(result)
    by_date = {o["ref_date"]: o for o in obs}

    vals_feb_to_dec_2025 = [12.25, 11.75, 11.25, 11.25, 11.25,
                            11.25, 11.25, 11.25, 11.75, 12.25, 12.75]
    expected_jan_2026 = (sum(vals_feb_to_dec_2025) + 13.15) / 12
    assert abs(by_date["2026-01"]["media_12m"] - expected_jan_2026) < 1e-9


def test_flatten_matrix_to_observations_empty_matrix():
    assert flatten_matrix_to_observations({}) == []
    assert flatten_matrix_to_observations(
        {"years": [], "months": [], "matrix": {}}) == []
