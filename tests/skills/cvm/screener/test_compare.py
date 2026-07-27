"""Tests for skills/cvm/screener/ — compare mode.

[Phase 4] Split out of the original single-file `test_screener.py`.
Covers the compare mode:
  - basic shape (status, ticker, setor, comparison, my_data, medians)
  - vs_sector labels (cheap/expensive for valuation multiples,
    above/below for quality metrics — and [v1.2] the new metrics
    roa, margem_liquida, divida_pl)
  - ticker not in bridge → not_found

The mock VAL_* data includes roe directly (Phase 2B calculations output),
so the [v1.2] simplification of `_roe_from_ratios()` to `ratios.get("roe")`
works without falling back to the lucro_liquido/patrimonio_liquido division.
"""
from __future__ import annotations

from skills.cvm.screener import screener
from tests.skills.cvm.screener.conftest import (
    CAD_COMPANIES, BRIDGE_SUZB3, BRIDGE_KLBN11, VAL_SUZB3, VAL_KLBN11,
)


class TestCompareMode:
    def test_basic_shape(self, mock_all, monkeypatch):
        mock_all(monkeypatch, CAD_COMPANIES,
                 {"SUZB3": BRIDGE_SUZB3, "KLBN11": BRIDGE_KLBN11},
                 {"SUZB3": VAL_SUZB3, "KLBN11": VAL_KLBN11})
        r = screener.compare(company="SUZB3")
        assert r["status"] == "ok"
        assert r["ticker"] == "SUZB3"
        assert r["setor"] == "Papel e Celulose"
        assert "comparison" in r
        assert "my_data" in r
        assert "medians" in r

    def test_comparison_shows_cheap_or_expensive(self, mock_all, monkeypatch):
        mock_all(monkeypatch, CAD_COMPANIES,
                 {"SUZB3": BRIDGE_SUZB3, "KLBN11": BRIDGE_KLBN11},
                 {"SUZB3": VAL_SUZB3, "KLBN11": VAL_KLBN11})
        r = screener.compare(company="SUZB3")
        comp = r["comparison"]
        # SUZB3 P/L=4.0, median=8.5 → cheap
        assert comp["p_l"]["vs_sector"] == "cheap"
        # SUZB3 ROE=0.295, KLBN11 ROE=0.118, median=0.2065 → SUZB3 above
        assert comp["roe"]["vs_sector"] == "above"
        # [v1.2] New metrics in comparison dict
        # SUZB3 ROA=0.10, median=0.07 → above
        assert comp["roa"]["vs_sector"] == "above"
        # SUZB3 margem_liquida=0.25, median=0.175 → above
        assert comp["margem_liquida"]["vs_sector"] == "above"
        # SUZB3 divida_pl=0.85, median=1.175 → "cheap" (less leveraged)
        assert comp["divida_pl"]["vs_sector"] == "cheap"

    def test_ticker_not_in_bridge(self, mock_all, monkeypatch):
        mock_all(monkeypatch, CAD_COMPANIES, {}, {})
        r = screener.compare(company="UNKNOWN4")
        assert r["status"] == "not_found"
