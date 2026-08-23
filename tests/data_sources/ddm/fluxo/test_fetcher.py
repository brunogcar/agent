"""tests/data_sources/ddm/fluxo/test_fetcher.py - HTML parser tests.

No network access. Uses synthetic HTML that mirrors the DDM /fluxo page
shape:
  - 1 <table class="normal-table" id="flow"> block
  - 6 columns: Data | Estrangeiro | Institucional | Pessoa fisica |
    Inst. Financeira | Outros
  - Values are PT-BR formatted strings with "mi" suffix (millions R$)
    ("-1.582,35 mi", "1.029,81 mi", "42,36 mi", "-9,31 mi")
  - Dates are DD/MM/YYYY DESC (newest first)

Verifies:
  - parse_br_number parses values with "mi" suffix (positive + negative)
  - parse_br_number handles no-thousands-separator values
  - parse_br_date_iso parses DD/MM/YYYY -> YYYY-MM-DD
  - parse_fluxo_table returns rows with the right ref_date + fields
  - Header rows + malformed rows are skipped
  - Empty / malformed HTML is handled gracefully
"""
from __future__ import annotations

from data_sources.ddm.fluxo.fetcher import (
    parse_br_date_iso,
    parse_br_number,
    strip_html,
    parse_fluxo_table,
)


# ────────────────────────────────────────────────────────────────────────
# Sample HTML fragments
# ────────────────────────────────────────────────────────────────────────

SAMPLE_FLUXO_HTML = """
<html>
<head><title>Fluxo de investimento na B3 - Dados de Mercado</title></head>
<body>
  <h1>Fluxo de investimento na B3</h1>

  <table class="normal-table" id="flow">
    <thead>
      <tr>
        <th style="width: calc(100% / 6)">Data</th>
        <th class="right" style="width: calc(100% / 6)">Estrangeiro</th>
        <th class="right" style="width: calc(100% / 6)">Institucional</th>
        <th class="right" style="width: calc(100% / 6)">Pessoa f&iacute;sica</th>
        <th class="right" style="width: calc(100% / 6)">Inst. Financeira</th>
        <th class="right" style="width: calc(100% / 6)">Outros</th>
      </tr>
    </thead>
    <tbody>

      <tr>
        <td>19/08/2026</td>
        <td class="right nw">-1.582,35 mi</td>
        <td class="right nw">1.029,81 mi</td>
        <td class="right nw">42,36 mi</td>
        <td class="right nw">519,49 mi</td>
        <td class="right nw">-9,31 mi</td>
      </tr>

      <tr>
        <td>18/08/2026</td>
        <td class="right nw">-1.782,10 mi</td>
        <td class="right nw">1.362,50 mi</td>
        <td class="right nw">357,75 mi</td>
        <td class="right nw">-9,69 mi</td>
        <td class="right nw">71,54 mi</td>
      </tr>

      <tr>
        <td>17/08/2026</td>
        <td class="right nw">-496,07 mi</td>
        <td class="right nw">71,25 mi</td>
        <td class="right nw">154,80 mi</td>
        <td class="right nw">181,58 mi</td>
        <td class="right nw">88,44 mi</td>
      </tr>

    </tbody>
  </table>
</body>
</html>
"""


# ────────────────────────────────────────────────────────────────────────
# Helper tests
# ────────────────────────────────────────────────────────────────────────

def test_parse_br_number_negative_with_thousands():
    """'-1.582,35 mi' -> -1582.35 (negative, dot=thousands, comma=decimal)."""
    assert parse_br_number("-1.582,35 mi") == -1582.35


def test_parse_br_number_positive_with_thousands():
    """'1.029,81 mi' -> 1029.81."""
    assert parse_br_number("1.029,81 mi") == 1029.81


def test_parse_br_number_no_thousands():
    """'42,36 mi' -> 42.36 (no thousands separator)."""
    assert parse_br_number("42,36 mi") == 42.36


def test_parse_br_number_negative_no_thousands():
    """'-9,31 mi' -> -9.31."""
    assert parse_br_number("-9,31 mi") == -9.31


def test_parse_br_number_large_value():
    """'1.234.567,89 mi' -> 1234567.89 (multiple thousands separators)."""
    assert parse_br_number("1.234.567,89 mi") == 1234567.89


def test_parse_br_number_zero():
    """'0,00 mi' -> 0.0."""
    assert parse_br_number("0,00 mi") == 0.0


def test_parse_br_number_dash_dash_is_none():
    assert parse_br_number("--") is None
    assert parse_br_number("") is None
    assert parse_br_number(None) is None


def test_parse_br_number_case_insensitive_mi():
    """'1.234,56 MI' (uppercase) -> 1234.56."""
    assert parse_br_number("1.234,56 MI") == 1234.56


def test_parse_br_date_pt_br_to_iso():
    """'19/08/2026' -> '2026-08-19'."""
    assert parse_br_date_iso("19/08/2026") == "2026-08-19"


def test_parse_br_date_single_digit():
    """'9/8/2026' -> '2026-08-09' (single-digit day + month)."""
    assert parse_br_date_iso("9/8/2026") == "2026-08-09"


def test_parse_br_date_invalid_returns_empty():
    assert parse_br_date_iso("") == ""
    assert parse_br_date_iso("not-a-date") == ""
    assert parse_br_date_iso("2026-08-19") == "2026-08-19"  # ISO passthrough


def test_strip_html_strips_tags_and_collapses_whitespace():
    assert strip_html("<td>19/08/2026</td>") == "19/08/2026"
    assert strip_html("  hello   world  ") == "hello world"
    assert strip_html("<b>IPCA</b>") == "IPCA"


# ────────────────────────────────────────────────────────────────────────
# parse_fluxo_table tests
# ────────────────────────────────────────────────────────────────────────

def test_parse_fluxo_table_returns_rows():
    """The sample HTML has 3 data rows."""
    rows = parse_fluxo_table(SAMPLE_FLUXO_HTML)
    assert len(rows) == 3


def test_parse_fluxo_table_extracts_ref_date_iso():
    """ref_date is normalized to YYYY-MM-DD."""
    rows = parse_fluxo_table(SAMPLE_FLUXO_HTML)
    ref_dates = [r["ref_date"] for r in rows]
    assert ref_dates == ["2026-08-19", "2026-08-18", "2026-08-17"]


def test_parse_fluxo_table_parses_values_to_floats():
    """Values are parsed to floats (millions R$)."""
    rows = parse_fluxo_table(SAMPLE_FLUXO_HTML)
    first = rows[0]
    assert first["estrangeiro"] == -1582.35
    assert first["institucional"] == 1029.81
    assert first["pessoa_fisica"] == 42.36
    assert first["inst_financeira"] == 519.49
    assert first["outros"] == -9.31


def test_parse_fluxo_table_handles_negatives_in_all_columns():
    """Negative values appear in any column (including Inst. Financeira + Outros)."""
    rows = parse_fluxo_table(SAMPLE_FLUXO_HTML)
    second = rows[1]
    assert second["inst_financeira"] == -9.69
    third = rows[2]
    assert third["estrangeiro"] == -496.07


def test_parse_fluxo_table_empty_html():
    """Empty / no-table HTML returns []."""
    assert parse_fluxo_table("") == []
    assert parse_fluxo_table("<html><body>no tables</body></html>") == []


def test_parse_fluxo_table_skips_header_row():
    """The header row (first cell == 'Data') is skipped."""
    rows = parse_fluxo_table(SAMPLE_FLUXO_HTML)
    # All rows have a real date, not the literal 'Data' label.
    for r in rows:
        assert r["ref_date"].startswith("20")


def test_parse_fluxo_table_skips_malformed_rows():
    """Rows with fewer than 6 cells are skipped."""
    html = """
    <table class="normal-table" id="flow">
      <tbody>
        <tr><td>19/08/2026</td><td>-1.582,35 mi</td></tr>
        <tr>
          <td>19/08/2026</td>
          <td>-1.582,35 mi</td>
          <td>1.029,81 mi</td>
          <td>42,36 mi</td>
          <td>519,49 mi</td>
          <td>-9,31 mi</td>
        </tr>
      </tbody>
    </table>
    """
    rows = parse_fluxo_table(html)
    assert len(rows) == 1
    assert rows[0]["estrangeiro"] == -1582.35


def test_parse_fluxo_table_no_class_attribute():
    """Fallback: find a table by id='flow' if class is missing."""
    html = """
    <table id="flow">
      <tbody>
        <tr>
          <td>19/08/2026</td>
          <td>-1.582,35 mi</td>
          <td>1.029,81 mi</td>
          <td>42,36 mi</td>
          <td>519,49 mi</td>
          <td>-9,31 mi</td>
        </tr>
      </tbody>
    </table>
    """
    rows = parse_fluxo_table(html)
    assert len(rows) == 1
    assert rows[0]["ref_date"] == "2026-08-19"


def test_parse_fluxo_table_preserves_source_order():
    """Rows are returned in source order (DESC = newest first)."""
    rows = parse_fluxo_table(SAMPLE_FLUXO_HTML)
    assert rows[0]["ref_date"] == "2026-08-19"
    assert rows[-1]["ref_date"] == "2026-08-17"
