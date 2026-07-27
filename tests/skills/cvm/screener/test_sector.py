"""Tests for skills/cvm/screener/ — sector mode.

[Phase 4] Split out of the original single-file `test_screener.py`.
Covers the sector mode end-to-end:
  - basic shape (status, setor, peer_count, peers, medians)
  - peers sorted by P/L cheapest-first (None P/L goes last)
  - medians computed (P/L, Div Yield, etc. — and [v1.2] roa, margem_liquida,
    divida_pl)
  - "no companies found" path
  - companies without ticker (not in bridge) are skipped
  - [v1.2] new metrics (roa, margem_liquida, divida_pl) are populated
"""
from __future__ import annotations

import pytest

from skills.cvm.screener import screener
from tests.skills.cvm.screener.conftest import (
    CAD_COMPANIES, BRIDGE_SUZB3, BRIDGE_KLBN11, VAL_SUZB3, VAL_KLBN11,
)


class TestSectorMode:
    def test_basic_shape(self, mock_all, monkeypatch):
        mock_all(monkeypatch, CAD_COMPANIES,
                 {"SUZB3": BRIDGE_SUZB3, "KLBN11": BRIDGE_KLBN11},
                 {"SUZB3": VAL_SUZB3, "KLBN11": VAL_KLBN11})
        r = screener.sector(setor="Papel e Celulose")
        assert r["status"] == "ok"
        assert r["setor"] == "Papel e Celulose"
        assert r["peer_count"] == 2
        assert len(r["peers"]) == 2
        assert "medians" in r

    def test_peers_sorted_by_pl_cheapest_first(self, mock_all, monkeypatch):
        mock_all(monkeypatch, CAD_COMPANIES,
                 {"SUZB3": BRIDGE_SUZB3, "KLBN11": BRIDGE_KLBN11},
                 {"SUZB3": VAL_SUZB3, "KLBN11": VAL_KLBN11})
        r = screener.sector(setor="Papel")
        # SUZB3 P/L=4.0, KLBN11 P/L=13.0 → SUZB3 first (cheapest)
        assert r["peers"][0]["ticker"] == "SUZB3"
        assert r["peers"][1]["ticker"] == "KLBN11"

    def test_medians_computed(self, mock_all, monkeypatch):
        mock_all(monkeypatch, CAD_COMPANIES,
                 {"SUZB3": BRIDGE_SUZB3, "KLBN11": BRIDGE_KLBN11},
                 {"SUZB3": VAL_SUZB3, "KLBN11": VAL_KLBN11})
        r = screener.sector(setor="Papel")
        # median of [4.0, 13.0] = 8.5
        assert r["medians"]["p_l"] == 8.5
        # median of [0.25, 0.015] = 0.1325
        assert r["medians"]["dividend_yield"] == pytest.approx(0.1325)
        # [v1.2] New medians — from calculations via valuation
        assert r["medians"]["roe"] == pytest.approx((0.295 + 0.118) / 2)
        assert r["medians"]["roa"] == pytest.approx((0.10 + 0.04) / 2)
        assert r["medians"]["margem_liquida"] == pytest.approx((0.25 + 0.10) / 2)
        assert r["medians"]["divida_pl"] == pytest.approx((0.85 + 1.50) / 2)

    def test_no_companies_found(self, mock_all, monkeypatch):
        mock_all(monkeypatch, [], {}, {})
        r = screener.sector(setor="Nonexistent")
        assert r["status"] == "not_found"

    def test_skips_companies_without_ticker(self, mock_all, monkeypatch):
        """Companies in CAD but not in bridge are skipped (not an error)."""
        mock_all(monkeypatch, CAD_COMPANIES,
                 {"SUZB3": BRIDGE_SUZB3},  # KLBN11 not in bridge
                 {"SUZB3": VAL_SUZB3})
        r = screener.sector(setor="Papel")
        assert r["status"] == "ok"
        assert r["peer_count"] == 1  # only SUZB3

    def test_v12_new_metrics_populated_in_peers(self, mock_all, monkeypatch):
        """[v1.2] roa, margem_liquida, divida_pl flow through valuation.ratios
        into the peer dicts."""
        mock_all(monkeypatch, CAD_COMPANIES,
                 {"SUZB3": BRIDGE_SUZB3, "KLBN11": BRIDGE_KLBN11},
                 {"SUZB3": VAL_SUZB3, "KLBN11": VAL_KLBN11})
        r = screener.sector(setor="Papel e Celulose")
        suzb3 = next(p for p in r["peers"] if p["ticker"] == "SUZB3")
        assert suzb3["roa"] == 0.10
        assert suzb3["margem_liquida"] == 0.25
        assert suzb3["divida_pl"] == 0.85
        # roe now comes directly from val_ratios["roe"] (was derived before)
        assert suzb3["roe"] == 0.295
        klbn11 = next(p for p in r["peers"] if p["ticker"] == "KLBN11")
        assert klbn11["roa"] == 0.04
        assert klbn11["margem_liquida"] == 0.10
        assert klbn11["divida_pl"] == 1.50
