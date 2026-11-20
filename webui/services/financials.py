"""webui/services/financials.py — financial data service.

[WebUI v1.3 fix 1] Financial data for the Financials tab. Direct imports from
skills/cvm — NOT through the MCP dispatcher.

[v1.3 fix 1] Fixes from user feedback:
  - overview(): "Resultado TTM" now comes from the REAL ttm mode
    (compute_ttm_with_engines — trailing twelve months ending at the latest
    quarter), NOT the latest annual statement. Latest + year-ago TTM are
    returned so the UI can show a Δ 1A column.
  - overview(): Trajetória Anual now fetches periods=10 (matches the static
    dashboard: 2016→2025) and includes year-end closing prices for the
    dashed price overlay (right axis).
  - overview(): Red Flags are now computed server-side via
    build_red_flags_section() (BPA/BPP/DRE/DVA consistency + PL/FCO checks)
    instead of a client-side loading placeholder that never resolved.
  - statements(): ONE SQL pass via _fetch_all_statements_annual/_quarterly
    (replaces 5 separate mode calls). Quarterly values are STANDALONE
    (curr_cum − prev_cum), matching the static dashboard. Response is a
    compact columnar shape {labels, dates, statements: {G: rows[]}} so the
    client can switch Completo/BPA/BPP/DRE/DFC/DVA without refetching.

Provides:
  - overview(ticker) → ttm + annual + quarterly + ratios + prices + red flags
  - statements(ticker, period, periods) → all 5 statements, columnar

[WebUI v1.5] HARDENING:
  - overview() reuses the module-level CompanyService singleton (was a
    fresh instance per call).
  - statements() runs inside engine_cache_scope() (shares the in-memory
    engine cache with the rest of the request).
  - _red_flags() returns a distinct {"error": …} state instead of None on
    failure — the UI can now tell "checked, no warnings" apart from
    "couldn't check" (the old bare except showed a false all-clear).
  - *_error strings are PT-BR (raw exceptions logged server-side).
"""
from __future__ import annotations

import sys
import traceback
from typing import Any

from webui.services.company import CompanyService

# Module-level singleton (overview() used to build a fresh CompanyService
# on every call — every other service here is a module singleton too).
_company = CompanyService()


# Number of TTM periods to fetch (latest + 4-back gives the Δ 1A comparison).
_TTM_PERIODS = 5
# Annual periods for the Trajetória chart (static dashboard uses 10 → 2016+).
_ANNUAL_PERIODS = 10
# Quarters shown in the quarterly trend table.
_QUARTERLY_PERIODS = 8


class FinancialsService:
    """Financial data service — wraps financials modes directly."""

    def overview(self, ticker: str) -> dict[str, Any]:
        """Overview data: TTM + annual + quarterly summaries + risk metrics.

        Returns the data needed for:
          - Resultado TTM table (real trailing-twelve-months, latest quarter)
          - Balanço + Fluxo de Caixa tables (TTM metrics / 4Q averages)
          - Margens table (computed from TTM flows)
          - Trajetória Anual chart (Receita/EBITDA/Lucro bars + price line,
            periods=10 → from 2016 like the static dashboard)
          - Quarterly Trend table (QoQ deltas)
          - WACC + DuPont + Altman Z tables
          - Red Flags (server-side accounting consistency checks)
        """
        tk = ticker.upper()
        result: dict[str, Any] = {"ticker": tk}

        # ── 1. Latest TTM (real trailing twelve months) ──
        # The ttm mode returns periods OLDEST-FIRST; the last entry is the
        # latest TTM window (ending at the most recent quarter). We keep the
        # last 2 to compute the Δ 1A in the UI (latest vs 4 quarters back).
        try:
            from skills._base import engine_cache_scope
            from skills.cvm.financials.modes.ttm import ttm as ttm_mode
            with engine_cache_scope():
                ttm_data = ttm_mode(company=tk, periods=_TTM_PERIODS)
            if ttm_data.get("status") == "ok" and ttm_data.get("periods"):
                periods = ttm_data["periods"]
                latest = periods[-1]
                year_ago = periods[0] if len(periods) >= _TTM_PERIODS else None
                result["ttm"] = {
                    "period_range": latest.get("period_range", ""),
                    "ttm_date": latest.get("ttm_date", ""),
                    "quarter": latest.get("quarter", ""),
                    "metrics": latest.get("metrics", {}),
                    "ratios": latest.get("ratios", {}),
                    "year_ago_metrics": (year_ago or {}).get("metrics", {}),
                }
            else:
                result["ttm"] = None
        except Exception as e:
            result["ttm"] = None
            result["ttm_error"] = str(e)

        # ── 2. Annual summary (10 years — Trajetória from 2016) ──
        try:
            from skills.cvm.financials.modes.annual import annual
            annual_data = annual(company=tk, periods=_ANNUAL_PERIODS)
            result["annual"] = annual_data if annual_data.get("status") == "ok" else None
        except Exception as e:
            result["annual"] = None
            result["annual_error"] = str(e)

        # ── 3. Quarterly summary (8 quarters — trend table) ──
        try:
            from skills.cvm.financials.modes.quarterly import quarterly
            quarterly_data = quarterly(company=tk, periods=_QUARTERLY_PERIODS)
            result["quarterly"] = quarterly_data if quarterly_data.get("status") == "ok" else None
        except Exception as e:
            result["quarterly"] = None
            result["quarterly_error"] = str(e)

        # ── 4. Ratios (WACC / DuPont / Altman — point-in-time) ──
        try:
            ratios = _company.ratios(tk)
            result["ratios"] = ratios if "_error" not in ratios else None
        except Exception as e:
            result["ratios"] = None
            result["ratios_error"] = "falha ao calcular indicadores"
            print(f"[webui] financials.overview ratios({tk}) failed: {e}\n"
                  f"{traceback.format_exc()}", file=sys.stderr)

        # ── 5. Year-end prices for the Trajetória overlay ──
        # {year: close} — Dec-31 (or closest prior trading day) close.
        result["year_end_prices"] = self._year_end_prices(tk, result.get("annual"))

        # ── 6. Red Flags (server-side accounting consistency checks) ──
        result["red_flags"] = self._red_flags(tk, result.get("annual"))

        return result

    # ── helpers ─────────────────────────────────────────────────────────────

    @staticmethod
    def _year_end_prices(ticker: str, annual_result: dict | None) -> dict[str, float]:
        """Dec-31 (closest prior trading day) close per year label.

        Mirrors skills/cvm/financials/report/overview.py::_fetch_year_end_prices
        (single price_series fetch for the whole year range).
        """
        try:
            periods = (annual_result or {}).get("periods") or []
            years = [str(p.get("period")) for p in periods if p.get("period")]
            if not years:
                return {}
            from skills.cvm.calculations.engines.price import price_series
            series = price_series(
                ticker, f"{min(years)}-01-01", f"{max(years)}-12-31")
            by_year: dict[str, float] = {}
            for point in series or []:
                d = point.get("date") or ""
                if len(d) >= 4 and point.get("close") is not None:
                    by_year[d[:4]] = float(point["close"])
            return {y: by_year[y] for y in years if y in by_year}
        except Exception:
            return {}

    @staticmethod
    def _red_flags(ticker: str, annual_result: dict | None) -> dict | None:
        """Accounting red flags via build_red_flags_section.

        [WebUI v1.5] Returns {"error": …} on failure (distinct from None =
        nothing to check) so the UI can render "verificação indisponível"
        instead of a false "no red flags" all-clear.

        Fetches the 5 statements in ONE SQL pass (annual, 5 years), reshapes
        them to the dict-keyed accounts shape validate_statement_consistency
        expects, and extracts the check rows for the UI.
        """
        try:
            from skills.cvm.financials.fetchers import _fetch_all_statements_annual
            from skills.cvm.financials.report.analysis import build_red_flags_section

            all_data = _fetch_all_statements_annual(ticker, 1, 5)
            if not isinstance(all_data, dict) or "BPA" not in all_data:
                return None

            def _keyed(grupo: str) -> dict:
                """Reshape accounts list → {codigo: {label, valor_brl}}."""
                src = all_data.get(grupo) or {}
                out_periods = []
                for p in src.get("periods") or []:
                    accounts = {}
                    for a in p.get("accounts") or []:
                        accounts[a.get("codigo", "")] = {
                            "label": a.get("descricao") or a.get("codigo", ""),
                            "valor_brl": a.get("valor_brl"),
                        }
                    out_periods.append({
                        "data_fim_exerc": p.get("data_fim_exerc")
                            or f"{p.get('year')}-12-31",
                        "accounts": accounts,
                    })
                return {"status": src.get("status", "ok"), "periods": out_periods}

            section = build_red_flags_section(
                _keyed("BPA"), _keyed("BPP"), _keyed("DRE"),
                _keyed("DFC_MI"), _keyed("DVA"),
                (annual_result or {}).get("periods") or [],
            )
            rows: list[list[str]] = []
            for sub in section.get("sections") or []:
                rows.extend(sub.get("rows") or [])
            if not rows:
                return None
            return {
                "rows": rows,
                "has_warnings": any("⚠" in str(r[1]) for r in rows if len(r) > 1),
            }
        except Exception as e:
            print(f"[webui] red_flags({ticker}) failed: {e}\n"
                  f"{traceback.format_exc()}", file=sys.stderr)
            return {"error": "verificação indisponível"}

    # ── statements ──────────────────────────────────────────────────────────

    def statements(self, ticker: str, period: str = "annual",
                   periods: int | None = None) -> dict[str, Any]:
        """All 5 statements (BPA/BPP/DRE/DFC/DVA) in ONE SQL pass.

        [v1.3 fix 1] Replaces the per-statement mode calls (bpa/bpp/dre/dfc/dva —
        5 SQL passes, cumulative quarterly values) with the single-fetch
        helpers used by the static dashboard's financials mode:
          - annual    → _fetch_all_statements_annual   (DFP, meses=12)
          - quarterly → _fetch_all_statements_quarterly (ITR+DFP, STANDALONE
                        flows = curr_cum − prev_cum; BPA/BPP snapshots with
                        carry-forward)

        Returns a compact columnar shape — the client switches
        Completo/BPA/BPP/DRE/DFC/DVA views without refetching:
          {
            "ticker", "status": "ok", "period_type",
            "labels": ["2016", ..., "2025"] | ["4T2024", ..., "3T2026"],  # oldest-first [v1.3 fix 4]
            "dates":  ["2016-12-31", ...],
            "statements": {
              "BPA": {"rows": [{"codigo", "label", "section", "values": [...]}]},
              "BPP": {...}, "DRE": {...}, "DFC": {...}, "DVA": {...}
            }
          }

        Args:
          ticker: B3 ticker.
          period: "annual" (default) or "quarterly".
          periods: Number of periods. Default 10 annual / 20 quarterly
                   (matches the static dashboard).
        """
        tk = ticker.upper()
        period = (period or "annual").strip().lower()
        if period not in ("annual", "quarterly"):
            return {"_error": f"período inválido: use 'annual' ou 'quarterly' (recebido: '{period}')"}

        n = periods if periods else (10 if period == "annual" else 20)
        n = max(1, min(int(n), 40))

        try:
            from skills._base import engine_cache_scope
            from skills.cvm.financials.fetchers import (
                _fetch_all_statements_annual,
                _fetch_all_statements_quarterly,
            )
            with engine_cache_scope():
                if period == "quarterly":
                    data = _fetch_all_statements_quarterly(tk, 1, n)
                else:
                    data = _fetch_all_statements_annual(tk, 1, n)
        except Exception as e:
            print(f"[webui] statements({tk}) failed: {e}\n{traceback.format_exc()}",
                  file=sys.stderr)
            return {"_error": "erro ao carregar demonstrações"}

        if not isinstance(data, dict) or "BPA" not in data:
            err = data.get("error") if isinstance(data, dict) else None
            return {"_error": err or "sem dados de demonstrações"}

        # ── Build the columnar shape from the per-grupo results ──
        from skills.cvm.financials.modes._statement_sections import (
            bpa_section_for, bpp_section_for, dre_section_for,
            dfc_section_for, dva_section_for,
        )

        # 1. Labels + dates from the first grupo with periods (all grupos
        #    share the same period list construction).
        #    NOTE: annual fetchers return NEWEST-FIRST; quarterly fetchers
        #    (_build_quarter_labels) return OLDEST-FIRST. [WebUI v1.3 fix 4]
        #    Normalize BOTH to OLDEST-FIRST — Comparativo Anual and
        #    Comparativo Trimestral tables (and their charts) flow left →
        #    right, oldest period first, matching the Visão Geral trend.
        labels: list[str] = []
        dates: list[str] = []
        for grupo in ("BPA", "BPP", "DRE", "DFC_MI", "DVA"):
            src = data.get(grupo) or {}
            if src.get("status") == "ok" and src.get("periods"):
                for p in src["periods"]:
                    if period == "quarterly":
                        labels.append(str(p.get("period") or ""))
                    else:
                        labels.append(str(p.get("year")
                                          or (p.get("data_fim_exerc") or "")[:4]))
                    dates.append(p.get("data_fim_exerc") or "")
                break

        if not labels:
            return {"_error": "sem períodos disponíveis"}

        # [WebUI v1.3 fix 4] Annual arrives newest-first → flip it. Quarterly
        # already arrives oldest-first → keep as-is. Both end up oldest-first.
        if period == "annual":
            labels.reverse()
            dates.reverse()

        n_cols = len(labels)
        label_to_idx = {lab: i for i, lab in enumerate(labels)}

        def _col_index(p: dict) -> int | None:
            """Column index for a grupo's period, matched BY LABEL (not by
            position — grupos can have diverging period lists, e.g. DVA
            starting later than BPA)."""
            if period == "quarterly":
                key = str(p.get("period") or "")
                return label_to_idx.get(key)
            key = str(p.get("year") or (p.get("data_fim_exerc") or "")[:4])
            return label_to_idx.get(key)

        def _code_sort_key(row: dict) -> tuple:
            """'1.01.02' → (1, 1, 2) — natural numeric account ordering."""
            parts: list[int] = []
            for chunk in str(row.get("codigo", "")).split("."):
                try:
                    parts.append(int(chunk))
                except ValueError:
                    parts.append(9999)
            return tuple(parts)

        # 2. Rows per grupo: {codigo, label, section, values[n_cols]}.
        #    Accounts missing in a given period → None (UI shows "—").
        def _rows(grupo: str, section_fn) -> list[dict]:
            src = data.get(grupo) or {}
            by_code: dict[str, dict] = {}
            for p in src.get("periods") or []:
                col = _col_index(p)
                if col is None:
                    continue
                for a in p.get("accounts") or []:
                    code = a.get("codigo") or ""
                    if not code:
                        continue
                    row = by_code.setdefault(code, {
                        "codigo": code,
                        "label": a.get("descricao") or code,
                        "section": section_fn(code),
                        "values": [None] * n_cols,
                    })
                    if a.get("descricao"):
                        row["label"] = a["descricao"]
                    row["values"][col] = a.get("valor_brl")
            return sorted(by_code.values(), key=_code_sort_key)

        statements = {
            "BPA": {"rows": _rows("BPA", bpa_section_for)},
            "BPP": {"rows": _rows("BPP", bpp_section_for)},
            "DRE": {"rows": _rows("DRE", dre_section_for)},
            "DFC": {"rows": _rows("DFC_MI", dfc_section_for)},
            "DVA": {"rows": _rows("DVA", dva_section_for)},
        }

        return {
            "ticker": tk,
            "status": "ok",
            "period_type": period,
            "labels": labels,
            "dates": dates,
            "statements": statements,
        }
