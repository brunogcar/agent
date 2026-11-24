"""webui/services/historical.py — historical (5A) data service.

[WebUI v1.24] The company page's Histórico tab — "is the company cheap
vs ITS OWN history?". Direct imports from skills/cvm (NOT through the
MCP dispatcher), mirroring webui/services/valuation.py.

The reference: the user-uploaded PETR4_historical_dashboard.html — the
static dashboard emitted by skills/cvm/historical's dashboard mode. That
dashboard had 9 main tabs, each with a Percentil / Gráfico / Tendência /
per-metric-5A subtab row (the Valuation tab alone carried 6 subtabs).
The user's v1.24 ask: combine them, charts side by side, and turn
"Análise de Percentis (5A)" into a colored-indicator heatmap that IS
the Visão Geral. This service reshapes the SAME data into 4 subtabs:

  - overview()       → 6 KPI cards + "Heatmap de Valoração — Indicadores
                       Coloridos" (all metrics, direction-aware green/
                       amber/red cells) + the Tendência table (Atual vs
                       médias 1A/3A/5A, ALL metrics, COLLAPSED — the
                       v1.23 matrix-first convention: the colored read
                       on top, the raw ledger behind a click)
  - valuation()      → P/L | P/VPA | EV/EBITDA | Div Yield 5A charts
                       (side by side, each with the 5A mín–máx band +
                       mediana) + the Tendência table for those 4
  - profitability()  → ROE | ROIC | Marg. Bruta | Marg. Líquida |
                       Cresc. Receita | Cresc. Lucro charts + Tendência
  - leverage()       → Dívida/PL | Dív. Líq./EBITDA | Cobertura Juros |
                       COE | Beta charts + Tendência + the Avançado
                       point-in-time table (WACC, DuPont, Altman Z)

Direction-aware coloring — the static dashboard's percentile section
said "cheap" for ANY metric below its 25th percentile, which reads
right for P/L but wrong for Div Yield (high = good) and nonsensical
for ROE. Every metric here carries a direction: 'low' (lower ratio is
favorable — P/L, P/VPA, EV/EBITDA, leverage, beta, COE) or 'high'
(higher is favorable — yields, returns, margins, coverage, turnover,
growth). Valuation metrics keep the Barata/Cara language; the rest read
Abaixo/Na/Acima da faixa with the color encoding favorability.

Performance — the static dashboard mode re-fetched everything per run
(~400s pre-optimization). Here ONE build inside a single
engine_cache_scope collects summary + quartiles + monthly-downsampled
series for all 17 metrics (~2.5s against real synced data — each engine
is queried once, the metric history_fn calls hit the shared cache), and
the result is memoized per ticker (10 min TTL) so the 4 subtabs slice
from the same payload. Series are month-end downsampled (61 points for
5Y, not ~1300 dailies) — the x axis renders "jul/2026" ticks.
"""
from __future__ import annotations

import time
from datetime import datetime
from typing import Any

# TTL for the per-ticker metric cache (seconds). Long enough that the 4
# subtabs + a refresh cycle share one build; short enough that a sync
# shows up on the next visit.
_HIST_TTL = 600.0

# (metric name, PT-BR label, unit, category, direction)
#   unit      — 'ratio' (raw number) | 'pct' (fraction, ×100 to display)
#   direction — 'low' (lower is favorable) | 'high' (higher is favorable)
# Mirrors skills/cvm/historical/modes/dashboard.py's _METRIC_DEFS +
# the favorability direction the static dashboard's language lacked.
_METRIC_DEFS: list[tuple[str, str, str, str, str]] = [
    ("lpa", "P/L", "ratio", "valuation", "low"),
    ("vpa", "P/VPA", "ratio", "valuation", "low"),
    ("ev_ebitda", "EV/EBITDA", "ratio", "valuation", "low"),
    ("roe", "ROE", "pct", "profitability", "high"),
    ("roic", "ROIC", "pct", "profitability", "high"),
    ("dpa", "Dividend Yield", "pct", "profitability", "high"),
    ("gross_margin", "Marg. Bruta", "pct", "profitability", "high"),
    ("net_margin", "Marg. Líquida", "pct", "profitability", "high"),
    ("debt_equity", "Dívida/PL", "ratio", "leverage", "low"),
    ("net_debt_ebitda", "Dív. Líq./EBITDA", "ratio", "leverage", "low"),
    ("interest_coverage", "Cobertura Juros", "ratio", "leverage", "high"),
    ("asset_turnover", "Giro Ativo", "ratio", "efficiency", "high"),
    ("inventory_turnover", "Giro Estoque", "ratio", "efficiency", "high"),
    ("revenue_growth_3m", "Cresc. Receita", "pct", "growth", "high"),
    ("net_income_growth_3m", "Cresc. Lucro", "pct", "growth", "high"),
    ("coe", "COE (CAPM)", "pct", "market", "low"),
    ("beta", "Beta (5A)", "ratio", "market", "low"),
]
_METRICS_BY_NAME = {m[0]: m for m in _METRIC_DEFS}

# Category → display label (the heatmap/trend groupings read in order).
_CATEGORY_LABELS = {
    "valuation": "Valuation",
    "profitability": "Rentabilidade",
    "leverage": "Alavancagem",
    "efficiency": "Eficiência",
    "growth": "Crescimento",
    "market": "Risco de Mercado",
}

# Overview KPI cards — the 6 headline multiples/returns (label, metric).
_KPI_METRICS = [
    ("lpa", "P/L"), ("vpa", "P/VPA"), ("ev_ebitda", "EV/EBITDA"),
    ("dpa", "Dividend Yield"), ("roe", "ROE"), ("roic", "ROIC"),
]

# Chart rosters per subtab (metric names, in display order). DY pairs
# with the valuation charts — it IS a price ratio; ROE/margens/cresc.
# carry the profitability family; the leverage subtab absorbs the
# static's "Risco de Mercado" (COE + beta).
_VALUATION_CHARTS = ["lpa", "vpa", "ev_ebitda", "dpa"]
_PROFIT_CHARTS = ["roe", "roic", "gross_margin", "net_margin",
                  "revenue_growth_3m", "net_income_growth_3m"]
_LEVERAGE_CHARTS = ["debt_equity", "net_debt_ebitda",
                    "interest_coverage", "coe", "beta"]

# Heatmap cell colors (bg, fg) — same rgba palette the valuation
# heatmap (skills/cvm/valuation/report/overview.py) established.
_GOOD = ("rgba(34,197,94,0.18)", "#16a34a")   # favorable position
_BAD = ("rgba(220,38,38,0.18)", "#dc2626")    # unfavorable
_NEUTRAL = ("rgba(245,158,11,0.16)", "#d97706")  # faixa média


class HistoricalService:
    """The Histórico tab's 4 subtab payloads (one lazy endpoint each)."""

    def __init__(self) -> None:
        # ticker → (monotonic_time, {metric → payload}) — ONE build feeds
        # every subtab (the PriceService OHLCV-cache pattern).
        self._cache: dict[str, tuple[float, dict[str, Any]]] = {}
        # ticker → (monotonic_time, advanced rows) — WACC/DuPont/Altman
        # (computed once per TTL window, only the leverage subtab asks).
        self._adv_cache: dict[str, tuple[float, list[list[Any]]]] = {}

    # ── the shared build ────────────────────────────────────────────────

    def _build(self, ticker: str) -> dict[str, Any]:
        """All metrics' summary + quartiles + monthly series, cached."""
        hit = self._cache.get(ticker)
        if hit and (time.monotonic() - hit[0]) < _HIST_TTL:
            return hit[1]

        from skills._base import engine_cache_scope
        from skills.cvm.historical.helpers import _months_ago
        from skills.cvm.historical.modes.summary import summary
        from skills.cvm.historical.report import compute_quartiles
        from skills.cvm.calculations._registry import resolve_metric

        data: dict[str, Any] = {}
        date_to = datetime.now().strftime("%Y-%m-%d")
        with engine_cache_scope():
            for name, _label, _unit, _cat, _dirn in _METRIC_DEFS:
                entry: dict[str, Any] = {"summary": None,
                                         "quartiles": None,
                                         "series": None}
                try:
                    s = summary(company=ticker, metric=name)
                except Exception:
                    s = {"status": "error", "error": "summary falhou"}
                entry["summary"] = s
                if isinstance(s, dict) and s.get("status") == "ok":
                    try:
                        spec = resolve_metric(name)
                        series = spec.history_fn(
                            ticker, _months_ago(60), date_to) or []
                        entry["series"] = series
                        entry["quartiles"] = compute_quartiles(
                            series, spec.ratio_key,
                            allow_negative=getattr(spec, "allow_negative",
                                                   False))
                    except Exception:
                        pass
                data[name] = entry
        self._cache[ticker] = (time.monotonic(), data)
        return data

    # ── formatting / coloring helpers ───────────────────────────────────

    @staticmethod
    def _fmt(v: Any, spec: str) -> str:
        """apply_fmt wrapper that never raises ("—" on None/garbage)."""
        if v is None:
            return "—"
        try:
            from tools.report_ops.formats import apply_fmt
            return apply_fmt(v, spec)
        except Exception:
            return str(v)

    @staticmethod
    def _pp(v: float | None) -> str:
        """Signed percent, pt-BR comma, ASCII sign — the _pp convention
        (poupança v1.23) so the client's valNumHtml colors it."""
        if v is None:
            return "—"
        s = f"{v * 100:+.2f}".replace(".", ",")
        return s + "%"

    @classmethod
    def _verdict(cls, direction: str, percentile: float | None,
                 is_valuation: bool) -> tuple[str, tuple[str, str]]:
        """Percentile + direction → (label, (bg, fg)) for the heatmap.

        Valuation metrics keep the dashboard's Barata/Cara language;
        every other family reads Abaixo/Na/Acima da faixa. The COLOR
        always encodes favorability (green = the current position is
        the good side of the 5A distribution).
        """
        if percentile is None:
            return "—", ("", "")
        if direction == "low":
            # Lower ratio is favorable → LOW percentile is good.
            if percentile <= 25:
                label = ("Barata vs histórico" if is_valuation
                         else "Abaixo da faixa")
                return label, _GOOD
            if percentile >= 75:
                label = ("Cara vs histórico" if is_valuation
                         else "Acima da faixa")
                return label, _BAD
        else:
            # Higher is favorable → HIGH percentile is good.
            if percentile >= 75:
                return ("Acima da faixa", _GOOD)
            if percentile <= 25:
                return ("Abaixo da faixa", _BAD)
        return "Na faixa", _NEUTRAL

    @staticmethod
    def _month_end(series: list[dict], ratio_key: str) -> list[tuple[str, float]]:
        """Downsample a daily series to month-end points (YYYY-MM key →
        the LAST valid observation of that month). ~61 points for 5Y."""
        last: dict[str, tuple[str, float]] = {}
        for s in series or []:
            v = s.get(ratio_key)
            d = s.get("date", "")
            if v is None or not d:
                continue
            last[d[:7]] = (d, v)
        return [last[m] for m in sorted(last)]

    def _current_of(self, name: str, entry: dict) -> tuple[Any, Any]:
        """(current ratio value, spec) — (None, None) when unavailable."""
        s = entry.get("summary") or {}
        if s.get("status") != "ok":
            return None, None
        try:
            from skills.cvm.calculations._registry import resolve_metric
            spec = resolve_metric(name)
        except Exception:
            return None, None
        cur = (s.get("current") or {}).get(spec.ratio_key)
        return cur, spec

    # ── shared section builders ─────────────────────────────────────────

    def _heatmap_section(self, data: dict[str, Any]) -> dict[str, Any]:
        """'Heatmap de Valoração — Indicadores Coloridos'.

        One row per metric: Atual (colored by verdict), the 5A
        quartiles, the Percentil (colored) and the Leitura (colored).
        Percent-scaled for 'pct' metrics; the metric label carries the
        shared formula tooltip on the Atual cell.
        """
        from skills.cvm._shared_report.tooltips import get_tooltip as _gt

        columns = ["Métrica", "Atual", "Mín 5A", "25º", "Mediana 5A",
                   "75º", "Máx 5A", "Percentil", "Leitura"]
        rows: list[list[Any]] = []
        for name, label, unit, cat, direction in _METRIC_DEFS:
            entry = data.get(name) or {}
            cur, _spec = self._current_of(name, entry)
            q = entry.get("quartiles") or {}
            s = entry.get("summary") or {}
            pct = s.get("percentile") if isinstance(s, dict) else None
            spec_fmt = "pct" if unit == "pct" else "num"

            is_val = cat == "valuation"
            verdict, (bg, fg) = self._verdict(direction, pct, is_val)

            # NOTE: no pre-scaling — apply_fmt's "pct" spec multiplies
            # by 100 itself (0.2294 → "22,94%"). Pre-scaling would give
            # 2294,00% (the double-multiplication bug the historical
            # report.py's ratio-grid once had).
            def _num(v: Any) -> str:
                return "—" if v is None else self._fmt(v, spec_fmt)

            pct_txt = ("—" if pct is None
                       else f"{pct:.1f}".replace(".", ",") + "º")
            rows.append([
                # Metric label — the shared formula tooltip (the table
                # branch's {text, tooltip} col-0 shape, honored by the
                # heatmap renderer since v1.24).
                {"text": label, "tooltip": _gt(name)},
                {"text": _num(cur), "bg": bg, "color": fg},
                _num(q.get("min")), _num(q.get("p25")),
                _num(q.get("median")), _num(q.get("p75")),
                _num(q.get("max")),
                {"text": pct_txt, "bg": bg, "color": fg,
                 "tooltip": "Posição do valor atual na distribuição "
                            "dos últimos 5 anos (0º = mín, 100º = máx)."},
                {"text": verdict, "bg": bg, "color": fg},
            ])
        return {
            "type": "heatmap",
            "title": "Heatmap de Valoração — Indicadores Coloridos",
            "description": ("Posição de cada indicador na própria "
                            "história (5 anos). Verde = lado favorável "
                            "da faixa histórica · vermelho = lado "
                            "desfavorável · âmbar = faixa média. "
                            "Percentis de P/L, P/VPA e EV/EBITDA leem "
                            "direto (baixo = barata); yield, retornos, "
                            "margens e cobertura invertem (alto = "
                            "favorável)."),
            "columns": columns,
            "rows": rows,
        }

    def _trend_section(self, data: dict[str, Any],
                       metric_names: list[str] | None = None,
                       collapsed: bool = False) -> dict[str, Any]:
        """'Tendência — Atual vs Médias (1A/3A/5A)'.

        The static dashboard's Tendência + Ratio Grid tables combined
        (both showed Atual vs 1A/3A/5A — the grid without Δ, the trend
        with). Δ = (atual − média) / média, signed pt-BR percent.
        """
        from skills.cvm._shared_report.tooltips import get_tooltip as _gt

        defs = _METRIC_DEFS if metric_names is None else [
            _METRICS_BY_NAME[n] for n in metric_names
            if n in _METRICS_BY_NAME]
        columns = ["Métrica", "Atual", "Média 1A", "Δ 1A", "Média 3A",
                   "Δ 3A", "Média 5A", "Δ 5A"]
        rows: list[list[Any]] = []

        def _chg(cur: Any, avg: Any) -> str:
            if cur is None or avg is None or avg == 0:
                return "—"
            return self._pp((cur - avg) / avg)

        for name, label, unit, _cat, _dirn in defs:
            entry = data.get(name) or {}
            cur, _spec = self._current_of(name, entry)
            s = entry.get("summary") or {}
            avgs = (s.get("averages") or {}) if isinstance(s, dict) else {}
            spec_fmt = "pct" if unit == "pct" else "num"
            rows.append([
                {"text": label, "tooltip": _gt(name)},
                self._fmt(cur, spec_fmt),
                self._fmt(avgs.get("1y"), spec_fmt),
                _chg(cur, avgs.get("1y")),
                self._fmt(avgs.get("3y"), spec_fmt),
                _chg(cur, avgs.get("3y")),
                self._fmt(avgs.get("5y"), spec_fmt),
                _chg(cur, avgs.get("5y")),
            ])
        out: dict[str, Any] = {
            "title": "Tendência — Atual vs Médias (1A/3A/5A)",
            "description": "Δ = (atual − média) / média, na janela de 5 anos.",
            "type": "table",
            "columns": columns,
            "rows": rows,
            "note": self._freshness_note(),
        }
        if collapsed:
            out["collapsed"] = True  # the v1.23 auto-collapsed convention
        return out

    @staticmethod
    def _freshness_note() -> str:
        """'DFP: … · ITR: … · COTAHIST: …' (best-effort, '' on failure)."""
        try:
            from skills._freshness import (get_freshness,
                                           get_last_synced_period)
            fresh = get_freshness()
            last = get_last_synced_period()
            return ("Fontes — DFP: {0} (até {1}) · ITR: {2} (até {3}) · "
                    "COTAHIST: {4}").format(
                (fresh.get("dfp") or "")[:10] or "—",
                last.get("dfp") or "—",
                (fresh.get("itr") or "")[:10] or "—",
                last.get("itr") or "—",
                (fresh.get("cotahist") or "")[:10] or "—")
        except Exception:
            return ""

    def _band_chart(self, name: str, entry: dict) -> dict[str, Any] | None:
        """One metric's 5A line chart: monthly series + the 5A mín–máx
        band + the mediana line. None when there is no series.

        Datasets: [faixa_mín (fill '+1' → the máx line, hidden from the
        legend), faixa_máx (hidden), mediana (dashed amber), the metric
        (teal)]. `hideLegend` is honored by renderValChart (v1.24) — the
        two band datasets collapse into ONE legend entry.
        """
        label = _METRICS_BY_NAME[name][1]
        unit = _METRICS_BY_NAME[name][2]
        _spec = None
        try:
            from skills.cvm.calculations._registry import resolve_metric
            _spec = resolve_metric(name)
        except Exception:
            return None
        if _spec is None:
            return None
        monthly = self._month_end(entry.get("series") or [],
                                  _spec.ratio_key)
        if len(monthly) < 2:
            return None
        sc = 100.0 if unit == "pct" else 1.0
        labels = [d[:7] for d, _v in monthly]  # YYYY-MM → fmtMonth axis
        vals = [round(v * sc, 4) for _d, v in monthly]

        datasets: list[dict[str, Any]] = []
        q = entry.get("quartiles") or {}
        if q.get("min") is not None and q.get("max") is not None:
            qmin = round(q["min"] * sc, 4)
            qmax = round(q["max"] * sc, 4)
            datasets.append({
                "label": "Faixa 5A (mín–máx)", "data": [qmin] * len(labels),
                "backgroundColor": "rgba(13,148,136,0.10)",
                "borderColor": "rgba(13,148,136,0.18)", "borderWidth": 0,
                "pointRadius": 0, "fill": "+1", "hideLegend": False,
            })
            datasets.append({
                "label": "Faixa máx", "data": [qmax] * len(labels),
                "borderColor": "rgba(13,148,136,0.18)", "borderWidth": 0,
                "pointRadius": 0, "fill": False, "hideLegend": True,
            })
            if q.get("median") is not None:
                datasets.append({
                    "label": "Mediana 5A",
                    "data": [round(q["median"] * sc, 4)] * len(labels),
                    "borderColor": "#f59e0b", "borderDash": [6, 4],
                    "borderWidth": 1.5, "pointRadius": 0, "fill": False,
                })
        datasets.append({
            "label": label, "data": vals, "borderColor": "#0d9488",
            "borderWidth": 2, "pointRadius": 0, "tension": 0.3,
            "fill": False,
        })
        chart_data: dict[str, Any] = {
            "type": "line",
            "data": {"labels": labels, "datasets": datasets},
        }
        if unit == "pct":
            # The series ships ×100 — tooltips get the % suffix (the
            # v1.14 tooltipUnit convention).
            chart_data["options"] = {"tooltipUnit": "%"}
        return {
            "type": "chart", "title": f"{label} — 5A",
            "description": "Mensal. Faixa sombreada = mín–máx dos últimos "
                           "5 anos; linha tracejada = mediana.",
            "chart_data": chart_data,
        }

    def _charts(self, data: dict[str, Any],
                names: list[str]) -> list[dict[str, Any]]:
        """Chart sections for the given metrics (missing series drop
        out gracefully — an empty roster renders 'Sem dados')."""
        out: list[dict[str, Any]] = []
        for n in names:
            sec = self._band_chart(n, data.get(n) or {})
            if sec:
                out.append(sec)
        return out

    # ── subtab 1: Visão Geral ───────────────────────────────────────────

    def overview(self, ticker: str) -> dict[str, Any]:
        """KPI cards + the colored heatmap + the collapsed trend table."""
        tk = ticker.upper()
        try:
            data = self._build(tk)
        except Exception as e:
            return {"ticker": tk, "_error": str(e)}

        from skills.cvm._shared_report.tooltips import get_tooltip as _gt

        kpis: list[dict[str, Any]] = []
        for name, label in _KPI_METRICS:
            entry = data.get(name) or {}
            cur, _spec = self._current_of(name, entry)
            unit = _METRICS_BY_NAME[name][2]
            kpis.append({
                "label": label,
                "value": self._fmt(cur, "pct" if unit == "pct" else "num"),
                "tooltip": _gt(name),
            })

        sections = [self._heatmap_section(data),
                    self._trend_section(data, collapsed=True)]
        return {"ticker": tk, "status": "ok", "kpis": kpis,
                "sections": sections}

    # ── subtab 2: Valuation 5A ──────────────────────────────────────────

    def valuation(self, ticker: str) -> dict[str, Any]:
        """P/L | P/VPA | EV/EBITDA | Div Yield 5A + the trend subset."""
        tk = ticker.upper()
        try:
            data = self._build(tk)
        except Exception as e:
            return {"ticker": tk, "_error": str(e)}
        sections = self._charts(data, _VALUATION_CHARTS)
        if not sections:
            return {"ticker": tk, "_error":
                    "sem séries históricas de valuation "
                    f"para {tk} (sincronize COTAHIST + DFP/ITR/FRE)"}
        sections.append(self._trend_section(data, _VALUATION_CHARTS))
        return {"ticker": tk, "status": "ok", "sections": sections}

    # ── subtab 3: Rentabilidade e Crescimento ───────────────────────────

    def profitability(self, ticker: str) -> dict[str, Any]:
        """ROE | ROIC | margens | crescimento 5A + the trend subset."""
        tk = ticker.upper()
        try:
            data = self._build(tk)
        except Exception as e:
            return {"ticker": tk, "_error": str(e)}
        sections = self._charts(data, _PROFIT_CHARTS)
        if not sections:
            return {"ticker": tk, "_error":
                    "sem séries históricas de rentabilidade para "
                    f"{tk} (sincronize DFP/ITR/FRE)"}
        sections.append(self._trend_section(data, _PROFIT_CHARTS))
        return {"ticker": tk, "status": "ok", "sections": sections}

    # ── subtab 4: Alavancagem e Risco ───────────────────────────────────

    def leverage(self, ticker: str) -> dict[str, Any]:
        """Alavancagem + risco 5A charts + trend + Avançado table."""
        tk = ticker.upper()
        try:
            data = self._build(tk)
        except Exception as e:
            return {"ticker": tk, "_error": str(e)}
        sections = self._charts(data, _LEVERAGE_CHARTS)
        trend = self._trend_section(data, _LEVERAGE_CHARTS)
        if not sections:
            # No series at all — the trend table + advanced still render.
            sections = [trend]
        else:
            sections.append(trend)
        adv = self._advanced_section(tk)
        if adv:
            sections.append(adv)
        if len(sections) == 1 and not (sections[0].get("rows")):
            return {"ticker": tk, "_error":
                    "sem dados de alavancagem/risco para "
                    f"{tk} (sincronize DFP/ITR + COTAHIST)"}
        return {"ticker": tk, "status": "ok", "sections": sections}

    def _advanced_section(self, ticker: str) -> dict[str, Any] | None:
        """WACC / DuPont ROE / Altman Z — point-in-time (today), the
        static dashboard's 'Advanced Valuation' tab. Too expensive to
        run per-date (that's why they have no 5A series), so a single
        reading each, cached per TTL window."""
        hit = self._adv_cache.get(ticker)
        if hit and (time.monotonic() - hit[0]) < _HIST_TTL:
            rows = hit[1]
        else:
            rows: list[list[Any]] = []
            today = datetime.now().strftime("%Y-%m-%d")
            try:
                from skills.cvm.calculations.metrics.wacc import wacc_at
                from skills.cvm.calculations.metrics.dupont import dupont_at
                from skills.cvm.calculations.metrics.altman_z import (
                    altman_z_at)
                try:
                    v = wacc_at(ticker, today)
                    if v is not None:
                        rows.append(["WACC", self._fmt(v, "pct"),
                                     "Custo médio ponderado de capital "
                                     "(CAPM + estrutura de capital)"])
                except Exception:
                    pass
                try:
                    v = dupont_at(ticker, today)
                    if v is not None:
                        rows.append(["DuPont ROE", self._fmt(v, "pct"),
                                     "ROE decomposto (margem × giro × "
                                     "multiplicador)"])
                except Exception:
                    pass
                try:
                    v = altman_z_at(ticker, today)
                    if v is not None:
                        zone = ("Seguro" if v > 2.99
                                else "Cinza" if v > 1.81 else "Risco")
                        rows.append(["Altman Z-Score", f"{v:.2f} ({zone})",
                                     "Risco de falência: >2,99 seguro · "
                                     "1,81–2,99 cinza · <1,81 risco"])
                except Exception:
                    pass
            except Exception:
                rows = []
            self._adv_cache[ticker] = (time.monotonic(), rows)
        if not rows:
            return None
        return {
            "title": "Avançado (hoje)",
            "description": "Leituras pontuais — sem série histórica "
                           "(o cálculo por data é custoso demais para "
                           "uma série de 5 anos).",
            "type": "table",
            "columns": ["Métrica", "Valor", "Leitura"],
            "rows": rows,
        }
