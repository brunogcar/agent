"""Tests for skills/cvm/calculations/metrics/vpa.py + engines/pl.py.

Uses mocked engines (price, pl, shares) — no database needed.
"""
from __future__ import annotations

import pytest
from skills.cvm.calculations.metrics import vpa as vpa_metric
from skills.cvm.calculations.engines import pl as pl_engine


# ── Mock data ────────────────────────────────────────────────────────────────

MOCK_PRICES = [
    {"date": "2024-01-15", "close": 35.0},
    {"date": "2024-02-15", "close": 36.0},
    {"date": "2024-03-15", "close": 38.0},
    {"date": "2024-04-15", "close": 37.0},
    {"date": "2024-06-15", "close": 40.0},
]

MOCK_PL_PERIODS = [
    {"date": "2023-12-31", "pl": 290e9},
    {"date": "2024-03-31", "pl": 300e9},  # Q1 2024 snapshot
    {"date": "2024-06-30", "pl": 310e9},  # H1 2024 snapshot
]

MOCK_SHARES_PERIODS = [
    {"date": "2000-01-01", "shares": 13e9},  # constant (investsite fallback)
]


def _mock_engines(monkeypatch):
    """Mock price + pl + shares engines for vpa metric tests."""
    monkeypatch.setattr(
        "skills.cvm.calculations.metrics.vpa.price_series",
        lambda ticker, df, dt: list(MOCK_PRICES),
    )
    monkeypatch.setattr(
        "skills.cvm.calculations.metrics.vpa.pl_periods",
        lambda company: list(MOCK_PL_PERIODS),
    )
    monkeypatch.setattr(
        "skills.cvm.calculations.metrics.vpa.shares_periods",
        lambda company: list(MOCK_SHARES_PERIODS),
    )


# ── vpa_at() tests (per-share value = PL / shares) ──────────────────────────

class TestVpaAt:
    def test_basic_computation(self, monkeypatch):
        """vpa_at = PL / shares (per-share value, NOT the ratio)."""
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.vpa.pl_at", lambda c, d: 310e9
        )
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.vpa.shares_at", lambda c, d: 13e9
        )
        # VPA = 310e9 / 13e9 = 23.846...
        result = vpa_metric.vpa_at("PETR4", "2024-06-15")
        assert result == pytest.approx(310e9 / 13e9, rel=1e-3)

    def test_missing_pl(self, monkeypatch):
        monkeypatch.setattr("skills.cvm.calculations.metrics.vpa.pl_at", lambda c, d: None)
        monkeypatch.setattr("skills.cvm.calculations.metrics.vpa.shares_at", lambda c, d: 13e9)
        assert vpa_metric.vpa_at("PETR4", "2024-06-15") is None

    def test_missing_shares(self, monkeypatch):
        monkeypatch.setattr("skills.cvm.calculations.metrics.vpa.pl_at", lambda c, d: 310e9)
        monkeypatch.setattr("skills.cvm.calculations.metrics.vpa.shares_at", lambda c, d: None)
        assert vpa_metric.vpa_at("PETR4", "2024-06-15") is None

    def test_negative_pl_returns_none(self, monkeypatch):
        """Negative equity → VPA meaningless → None."""
        monkeypatch.setattr("skills.cvm.calculations.metrics.vpa.pl_at", lambda c, d: -50e9)
        monkeypatch.setattr("skills.cvm.calculations.metrics.vpa.shares_at", lambda c, d: 13e9)
        assert vpa_metric.vpa_at("PETR4", "2024-06-15") is None


# ── pvpa_at() tests (ratio = price / VPA) ────────────────────────────────────

class TestPvpaAt:
    def test_basic_computation(self, monkeypatch):
        """pvpa_at = price / VPA = price / (PL / shares)."""
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.vpa.price_at", lambda t, d: 38.0
        )
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.vpa.pl_at", lambda c, d: 310e9
        )
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.vpa.shares_at", lambda c, d: 13e9
        )
        # P/VPA = 38.0 / (310e9 / 13e9) = 38.0 / 23.846 = 1.5935...
        result = vpa_metric.pvpa_at("PETR4", "2024-06-15")
        assert result == pytest.approx(38.0 / (310e9 / 13e9), rel=1e-3)

    def test_missing_price(self, monkeypatch):
        monkeypatch.setattr("skills.cvm.calculations.metrics.vpa.price_at", lambda t, d: None)
        monkeypatch.setattr("skills.cvm.calculations.metrics.vpa.pl_at", lambda c, d: 310e9)
        monkeypatch.setattr("skills.cvm.calculations.metrics.vpa.shares_at", lambda c, d: 13e9)
        assert vpa_metric.pvpa_at("PETR4", "2024-06-15") is None

    def test_zero_price_returns_none(self, monkeypatch):
        monkeypatch.setattr("skills.cvm.calculations.metrics.vpa.price_at", lambda t, d: 0.0)
        monkeypatch.setattr("skills.cvm.calculations.metrics.vpa.pl_at", lambda c, d: 310e9)
        monkeypatch.setattr("skills.cvm.calculations.metrics.vpa.shares_at", lambda c, d: 13e9)
        assert vpa_metric.pvpa_at("PETR4", "2024-06-15") is None

    def test_negative_pl_returns_none(self, monkeypatch):
        """Negative equity → P/VPA meaningless → None."""
        monkeypatch.setattr("skills.cvm.calculations.metrics.vpa.price_at", lambda t, d: 38.0)
        monkeypatch.setattr("skills.cvm.calculations.metrics.vpa.pl_at", lambda c, d: -50e9)
        monkeypatch.setattr("skills.cvm.calculations.metrics.vpa.shares_at", lambda c, d: 13e9)
        assert vpa_metric.pvpa_at("PETR4", "2024-06-15") is None


# ── vpa_history() tests (series with vpa + pvpa) ─────────────────────────────

class TestVpaHistory:
    def test_basic_shape(self, monkeypatch):
        _mock_engines(monkeypatch)
        result = vpa_metric.vpa_history("PETR4", "2024-01-01", "2024-06-30")
        assert len(result) == 5
        for entry in result:
            assert "date" in entry
            assert "price" in entry
            assert "pl" in entry
            assert "shares" in entry
            assert "vpa" in entry     # per-share value
            assert "pvpa" in entry    # price ratio

    def test_step_function_pl_lookup(self, monkeypatch):
        """PL should be the most recent snapshot <= date."""
        _mock_engines(monkeypatch)
        result = vpa_metric.vpa_history("PETR4", "2024-01-01", "2024-06-30")
        # 2024-01-15 → most recent PL snapshot <= 2024-01-15 is 2023-12-31 (290e9)
        assert result[0]["pl"] == 290e9
        assert result[0]["vpa"] == pytest.approx(290e9 / 13e9, rel=1e-3)
        assert result[0]["pvpa"] == pytest.approx(35.0 / (290e9 / 13e9), rel=1e-3)
        # 2024-04-15 → most recent PL is 2024-03-31 (300e9)
        assert result[3]["pl"] == 300e9
        # 2024-06-15 → most recent PL is 2024-03-31 (300e9), NOT 2024-06-30 (after)
        assert result[4]["pl"] == 300e9

    def test_empty_prices_returns_empty(self, monkeypatch):
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.vpa.price_series",
            lambda t, df, dt: [],
        )
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.vpa.pl_periods",
            lambda c: list(MOCK_PL_PERIODS),
        )
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.vpa.shares_periods",
            lambda c: list(MOCK_SHARES_PERIODS),
        )
        assert vpa_metric.vpa_history("PETR4", "2024-01-01", "2024-06-30") == []

    def test_no_pl_before_date_yields_none_vpa(self, monkeypatch):
        """If no PL snapshot <= date, vpa and pvpa should be None."""
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.vpa.price_series",
            lambda t, df, dt: [{"date": "2020-01-15", "close": 30.0}],
        )
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.vpa.pl_periods",
            lambda c: [{"date": "2023-12-31", "pl": 290e9}],  # all after 2020-01-15
        )
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.vpa.shares_periods",
            lambda c: list(MOCK_SHARES_PERIODS),
        )
        result = vpa_metric.vpa_history("PETR4", "2020-01-01", "2020-02-01")
        assert len(result) == 1
        assert result[0]["vpa"] is None
        assert result[0]["pvpa"] is None
        assert result[0]["pl"] is None


# ── _pick_pl_value() unit tests (zero-value trap + 2.08 fallback) ────────────

class TestPickPlValue:
    """[v1.6 review-fix] Tests for the zero-value trap + 2.08 fallback logic.

    _pick_pl_value takes a list of candidate rows for a single snapshot
    date and returns (value, source_code).  The != 0 check prevents
    zero-value data errors from polluting the PL series; the 2.08
    fallback (with description check) handles old-chart filers that
    omit 2.03.
    """

    def test_picks_nonzero_2_03(self):
        """When 2.03 is non-zero, it is preferred (source_code = '2.03')."""
        candidates = [
            {"codigo": "2.03", "valor": 380e9, "escala": 1, "descricao": "Patrimônio Líquido Consolidado"},
        ]
        val, src = pl_engine._pick_pl_value(candidates)
        assert val == pytest.approx(380e9)
        assert src == "2.03"

    def test_zero_value_2_03_rejected(self):
        """[zero-value trap] A zero 2.03 valor does NOT become 0.0 PL."""
        candidates = [
            {"codigo": "2.03", "valor": 0, "escala": 1, "descricao": "Patrimônio Líquido Consolidado"},
        ]
        val, src = pl_engine._pick_pl_value(candidates)
        assert val is None
        assert src is None

    def test_null_2_03_rejected(self):
        """A NULL (None) 2.03 valor is also rejected."""
        candidates = [
            {"codigo": "2.03", "valor": None, "escala": 1, "descricao": "Patrimônio Líquido"},
        ]
        val, src = pl_engine._pick_pl_value(candidates)
        assert val is None

    def test_falls_back_to_2_08_when_2_03_zero(self):
        """When 2.03 is zero, fall back to 2.08 (retained earnings) if desc matches."""
        candidates = [
            {"codigo": "2.03", "valor": 0, "escala": 1, "descricao": "Patrimônio Líquido"},
            {"codigo": "2.08", "valor": 50e9, "escala": 1, "descricao": "Lucros ou Prejuízos Acumulados"},
        ]
        val, src = pl_engine._pick_pl_value(candidates)
        assert val == pytest.approx(50e9)
        assert src == "2.08"

    def test_2_08_description_check_blocks_wrong_desc(self):
        """2.08 with a non-retained-earnings descricao is rejected."""
        candidates = [
            {"codigo": "2.03", "valor": 0, "escala": 1, "descricao": "Patrimônio Líquido"},
            {"codigo": "2.08", "valor": 50e9, "escala": 1, "descricao": "Reservas de Capital"},  # wrong desc
        ]
        val, src = pl_engine._pick_pl_value(candidates)
        assert val is None  # 2.03 zero + 2.08 desc doesn't match → dropped

    def test_2_08_description_check_accent_insensitive(self):
        """descricao 'Prejuízo' (accented) and 'Prejuizo' (unaccented) both match."""
        for desc in ("Prejuízos Acumulados", "Prejuizos Acumulados"):
            candidates = [
                {"codigo": "2.08", "valor": 30e9, "escala": 1, "descricao": desc},
            ]
            val, src = pl_engine._pick_pl_value(candidates)
            assert val == pytest.approx(30e9), f"Failed for desc={desc!r}"
            assert src == "2.08"

    def test_zero_2_08_also_rejected(self):
        """Both 2.03 and 2.08 zero → date dropped entirely."""
        candidates = [
            {"codigo": "2.03", "valor": 0, "escala": 1, "descricao": "Patrimônio Líquido"},
            {"codigo": "2.08", "valor": 0, "escala": 1, "descricao": "Lucros Acumulados"},
        ]
        val, src = pl_engine._pick_pl_value(candidates)
        assert val is None
        assert src is None

    def test_2_03_preferred_over_2_08_when_both_nonzero(self):
        """When both are non-zero, 2.03 (total equity) wins over 2.08 (RE)."""
        candidates = [
            {"codigo": "2.03", "valor": 380e9, "escala": 1, "descricao": "Patrimônio Líquido"},
            {"codigo": "2.08", "valor": 50e9, "escala": 1, "descricao": "Lucros Acumulados"},
        ]
        val, src = pl_engine._pick_pl_value(candidates)
        assert val == pytest.approx(380e9)
        assert src == "2.03"

    def test_escala_applied(self):
        """escala is applied to the raw valor before the != 0 check."""
        # valor=380, escala=1e6 → 380e6 (non-zero → accepted)
        candidates = [
            {"codigo": "2.03", "valor": 380, "escala": 1e6, "descricao": "Patrimônio Líquido"},
        ]
        val, src = pl_engine._pick_pl_value(candidates)
        assert val == pytest.approx(380e6)
        assert src == "2.03"

    def test_escala_zero_after_multiply_rejected(self):
        """valor=0 with any escala → 0.0 → rejected."""
        candidates = [
            {"codigo": "2.03", "valor": 0, "escala": 1e6, "descricao": "Patrimônio Líquido"},
        ]
        val, src = pl_engine._pick_pl_value(candidates)
        assert val is None

    def test_empty_candidates(self):
        """No candidates → (None, None)."""
        val, src = pl_engine._pick_pl_value([])
        assert val is None
        assert src is None


# ── PL engine tests (mocked DB) ──────────────────────────────────────────────

class TestPlEngine:
    def test_pl_at_finds_most_recent_snapshot(self, monkeypatch):
        """pl_at should return the most recent PL snapshot <= date."""
        fake_dfp = {"2023-12-31": {"value": 290e9, "year": 2023}}
        fake_itr = {
            "2024-03-31": {"value": 300e9, "meses": 3, "year": 2024},
            "2024-06-30": {"value": 310e9, "meses": 6, "year": 2024},
        }
        monkeypatch.setattr(pl_engine, "_get_dfp_pl", lambda c: fake_dfp)
        monkeypatch.setattr(pl_engine, "_get_itr_pl", lambda c: fake_itr)

        assert pl_engine.pl_at("PETR4", "2024-04-15") == 300e9
        assert pl_engine.pl_at("PETR4", "2024-07-01") == 310e9
        assert pl_engine.pl_at("PETR4", "2023-12-31") == 290e9

    def test_pl_at_no_data_returns_none(self, monkeypatch):
        monkeypatch.setattr(pl_engine, "_get_dfp_pl", lambda c: {})
        monkeypatch.setattr(pl_engine, "_get_itr_pl", lambda c: {})
        assert pl_engine.pl_at("PETR4", "2024-06-30") is None

    def test_pl_at_no_snapshot_before_date(self, monkeypatch):
        """If all snapshots are after date, return None."""
        fake_dfp = {"2024-12-31": {"value": 380e9, "year": 2024}}
        fake_itr = {}
        monkeypatch.setattr(pl_engine, "_get_dfp_pl", lambda c: fake_dfp)
        monkeypatch.setattr(pl_engine, "_get_itr_pl", lambda c: fake_itr)
        assert pl_engine.pl_at("PETR4", "2024-06-30") is None

    def test_pl_periods_merges_dfp_and_itr(self, monkeypatch):
        """pl_periods should merge DFP + ITR snapshots, sorted oldest-first."""
        fake_dfp = {
            "2023-12-31": {"value": 290e9, "year": 2023},
            "2024-12-31": {"value": 380e9, "year": 2024},
        }
        fake_itr = {
            "2024-03-31": {"value": 300e9, "meses": 3, "year": 2024},
            "2024-06-30": {"value": 310e9, "meses": 6, "year": 2024},
            "2024-09-30": {"value": 330e9, "meses": 9, "year": 2024},
        }
        monkeypatch.setattr(pl_engine, "_get_dfp_pl", lambda c: fake_dfp)
        monkeypatch.setattr(pl_engine, "_get_itr_pl", lambda c: fake_itr)

        result = pl_engine.pl_periods("PETR4")
        assert len(result) == 5
        assert result[0] == {"date": "2023-12-31", "pl": 290e9}
        assert result[4] == {"date": "2024-12-31", "pl": 380e9}

    def test_pl_periods_dedupes_same_date(self, monkeypatch):
        fake_dfp = {"2024-12-31": {"value": 380e9, "year": 2024}}
        fake_itr = {"2024-12-31": {"value": 380e9, "meses": 9, "year": 2024}}
        monkeypatch.setattr(pl_engine, "_get_dfp_pl", lambda c: fake_dfp)
        monkeypatch.setattr(pl_engine, "_get_itr_pl", lambda c: fake_itr)

        result = pl_engine.pl_periods("PETR4")
        assert len(result) == 1

    def test_pl_periods_empty(self, monkeypatch):
        monkeypatch.setattr(pl_engine, "_get_dfp_pl", lambda c: {})
        monkeypatch.setattr(pl_engine, "_get_itr_pl", lambda c: {})
        assert pl_engine.pl_periods("PETR4") == []


# ── Metric registry test ────────────────────────────────────────────────────

class TestMetricRegistry:
    def test_vpa_registered(self):
        from skills.cvm.calculations._registry import METRICS
        assert "vpa" in METRICS
        assert METRICS["vpa"].ratio_key == "pvpa"
        assert METRICS["vpa"].per_share_key == "vpa"

    def test_vpa_aliases_include_pvpa(self):
        from skills.cvm.calculations._registry import resolve_metric
        assert resolve_metric("pvpa").name == "vpa"
        assert resolve_metric("p/vpa").name == "vpa"
