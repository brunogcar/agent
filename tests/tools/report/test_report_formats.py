"""Tests for report_ops/formats.py — number formatting specs + Jinja filter fns.

Covers the spec vocabulary (brl, brl_full, pct, pct_raw, num, int, compact,
text), None/NaN handling, and the Excel number-format bridge.
"""
from __future__ import annotations

import math

import pytest

from tools.report_ops import formats


class TestBrl:
    def test_brl_compact_millions(self):
        # 1,234,567 -> R$ 1,23 M
        assert formats.fmt_brl(1_234_567.0) == "R$ 1,23 M"

    def test_brl_compact_billions(self):
        # 500,000,000,000 -> R$ 500,00 B
        assert formats.fmt_brl(500_000_000_000.0) == "R$ 500,00 B"

    def test_brl_full_no_suffix(self):
        # suffix=False -> full with thousands separators
        assert formats.fmt_brl(1234.56, suffix=False) == "R$ 1.234,56"

    def test_brl_negative(self):
        assert formats.fmt_brl(-50.0, suffix=False) == "-R$ 50,00"

    def test_brl_none_is_dash(self):
        assert formats.fmt_brl(None) == "—"

    def test_brl_nan_is_dash(self):
        assert formats.fmt_brl(float("nan")) == "—"

    def test_brl_bad_string_is_dash(self):
        assert formats.fmt_brl("not a number") == "—"


class TestPct:
    def test_pct_from_fraction(self):
        # 0.1234 -> 12,34%
        assert formats.fmt_pct(0.1234) == "12,34%"

    def test_pct_already_percent(self):
        # 45.23 -> 45,23%
        assert formats.fmt_pct(45.23, already_percent=True) == "45,23%"

    def test_pct_zero(self):
        assert formats.fmt_pct(0.0) == "0,00%"

    def test_pct_none_is_dash(self):
        assert formats.fmt_pct(None) == "—"

    def test_pct_nan_is_dash(self):
        assert formats.fmt_pct(float("nan")) == "—"


class TestNumInt:
    def test_num_two_decimals(self):
        # 1234.56 -> 1.234,56
        assert formats.fmt_num(1234.56) == "1.234,56"

    def test_num_custom_decimals(self):
        assert formats.fmt_num(1234.5, decimals=3) == "1.234,500"

    def test_int_thousands(self):
        # 13000000000 -> 13.000.000.000
        assert formats.fmt_int(13_000_000_000) == "13.000.000.000"

    def test_int_none_is_dash(self):
        assert formats.fmt_int(None) == "—"


class TestCompact:
    def test_compact_trillion(self):
        assert formats.fmt_compact(1_230_000_000_000.0) == "1,23 T"

    def test_compact_billion(self):
        assert formats.fmt_compact(1_230_000_000.0) == "1,23 B"

    def test_compact_million(self):
        assert formats.fmt_compact(3_450_000.0) == "3,45 M"

    def test_compact_thousand(self):
        assert formats.fmt_compact(567_890.0) == "568 K"

    def test_compact_negative(self):
        assert formats.fmt_compact(-1_230_000.0) == "-1,23 M"

    def test_compact_none_is_dash(self):
        assert formats.fmt_compact(None) == "—"


class TestApplyFmt:
    """The fmt Jinja filter dispatch — one spec tag, one result."""

    def test_apply_brl(self):
        assert formats.apply_fmt(1_234_567.0, "brl") == "R$ 1,23 M"

    def test_apply_brl_full(self):
        assert formats.apply_fmt(1234.56, "brl_full") == "R$ 1.234,56"

    def test_apply_pct(self):
        assert formats.apply_fmt(0.185, "pct") == "18,50%"

    def test_apply_pct_raw(self):
        assert formats.apply_fmt(45.23, "pct_raw") == "45,23%"

    def test_apply_num(self):
        assert formats.apply_fmt(8.2, "num") == "8,20"

    def test_apply_int(self):
        assert formats.apply_fmt(1234, "int") == "1.234"

    def test_apply_compact(self):
        assert formats.apply_fmt(1_230_000_000_000.0, "compact") == "1,23 T"

    def test_apply_text_passthrough(self):
        assert formats.apply_fmt("PETR4", "text") == "PETR4"

    def test_apply_none_spec_is_text(self):
        assert formats.apply_fmt("hello", None) == "hello"

    def test_apply_unknown_spec_falls_back_to_text(self):
        # Unknown spec must NOT raise (templates can't handle exceptions)
        assert formats.apply_fmt("x", "not_a_spec") == "x"

    def test_apply_none_value_is_dash(self):
        assert formats.apply_fmt(None, "brl") == "—"


class TestExcelFormat:
    """Bridge between spec tags and native Excel number formats."""

    def test_excel_brl(self):
        assert formats.excel_format("brl") == '"R$ "#,##0.00'

    def test_excel_pct(self):
        # fraction -> Excel percentage
        assert formats.excel_format("pct") == "0.00%"

    def test_excel_pct_raw(self):
        assert formats.excel_format("pct_raw") == '0.00"%"'

    def test_excel_int(self):
        assert formats.excel_format("int") == "#,##0"

    def test_excel_text(self):
        assert formats.excel_format("text") == "@"

    def test_excel_unknown_is_text(self):
        assert formats.excel_format("weird") == "@"

    def test_excel_none_is_text(self):
        assert formats.excel_format(None) == "@"


class TestIsNumericSpec:
    def test_numeric_specs(self):
        for s in ("brl", "brl_full", "pct", "pct_raw", "num", "int", "compact"):
            assert formats.is_numeric_spec(s) is True

    def test_text_is_not_numeric(self):
        assert formats.is_numeric_spec("text") is False

    def test_none_is_not_numeric(self):
        assert formats.is_numeric_spec(None) is False
