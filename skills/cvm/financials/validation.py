"""skills/cvm/financials/validation.py -- Cross-statement consistency checks.

This module provides a single public function, ``validate_statement_consistency``,
that checks whether the numbers within a single statement period are
internally consistent (e.g., BPA 1 = 1.01 + 1.02; DRE 3.03 = 3.01 - 3.02;
etc.). It does NOT raise — instead, it returns a list of human-readable
warning strings describing each detected mismatch.

The check is INTENDED to surface data-entry or extraction bugs, not to
enforce strict accounting identity. A 5% tolerance is applied before
flagging — within tolerance, the period is considered consistent.

Usage:
    from skills.cvm.financials.validation import validate_statement_consistency

    r = bpp(company="PETR4", periods=5)
    warnings = validate_statement_consistency(r.get("periods", []), "bpp")
    for w in warnings:
        print(w)
"""
from __future__ import annotations


# Tolerance (5%) for cross-line consistency checks. Within tolerance, the
# period is considered consistent (no warning emitted). The tolerance is
# generous because filers sometimes round sub-totals differently across
# years, and small inconsistencies (< 5%) are usually rounding rather than
# data errors.
_TOLERANCE = 0.05


def _get_valor(accounts: dict, codigo: str) -> float | None:
    """Extract the ``valor_brl`` for a given codigo from a period's accounts.

    Args:
        accounts: ``{codigo: {label, section, valor_brl}}`` dict.
        codigo: CVM account code to look up (e.g. "1", "3.03", "7.08.04").

    Returns:
        The ``valor_brl`` as a float, or None if the codigo is missing or
        its value cannot be coerced to float.
    """
    if not accounts or codigo not in accounts:
        return None
    entry = accounts[codigo]
    if not isinstance(entry, dict):
        return None
    valor = entry.get("valor_brl")
    if valor is None:
        return None
    try:
        return float(valor)
    except (TypeError, ValueError):
        return None


def _pct_diff(observed: float, expected: float) -> float:
    """Return |observed - expected| / max(|expected|, 1.0) as a fraction.

    The denominator is clamped to >= 1.0 to avoid huge percentages when
    ``expected`` is near zero (e.g., DVA distribution summing to 0 when a
    filer has no wealth to distribute). For very small expected values, we
    treat the absolute difference as the percentage (so a 1 BRL mismatch
    on a 0 expected sum is 100% — flagged).
    """
    denom = max(abs(expected), 1.0)
    return abs(observed - expected) / denom


def _check_dva(period: dict, date_key: str) -> list[str]:
    """DVA: 7.08 ≈ 7.08.01 + 7.08.02 + 7.08.03 + 7.08.04 (and 7.10/7.11.*)."""
    accounts = period.get("accounts", {})
    warnings: list[str] = []

    # Total to distribute: prefer old-chart 7.08, fall back to new-chart 7.10
    total = _get_valor(accounts, "7.08")
    total_label = "7.08"
    if total is None:
        total = _get_valor(accounts, "7.10")
        total_label = "7.10"
    if total is None:
        return warnings  # Nothing to compare against

    # Distribution-side lines: prefer old-chart 7.08.0x, fall back to new-chart 7.11.0x
    components = []
    for old_code, new_code, label in [
        ("7.08.01", "7.11.01", "Pessoal"),
        ("7.08.02", "7.11.02", "Impostos"),
        ("7.08.03", "7.11.03", "Capital de Terceiros"),
        ("7.08.04", "7.11.04", "Capital Próprio"),
    ]:
        v = _get_valor(accounts, old_code)
        if v is None:
            v = _get_valor(accounts, new_code)
        if v is not None:
            components.append(v)

    if not components:
        return warnings  # No distribution lines to sum against

    expected = sum(components)
    if _pct_diff(total, expected) > _TOLERANCE:
        warnings.append(
            f"DVA {date_key}: total {total_label}={total:,.0f} diverges from "
            f"sum of distribution lines ({len(components)} componentes)={expected:,.0f} "
            f"({_pct_diff(total, expected) * 100:.1f}% off)"
        )
    return warnings


def _check_dre(period: dict, date_key: str) -> list[str]:
    """DRE: 3.01 - 3.02 ≈ 3.03 (revenue - costs ≈ gross profit)."""
    accounts = period.get("accounts", {})
    warnings: list[str] = []

    revenue = _get_valor(accounts, "3.01")
    cogs = _get_valor(accounts, "3.02")
    gross_profit = _get_valor(accounts, "3.03")

    if revenue is None or cogs is None or gross_profit is None:
        return warnings  # Need all three to check

    expected = revenue - cogs
    if _pct_diff(gross_profit, expected) > _TOLERANCE:
        warnings.append(
            f"DRE {date_key}: Resultado Bruto 3.03={gross_profit:,.0f} diverges "
            f"from Receita 3.01 - COGS 3.02 = {revenue:,.0f} - {cogs:,.0f} = "
            f"{expected:,.0f} ({_pct_diff(gross_profit, expected) * 100:.1f}% off)"
        )
    return warnings


def _check_bpa(period: dict, date_key: str) -> list[str]:
    """BPA: 1 ≈ 1.01 + 1.02 (total assets ≈ current + non-current).

    NOTE: Multiple labels per code (CVM chart drift). OLD chart: 1.01 =
    "Ativo Circulante", 1.02 = "Ativo Não Circulante". NEW chart: 1.01 =
    "Caixa e Equivalentes", 1.02 = "Aplicações Financeiras" (subsets of
    current assets, NOT the full current-asset total). This check is most
    reliable for OLD-chart filers; for NEW-chart filers the mismatch is
    expected and will surface as a warning (callers can ignore).
    """
    accounts = period.get("accounts", {})
    warnings: list[str] = []

    total = _get_valor(accounts, "1")
    current = _get_valor(accounts, "1.01")
    non_current = _get_valor(accounts, "1.02")

    if total is None or current is None or non_current is None:
        return warnings

    expected = current + non_current
    if _pct_diff(total, expected) > _TOLERANCE:
        warnings.append(
            f"BPA {date_key}: Ativo Total 1={total:,.0f} diverges from "
            f"1.01 + 1.02 = {current:,.0f} + {non_current:,.0f} = {expected:,.0f} "
            f"({_pct_diff(total, expected) * 100:.1f}% off) — may indicate "
            f"NEW-chart filer where 1.01/1.02 are sub-lines, not totals"
        )
    return warnings


def _check_bpp(period: dict, date_key: str) -> list[str]:
    """BPP: 2 ≈ 2.01 + 2.02 + 2.03 (total ≈ current + non-current + equity).

    NOTE: For NEW-chart filers, 2.03 = amortized-cost debt (NOT equity) and
    PL moves to 2.08. This check uses 2.03 (the engine's canonical PL code);
    for NEW-chart filers the check will flag a mismatch (callers can fall
    back to 2.08 manually).
    """
    accounts = period.get("accounts", {})
    warnings: list[str] = []

    total = _get_valor(accounts, "2")
    current = _get_valor(accounts, "2.01")
    non_current = _get_valor(accounts, "2.02")
    equity = _get_valor(accounts, "2.03")
    equity_new = _get_valor(accounts, "2.08")

    # For NEW-chart filers, prefer 2.08 over 2.03 (mirrors the pl engine).
    if equity_new is not None:
        equity = equity_new

    if total is None or current is None or non_current is None or equity is None:
        return warnings

    expected = current + non_current + equity
    if _pct_diff(total, expected) > _TOLERANCE:
        warnings.append(
            f"BPP {date_key}: Passivo Total 2={total:,.0f} diverges from "
            f"2.01 + 2.02 + 2.03 = {current:,.0f} + {non_current:,.0f} + "
            f"{equity:,.0f} = {expected:,.0f} ({_pct_diff(total, expected) * 100:.1f}% off)"
        )
    return warnings


def validate_statement_consistency(
    periods: list[dict],
    statement_type: str,
) -> list[str]:
    """Check cross-line consistency for each period in a statement.

    For each period dict in ``periods``, checks the internal arithmetic
    identity of the statement (e.g., BPA 1 ≈ 1.01 + 1.02). Returns a list
    of human-readable warning strings describing each detected mismatch.
    Does NOT raise.

    Args:
        periods: List of period dicts (as returned by the dva/dre/bpa/bpp
            standalone modes). Each dict must have a ``data_fim_exerc`` key
            (used as the period identifier in warning strings) and an
            ``accounts`` key holding ``{codigo: {label, section, valor_brl}}``.
        statement_type: One of ``"dva"``, ``"dre"``, ``"bpa"``, ``"bpp"``.
            Determines which consistency check is applied.

    Returns:
        List of warning strings. Empty list if all periods are consistent
        (within 5% tolerance) or if no periods are provided. Periods that
        lack the necessary codes to perform a check are silently skipped
        (no warning emitted for missing data).
    """
    if not periods:
        return []

    statement_type = statement_type.lower().strip()
    checker = {
        "dva": _check_dva,
        "dre": _check_dre,
        "bpa": _check_bpa,
        "bpp": _check_bpp,
    }.get(statement_type)

    if checker is None:
        return [
            f"Unknown statement_type '{statement_type}'. "
            f"Supported: dva, dre, bpa, bpp."
        ]

    warnings: list[str] = []
    for period in periods:
        if not isinstance(period, dict):
            continue
        date_key = str(period.get("data_fim_exerc", "?"))
        warnings.extend(checker(period, date_key))
    return warnings
