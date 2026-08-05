"""tests/skills/cvm/calculations/test_beta_selic_coe.py -- Tests for Beta, Selic, COE."""
from __future__ import annotations
from unittest.mock import patch


# ── Selic engine tests ──────────────────────────────────────────────────────

@patch("skills.cvm.calculations.engines.selic._connect")
def test_selic_at_returns_annualized(mock_connect):
    """Selic daily rate should be annualized (x252)."""
    import sqlite3
    mock_conn = sqlite3.connect(":memory:")
    mock_conn.row_factory = sqlite3.Row
    mock_conn.execute("CREATE TABLE series_observations (series_code INT, ref_date TEXT, value REAL)")
    mock_conn.execute("INSERT INTO series_observations VALUES (11, '2024-06-30', 0.04)")
    mock_conn.commit()
    mock_connect.return_value = mock_conn

    from skills.cvm.calculations.engines.selic import selic_at
    result = selic_at("PETR4", "2024-07-01")
    assert result is not None
    assert abs(result - 0.04 * 252) < 0.01  # 0.04 * 252 = 10.08


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

    # Mock Selic
    with patch("skills.cvm.calculations.engines.selic.selic_at", return_value=10.0):
        from skills.cvm.calculations.metrics.coe import coe_at
        result = coe_at("PETR4", "2024-06-30")

    assert result is not None
    # COE = 10 + beta * 5.5. Beta should be ~1.2, so COE ~= 10 + 1.2*5.5 = 16.6
    # Allow tolerance for regression noise
    assert 15.0 < result < 18.0


@patch("skills.cvm.calculations.metrics.coe.beta_at")
@patch("skills.cvm.calculations.metrics.coe.selic_at")
def test_coe_at_none_when_selic_missing(mock_selic, mock_beta):
    """COE should return None when Selic is unavailable."""
    mock_selic.return_value = None
    mock_beta.return_value = {"beta": 1.2}

    from skills.cvm.calculations.metrics.coe import coe_at
    assert coe_at("PETR4", "2024-06-30") is None


@patch("skills.cvm.calculations.metrics.coe.beta_at")
@patch("skills.cvm.calculations.metrics.coe.selic_at")
def test_coe_at_none_when_beta_missing(mock_selic, mock_beta):
    """COE should return None when Beta is unavailable."""
    mock_selic.return_value = 10.0
    mock_beta.return_value = None

    from skills.cvm.calculations.metrics.coe import coe_at
    assert coe_at("PETR4", "2024-06-30") is None
