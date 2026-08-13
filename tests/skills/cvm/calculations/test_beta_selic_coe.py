"""tests/skills/cvm/calculations/test_beta_selic_coe.py -- Tests for Beta, Selic, COE."""
from __future__ import annotations
from unittest.mock import patch


# ── Selic engine tests ──────────────────────────────────────────────────────

@patch("skills.cvm.calculations.engines.selic._connect")
def test_selic_at_returns_annualized(mock_connect):
    """Selic series 432 (Meta Copom) returns annual rate directly."""
    import sqlite3
    mock_conn = sqlite3.connect(":memory:")
    mock_conn.row_factory = sqlite3.Row
    mock_conn.execute("CREATE TABLE series_observations (series_code INT, ref_date TEXT, value REAL)")
    # [v2.0] Series 432, not 11. Value is already annual % (e.g. 14.25)
    mock_conn.execute("INSERT INTO series_observations VALUES (432, '2024-06-30', 14.25)")
    mock_conn.commit()
    mock_connect.return_value = mock_conn

    from skills.cvm.calculations.engines.selic import selic_at
    result = selic_at("PETR4", "2024-07-01")
    assert result is not None
    # Series 432 is already annual — no compounding needed
    assert abs(result - 14.25) < 0.01


@patch("skills.cvm.calculations.engines.selic._connect")
def test_selic_at_none_when_no_data(mock_connect):
    import sqlite3
    mock_conn = sqlite3.connect(":memory:")
    mock_conn.row_factory = sqlite3.Row
    mock_conn.execute("CREATE TABLE series_observations (series_code INT, ref_date TEXT, value REAL)")
    mock_conn.commit()
    mock_connect.return_value = mock_conn

    from skills.cvm.calculations.engines.selic import selic_at
    assert selic_at("PETR4", "2024-07-01") is None


# ── Beta engine tests ──────────────────────────────────────────────────────

def test_ols_regression_basic():
    """Test OLS with known data: y = 2x should give beta=2."""
    from skills.cvm.calculations.engines.beta import _ols_regression
    x = [0.01, 0.02, -0.01, 0.03, 0.005, -0.02, 0.015, -0.005,
         0.025, -0.015, 0.01, 0.02, -0.01, 0.03, 0.005, -0.02,
         0.015, -0.005, 0.025, -0.015, 0.01, 0.02, -0.01, 0.03,
         0.005, -0.02, 0.015, -0.005, 0.025, -0.015]
    y = [2 * xi for xi in x]  # beta = 2.0
    result = _ols_regression(y, x)
    assert result["beta"] is not None
    assert abs(result["beta"] - 2.0) < 0.01
    assert abs(result["r_squared"] - 1.0) < 0.01


def test_ols_regression_insufficient_data():
    """Should return None for n < 30."""
    from skills.cvm.calculations.engines.beta import _ols_regression
    result = _ols_regression([0.01, 0.02], [0.01, 0.02])
    assert result["beta"] is None


# ── COE metric tests ───────────────────────────────────────────────────────

@patch("skills.cvm.calculations.engines.beta._fetch_ibov_returns")
@patch("skills.cvm.calculations.engines.beta._fetch_stock_returns")
def test_coe_at_capm_formula(mock_stock_ret, mock_ibov_ret):
    """COE = Rf + Beta * (Rm - Rf) = 10 + 1.2 * 5.5 = 16.6.

    Mocks the return series so Beta regression produces a known value,
    and mocks Selic to return a known Rf. Then COE should be deterministic.
    """
    # Create return series where stock has beta=1.2 relative to IBOV
    # If ibov_returns = [0.01, -0.01, ...] and stock = [0.012, -0.012, ...]
    # then beta = cov(s,i)/var(i) = 1.2
    import random
    random.seed(42)
    ibov_returns_list = [random.gauss(0, 0.01) for _ in range(100)]
    stock_returns_list = [1.2 * r + random.gauss(0, 0.001) for r in ibov_returns_list]

    dates = [f"2024-01-{i+1:02d}" for i in range(100)]
    mock_stock_ret.return_value = dict(zip(dates, stock_returns_list))
    mock_ibov_ret.return_value = dict(zip(dates, ibov_returns_list))

    # Mock Selic — patch at the CALLING module namespace (coe.selic_at), not the
    # source module (selic.selic_at). coe.py does `from ...selic import selic_at`
    # which binds a local ref at import time; patching the source doesn't affect it.
    with patch("skills.cvm.calculations.metrics.coe.selic_at", return_value=10.0):
        from skills.cvm.calculations.metrics.coe import coe_at
        result = coe_at("PETR4", "2024-06-30")

    assert result is not None
    # [v4 P2] COE now returns FRACTION (was percent). COE ~= 10% + 1.2 * 5.5% = 16.6% = 0.166
    # Allow tolerance for regression noise
    assert 0.15 < result < 0.18


@patch("skills.cvm.calculations.metrics.coe.beta_stats_at")
@patch("skills.cvm.calculations.metrics.coe.selic_at")
def test_coe_at_none_when_selic_missing(mock_selic, mock_beta):
    """COE returns fallback when Selic is unavailable (v2.0 DEFAULT_RF_PCT)."""
    mock_selic.return_value = None
    mock_beta.return_value = {"beta": 1.2}

    from skills.cvm.calculations.metrics.coe import coe_at, DEFAULT_RF_PCT
    result = coe_at("PETR4", "2024-06-30")
    # [v2.0] When selic=None, COE uses DEFAULT_RF_PCT (14.0%) + beta * ERP
    assert result is not None
    expected = (DEFAULT_RF_PCT / 100.0) + 1.2 * 0.055
    assert abs(result - expected) < 0.001


@patch("skills.cvm.calculations.metrics.coe.beta_stats_at")
@patch("skills.cvm.calculations.metrics.coe.selic_at")
def test_coe_at_none_when_beta_missing(mock_selic, mock_beta):
    """COE should return None when Beta is unavailable."""
    mock_selic.return_value = 10.0
    mock_beta.return_value = None

    from skills.cvm.calculations.metrics.coe import coe_at
    assert coe_at("PETR4", "2024-06-30") is None


# ── beta_periods signature contract (v1.14 fix) ────────────────────────────

@patch("skills.cvm.calculations.engines.beta._fetch_stock_returns")
@patch("skills.cvm.calculations.engines.beta._fetch_ibov_returns")
def test_beta_periods_accepts_3_args(mock_ibov, mock_stock):
    """[v1.14] beta_periods must accept (company, date_from, date_to) to match
    the MetricSpec history_fn contract.

    Before the fix, beta_periods(company) took only 1 arg, so
    summary(metric='beta') -> spec.history_fn(company, date_from, date_to)
    raised TypeError -> Beta showed '-' in the dashboard.
    """
    mock_stock.return_value = {}
    mock_ibov.return_value = {}
    from skills.cvm.calculations.engines.beta import beta_periods
    # Must not raise TypeError — accepts 3 positional args
    result = beta_periods("PETR4", "2020-01-01", "2025-01-01")
    assert isinstance(result, list)


@patch("skills.cvm.calculations.engines.beta._fetch_stock_returns")
@patch("skills.cvm.calculations.engines.beta._fetch_ibov_returns")
def test_beta_periods_filters_by_date_range(mock_ibov, mock_stock):
    """[v1.14] beta_periods respects date_from / date_to filtering."""
    mock_stock.return_value = {}
    mock_ibov.return_value = {}
    from skills.cvm.calculations.engines.beta import beta_periods
    result = beta_periods("PETR4", date_from="2023-01-01", date_to="2025-01-01")
    assert result == []


def test_beta_periods_registered_as_history_fn():
    """[v1.14] Verify the MetricSpec for 'beta' uses beta_periods as history_fn
    AND that it accepts 3 args (the history_fn contract). Regression guard.
    """
    import inspect
    from skills.cvm.calculations._registry import resolve_metric
    spec = resolve_metric("beta")
    assert spec.history_fn.__name__ == "beta_periods"
    sig = inspect.signature(spec.history_fn)
    params = list(sig.parameters.keys())
    assert params == ["company", "date_from", "date_to"], \
        f"beta_periods must accept (company, date_from, date_to), got {params}"


def test_summary_rounds_to_4_decimals_not_2():
    """[v1.14] summary() must round to 4 decimals (not 2) to preserve percentage
    precision. round(0.0269, 2) = 0.03 -> '3,00%' (loses .69%).
    round(0.0269, 4) = 0.0269 -> '2,69%' (correct).
    """
    import inspect
    from skills.cvm.historical.modes.summary import summary
    source = inspect.getsource(summary)
    assert "round(current_ratio, 2)" not in source, \
        "summary() must use round(x, 4) not round(x, 2) for ratio values"
    assert "round(current_ratio, 4)" in source, \
        "summary() must use round(current_ratio, 4)"
