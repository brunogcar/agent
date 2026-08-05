"""Tests for skills/cvm/calculations/engines/dva_gross_va.py.

Generation-side DVA engine (DVA grupo LIKE '%Valor Adicionado%', codigo 7.04
-- Valor Adicionado Bruto / gross value added, TTM derivation from DFP +
ITR cumulative). Mocks the internal _get_dfp_dva_gross_va +
_get_itr_dva_gross_va functions via monkeypatch -- no database needed.

DVA 7.04 = Revenues (7.01) - Inputs (7.03). It is the second line of the
DVA generation side and is typically reported as a POSITIVE figure (wealth
created before retentions like depreciation). This engine returns the raw
value (sign preserved). These tests use positive mock values to mirror
the real DVA.

Generation-side identity:
  Revenues (7.01) - Inputs (7.03) = Gross Value Added (7.04)
  + Retentions (7.05) = Net Value Added Produced (7.06)
  + VA Received in Transfer (7.07) = Total VA to Distribute (7.08)
"""
from __future__ import annotations

import pytest

from skills.cvm.calculations.engines import dva_gross_va as dva_gva_engine


# -- Cache-clearing fixture --------------------------------------------------
# The @engine_cached decorator on dva_gross_va_at / dva_gross_va_periods
# uses a ContextVar (_ENGINE_CACHE in skills._base). When an
# engine_cache_scope is active, results are memoized. To prevent
# cross-test contamination we reset the ContextVar to None (passthrough
# mode) before every test.

@pytest.fixture(autouse=True)
def _clear_engine_cache():
    from skills._base import _ENGINE_CACHE
    token = _ENGINE_CACHE.set(None)
    try:
        yield
    finally:
        _ENGINE_CACHE.reset(token)


# -- Mock data ---------------------------------------------------------------
# Mirror real DVA sign convention: gross value added is a POSITIVE figure
# (revenues minus inputs -- the wealth created before retentions). Values
# are realistic for a large Brazilian issuer (e.g. PETR4 -- annual gross
# VA in the ~130 BRL billion range, ~revenue minus inputs).

FAKE_DFP = {
    "2023": {"value": 130e9, "date": "2023-12-31"},
}

FAKE_ITR = {
    "2024-03-31": {"value": 32e9, "meses": 3, "year": 2024},
    "2023-03-31": {"value": 30e9, "meses": 3, "year": 2023},
}


# -- dva_gross_va_at() tests (TTM derivation) --------------------------------

class TestDvaGrossVaAt:
    def test_ttm_derivation(self, monkeypatch):
        """dva_gross_va_at should derive TTM via DFP - ITR_prior + ITR_current.

        TTM at 2024-04-15 = DFP_2023 - ITR_2023_Q1 + ITR_2024_Q1
                          = 130e9 - 30e9 + 32e9
                          = 132e9
        """
        monkeypatch.setattr(dva_gva_engine, "_get_dfp_dva_gross_va", lambda c: FAKE_DFP)
        monkeypatch.setattr(dva_gva_engine, "_get_itr_dva_gross_va", lambda c: FAKE_ITR)

        result = dva_gva_engine.dva_gross_va_at("PETR4", "2024-04-15")
        assert result == pytest.approx(132e9, rel=1e-6)

    def test_returns_none_for_missing_company(self, monkeypatch):
        """Missing company (no DVA data) -> None.

        DVA is optional-filing in CVM -- some companies don't produce it.
        The engine should return None gracefully when no data exists.
        """
        monkeypatch.setattr(dva_gva_engine, "_get_dfp_dva_gross_va", lambda c: {})
        monkeypatch.setattr(dva_gva_engine, "_get_itr_dva_gross_va", lambda c: {})

        assert dva_gva_engine.dva_gross_va_at("UNKNOWN", "2024-06-30") is None

    def test_returns_none_for_insufficient_history(self, monkeypatch):
        """Only current ITR, no prior-year DFP -> can't derive TTM -> None.

        Without DFP for the prior year, the TTM bridge
        (DFP_prior - ITR_prior + ITR_current) cannot be computed. The
        engine returns None rather than emitting a partial / misleading
        figure.
        """
        fake_dfp = {}
        fake_itr = {
            "2024-03-31": {"value": 32e9, "meses": 3, "year": 2024},
        }
        monkeypatch.setattr(dva_gva_engine, "_get_dfp_dva_gross_va", lambda c: fake_dfp)
        monkeypatch.setattr(dva_gva_engine, "_get_itr_dva_gross_va", lambda c: fake_itr)

        assert dva_gva_engine.dva_gross_va_at("PETR4", "2024-04-15") is None

    def test_returns_dfp_when_no_itr_before_date(self, monkeypatch):
        """No ITR before date -> fall back to DFP annual."""
        fake_dfp = {"2020": {"value": 85e9, "date": "2020-12-31"}}
        monkeypatch.setattr(dva_gva_engine, "_get_dfp_dva_gross_va", lambda c: fake_dfp)
        monkeypatch.setattr(dva_gva_engine, "_get_itr_dva_gross_va", lambda c: {})

        assert dva_gva_engine.dva_gross_va_at("PETR4", "2021-01-15") == 85e9

    def test_ttm_at_exact_period_end(self, monkeypatch):
        """TTM at exact ITR period end date should use that ITR."""
        monkeypatch.setattr(dva_gva_engine, "_get_dfp_dva_gross_va", lambda c: FAKE_DFP)
        monkeypatch.setattr(dva_gva_engine, "_get_itr_dva_gross_va", lambda c: FAKE_ITR)

        result = dva_gva_engine.dva_gross_va_at("PETR4", "2024-03-31")
        assert result == pytest.approx(132e9, rel=1e-6)


# -- dva_gross_va_periods() tests --------------------------------------------

class TestDvaGrossVaPeriods:
    def test_periods(self, monkeypatch):
        """dva_gross_va_periods returns list of {date, ttm_dva_gross_va}."""
        fake_dfp = {
            "2021": {"value": 90e9, "date": "2021-12-31"},
            "2022": {"value": 110e9, "date": "2022-12-31"},
            "2023": {"value": 130e9, "date": "2023-12-31"},
        }
        fake_itr = {
            "2022-03-31": {"value": 25e9, "meses": 3, "year": 2022},
            "2023-03-31": {"value": 30e9, "meses": 3, "year": 2023},
            "2024-03-31": {"value": 32e9, "meses": 3, "year": 2024},
        }
        monkeypatch.setattr(dva_gva_engine, "_get_dfp_dva_gross_va", lambda c: fake_dfp)
        monkeypatch.setattr(dva_gva_engine, "_get_itr_dva_gross_va", lambda c: fake_itr)

        result = dva_gva_engine.dva_gross_va_periods("PETR4")
        assert isinstance(result, list)
        assert len(result) >= 1

        # Each entry has the correct key
        for entry in result:
            assert "date" in entry
            assert "ttm_dva_gross_va" in entry
            assert isinstance(entry["ttm_dva_gross_va"], float)

        # Sorted oldest-first
        dates = [e["date"] for e in result]
        assert dates == sorted(dates)

        # Deduplicated
        assert len(dates) == len(set(dates))

    def test_periods_empty_when_no_data(self, monkeypatch):
        """No DVA data -> empty periods list (graceful degradation)."""
        monkeypatch.setattr(dva_gva_engine, "_get_dfp_dva_gross_va", lambda c: {})
        monkeypatch.setattr(dva_gva_engine, "_get_itr_dva_gross_va", lambda c: {})

        assert dva_gva_engine.dva_gross_va_periods("UNKNOWN") == []


# -- Registry tests ----------------------------------------------------------

class TestDvaGrossVaRegistry:
    def test_registry(self):
        """Engine should be registered with correct name, category, quantity."""
        from skills.cvm.calculations._registry import ENGINES
        assert "dva_gross_va" in ENGINES
        spec = ENGINES["dva_gross_va"]
        assert spec.name == "dva_gross_va"
        assert spec.category == "dva"
        assert spec.quantity == "ttm_dva_gross_va"
        assert spec.at_fn is dva_gva_engine.dva_gross_va_at
        assert spec.periods_fn is dva_gva_engine.dva_gross_va_periods

    def test_uses_correct_cvm_code(self):
        """Engine should query DVA codigo 7.04 (Valor Adicionado Bruto)."""
        assert dva_gva_engine.DVA_GROSS_VA_CODE == "7.04"

    def test_uses_grupo_like_filter(self):
        """Engine should NOT use a literal DVA_GRUPO variable (SQL uses LIKE).

        The grupo field stores the full Portuguese statement name (e.g.
        "DF Consolidado - Demonstração de Valor Adicionado"), not the
        short "DVA" abbreviation — so the SQL uses ``grupo LIKE '%Valor
        Adicionado%'`` and there is no DVA_GRUPO constant on the module.
        """
        assert not hasattr(dva_gva_engine, "DVA_GRUPO")

    def test_source_mentions_codigo(self):
        """Engine source string should mention the CVM code for documentation."""
        from skills.cvm.calculations._registry import ENGINES
        assert "7.04" in ENGINES["dva_gross_va"].source

    def test_source_mentions_grupo_dva(self):
        """Engine source string should mention the DVA grupo filter for documentation."""
        from skills.cvm.calculations._registry import ENGINES
        assert "Valor Adicionado" in ENGINES["dva_gross_va"].source
