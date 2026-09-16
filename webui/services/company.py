"""webui/services/company.py — company data service.

[WebUI v1] The ONLY layer that imports skills/cvm/_shared_report +
calculations engines. Routes call this, not the engines directly.

Reuses build_company_header() directly (it already fetches FCA/CAD/
COTAHIST/B3-instruments + computes market cap + total shares).

For the valuation tab, imports compute_all_ratios directly (bypasses
the MCP skill() dispatcher — 10-100x faster, type-safe, no JSON
serialization overhead).
"""
from __future__ import annotations

from datetime import date
from typing import Any

from skills.cvm._shared_report.company_header import build_company_header


class CompanyService:
    """Company data service — wraps skill engines for the WebUI."""

    def header(self, ticker: str) -> dict[str, Any]:
        """Company header data (identity + registration + market cap + shares).

        Reuses build_company_header() — already fetches FCA/CAD/COTAHIST/
        B3-instruments + computes market_cap + total_shares.
        """
        return build_company_header(ticker)

    def search(self, query: str, limit: int = 10) -> list[dict[str, str]]:
        """Ticker search via the bridge DB. Returns [{ticker, name}, ...]."""
        q = (query or "").strip().upper()
        if not q or len(q) < 1:
            return []
        try:
            from data_sources.cvm._db import bridge_db_path
            import sqlite3
            db = bridge_db_path()
            if not db.exists():
                return []
            conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
            conn.row_factory = sqlite3.Row
            # The bridge table is "ticker_map" with columns:
            # ticker, cd_cvm, trading_name, cnpj
            # Match ticker prefix OR trading_name substring
            rows = conn.execute(
                """SELECT ticker, trading_name as name FROM ticker_map
                   WHERE UPPER(ticker) LIKE ? OR UPPER(trading_name) LIKE ?
                   ORDER BY ticker LIMIT ?""",
                (f"{q}%", f"%{q}%", limit),
            ).fetchall()
            conn.close()
            return [{"ticker": r["ticker"], "name": r["name"] or ""} for r in rows]
        except Exception:
            return []

    def ratios(self, ticker: str) -> dict[str, Any]:
        """Valuation ratios via direct compute_all_ratios import.

        Bypasses the MCP skill() dispatcher — direct Python call.
        Uses the existing engine_cache_scope for caching.
        """
        try:
            from skills._base import engine_cache_scope
            from skills.cvm.calculations._registry import compute_all_ratios
            today = date.today().isoformat()
            with engine_cache_scope():
                return compute_all_ratios(ticker, today)
        except Exception as e:
            return {"_error": str(e)}

    def price_series(self, ticker: str, years: int = 5) -> list[dict]:
        """Historical daily price series for the price chart.

        Accepts fractional years (0.083 = 1 month, 0.5 = 6 months, 10 = 10 years).
        """
        try:
            from skills.cvm.calculations.engines.price import price_series as _price_series
            from datetime import date, timedelta
            date_to = date.today().isoformat()
            # Convert years to days (365.25 to account for leap years)
            days = int(years * 365.25)
            date_from = (date.today() - timedelta(days=days)).isoformat()
            return _price_series(ticker, date_from, date_to)
        except Exception:
            return []
