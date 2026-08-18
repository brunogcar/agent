"""Tests for the Black-Scholes engine (skills/b3/options/engines.py).

7 tests covering:
  - Put-call parity (C - P = S - K*exp(-rT))
  - IV round-trip (call): invert BS to recover sigma
  - IV round-trip (put): same for puts
  - Invalid inputs (T<=0, negative price) -> None
  - Below-intrinsic price (arbitrage violation) -> None
  - Intrinsic value at T=0 (call worth S-K if ITM, else 0)
  - Vega > 0 (option price is monotonic in sigma)

Reference values for ATM with sigma=0.20:
  S=K=100, T=1, r=0.05:
    call = 10.4506
    put  =  5.5735
"""
from __future__ import annotations

import math

import pytest

from skills.b3.options.engines import (
    bs_price, bs_vega, implied_vol, _norm_cdf,
)


# ── Reference values (verified against scipy + analytical formulae) ────────
_S, _K, _T, _R, _SIGMA = 100.0, 100.0, 1.0, 0.05, 0.20
_EXPECTED_CALL = 10.4506
_EXPECTED_PUT  = 5.5735


class TestBlackScholes:
    def test_put_call_parity(self):
        """C - P = S - K*exp(-rT) at ATM (sigma=0.20)."""
        call = bs_price(_S, _K, _T, _R, _SIGMA, "CALL")
        put  = bs_price(_S, _K, _T, _R, _SIGMA, "PUT")
        # Sanity check the absolute prices match the known ATM values.
        assert call == pytest.approx(_EXPECTED_CALL, abs=1e-4)
        assert put  == pytest.approx(_EXPECTED_PUT,  abs=1e-4)
        # Parity: C - P = S - K*exp(-rT).
        lhs = call - put
        rhs = _S - _K * math.exp(-_R * _T)
        assert lhs == pytest.approx(rhs, abs=1e-9)

    def test_iv_round_trip_call(self):
        """Invert BS (call) to recover the input sigma."""
        price = bs_price(_S, _K, _T, _R, _SIGMA, "CALL")
        iv = implied_vol(price, _S, _K, _T, _R, "CALL")
        assert iv is not None
        assert iv == pytest.approx(_SIGMA, abs=1e-6)

    def test_iv_round_trip_put(self):
        """Invert BS (put) to recover the input sigma."""
        price = bs_price(_S, _K, _T, _R, _SIGMA, "PUT")
        iv = implied_vol(price, _S, _K, _T, _R, "PUT")
        assert iv is not None
        assert iv == pytest.approx(_SIGMA, abs=1e-6)

    def test_iv_invalid_inputs_return_none(self):
        """Invalid inputs (T<=0, price<=0, S<=0, K<=0) -> None."""
        assert implied_vol(5.0, 100.0, 100.0, 0.0, 0.05, "CALL") is None     # T<=0
        assert implied_vol(5.0, 100.0, 100.0, -1.0, 0.05, "CALL") is None    # T<0
        assert implied_vol(-5.0, 100.0, 100.0, 1.0, 0.05, "CALL") is None    # price<0
        assert implied_vol(5.0, 0.0, 100.0, 1.0, 0.05, "CALL") is None       # S<=0
        assert implied_vol(5.0, 100.0, 0.0, 1.0, 0.05, "CALL") is None       # K<=0
        assert implied_vol(5.0, 100.0, 100.0, 1.0, 0.05, "WTF") is None      # bad type

    def test_iv_below_intrinsic_returns_none(self):
        """A market price below the option's intrinsic value is an arbitrage
        violation -- no positive sigma can reproduce it, so IV returns None."""
        # Deep ITM call: S=200, K=100 -> intrinsic = 100.
        # A price of 0.01 is far below intrinsic -- impossible.
        assert implied_vol(0.01, 200.0, 100.0, 1.0, 0.05, "CALL") is None
        # Same for a deep ITM put: S=100, K=200 -> intrinsic = 100.
        assert implied_vol(0.01, 100.0, 200.0, 1.0, 0.05, "PUT") is None

    def test_intrinsic_at_t_zero(self):
        """At T=0 the option is worth its intrinsic value (max(S-K, 0) for calls)."""
        # ITM call: S=105, K=100 -> intrinsic = 5.
        assert bs_price(105.0, 100.0, 0.0, 0.05, 0.20, "CALL") == pytest.approx(5.0)
        # OTM call: S=95, K=100 -> intrinsic = 0.
        assert bs_price(95.0, 100.0, 0.0, 0.05, 0.20, "CALL") == pytest.approx(0.0)
        # ITM put: S=100, K=105 -> intrinsic = 5.
        assert bs_price(100.0, 105.0, 0.0, 0.05, 0.20, "PUT") == pytest.approx(5.0)
        # OTM put: S=100, K=95 -> intrinsic = 0.
        assert bs_price(100.0, 95.0, 0.0, 0.05, 0.20, "PUT") == pytest.approx(0.0)

    def test_vega_positive(self):
        """Vega is always > 0 (option price is monotonic in sigma)."""
        v = bs_vega(_S, _K, _T, _R, _SIGMA)
        assert v > 0
        # Vega scales with sqrt(T) for ATM options.
        v_short = bs_vega(_S, _K, 0.25, _R, _SIGMA)
        assert 0 < v_short < v  # shorter T -> smaller vega.

    def test_norm_cdf_basics(self):
        """Sanity-check _norm_cdf at known quantiles."""
        assert _norm_cdf(0.0) == pytest.approx(0.5, abs=1e-12)
        assert _norm_cdf(-10.0) == pytest.approx(0.0, abs=1e-20)
        assert _norm_cdf(10.0)  == pytest.approx(1.0, abs=1e-20)
        # Symmetry: Phi(x) + Phi(-x) = 1.
        assert _norm_cdf(1.5) + _norm_cdf(-1.5) == pytest.approx(1.0, abs=1e-12)
