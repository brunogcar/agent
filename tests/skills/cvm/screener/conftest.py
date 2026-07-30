"""Shared fixtures for the screener skill tests.

[Phase 4] Extracted from the original single-file `test_screener.py` so
each mode (validation / sector / compare / route / dashboard) can live in
its own per-mode test module. [v1.4] per-mode tests now import their mode
function directly from `skills.cvm.screener.modes.<mode>` instead of from
the legacy monolithic screener module (which was removed in the v1.4
modular split). The fixture provides:

  - Synthetic CAD company rows (CAD_COMPANIES).
  - Synthetic bridge lookup responses (BRIDGE_*).
  - Synthetic valuation.ratios() responses (VAL_*) — including the [v1.2]
    additions (roe, roa, margem_liquida, divida_pl from calculations
    metrics via valuation.ratios).
  - A `mock_all` fixture that monkeypatches CAD search + CAD lookup +
    bridge lookup + valuation.ratios to return the synthetic data.

Env vars (PLANNER_MODEL etc.) are set by the parent conftest at
``tests/skills/cvm/conftest.py``.
"""
from __future__ import annotations

import pytest

# ── Synthetic data ───────────────────────────────────────────────────────────

CAD_COMPANIES = [
    {"CD_CVM": "13986", "CNPJ_CIA": "16404287000155",
     "DENOM_COMERC": "SUZANO", "DENOM_SOCIAL": "SUZANO S.A.",
     "SETOR_ATIV": "Papel e Celulose"},
    {"CD_CVM": "12653", "CNPJ_CIA": "89637490000145",
     "DENOM_COMERC": "KLABIN", "DENOM_SOCIAL": "KLABIN S.A.",
     "SETOR_ATIV": "Papel e Celulose"},
]

BRIDGE_SUZB3 = {"status": "ok", "ticker": "SUZB3", "cnpj": "16404287000155", "cd_cvm": "13986"}
BRIDGE_KLBN11 = {"status": "ok", "ticker": "KLBN11", "cnpj": "89637490000145", "cd_cvm": "12653"}

# [v1.2] Now includes roe, roa, margem_liquida, divida_pl directly — these
# are what valuation.ratios() returns after Phase 2B (calculations metrics).
# SUZB3: roe=0.295 (= 13B / 44B from old mock), roa=0.10, margem_liquida=0.25,
#        divida_pl=0.85 (high leverage — pulp companies are capital-intensive)
# KLBN11: roe=0.118 (= 1.7B / 14.4B), roa=0.04, margem_liquida=0.10,
#         divida_pl=1.50 (even higher leverage)
VAL_SUZB3 = {"status": "ok", "ticker": "SUZB3", "ratios": {
    "price": 42.0, "market_cap": 53_000_000_000, "p_l": 4.0, "p_vpa": 1.2,
    "ev_ebitda": 6.0, "dividend_yield": 0.25,
    # Phase 2B additions — populated by calculations metrics inside valuation
    "roe": 0.295, "roa": 0.10, "margem_liquida": 0.25, "divida_pl": 0.85,
    # Legacy fields kept for backward-compat assertions
    "lucro_liquido": 13_000_000_000, "patrimonio_liquido": 44_000_000_000,
}}

VAL_KLBN11 = {"status": "ok", "ticker": "KLBN11", "ratios": {
    "price": 17.0, "market_cap": 22_000_000_000, "p_l": 13.0, "p_vpa": 7.0,
    "ev_ebitda": 20.0, "dividend_yield": 0.015,
    # Phase 2B additions — populated by calculations metrics inside valuation
    "roe": 0.118, "roa": 0.04, "margem_liquida": 0.10, "divida_pl": 1.50,
    # Legacy fields kept for backward-compat assertions
    "lucro_liquido": 1_700_000_000, "patrimonio_liquido": 14_400_000_000,
}}


def _mock_all(monkeypatch, cad_comps, bridge_map, val_map):
    """Mock CAD search, CAD lookup, bridge lookup, valuation ratios,
    financials.annual, + FCA segment resolution.

    Each map is keyed by the relevant identifier (ticker for bridge + val;
    cad_comps is a list). Identifiers not in the map return a not_found /
    error response so the best-effort skip path can be tested.

    [v2] Added financials.annual + _resolve_via_fca_segmento mocks —
    sector() calls both of these per-peer, and without mocks they hit real
    DFP + FCA databases, making tests take 2+ minutes on a machine with
    real data. The mocks return synthetic financials so the peer dict is
    fully populated (receita, ebitda, margens, payout, segmento).
    """
    def fake_cad_search(setor="", **kwargs):
        return {"status": "ok",
                "companies": [c for c in cad_comps
                              if setor.lower() in c.get("SETOR_ATIV", "").lower()]}
    def fake_bridge_lookup(ticker="", cd_cvm="", cnpj=""):
        if ticker:
            return bridge_map.get(ticker, {"status": "not_found"})
        if cd_cvm:
            for t, r in bridge_map.items():
                if r.get("cd_cvm") == cd_cvm:
                    return r
            return {"status": "not_found"}
        return {"status": "not_found"}
    def fake_val_ratios(company=""):
        return val_map.get(company, {"status": "error", "error": "no data"})
    def fake_cad_lookup(cnpj="", cd_cvm="", name=""):
        for c in cad_comps:
            if cnpj and c.get("CNPJ_CIA", "").replace(".", "").replace("/", "").replace("-", "") \
                    == cnpj.replace(".", "").replace("/", "").replace("-", ""):
                return {"status": "ok", "company": c}
            if cd_cvm and c.get("CD_CVM") == cd_cvm:
                return {"status": "ok", "company": c}
        return {"status": "not_found"}

    # [v2] Mock financials.annual — sector() calls fin_annual(company, periods=2)
    # per peer to enrich the peer dict with receita/ebitda/margens/payout/growth.
    # Without this mock, every test that calls sector() or compare() hits the
    # real DFP database for each peer (2 queries × N peers = slow on real data).
    def fake_fin_annual(company="", periods=2, **kwargs):
        return {
            "status": "ok",
            "company": company,
            "periods": [
                {"metrics": {"receita_liquida": 10_000_000_000,
                             "ebitda": 3_000_000_000,
                             "lucro_liquido": 2_000_000_000},
                 "ratios": {"marg_ebitda": 0.30, "marg_liquida": 0.20,
                            "payout": 0.40}},
                {"metrics": {"receita_liquida": 9_000_000_000}},
            ],
        }

    # [v2] Mock FCA segment resolution — sector() calls _resolve_via_fca_segmento
    # per peer to get the listing segment (Novo Mercado, Nível 1, etc.).
    # Without this mock, each call hits the FCA database.
    def fake_fca_segmento(ticker=""):
        return "Novo Mercado"

    monkeypatch.setattr("data_sources.cvm.cad.query_engine.search", fake_cad_search)
    monkeypatch.setattr("data_sources.cvm.cad.query_engine.lookup", fake_cad_lookup)
    monkeypatch.setattr("data_sources.cvm.bridge.query_engine.lookup", fake_bridge_lookup)
    monkeypatch.setattr("skills.cvm.valuation.modes.ratios.ratios", fake_val_ratios)
    monkeypatch.setattr("skills.cvm.financials.modes.annual.annual", fake_fin_annual)
    monkeypatch.setattr("data_sources.cvm._bridge._resolve_via_fca_segmento", fake_fca_segmento)


@pytest.fixture
def mock_all():
    """Return the `_mock_all` helper so per-mode tests can call it.

    Usage:
        def test_x(mock_all, monkeypatch):
            mock_all(monkeypatch, CAD_COMPANIES,
                     {"SUZB3": BRIDGE_SUZB3, "KLBN11": BRIDGE_KLBN11},
                     {"SUZB3": VAL_SUZB3, "KLBN11": VAL_KLBN11})
            ...
    """
    return _mock_all


@pytest.fixture
def papel_env(mock_all, monkeypatch):
    """Pre-built 2-peer "Papel e Celulose" sector environment.

    Convenience: most sector / compare tests want exactly this setup.
    """
    mock_all(monkeypatch, CAD_COMPANIES,
             {"SUZB3": BRIDGE_SUZB3, "KLBN11": BRIDGE_KLBN11},
             {"SUZB3": VAL_SUZB3, "KLBN11": VAL_KLBN11})
    return {"SUZB3": VAL_SUZB3, "KLBN11": VAL_KLBN11}
