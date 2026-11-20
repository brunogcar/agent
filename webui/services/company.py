"""webui/services/company.py — company data service.

[WebUI v1] The ONLY layer that imports skills/cvm/_shared_report +
calculations engines. Routes call this, not the engines directly.

Reuses build_company_header() directly (it already fetches FCA/CAD/
COTAHIST/B3-instruments + computes market cap + total shares).

For the valuation tab, imports compute_all_ratios directly (bypasses
the MCP skill() dispatcher — 10-100x faster, type-safe, no JSON
serialization overhead).

[WebUI v1.5] HARDENING:
  - search(): LIKE wildcards in user input are escaped (a literal "%" or
    "_" used to match every row); results are relevance-ranked (exact
    ticker first, then ticker prefix, then name substring); the sqlite
    connection now closes on the error path too (try/finally — a locked
    DB used to leak the handle on Windows).
  - ratios(): raw str(e) no longer reaches the UI (English internals in
    a pt-BR UI); the exception is logged server-side and the UI gets a
    short PT-BR message.
"""
from __future__ import annotations

import sys
import traceback
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
        """Ticker search via the bridge DB. Returns [{ticker, name}, ...].

        [WebUI v1.5] Wildcard-escaped + relevance-ranked (exact > prefix >
        name match). Connection closes even when the query raises.
        """
        q = (query or "").strip().upper()
        if not q:
            return []
        try:
            import contextlib
            import sqlite3
            from data_sources.cvm._db import bridge_db_path
            db = bridge_db_path()
            if not db.exists():
                return []
            # Escape LIKE wildcards so a literal "%"/"_" in the query can't
            # match every row (ESCAPE '\' declares the escape character).
            esc = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            with contextlib.closing(sqlite3.connect(f"file:{db}?mode=ro", uri=True)) as conn:
                conn.row_factory = sqlite3.Row
                # The bridge table is "ticker_map" with columns:
                # ticker, cd_cvm, trading_name, cnpj.
                rows = conn.execute(
                    """SELECT ticker, trading_name as name FROM ticker_map
                       WHERE UPPER(ticker) LIKE ? ESCAPE '\\'
                          OR UPPER(trading_name) LIKE ? ESCAPE '\\'
                       ORDER BY CASE
                           WHEN UPPER(ticker) = ? THEN 0
                           WHEN UPPER(ticker) LIKE ? ESCAPE '\\' THEN 1
                           ELSE 2
                       END, ticker LIMIT ?""",
                    (f"{esc}%", f"%{esc}%", esc, f"{esc}%", limit),
                ).fetchall()
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
            # Log the real error server-side; UI gets a short PT-BR message
            # (raw exception text leaked English internals into the UI).
            print(f"[webui] ratios({ticker}) failed: {e}\n{traceback.format_exc()}",
                  file=sys.stderr)
            return {"_error": "falha ao calcular os indicadores"}

    def price_series(self, ticker: str, years: int = 5) -> list[dict]:
        """Historical daily price series for the price chart.

        Accepts fractional years (0.083 = 1 month, 0.5 = 6 months, 10 = 10 years).
        """
        try:
            from skills.cvm.calculations.engines.price import price_series as _price_series
            from datetime import date, timedelta
            if not years or years <= 0 or years > 50:
                return []
            date_to = date.today().isoformat()
            # Convert years to days (365.25 to account for leap years)
            days = int(years * 365.25)
            date_from = (date.today() - timedelta(days=days)).isoformat()
            return _price_series(ticker, date_from, date_to)
        except Exception:
            return []
