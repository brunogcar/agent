"""webui/services/valuation.py — valuation data service.

[WebUI v1.4] Valuation tab data. Direct imports from skills/cvm — NOT
through the MCP dispatcher. Mirrors webui/services/financials.py.

Architecture: the static dashboard's report builders
(skills/cvm/valuation/report/*) return ready-made "section" dicts
(type: table / two_column / ratio_grid / chart / heatmap). This service
serializes them straight to JSON — the client renders them with ONE
generic section renderer (renderValSection in app.js). Improving a
subtab later = adding sections server-side, zero client rework.

Subtabs (one lazy endpoint each — client fetches on first click):
  - overview()     → KPI cards + heatmap + radar + Mercado/Resultado/
                     Balanço/Per-share two-column blocks
  - multiples()    → nested subtabs (Preço | EBIT/EBITDA | EV | Menos
                     Comuns): grouped tables + comparativo charts + the
                     dashboard's 5Y daily history charts (P/L-LPA-P/VP-VPA,
                     Múltiplos de Preço, Múltiplos EBIT, Múltiplos EBITDA,
                     Preço/Balanço, Ativo/Preço e Alavancagem — with the
                     Tudo/1A/6M/3M/1M range selector) + Per-share Values
                     (R$) table + monthly Histórico 5Y summary chart
  - intrinsic()    → DCF + TIR summary table + sensitivity table +
                     intrinsic-value-vs-terminal-g curve chart
  - fundamentals() → Rentabilidade (Retornos + Margens + 5Y trends) /
                     Liquidez e Alavancagem / Eficiência e Crescimento
  - all_metrics()  → every ratio grouped by category, PT-BR labels

Ratios come from the valuation ratios MODE (not raw compute_all_ratios):
the mode restores the true per-share values that compute_all_ratios
overwrites (lpa→P/E, vpa→P/VPA, dpa→DY, rps→P/S) and adds the manual
market ratios (P/L, P/VPA, EV, PSR, market_cap, dividend_yield,
divida_liquida_ebitda).
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any


class ValuationService:
    """Valuation data service — wraps valuation modes + report builders."""

    # ── shared: ratios dict from the valuation ratios mode ──────────────────

    def _ratios(self, ticker: str) -> dict[str, Any]:
        """Full ratios dict via the valuation ratios mode (NO cache scope —
        callers wrap the whole method in engine_cache_scope so the engine
        cache also covers the section builders that follow)."""
        try:
            from skills.cvm.valuation.modes.ratios import ratios as _ratios_mode
            out = _ratios_mode(ticker)
        except Exception as e:
            return {"_error": str(e)}
        if not isinstance(out, dict) or out.get("status") != "ok":
            err = out.get("error") if isinstance(out, dict) else None
            return {"_error": err or "sem dados de valuation"}
        r = out.get("ratios")
        if not isinstance(r, dict) or "status" in r:
            # Error/partial path inside ratios (e.g. price unavailable).
            note = (r.get("note") or r.get("error")) if isinstance(r, dict) else None
            err = note or "preço ou fundamentos indisponíveis"
            if isinstance(err, str) and err.startswith("Price unavailable:"):
                # [v1.4 fix1] PT-BR for the price-chain error prefix.
                err = "Preço indisponível — " + err[len("Price unavailable:"):].strip()
            return {"_error": err}
        return r

    # ── subtab 1: Visão Geral ───────────────────────────────────────────────

    # KPI label → tooltip (labels come from build_overview_kpis).
    _KPI_TOOLTIPS = {
        "P/L": "lpa", "P/VPA": "vpa", "EV/EBITDA": "ev_ebitda",
        "Dividend Yield": "dpa", "ROE": "roe",
    }

    def overview(self, ticker: str) -> dict[str, Any]:
        """KPI cards + heatmap + radar + two-column blocks."""
        tk = ticker.upper()
        try:
            from skills._base import engine_cache_scope
            from skills.cvm._shared_report.tooltips import get_tooltip as _gt
            from skills.cvm.valuation.report.overview import (
                build_overview_kpis,
                build_overview_sections,
                build_valuation_radar,
                build_valuation_heatmap,
            )
            with engine_cache_scope():
                r = self._ratios(tk)
                if "_error" in r:
                    return {"ticker": tk, "_error": r["_error"]}
                kpis = build_overview_kpis(r)
                blocks = build_overview_sections(r) or []
                radar = build_valuation_radar(r)
                heatmap = build_valuation_heatmap(r)
        except Exception as e:
            return {"ticker": tk, "_error": str(e)}

        # [WebUI v1.4 fix1] Tooltips on KPI cards (hover → formula).
        for k in kpis:
            if k.get("tooltip"):
                continue
            tip_key = self._KPI_TOOLTIPS.get(k.get("label", ""))
            if tip_key:
                k["tooltip"] = _gt(tip_key)
            elif k.get("label") == "Market Cap":
                k["tooltip"] = "Market Cap = Preço × Total de Ações. Valor de mercado da empresa."

        sections = [s for s in (heatmap, radar) if s] + blocks
        if not sections:
            return {"ticker": tk, "_error": "sem dados de valuation"}
        return {"ticker": tk, "status": "ok", "kpis": kpis, "sections": sections}

    # ── subtab 2: Múltiplos ─────────────────────────────────────────────────

    # [WebUI v1.4 fix2] Section title prefix → subtab group (mirrors the
    # static dashboard's multiples split). Unmatched sections land in a
    # trailing "Outros" group so future builder sections still render.
    # [WebUI v1.4 fix3] Routs the dashboard's history charts + per-share
    # sections: "P/L, LPA, P/VP, VPA", "Per-share Values (R$)" and
    # "Valores por Ação — Comparativo" → Preço; "Preço/Balanço" and
    # "Ativo/Preço e Alavancagem" → Menos Comuns.
    _MULTIPLES_GROUPS = ["Preço", "EBIT/EBITDA", "EV", "Menos Comuns"]

    @classmethod
    def _multiples_group_of(cls, title: str) -> str:
        t = (title or "").lower()
        if (t.startswith("múltiplos de preço") or t.startswith("histórico")
                or t.startswith("p/l") or t.startswith("per-share values")
                or t.startswith("valores por ação")):
            return "Preço"
        if t.startswith("múltiplos ebit"):  # covers EBIT and EBITDA
            return "EBIT/EBITDA"
        if t.startswith("múltiplos ev"):
            return "EV"
        if (t.startswith("múltiplos menos comuns") or t.startswith("preço/balanço")
                or t.startswith("ativo/preço")):
            return "Menos Comuns"
        return "Outros"

    def multiples(self, ticker: str) -> dict[str, Any]:
        """Grouped multiple tables + comparativo + 5Y history charts.

        [WebUI v1.4 fix2] Payload is grouped for the client's nested
        subtabs — Preço, EBIT/EBITDA, EV, Menos Comuns — matching the
        static dashboard's organization.
        [WebUI v1.4 fix3] Dashboard parity for the history charts and the
        per-share table: Preço gets P/L-LPA-P/VP-VPA + Múltiplos de Preço
        (5Y daily, dual-axis) plus Per-share Values (R$); EBIT/EBITDA gets
        Múltiplos EBIT + Múltiplos EBITDA; Menos Comuns gets Preço/Balanço
        + Ativo/Preço e Alavancagem. Sections are appended in dashboard
        order (charts first, then tables/comparativos, then per-share),
        so each bucket renders in the dashboard's sequence.
        """
        tk = ticker.upper()
        try:
            from skills._base import engine_cache_scope
            from skills.cvm.valuation.report.multiples import (
                build_multiples_sections,
                build_per_share_sections,
            )
            from skills.cvm.valuation.report import history_charts
            with engine_cache_scope():
                r = self._ratios(tk)
                if "_error" in r:
                    return {"ticker": tk, "_error": r["_error"]}
                # [v1.4 fix3] Dashboard history charts, in dashboard order.
                # Each builder returns a 5Y daily step-line section (or None
                # when the underlying history series is unavailable) — per
                # builder try/except keeps one failing chart from taking
                # down the whole subtab.
                sections: list[dict] = []
                for builder in (
                    history_charts.build_pl_lpa_pvp_vpa_history_chart,
                    history_charts.build_price_multiples_history_chart,
                    history_charts.build_ebit_multiples_history_chart,
                    history_charts.build_ebitda_multiples_history_chart,
                    history_charts.build_price_to_balance_history_chart,
                    history_charts.build_asset_to_price_history_chart,
                ):
                    try:
                        sec = builder(tk)
                    except Exception:
                        sec = None
                    if sec:
                        sections.append(self._webui_chart(sec))
                sections.extend(build_multiples_sections(r) or [])
                sections.extend(build_per_share_sections(r) or [])
                hist = self._multiples_history(tk)
        except Exception as e:
            return {"ticker": tk, "_error": str(e)}

        if hist:
            sections.append(hist)

        buckets: dict[str, list[dict]] = {g: [] for g in self._MULTIPLES_GROUPS}
        for s in sections:
            buckets.setdefault(self._multiples_group_of(s.get("title", "")), []).append(s)

        order = list(self._MULTIPLES_GROUPS)
        if buckets.get("Outros"):
            order.append("Outros")
        groups = [{"name": g, "sections": buckets[g]} for g in order if buckets.get(g)]
        if not groups:
            return {"ticker": tk, "_error": "sem dados de múltiplos"}
        return {"ticker": tk, "status": "ok", "groups": groups}

    @staticmethod
    def _webui_chart(sec: dict, range_selector: bool = True) -> dict:
        """[v1.4 fix3] Normalize a report-builder chart section for the API.

        The Jinja dashboard stashes duplicate full series (price_full_*)
        for its server-rendered range filter; the WebUI filters client-side
        from the main chart_data arrays, so the duplicates are dropped
        (roughly halves the history-chart payload). The
        price_range_selector flag is kept for the Múltiplos history charts
        — app.js renders the Tudo/1A/6M/3M/1M button row from it — and
        stripped for Fundamentals (range_selector=False), whose quarterly
        step charts keep the fix2 2-col grid look (no visual change).
        """
        out = {k: v for k, v in sec.items() if not k.startswith("price_full")}
        if not range_selector:
            out.pop("price_range_selector", None)
        return out

    def _multiples_history(self, tk: str, years: int = 5) -> dict | None:
        """5Y P/L + P/VP + EV/EBITDA chart section, monthly downsampled.

        Daily series come from the calculations history functions
        (lpa_history carries `pe`, vpa_history carries `pvpa`,
        ev_ebitda_history carries `ev_ebitda`). Downsampled to one point
        per month (the LAST trading day of each month) to keep the JSON
        payload small (~60 points per series).
        """
        try:
            from skills.cvm.calculations.metrics.lpa import lpa_history
            from skills.cvm.calculations.metrics.vpa import vpa_history
            from skills.cvm.calculations.metrics.ev_ebitda import ev_ebitda_history
        except ImportError:
            return None

        today = date.today()
        d_from = (today - timedelta(days=365 * years)).isoformat()
        d_to = today.isoformat()

        try:
            pe = {p["date"]: p.get("pe")
                  for p in lpa_history(tk, d_from, d_to) if p.get("date")}
            pvpa = {p["date"]: p.get("pvpa")
                    for p in vpa_history(tk, d_from, d_to) if p.get("date")}
        except Exception:
            return None
        try:
            eve = {p["date"]: p.get("ev_ebitda")
                   for p in ev_ebitda_history(tk, d_from, d_to) if p.get("date")}
        except Exception:
            eve = {}

        if not pe and not pvpa and not eve:
            return None

        # Monthly downsample: last available date per YYYY-MM bucket.
        by_month: dict[str, str] = {}
        for d in sorted(set(pe) | set(pvpa) | set(eve)):
            by_month[d[:7]] = d
        kept = [by_month[m] for m in sorted(by_month)]
        labels = [d[5:7] + "/" + d[2:4] for d in kept]  # MM/YY

        colors = {"P/L": "#f59e0b", "P/VP": "#d946a0", "EV/EBITDA": "#a855f7"}
        datasets: list[dict] = []
        for label, src in (("P/L", pe), ("P/VP", pvpa), ("EV/EBITDA", eve)):
            if not src:
                continue
            datasets.append({
                "label": label,
                "data": [src.get(d) for d in kept],
                "borderColor": colors[label],
                "backgroundColor": colors[label],
                "fill": False, "tension": 0.2, "pointRadius": 0,
                "pointHoverRadius": 4, "borderWidth": 2,
            })

        return {
            "type": "chart",
            "title": "Histórico 5 Anos — P/L, P/VP, EV/EBITDA",
            "description": (
                "Evolução mensal dos múltiplos (5 anos). Responde: 'está "
                "barato vs a própria história?' — compare o valor atual "
                "com a faixa histórica de cada múltiplo."
            ),
            "chart_data": {
                "type": "line",
                "data": {"labels": labels, "datasets": datasets},
            },
        }

    # ── subtab 3: Valor Intrínseco ──────────────────────────────────────────

    def intrinsic(self, ticker: str) -> dict[str, Any]:
        """DCF + TIR summary + sensitivity table + curve chart."""
        tk = ticker.upper()
        today = date.today().isoformat()
        try:
            from skills._base import engine_cache_scope
            from skills.cvm.valuation.report.intrinsic import (
                build_dcf_sensitivity_section,
            )
            with engine_cache_scope():
                r = self._ratios(tk)
                if "_error" in r:
                    return {"ticker": tk, "_error": r["_error"]}
                sections: list[dict] = []
                summary = self._intrinsic_summary(r)
                if summary:
                    sections.append(summary)
                sections.extend(build_dcf_sensitivity_section(tk, today) or [])
        except Exception as e:
            return {"ticker": tk, "_error": str(e)}

        if not sections:
            return {"ticker": tk,
                    "_error": "DCF indisponível (sem FCF/WACC/ações)"}
        return {"ticker": tk, "status": "ok", "sections": sections}

    def _intrinsic_summary(self, r: dict[str, Any]) -> dict | None:
        """DCF + TIR summary table from the registry's intrinsic metrics."""
        from skills.cvm._shared_report.tooltips import get_tooltip as _gt
        from skills.cvm.valuation.report._helpers import _fmt, _safe_get

        # (label, ratio key, fmt spec, tooltip key or literal text)
        rows_spec = [
            ("DCF Valor Intrínseco", "dcf_intrinsic_value", "brl_full", ("k", "dcf_intrinsic_value")),
            ("Preço Atual", "price", "brl_full", ("t", "Preço da ação — último fechamento disponível.")),
            ("Margem de Segurança", "dcf_margin_of_safety", "pct", ("k", "dcf_margin_of_safety")),
            ("WACC", "wacc", "pct", ("k", "wacc")),
            ("TIR (ao preço atual)", "irr", "pct", ("k", "irr")),
            ("Graham Number", "graham_number", "brl_full", ("k", "graham_number")),
            ("Earnings Yield", "earnings_yield", "pct", ("t", "Earnings Yield = LPA / Preço = 1/(P/L). Retorno anual teórico ao preço atual.")),
            ("P/L", "p_l", "num", ("k", "lpa")),
            ("EV/EBITDA", "ev_ebitda", "num", ("k", "ev_ebitda")),
        ]
        rows: list[list] = []
        any_val = False
        for label, key, spec, (tip_kind, tip_src) in rows_spec:
            v = _safe_get(r, key)
            if v is not None:
                any_val = True
            tip = _gt(tip_src) if tip_kind == "k" else tip_src
            rows.append([{"text": label, "tooltip": tip}, _fmt(v, spec)])
        if not any_val:
            return None
        return {
            "title": "Valor Intrínseco — DCF + TIR",
            "description": (
                "DCF: fluxo de caixa descontado a 5 anos + valor terminal "
                "(crescimento = IPCA). TIR: taxa de retorno anualizada ao "
                "preço atual."
            ),
            "type": "table",
            "columns": ["Métrica", "Valor"],
            "rows": rows,
        }

    # ── subtab 4: Fundamentos ───────────────────────────────────────────────

    def fundamentals(self, ticker: str) -> dict[str, Any]:
        """Rentabilidade / Liquidez e Alavancagem / Eficiência e Crescimento.

        [WebUI v1.4 fix2] Groups render as the client's nested subtabs —
        one pill per group, one sub-pill per subsection:
          - Rentabilidade: Retornos | Margens (each grid+chart + 5Y trend)
          - Liquidez e Alavancagem: Liquidez | Endividamento
          - Eficiência e Crescimento: Eficiência | Crescimento (with the
            3M/1A/5A growth evolution charts)
        """
        tk = ticker.upper()
        try:
            from skills._base import engine_cache_scope
            from skills.cvm.valuation.report.profitability import (
                build_profitability_section,
                build_margin_trend_chart,
            )
            from skills.cvm.valuation.report.history_charts import (
                build_roe_trend_chart,
                build_growth_evolution_charts,
            )
            from skills.cvm.valuation.report.liquidity import (
                build_liquidity_leverage_sections,
            )
            from skills.cvm.valuation.report.efficiency import (
                build_efficiency_growth_sections,
            )
            with engine_cache_scope():
                r = self._ratios(tk)
                if "_error" in r:
                    return {"ticker": tk, "_error": r["_error"]}
                prof = build_profitability_section(r) or []
                # [v1.4 fix3] Chart normalization: strip the dashboard's
                # price_full_* duplicates AND the range-selector flag —
                # Fundamentos keeps the fix2 2-col grid look (quarterly
                # step charts; the user signed off on this subtab).
                roe_raw = build_roe_trend_chart(tk)
                roe_trend = self._webui_chart(roe_raw, range_selector=False) if roe_raw else None
                mar_raw = build_margin_trend_chart(tk)
                margin_trend = self._webui_chart(mar_raw, range_selector=False) if mar_raw else None
                liq_lev = build_liquidity_leverage_sections(r) or []
                eff_grow = build_efficiency_growth_sections(r, None) or []
                grow_charts = [self._webui_chart(c, range_selector=False)
                               for c in (build_growth_evolution_charts(tk) or [])]
        except Exception as e:
            return {"ticker": tk, "_error": str(e)}

        # Profitability builder order: [retornos grid, retornos chart,
        # margens grid, margens chart].
        ret_secs = list(prof[:2])
        if roe_trend:
            ret_secs.append(roe_trend)
        mar_secs = list(prof[2:])
        if margin_trend:
            mar_secs.append(margin_trend)

        def _split_at(sections: list[dict], keyword: str) -> tuple[list[dict], list[dict]]:
            head: list[dict] = []
            tail: list[dict] = []
            split = False
            for s in sections:
                if not split and keyword in (s.get("title") or "").lower():
                    split = True
                (tail if split else head).append(s)
            return head, tail

        liq_secs, lev_secs = _split_at(liq_lev, "alavancagem")
        eff_secs, grow_secs = _split_at(eff_grow, "crescimento")
        grow_secs.extend(grow_charts)

        groups: list[dict] = []
        if ret_secs or mar_secs:
            groups.append({"name": "Rentabilidade", "subsections": [
                {"name": "Retornos", "sections": ret_secs},
                {"name": "Margens", "sections": mar_secs},
            ]})
        if liq_secs or lev_secs:
            groups.append({"name": "Liquidez e Alavancagem", "subsections": [
                {"name": "Liquidez", "sections": liq_secs},
                {"name": "Endividamento", "sections": lev_secs},
            ]})
        if eff_secs or grow_secs:
            groups.append({"name": "Eficiência e Crescimento", "subsections": [
                {"name": "Eficiência", "sections": eff_secs},
                {"name": "Crescimento", "sections": grow_secs},
            ]})

        if not groups:
            return {"ticker": tk, "_error": "sem dados de fundamentos"}
        return {"ticker": tk, "status": "ok", "groups": groups}

    # ── subtab 5: Todas as métricas ─────────────────────────────────────────

    # PT-BR display labels for every ratio key (registry + manual).
    _LABELS: dict[str, str] = {
        # manual — mercado
        "price": "Preço Atual", "market_cap": "Market Cap",
        "ev": "Enterprise Value", "total_shares": "Total de Ações",
        "eps": "LPA (EPS)",
        # manual — resultado TTM
        "receita_liquida": "Receita Líquida", "ebit": "EBIT",
        "ebitda": "EBITDA", "lucro_liquido": "Lucro Líquido",
        "fco": "FCO", "fci": "FCI", "fcf": "FCF",
        "annual_dividends": "Dividendos Totais (BRL)",
        # manual — balanço
        "ativo_total": "Ativo Total", "caixa": "Caixa",
        "divida_bruta": "Dívida Bruta",
        "patrimonio_liquido": "Patrimônio Líquido",
        # manual — valuation extras
        "p_l": "P/L", "p_vpa": "P/VPA", "psr": "PSR",
        "dividend_yield": "Dividend Yield",
        "divida_liquida_ebitda": "Dívida Líq. / EBITDA",
        # valuation (registry)
        "dcf_intrinsic_value": "DCF Valor Intrínseco",
        "dcf_margin_of_safety": "Margem de Segurança (DCF)",
        "earnings_yield": "Earnings Yield", "ev_ebit": "EV/EBIT",
        "ev_ebitda": "EV/EBITDA", "ev_fcf": "EV/FCF",
        "ev_sales": "EV/Receita", "graham_number": "Graham Number",
        "irr": "TIR", "magic_number": "Magic Number",
        "p_ebit": "P/EBIT", "p_ebitda": "P/EBITDA", "p_ev": "P/EV",
        "p_fcf": "P/FCF", "p_fco": "P/FCO",
        "price_to_tangible_book": "P/Book Tangível", "wacc": "WACC",
        # profitability
        "dupont": "ROE (DuPont)", "ebitda_margin": "Margem EBITDA",
        "fcf_margin": "Margem FCF", "gross_margin": "Margem Bruta",
        "net_margin": "Margem Líquida", "ocf_margin": "Margem FCO",
        "operating_margin": "Margem Operacional", "roa": "ROA",
        "roe": "ROE", "roi": "ROI", "roic": "ROIC",
        # growth
        "revenue_growth_3m": "Crescimento Receita 3M",
        "revenue_growth_1y": "Crescimento Receita 1A",
        "revenue_growth_5y": "Crescimento Receita 5A",
        "gross_profit_growth_3m": "Cresc. Lucro Bruto 3M",
        "gross_profit_growth_1y": "Cresc. Lucro Bruto 1A",
        "gross_profit_growth_5y": "Cresc. Lucro Bruto 5A",
        "net_income_growth_3m": "Cresc. Lucro Líquido 3M",
        "net_income_growth_1y": "Cresc. Lucro Líquido 1A",
        "net_income_growth_5y": "Cresc. Lucro Líquido 5A",
        "revenue_cagr_3m": "Receita CAGR 3M", "revenue_cagr_1y": "Receita CAGR 1A",
        "revenue_cagr_5y": "Receita CAGR 5A",
        "gross_profit_cagr_3m": "Lucro Bruto CAGR 3M",
        "gross_profit_cagr_1y": "Lucro Bruto CAGR 1A",
        "gross_profit_cagr_5y": "Lucro Bruto CAGR 5A",
        "earnings_cagr_3m": "Lucro Líquido CAGR 3M",
        "earnings_cagr_1y": "Lucro Líquido CAGR 1A",
        "earnings_cagr_5y": "Lucro Líquido CAGR 5A",
        "retention_ratio": "Taxa de Retenção",
        "sustainable_growth": "Crescimento Sustentável",
        # liquidity
        "cash_ratio": "Liquidez Imediata", "current_ratio": "Liquidez Corrente",
        "quick_ratio": "Liquidez Seca", "working_capital": "Capital de Giro",
        # leverage
        "altman_z": "Altman Z-Score", "cash_flow_to_debt": "FCO / Dívida Total",
        "debt_equity": "Dívida Líquida / PL", "dl_ebit": "Dívida Líq. / EBIT",
        "financial_leverage": "Multiplicador de Alavancagem (Ativo/PL)",
        "gross_debt_equity": "Dívida Bruta / PL",
        "interest_coverage": "Cobertura de Juros",
        "net_debt_ebitda": "Dívida Líq. / EBITDA",
        # efficiency
        "asset_turnover": "Giro do Ativo",
        "capex_revenue": "CapEx / Receita",
        "fixed_asset_turnover": "Giro do Ativo Fixo",
        "inventory_turnover": "Giro de Estoques",
        "receivables_turnover": "Giro de Contas a Receber",
        # market
        "beta": "Beta", "coe": "Custo do Capital Próprio (Ke)",
        # per-share
        "apa": "Ativo por Ação", "cgpa": "Capital de Giro por Ação",
        "dbpa": "Dívida Bruta por Ação", "dpa": "Dividendos por Ação",
        "lpa": "Lucro por Ação", "ppa": "Passivo por Ação",
        "rbpa": "Receita Bruta por Ação", "rps": "Receita por Ação",
        "vpa": "Valor Patrimonial por Ação",
        # cash flow
        "fcl": "Fluxo de Caixa Livre", "fct": "Fluxo de Caixa Total",
        # tax
        "effective_tax_rate": "Taxa de Tributação Efetiva",
    }

    # Format spec sets (tools.report_ops.formats.apply_fmt specs).
    _PCT_KEYS = {
        "roe", "roa", "roi", "roic", "dupont", "earnings_yield",
        "dividend_yield", "effective_tax_rate", "capex_revenue",
        "retention_ratio", "sustainable_growth", "wacc", "coe", "irr",
        "dcf_margin_of_safety",
    }
    _PS_KEYS = {  # per-share / per-stock BRL
        "lpa", "vpa", "dpa", "rps", "apa", "cgpa", "dbpa", "ppa", "rbpa",
        "eps", "price", "dcf_intrinsic_value", "graham_number",
    }
    _BRL_KEYS = {
        "market_cap", "ev", "receita_liquida", "ebit", "ebitda",
        "lucro_liquido", "fco", "fci", "fcf", "fcl", "fct",
        "annual_dividends", "ativo_total", "caixa", "divida_bruta",
        "patrimonio_liquido", "working_capital",
    }

    # Registry category → display group (ordered below).
    _REGISTRY_GROUP = {
        "valuation": "Valuation", "profitability": "Rentabilidade",
        "growth": "Crescimento", "liquidity": "Liquidez",
        "leverage": "Alavancagem", "efficiency": "Eficiência",
        "per_share": "Valores por Ação", "cash_flow": "Fluxo de Caixa",
        "market": "Risco de Mercado", "tax": "Impostos",
    }
    # Manual (non-registry) keys → display group.
    _MANUAL_GROUP = {
        "price": "Mercado", "market_cap": "Mercado", "ev": "Mercado",
        "total_shares": "Mercado", "eps": "Mercado",
        "receita_liquida": "Resultado (TTM)", "ebit": "Resultado (TTM)",
        "ebitda": "Resultado (TTM)", "lucro_liquido": "Resultado (TTM)",
        "fco": "Resultado (TTM)", "fci": "Resultado (TTM)",
        "fcf": "Resultado (TTM)", "annual_dividends": "Resultado (TTM)",
        "ativo_total": "Balanço", "caixa": "Balanço",
        "divida_bruta": "Balanço", "patrimonio_liquido": "Balanço",
        "p_l": "Valuation", "p_vpa": "Valuation", "psr": "Valuation",
        "dividend_yield": "Valuation",
        "divida_liquida_ebitda": "Alavancagem",
    }

    # [WebUI v1.4 fix1] Tooltip lookup for manual keys (shared registry
    # covers registry keys via get_tooltip(key, spec)). Aliased keys point
    # at the shared registry entry that holds the matching formula.
    _MANUAL_TOOLTIPS = {
        "price": "Preço da ação — último fechamento disponível (brapi → trades → COTAHIST).",
        "market_cap": "Market Cap = Preço × Total de Ações. Valor de mercado da empresa.",
        "ev": "Enterprise Value = Market Cap + Dívida Líquida. Valor total da empresa.",
        "total_shares": "Total de ações outstanding (FRE/CVM).",
        "eps": "Lucro por Ação (EPS) reportado pela companhia.",
        "receita_liquida": "Receita total após deduções e devoluções (DRE 3.01). TTM.",
        "ebit": "EBIT = Resultado antes de juros e impostos (DRE 3.05). TTM.",
        "ebitda": "EBITDA = EBIT + Depreciação e Amortização. Geração operacional. TTM.",
        "lucro_liquido": "Lucro/Prejuízo Consolidado do Período (DRE 3.11). TTM.",
        "fco": "Fluxo de Caixa Operacional — caixa gerado pelas operações. TTM.",
        "fci": "Fluxo de Caixa de Investimentos — CapEx e aplicações. TTM.",
        "fcf": "Fluxo de Caixa Livre = FCO − CapEx. Caixa disponível aos acionistas. TTM.",
        "annual_dividends": "Dividendos + JCP pagos nos últimos 12 meses (total em BRL).",
        "ativo_total": "Ativo Total — soma de todos os ativos (BPA 1).",
        "caixa": "Caixa e Equivalentes de Caixa (BPA 1.01.01).",
        "divida_bruta": "Empréstimos e Financiamentos, Circ + Não Circ (2.01.04 + 2.02.01).",
        "patrimonio_liquido": "Patrimônio Líquido — capital próprio dos acionistas (BPP 2.03).",
        "p_l": ("alias", "lpa"),
        "p_vpa": ("alias", "vpa"),
        "psr": ("alias", "rps"),
        "dividend_yield": ("alias", "dpa"),
        "divida_liquida_ebitda": ("alias", "net_debt_ebitda"),
    }
    _GROUP_ORDER = [
        "Mercado", "Resultado (TTM)", "Balanço", "Valuation",
        "Rentabilidade", "Crescimento", "Liquidez", "Alavancagem",
        "Eficiência", "Valores por Ação", "Fluxo de Caixa",
        "Risco de Mercado", "Impostos",
    ]
    # Meta/source keys and PT backward-compat aliases — never displayed.
    _SKIP_KEYS = {
        "price_date", "price_source", "market_cap_source", "unit_ticker",
        "ebitda_method", "roic_tax_rate", "p_l_source", "status",
        "margem_bruta", "margem_operacional", "margem_liquida",
        "divida_pl", "giro_ativos", "liquidez_corrente",
    }

    def _spec_for(self, key: str) -> str:
        if key in self._PCT_KEYS:
            return "pct"
        if key.endswith("_margin") or key.endswith("_growth") or key.endswith("_cagr"):
            return "pct"
        if key in self._PS_KEYS:
            return "brl_full"
        if key in self._BRL_KEYS:
            return "brl"
        if key == "total_shares":
            return "int"
        return "num"

    def _tooltip_for(self, key: str, spec: Any = None) -> str:
        """Tooltip for a ratio key: shared registry → manual map → "".

        Registry keys resolve via get_tooltip(key, spec) (curated dict first,
        then the MetricSpec.tooltip set at registration). Manual keys use
        _MANUAL_TOOLTIPS; ("alias", k) tuples redirect to the shared entry
        that holds the matching formula (p_l → lpa's P/L tooltip).
        """
        from skills.cvm._shared_report.tooltips import get_tooltip as _gt
        tip = _gt(key, spec)
        if tip:
            return tip
        manual = self._MANUAL_TOOLTIPS.get(key)
        if isinstance(manual, tuple) and manual and manual[0] == "alias":
            return _gt(manual[1])
        return manual or ""

    def all_metrics(self, ticker: str) -> dict[str, Any]:
        """Every ratio in the ratios dict, grouped, PT-BR labels."""
        tk = ticker.upper()
        try:
            from skills._base import engine_cache_scope
            with engine_cache_scope():
                r = self._ratios(tk)
                if "_error" in r:
                    return {"ticker": tk, "_error": r["_error"]}
                from skills.cvm.calculations._registry import METRICS
                from skills.cvm.valuation.report._helpers import _fmt
                groups: dict[str, list[dict]] = {}
                for key, val in r.items():
                    if key in self._SKIP_KEYS or val is None:
                        continue
                    if not isinstance(val, (int, float)) or isinstance(val, bool):
                        continue
                    meta = METRICS.get(key)
                    if meta is not None:
                        grp = self._REGISTRY_GROUP.get(meta.category, "Outros")
                    else:
                        grp = self._MANUAL_GROUP.get(key)
                        if grp is None:
                            continue
                    groups.setdefault(grp, []).append({
                        "key": key,
                        "label": self._LABELS.get(key, key),
                        "value": _fmt(val, self._spec_for(key)),
                        "tooltip": self._tooltip_for(key, meta),
                    })
        except Exception as e:
            return {"ticker": tk, "_error": str(e)}

        payload = [{"name": g, "metrics": groups[g]}
                   for g in self._GROUP_ORDER if groups.get(g)]
        if not payload:
            return {"ticker": tk, "_error": "sem métricas disponíveis"}
        return {"ticker": tk, "status": "ok", "groups": payload}
