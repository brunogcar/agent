"""skills/b3/options/engines.py -- Black-Scholes pricing + implied vol engine.

Pure-Python Black-Scholes implementation for the options skill. No external
libs (no scipy, no numpy). Used by the IV tab (dashboard mode) to compute
implied volatility per option from the option's market price + the spot
price of the underlying + the Selic risk-free rate.

Functions:
  - _norm_cdf(x)                     -- standard normal CDF via math.erf
  - bs_price(S, K, T, r, sigma, ...) -- Black-Scholes call/put price
  - bs_vega(S, K, T, r, sigma)       -- dPrice/dSigma (for Newton-Raphson)
  - implied_vol(price, S, K, T, ...) -- invert BS to find sigma

[v1.2] First added -- implements P1 of the options ROADMAP (Implied
Volatility via Black-Scholes). The IV tab uses the Selic rate from BCB SGS
(series 432 = "Meta Selic Copom", unit "% a.a.") as the risk-free rate.

Design notes:
  - All angles are in radians (math.log, math.sqrt, math.erf are pure-Python).
  - T is in YEARS (callers must convert (maturity - refdate).days / 365).
  - r is the annualized continuous-compounding rate. The Selic "% a.a."
    series is annualized already, but it's a simple rate -- converting to
    continuous is r_cont = ln(1 + r_simple). We do this in the dashboard
    before calling the engine (engines.py stays pure math).
  - Returns None for invalid inputs (T <= 0, sigma <= 0, price < intrinsic)
    so callers can render "-" in the IV table without raising.
"""
from __future__ import annotations

import math


def _norm_cdf(x: float) -> float:
    """Standard normal cumulative distribution function.

    Uses the identity: Phi(x) = 0.5 * (1 + erf(x / sqrt(2))).
    math.erf is available in the CPython standard library (no scipy needed).
    """
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def bs_price(S: float, K: float, T: float, r: float, sigma: float,
             option_type: str = "CALL") -> float:
    """Black-Scholes option price.

    Args:
        S:           Spot price of the underlying.
        K:           Strike price.
        T:           Time to maturity in YEARS (must be > 0).
        r:           Annualized continuous-compounding risk-free rate
                     (e.g. 0.10 for 10%).
        sigma:       Annualized volatility (e.g. 0.30 for 30%).
        option_type: "CALL" or "PUT" (case-insensitive).

    Returns:
        Theoretical option price.

    Raises:
        ValueError: if T <= 0 or sigma <= 0 (degenerate inputs).
    """
    if T <= 0:
        # At expiry the option is worth its intrinsic value.
        if option_type.upper() == "CALL":
            return max(S - K, 0.0)
        return max(K - S, 0.0)
    if sigma <= 0:
        # No volatility: option value = discounted intrinsic.
        disc = math.exp(-r * T)
        if option_type.upper() == "CALL":
            return max(S - K * disc, 0.0)
        return max(K * disc - S, 0.0)

    sqrtT = math.sqrt(T)
    d1 = (math.log(S / K) + (r + 0.5 * sigma * sigma) * T) / (sigma * sqrtT)
    d2 = d1 - sigma * sqrtT

    if option_type.upper() == "CALL":
        return S * _norm_cdf(d1) - K * math.exp(-r * T) * _norm_cdf(d2)
    if option_type.upper() == "PUT":
        return K * math.exp(-r * T) * _norm_cdf(-d2) - S * _norm_cdf(-d1)
    raise ValueError(f"invalid option_type: {option_type!r} (must be CALL or PUT)")


def bs_vega(S: float, K: float, T: float, r: float, sigma: float) -> float:
    """Black-Scholes vega = dPrice/dSigma (same for calls and puts).

    Args:
        S:     Spot price.
        K:     Strike price.
        T:     Time to maturity (years, must be > 0).
        r:     Risk-free rate (annualized continuous).
        sigma: Volatility (annualized, must be > 0).

    Returns:
        Vega (always >= 0 -- option price is monotonic in sigma for vanilla
        European options).

    Raises:
        ValueError: if T <= 0 or sigma <= 0.
    """
    if T <= 0 or sigma <= 0:
        raise ValueError(f"invalid T ({T}) or sigma ({sigma}) for vega")
    sqrtT = math.sqrt(T)
    d1 = (math.log(S / K) + (r + 0.5 * sigma * sigma) * T) / (sigma * sqrtT)
    # Vega = S * sqrt(T) * phi(d1), where phi is the standard normal PDF.
    pdf_d1 = math.exp(-0.5 * d1 * d1) / math.sqrt(2.0 * math.pi)
    return S * sqrtT * pdf_d1


# Clamping range for implied_vol. Outside [0.01, 5.0] something is wrong with
# the inputs (negative price, T <= 0, etc.) so we return None instead.
_IV_MIN = 0.01    # 1% vol floor
_IV_MAX = 5.0     # 500% vol ceiling (covers deep ITM degenerate cases)


def implied_vol(price: float, S: float, K: float, T: float, r: float,
                option_type: str = "CALL",
                tol: float = 1e-6, max_iter: int = 100) -> float | None:
    """Compute implied volatility from a market option price via Newton-Raphson.

    Inverts the Black-Scholes pricing formula to find the sigma that produces
    `price`. Falls back to bisection if Newton-Raphson diverges (vega -> 0
    near expiry or deep ITM/OTM).

    Args:
        price:       Observed market price of the option (must be > 0).
        S:           Spot price of the underlying.
        K:           Strike price.
        T:           Time to maturity in YEARS (must be > 0).
        r:           Risk-free rate (annualized continuous compounding).
        option_type: "CALL" or "PUT".
        tol:         Convergence tolerance on the price residual.
        max_iter:    Max Newton-Raphson iterations.

    Returns:
        The implied volatility (sigma) clamped to [_IV_MIN, _IV_MAX], or
        None if the inputs are invalid (price <= 0, T <= 0, S <= 0, K <= 0,
        or the solver fails to converge).
    """
    # Validate inputs
    if price is None or S <= 0 or K <= 0 or T <= 0 or price <= 0:
        return None
    otype = option_type.upper()
    if otype not in ("CALL", "PUT"):
        return None

    # Check intrinsic-value floor. If the market price is below the option's
    # intrinsic value, no positive sigma can reproduce it (arbitrage
    # violation) -- return None.
    if otype == "CALL":
        intrinsic = max(S - K, 0.0)
    else:
        intrinsic = max(K - S, 0.0)
    if price < intrinsic - 1e-9:
        return None

    # Newton-Raphson with bisection fallback
    sigma = 0.2  # Initial guess: 20% vol (a reasonable mid-point for equities).
    for _ in range(max_iter):
        try:
            p = bs_price(S, K, T, r, sigma, otype)
        except ValueError:
            return None
        diff = p - price
        if abs(diff) < tol:
            return float(max(_IV_MIN, min(_IV_MAX, sigma)))
        try:
            v = bs_vega(S, K, T, r, sigma)
        except ValueError:
            return None
        if v < 1e-10:
            # Vega too small -- Newton-Raphson would divide by ~0. Bail out
            # to bisection (which doesn't need vega).
            break
        # Newton step: sigma_new = sigma - (price_diff / vega).
        sigma_new = sigma - diff / v
        # If Newton leaves the valid range, fall back to bisection.
        if not (_IV_MIN <= sigma_new <= _IV_MAX):
            break
        if abs(sigma_new - sigma) < tol:
            return float(max(_IV_MIN, min(_IV_MAX, sigma_new)))
        sigma = sigma_new

    # Bisection fallback (robust when Newton diverges)
    lo, hi = _IV_MIN, _IV_MAX
    try:
        p_lo = bs_price(S, K, T, r, lo, otype)
        p_hi = bs_price(S, K, T, r, hi, otype)
    except ValueError:
        return None
    # If the target price is outside [p_lo, p_hi], no sigma in our clamp
    # range reproduces it -- return None.
    if price < p_lo - tol or price > p_hi + tol:
        return None
    # Bisection needs the residual to have opposite signs at lo and hi.
    # If price is between p_lo and p_hi, this is guaranteed for vanilla BS.
    for _ in range(max_iter):
        mid = 0.5 * (lo + hi)
        try:
            p_mid = bs_price(S, K, T, r, mid, otype)
        except ValueError:
            return None
        if abs(p_mid - price) < tol:
            return float(mid)
        # BS price is monotonic increasing in sigma -- if the target is
        # above the mid-price, the true sigma is above mid.
        if price > p_mid:
            lo = mid
        else:
            hi = mid
        if hi - lo < tol:
            return float(mid)
    return None
