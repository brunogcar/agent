"""engines/shares.py — FRE shares outstanding engine.

Gets shares outstanding at any historical date from FRE distribuicao_capital
+ capital_social tables. Falls back to investsite (current only) for the
latest count, then assumes constant going backward.

Standalone module: importable by historical skill + future backtest skill.

Usage:
    from skills.cvm.calculations.engines.shares import shares_at
    s = shares_at("PETR4", "2024-06-30")  # → 13000000000
"""

from __future__ import annotations
from skills._base import engine_cached  # [v1.8 F7]


def _try_fre(cnpj: str, date: str) -> int | None:
    """Try FRE distribuicao_capital + capital_social for shares at date."""
    from data_sources.cvm._db import connect_fre

    try:
        conn = connect_fre(read_only=True)
    except FileNotFoundError:
        return None

    try:
        # Try distribuicao_capital — check qtd_total, then ON+PN sum
        row = conn.execute(
            "SELECT qtd_total_circulacao, qtd_on_circulacao, qtd_pn_circulacao "
            "FROM distribuicao_capital "
            "WHERE REPLACE(REPLACE(REPLACE(cnpj, '.', ''), '/', ''), '-', '') = ? "
            "AND data_referencia <= ? "
            "ORDER BY data_referencia DESC LIMIT 1",
            (cnpj, date),
        ).fetchone()

        if row:
            total = row["qtd_total_circulacao"] if row["qtd_total_circulacao"] else None
            if not total:
                on = row["qtd_on_circulacao"] if row["qtd_on_circulacao"] else 0
                pn = row["qtd_pn_circulacao"] if row["qtd_pn_circulacao"] else 0
                if on or pn:
                    total = on + pn
            if total:
                return int(total)

        # Try capital_social — check qtd_acoes_total, then ON+PN sum
        row = conn.execute(
            "SELECT qtd_acoes_total, qtd_acoes_on, qtd_acoes_pn "
            "FROM capital_social "
            "WHERE REPLACE(REPLACE(REPLACE(cnpj, '.', ''), '/', ''), '-', '') = ? "
            "AND data_referencia <= ? "
            "ORDER BY data_referencia DESC LIMIT 1",
            (cnpj, date),
        ).fetchone()

        if row:
            total = row["qtd_acoes_total"] if row["qtd_acoes_total"] else None
            if not total:
                on = row["qtd_acoes_on"] if row["qtd_acoes_on"] else 0
                pn = row["qtd_acoes_pn"] if row["qtd_acoes_pn"] else 0
                if on or pn:
                    total = on + pn
            if total:
                return int(total)

        return None
    except Exception:
        return None
    finally:
        conn.close()


def _try_investsite(ticker: str) -> int | None:
    """Get current shares from investsite (fallback for missing FRE data).

    investsite only has current data — used as a last resort. The historical
    engine assumes shares are constant going backward from the latest available.
    """
    try:
        from skills.investsite.modes.indicators import indicators
        r = indicators(ticker=ticker)
        if r.get("status") != "ok":
            return None
        balanco = r.get("sections", {}).get("balanco_patrimonial", {})
        total_str = balanco.get("Total")
        if total_str is None:
            return None
        if isinstance(total_str, (int, float)):
            return int(total_str)
        clean = str(total_str).strip().replace(".", "").replace(",", "")
        try:
            return int(clean)
        except ValueError:
            try:
                return int(float(clean))
            except ValueError:
                return None
    except Exception:
        return None


@engine_cached
def shares_at(company: str, date: str) -> int | None:
    """Get shares outstanding closest to date.

    Resolution order:
    1. FRE distribuicao_capital (qtd_total or ON+PN) at or before date
    2. FRE capital_social (qtd_acoes_total or ON+PN) at or before date
    3. Investsite current shares (assumed constant going backward)

    Args:
        company: Ticker, name, or CNPJ.
        date: YYYY-MM-DD.

    Returns:
        Total shares outstanding as int, or None if not available.
    """
    from data_sources.cvm._bridge import _resolve_via_bridge, _auto_sync_bridge

    # Resolve ticker → CNPJ
    cnpj, _ = _resolve_via_bridge(company)
    if not cnpj:
        _auto_sync_bridge(company)
        cnpj, _ = _resolve_via_bridge(company)
    if not cnpj:
        return None

    # Try FRE first
    shares = _try_fre(cnpj, date)
    if shares:
        return shares

    # Fallback: investsite (current only — assume constant backward)
    shares = _try_investsite(company)
    if shares:
        return shares

    return None


@engine_cached
def shares_periods(company: str) -> list[dict]:
    """Get all shares outstanding periods for a company.

    Returns: [{"date": "2024-12-31", "shares": 13000000000}, ...]
    Sorted oldest-first.

    If FRE has no share data, returns a single entry with investsite current
    shares (assumed constant). This enables the step-function lookup in
    pe_history() to work even without historical FRE share counts.
    """
    from data_sources.cvm._db import connect_fre
    from data_sources.cvm._bridge import _resolve_via_bridge

    cnpj, _ = _resolve_via_bridge(company)
    if not cnpj:
        return []

    try:
        conn = connect_fre(read_only=True)
    except FileNotFoundError:
        conn = None

    periods = []

    if conn:
        try:
            # Try distribuicao_capital
            rows = conn.execute(
                "SELECT data_referencia, qtd_total_circulacao, qtd_on_circulacao, qtd_pn_circulacao "
                "FROM distribuicao_capital "
                "WHERE REPLACE(REPLACE(REPLACE(cnpj, '.', ''), '/', ''), '-', '') = ? "
                "ORDER BY data_referencia ASC",
                (cnpj,),
            ).fetchall()

            for r in rows:
                total = r["qtd_total_circulacao"] if r["qtd_total_circulacao"] else None
                if not total:
                    on = r["qtd_on_circulacao"] if r["qtd_on_circulacao"] else 0
                    pn = r["qtd_pn_circulacao"] if r["qtd_pn_circulacao"] else 0
                    if on or pn:
                        total = on + pn
                if total:
                    periods.append({"date": r["data_referencia"], "shares": int(total)})

            # If no distribuicao_capital, try capital_social
            if not periods:
                rows = conn.execute(
                    "SELECT data_referencia, qtd_acoes_total, qtd_acoes_on, qtd_acoes_pn "
                    "FROM capital_social "
                    "WHERE REPLACE(REPLACE(REPLACE(cnpj, '.', ''), '/', ''), '-', '') = ? "
                    "ORDER BY data_referencia ASC",
                    (cnpj,),
                ).fetchall()

                for r in rows:
                    total = r["qtd_acoes_total"] if r["qtd_acoes_total"] else None
                    if not total:
                        on = r["qtd_acoes_on"] if r["qtd_acoes_on"] else 0
                        pn = r["qtd_acoes_pn"] if r["qtd_acoes_pn"] else 0
                        if on or pn:
                            total = on + pn
                    if total:
                        periods.append({"date": r["data_referencia"], "shares": int(total)})
        except Exception:
            pass
        finally:
            conn.close()

    # If FRE has no share data, use investsite as fallback (single entry, current)
    if not periods:
        shares = _try_investsite(company)
        if shares:
            # Use a very early date so it applies to all historical dates
            periods.append({"date": "2000-01-01", "shares": shares})

    return periods


# ── Register with the engine registry ────────────────────────────────────────

from skills.cvm.calculations._registry import EngineSpec, register_engine  # noqa: E402

register_engine(EngineSpec(
    name="shares",
    quantity="shares",
    at_fn=shares_at,
    periods_fn=shares_periods,
    source="FRE (distribuicao_capital) + investsite.com.br fallback",
    category="shares",
))
