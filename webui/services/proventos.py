"""webui/services/proventos.py — Proventos tab data service.

[WebUI v1.6] New "Proventos" company tab — the complete corporate-actions
view (dividendos, JCP, rendimentos, restituições, bonificações,
desdobramentos, grupamentos, subscrições). Improves on the static skill
dashboard (skills/cvm/dividends) which was the design reference:

  - HISTÓRICO COMPLETO: the skill dashboard sliced events[:5] (and its
    query layer capped at LIMIT 50). This service fetches EVERY
    cash_dividends row for the ticker — no slice, no cap.
  - ISIN DEDUPE: the B3 provents API returns one row PER SHARE CLASS
    (PETR3 ON + PETR4 PN → every event stored twice under the same
    ticker). Events are grouped by (label, dates, related_to) and merged;
    when the two classes carry DIFFERENT rates, the row matching the
    ticker's class (ISIN ...PR = preferencial, ...OR = ordinária) wins.
  - YIELD ENRICHMENT: each event gains yield-at-ex-date (rate ÷ last
    close strictly before the ex-date) when cotahist.db is available;
    gracefully omitted otherwise.
  - PT-BR type normalization: DIVIDENDO → Dividendo, JRS CAP PROPRIO →
    JCP, RENDIMENTO → Rendimento, RESTITUIÇÃO → Restituição (unknown
    labels pass through title-cased).
  - Event date = COALESCE(last_date_prior, payment_date, approved_on) —
    the EX-date is the investor-relevant date (own the share before it);
    the dpa engine prefers payment_date because old rows lack it, but
    for the per-event view the ex-date is the right anchor.

Endpoints (one lazy JSON per subtab, mirroring ValuationService):
  - overview()   → 6 KPI cards + Resumo two_column + 3 charts
                   (Proventos por Ano stacked, Sazonalidade mensal,
                   Yield TTM histórico when price data exists)
  - historico()  → full event list + corporate actions + subscriptions
                   (custom client renderer: type pills, year filter,
                   sortable columns, upcoming-payments card)
  - anual()      → per-ex-year aggregation table (Eventos, Dividendos,
                   JCP, Rendimento, Total, Δ% YoY, Yield no ano) +
                   stacked chart + DVA-declared table (DFP 7.08.04.*)

Sections are emitted in the SAME generic shape the valuation tab uses
(table / two_column / chart with chart_data) so the client reuses
valKpisHtml + valSectionsHtml + mountValCharts unchanged.
"""
from __future__ import annotations

import sys
import time
import traceback
from bisect import bisect_left
from datetime import date, timedelta
from typing import Any

# TTL for the per-ticker events cache — one dividends.db scan + (optional)
# cotahist range scan serves all three subtabs (mirrors PriceService).
_EVENTS_TTL = 60.0


def _log_err(where: str, e: Exception) -> None:
    print(f"[webui] {where} failed: {e}\n{traceback.format_exc()}", file=sys.stderr)


# ── Type normalization ───────────────────────────────────────────────────────

_TYPES: dict[str, tuple[str, str]] = {
    "DIVIDENDO":       ("Dividendo", "div"),
    "JRS CAP PROPRIO": ("JCP", "jcp"),
    "RENDIMENTO":      ("Rendimento", "rend"),
    "RESTITUICAO":     ("Restituição", "rest"),
    "RESTITUIÇÃO":     ("Restituição", "rest"),
}

# PT-BR tooltips for the event types (client shows them on the badge).
_TYPE_TOOLTIPS: dict[str, str] = {
    "Dividendo":   "Dividendo = distribuição de lucros aos acionistas.",
    "JCP":         "JCP = Juros sobre Capital Próprio (dedutível fiscalmente; valor bruto).",
    "Rendimento":  "Rendimento = distribuição de resultado (comum em fundos).",
    "Restituição": "Restituição = devolução de capital aos acionistas.",
}

# Chart palette — matches the repo convention (teal/orange/purple family).
_C_DIVIDENDO = "#0d9488"
_C_JCP = "#f59e0b"
_C_RENDIMENTO = "#a855f7"
_C_OUTROS = "#64748b"
_C_YIELD = "#16a34a"


def _fmt(value: Any, spec: str) -> str:
    """apply_fmt wrapper with dash fallback (mirrors dividends report.py)."""
    if value is None:
        return "—"
    try:
        from tools.report_ops.formats import apply_fmt
        return apply_fmt(value, spec)
    except Exception:
        return str(value)


def _fmt_rate(value: float | None) -> str:
    """Per-share BRL with 4 decimals (rates like 0,0204 need the precision
    that brl_full's 2 decimals destroy)."""
    if value is None:
        return "—"
    try:
        if abs(value) >= 1000:
            s = f"{value:,.2f}"
        else:
            s = f"{value:.4f}"
        return "R$ " + s.replace(",", "X").replace(".", ",").replace("X", ".")
    except Exception:
        return "—"


def _fmt_date(iso: str | None) -> str:
    """ISO YYYY-MM-DD → DD/MM/YYYY (dash when missing/placeholder)."""
    if not iso or len(iso) < 10 or iso >= "9999":
        return "—"
    return f"{iso[8:10]}/{iso[5:7]}/{iso[0:4]}"


def _num_or_none(v: Any) -> float | None:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _days_between(a: str, b: str) -> int:
    """Calendar-day distance of two ISO dates (a huge number when
    either is empty — [v1.22.4] the DDM merge's near-date check must
    NEVER treat a missing date as "near")."""
    try:
        from datetime import date as _d
        if not a or not b:
            return 99999
        return (_d.fromisoformat(a[:10]) - _d.fromisoformat(b[:10])).days
    except ValueError:
        return 99999


def _quarter_end(y: int, q: int) -> date:
    """Last calendar day of quarter q (0-based) of year y."""
    month = q * 3 + 1
    if month > 12:
        month -= 12
        y += 1
    return date(y, month, 1) - timedelta(days=1)


class ProventosService:
    """Proventos data service — dividends.db + (optional) cotahist + DVA."""

    def __init__(self) -> None:
        # ticker → (fetched_at_monotonic, events list)
        self._events_cache: dict[str, tuple[float, list[dict]]] = {}

    # ── shared: price map (cotahist, graceful) ──────────────────────────────

    @staticmethod
    def _price_map(ticker: str, date_from: str, date_to: str):
        """(dates_sorted, closes) from cotahist — ([], []) when unavailable."""
        try:
            from skills.cvm.calculations.engines.price import price_series
            series = price_series(ticker, date_from, date_to)
        except Exception as e:
            _log_err("proventos price_series", e)
            series = []
        return ([p["date"] for p in series], [p["close"] for p in series])

    @staticmethod
    def _last_close_before(dates: list[str], closes: list[float],
                           ref: str) -> float | None:
        """Last close strictly BEFORE `ref` (the cum-price for yield at ex)."""
        i = bisect_left(dates, ref) - 1
        if i < 0:
            return None
        return closes[i]

    # ── shared: all events, deduped + enriched + cached ─────────────────────

    def events_for(self, ticker: str) -> list[dict]:
        """[v1.22.3] PUBLIC read of ``_events`` for the Carteira join
        (proventos per position / yield-on-cost) — same deduped,
        normalized, cached events; an empty list on any failure (the
        Carteira view degrades to "sem proventos", never an error)."""
        try:
            return self._events(ticker)
        except Exception as e:
            _log_err("proventos events_for", e)
            return []

    def _events(self, ticker: str) -> list[dict]:
        """All cash provents for `ticker` — deduped, normalized, enriched.

        Each event: {ex_date, pay_date, approved_on, event_date, year, type,
        type_key, rate, yield_ex, related_to, remarks, classes, future}.
        Sorted by event date ASC. Cached 60s.
        """
        tk = ticker.upper()
        hit = self._events_cache.get(tk)
        if hit and time.monotonic() - hit[0] < _EVENTS_TTL:
            return hit[1]

        events = self._fetch_events(tk)
        self._events_cache[tk] = (time.monotonic(), events)
        return events

    @staticmethod
    def _pick_class_row(rows: list[dict], ticker: str) -> dict:
        """When share classes carry DIFFERENT rates, pick the ticker's class.

        ISIN convention: the share-class marker sits at NSIN positions 7-8
        (string slice [9:11]): 'PR' = preferencial, 'OR' = ordinária. Ticker
        suffix even digit → PN (prefer 'PR'); odd → ON (prefer 'OR'); units
        (11) and anything unmatched → highest rate (the PN minimum-dividend
        asymmetry makes this the safer display).
        """
        digit = ticker[-1] if ticker and ticker[-1].isdigit() else ""
        want = "PR" if digit in "024568" else ("OR" if digit else None)
        if want:
            for r in rows:
                if (r.get("isin_code") or "")[9:11] == want:
                    return r
        return max(rows, key=lambda r: _num_or_none(r.get("rate")) or 0.0)

    def _fetch_events(self, tk: str) -> list[dict]:
        from data_sources.b3.dividends.catalog import connect
        try:
            conn = connect(read_only=True)
        except FileNotFoundError:
            # [v1.22.4] No B3 dividends.db at all — the DDM merge below
            # still fills what the agenda source knows (graceful, not
            # an empty tab).
            conn = None
        rows: list[dict] = []
        if conn is not None:
            try:
                rows = [dict(r) for r in conn.execute(
                    "SELECT label, isin_code, approved_on, last_date_prior, "
                    "       rate, related_to, payment_date, remarks "
                    "FROM cash_dividends WHERE ticker=? "
                    "ORDER BY COALESCE(last_date_prior, payment_date, approved_on) ASC",
                    (tk,),
                ).fetchall()]
            finally:
                conn.close()

        if not rows:
            # Still run the pipeline (the DDM merge + enrichment) — an
            # empty B3 answer is not the end of the events.
            dates: list[str] = []
            closes: list[float] = []
            try:
                dates, closes = self._price_map(tk, "1990-01-01",
                                                date.today().isoformat())
            except Exception as e:
                _log_err("proventos price map", e)
            events = self._merge_ddm(tk, [], dates, closes,
                                     date.today().isoformat())
            events.sort(key=lambda e: e["event_date"] or "")
            return events

        # ── dedupe across share classes ──
        groups: dict[tuple, list[dict]] = {}
        order: list[tuple] = []
        for r in rows:
            key = (r.get("label"), r.get("approved_on"), r.get("last_date_prior"),
                   r.get("payment_date"), r.get("related_to"))
            if key not in groups:
                groups[key] = []
                order.append(key)
            groups[key].append(r)

        merged: list[tuple[dict, int]] = []
        for key in order:
            grp = groups[key]
            rates = {_num_or_none(r.get("rate")) for r in grp}
            rates.discard(None)
            if len(rates) <= 1:
                keep, classes = grp[0], len({r.get("isin_code") for r in grp})
            else:
                keep, classes = self._pick_class_row(grp, tk), 1
            merged.append((keep, classes))

        # ── price context for yield-at-ex (one scan, graceful when missing) ──
        today = date.today().isoformat()
        dates: list[str] = []
        closes: list[float] = []
        try:
            dates, closes = self._price_map(tk, "1990-01-01", today)
        except Exception as e:
            _log_err("proventos price map", e)

        # ── normalize + enrich ──
        events: list[dict] = []
        for keep, classes in merged:
            label_raw = (keep.get("label") or "").strip().upper()
            type_pt, type_key = _TYPES.get(label_raw,
                                           (label_raw.title() or "—", "outros"))
            ex_date = keep.get("last_date_prior") or ""
            pay_date = keep.get("payment_date") or ""
            approved = keep.get("approved_on") or ""
            event_date = ex_date or pay_date or approved
            rate = _num_or_none(keep.get("rate"))
            yield_ex = None
            if rate is not None and dates and ex_date:
                px = self._last_close_before(dates, closes, ex_date)
                if px is not None and px > 0:
                    yield_ex = rate / px
            events.append({
                "ex_date": ex_date,
                "pay_date": pay_date,
                "approved_on": approved,
                "event_date": event_date,
                "year": int(event_date[:4]) if event_date[:4].isdigit() else None,
                "type": type_pt,
                "type_key": type_key,
                "rate": rate,
                "yield_ex": yield_ex,
                "related_to": keep.get("related_to") or "",
                "remarks": keep.get("remarks") or "",
                "classes": classes,
                "future": bool(pay_date and pay_date > today),
                "source": "b3",
            })
        events = self._merge_ddm(tk, events, dates, closes, today)
        events.sort(key=lambda e: e["event_date"] or "")
        return events

    # ── [v1.22.4] second source: DDM agenda ─────────

    _DDM_TYPES = {"Dividendo": ("Dividendo", "div"),
                  "JCP": ("JCP", "jcp")}

    def _merge_ddm(self, tk: str, events: list[dict],
                   dates: list[str], closes: list[float],
                   today_iso: str) -> list[dict]:
        """Merge the DDM agenda rows into the B3 events — no duplicates.

        The two sources disagree on coverage (the B3 provents API misses
        recent/odd events the agenda publishes and vice-versa — the
        user-visible "proventos limitados"). B3 rows WIN on collision
        (they carry approved_on + remarks + the share-class detail);
        a DDM row is a duplicate when the type matches AND the ex-dates
        are within 5 days AND the per-share rates are within 2% (the
        sources follow slightly different date conventions — data com vs
        ex-date — and rounding).
        """
        try:
            from data_sources.ddm.dividends.catalog import connect as ddm_connect
        except Exception:
            return events
        try:
            conn = ddm_connect(read_only=True)
            rows = [dict(r) for r in conn.execute(
                "SELECT tipo, value, record_date, ex_date, payment_date "
                "FROM dividends WHERE ticker = ?", (tk,)).fetchall()]
            conn.close()
        except Exception:
            return events
        if not rows:
            return events

        def _iso(v: Any) -> str:
            s = str(v or "")
            return s[:10] if len(s) >= 10 else ""

        for r in rows:
            type_pt, type_key = self._DDM_TYPES.get(
                (r.get("tipo") or "").strip(),
                ((r.get("tipo") or "").strip().title() or "—", "outros"))
            rate = _num_or_none(r.get("value"))
            ex_date = _iso(r.get("ex_date")) or _iso(r.get("record_date"))
            pay_date = _iso(r.get("payment_date"))
            event_date = ex_date or pay_date
            if not event_date or rate is None:
                continue
            dup = False
            for ev in events:
                if ev.get("type_key") != type_key:
                    continue
                ev_ex = ev.get("ex_date") or ev.get("event_date") or ""
                near_date = (abs(_days_between(ev_ex, ex_date)) <= 5
                             or (pay_date and ev.get("pay_date") == pay_date))
                ev_rate = ev.get("rate")
                close_rate = (ev_rate is not None and
                              abs(ev_rate - rate) <= max(0.0005, abs(ev_rate) * 0.02))
                if near_date and (close_rate or ev_rate is None or rate == 0):
                    dup = True
                    break
            if dup:
                continue
            yield_ex = None
            if dates and ex_date:
                px = self._last_close_before(dates, closes, ex_date)
                if px is not None and px > 0:
                    yield_ex = rate / px
            events.append({
                "ex_date": ex_date,
                "pay_date": pay_date,
                "approved_on": "",
                "event_date": event_date,
                "year": int(event_date[:4]) if event_date[:4].isdigit() else None,
                "type": type_pt,
                "type_key": type_key,
                "rate": rate,
                "yield_ex": yield_ex,
                "related_to": "",
                "remarks": "fonte: Dados de Mercado (agenda)",
                "classes": 1,
                "future": bool(pay_date and pay_date > today_iso),
                "source": "ddm",
            })
        return events

    # ── shared helpers ──────────────────────────────────────────────────────

    @staticmethod
    def _type_totals(events: list[dict], year: int | None = None) -> dict[str, float]:
        """Sum of rates per type_key for a given ex-year (None = all)."""
        totals: dict[str, float] = {}
        for e in events:
            if year is not None and e["year"] != year:
                continue
            if e["rate"] is None:
                continue
            totals[e["type_key"]] = totals.get(e["type_key"], 0.0) + e["rate"]
        return totals

    def _year_end_yield(self, events: list[dict], dates: list[str],
                        closes: list[float], year: int) -> float | None:
        """Total ex'd in `year` ÷ close at Dec-31 (or the year's last close)."""
        total = sum(self._type_totals(events, year).values())
        if not total:
            return None
        ref = f"{year}-12-31"
        i = bisect_left(dates, ref)
        px: float | None = None
        if i < len(dates) and dates[i] == ref:
            px = closes[i]
        elif i > 0 and dates[i - 1][:4] == str(year):
            px = closes[i - 1]
        if px is None or not px or px <= 0:
            return None
        return total / px

    @staticmethod
    def _kpi(label: str, value: Any, spec: str, unit: str = "",
             tooltip: str = "") -> dict:
        out = {"label": label, "value": _fmt(value, spec), "unit": unit}
        if tooltip:
            out["tooltip"] = tooltip
        return out

    def _error(self, tk: str, e: Exception | None, fallback: str) -> dict:
        if e is not None:
            _log_err("proventos", e)
        return {"ticker": tk, "_error": fallback}

    # ══════════════════════════════════════════════════════════════════════
    # Subtab 1: Visão Geral
    # ══════════════════════════════════════════════════════════════════════

    def overview(self, ticker: str) -> dict[str, Any]:
        """6 KPI cards + Resumo two_column + charts (por ano, sazonalidade,
        yield TTM histórico)."""
        tk = ticker.upper()
        try:
            events = self._events(tk)
        except FileNotFoundError:
            return self._error(tk, None,
                "Sem dados de proventos — sincronize a fonte b3_dividends.")
        except Exception as e:
            return self._error(tk, e, "Falha ao consultar proventos.")

        if not events:
            return self._error(tk, None, "Nenhum provento encontrado para este ticker.")

        today = date.today().isoformat()
        today_dt = date.today()

        # ── price context (graceful) ──
        last_price = None
        try:
            from skills.cvm.calculations.engines.price import price_at
            last_price = price_at(tk, today)
        except Exception as e:
            _log_err("proventos price_at", e)

        # TTM paid (ex-date in the last 365 days) + yield
        cutoff = (today_dt - timedelta(days=365)).isoformat()
        ttm_total = sum(e["rate"] for e in events
                        if e["rate"] is not None and e["event_date"] >= cutoff)
        yield_ttm = (ttm_total / last_price) if (last_price and last_price > 0) else None

        # Annual totals per ex-year → média 5A + frequência
        years = sorted({e["year"] for e in events if e["year"]})
        year_totals = {y: sum(self._type_totals(events, y).values()) for y in years}
        complete_years = [y for y in years if y < today_dt.year]
        last5 = complete_years[-5:]
        avg_5y = (sum(year_totals[y] for y in last5) / len(last5)) if last5 else None
        freq = (len(events) / len(years)) if years else None

        # Próximo / último pagamento
        upcoming = sorted((e for e in events if e["future"]),
                          key=lambda e: e["pay_date"])
        next_ev = upcoming[0] if upcoming else None
        past = [e for e in events if e["pay_date"] and e["pay_date"] <= today]
        last_ev = past[-1] if past else None

        next_val = _fmt_rate(next_ev["rate"]) if next_ev else "—"
        kpis = [
            self._kpi("Dividend Yield (TTM)", yield_ttm, "pct", "pct",
                      "Yield TTM = proventos por ação nos últimos 12 meses ÷ preço atual."),
            self._kpi("Pago nos últimos 12M", ttm_total, "brl_full", "BRL",
                      "Soma dos valores por ação com data-ex nos últimos 365 dias."),
            self._kpi("Média Anual (5A)", avg_5y, "brl_full", "BRL",
                      "Média do total anual por ação nos 5 últimos anos completos."),
            self._kpi("Frequência",
                      f"{freq:.1f}".replace(".", ",") + " /ano" if freq else None,
                      "text", "", "Eventos por ano (média de todo o histórico)."),
            self._kpi("Próximo Pagamento", _fmt_date(next_ev["pay_date"]) if next_ev else None,
                      "text", "date",
                      f"Data do próximo pagamento já anunciado (valor: {next_val})."),
            self._kpi("Anos de Histórico", str(len(years)), "text", "",
                      f"De {years[0]} a {years[-1]}." if years else ""),
        ]

        # ── Resumo two_column ──
        def _ev_rows(ev: dict | None) -> list[dict]:
            if not ev:
                return [{"label": "Data de pagamento", "value": "—"}]
            rows = [
                {"label": "Data de pagamento", "value": _fmt_date(ev["pay_date"])},
                {"label": "Data-ex", "value": _fmt_date(ev["ex_date"])},
                {"label": "Tipo", "value": ev["type"]},
                {"label": "Valor por ação", "value": _fmt_rate(ev["rate"])},
                {"label": "Relativo a", "value": ev["related_to"] or "—"},
            ]
            if ev.get("yield_ex") is not None:
                rows.append({"label": "Yield na data-ex", "value": _fmt(ev["yield_ex"], "pct")})
            return rows

        sections: list[dict] = [{
            "type": "two_column",
            "left_title": "Último pagamento realizado",
            "left_rows": _ev_rows(last_ev),
            "right_title": "Próximo pagamento anunciado",
            "right_rows": _ev_rows(next_ev),
        }]

        # ── chart 1: Proventos por Ano (stacked) ──
        # [v1.6 fix1] B3's provents API returns only a recent window of
        # events (~18-30 rows ≈ 2 anos). The sync engine now MERGES (out-of-
        # window events are preserved), so this chart's coverage grows with
        # each re-sync; the multi-year DECLARED history (DVA, CVM) lives in
        # the Anual subtab. The description says so.
        by_type = {k: [] for k in ("div", "jcp", "rend", "outros")}
        for y in years:
            totals = self._type_totals(events, y)
            for k in by_type:
                by_type[k].append(round(totals.get(k, 0.0), 6))
        sections.append({
            "type": "chart",
            "title": "Proventos por Ano (R$/ação)",
            "description": "Total distribuído por ação em cada ano, agrupado "
                           "por data-ex e empilhado por tipo (Dividendo, JCP, "
                           "Rendimento). A API da B3 entrega apenas a janela "
                           "recente de eventos (~2 anos); a partir desta "
                           "versão o histórico acumula a cada re-sincronização, "
                           "e a visão declarada por exercício (mais anos) está "
                           "na aba Anual.",
            "chart_data": {
                "type": "bar",
                "data": {
                    "labels": [str(y) for y in years],
                    "datasets": [
                        {"label": "Dividendo", "data": by_type["div"],
                         "backgroundColor": _C_DIVIDENDO, "borderWidth": 0},
                        {"label": "JCP", "data": by_type["jcp"],
                         "backgroundColor": _C_JCP, "borderWidth": 0},
                        {"label": "Rendimento", "data": by_type["rend"],
                         "backgroundColor": _C_RENDIMENTO, "borderWidth": 0},
                        {"label": "Outros", "data": by_type["outros"],
                         "backgroundColor": _C_OUTROS, "borderWidth": 0},
                    ],
                },
                "options": {"scales": {
                    "x": {"stacked": True},
                    "y": {"stacked": True, "beginAtZero": True},
                }},
            },
        })

        # ── chart 2: Sazonalidade mensal ──
        month_totals = [0.0] * 12
        for e in events:
            if e["event_date"] and len(e["event_date"]) >= 7 and e["rate"] is not None:
                m = e["event_date"][5:7]
                if m.isdigit() and 1 <= int(m) <= 12:
                    month_totals[int(m) - 1] += e["rate"]
        if any(v > 0 for v in month_totals):
            sections.append({
                "type": "chart",
                "title": "Sazonalidade dos Pagamentos (R$/ação)",
                "description": "Total distribuído por ação em cada mês do ano, "
                               "somando todo o histórico — mostra quando a "
                               "empresa concentra seus pagamentos.",
                "chart_data": {
                    "type": "bar",
                    "data": {
                        "labels": ["Jan", "Fev", "Mar", "Abr", "Mai", "Jun",
                                   "Jul", "Ago", "Set", "Out", "Nov", "Dez"],
                        "datasets": [{
                            "label": "R$/ação por mês",
                            "data": [round(v, 6) for v in month_totals],
                            "backgroundColor": _C_JCP, "borderWidth": 0,
                        }],
                    },
                    "options": {"scales": {"y": {"beginAtZero": True}}},
                },
            })

        # ── chart 3: Yield TTM histórico (needs price) ──
        try:
            dates, closes = self._price_map(
                tk, (today_dt - timedelta(days=3650)).isoformat(), today)
        except Exception as e:
            _log_err("proventos yield chart", e)
            dates, closes = [], []
        if dates and events:
            d0 = date.fromisoformat(dates[0])
            y, q = d0.year, (d0.month - 1) // 3
            labels: list[str] = []
            values: list[float] = []
            while True:
                qe = _quarter_end(y, q)
                if qe.isoformat() > today:
                    break
                qe_iso = qe.isoformat()
                i = bisect_left(dates, qe_iso)
                if i < len(dates):
                    px = closes[i]
                    if px and px > 0:
                        cutoff_q = (qe - timedelta(days=365)).isoformat()
                        ttm = sum(e["rate"] for e in events
                                  if e["rate"] is not None
                                  and cutoff_q <= e["event_date"] <= qe_iso)
                        if ttm > 0:
                            # [v1.6 fix1] pt-BR label: MM/AAAA (was YYYY-MM,
                            # which reads backwards in Brazil).
                            labels.append(f"{qe_iso[5:7]}/{qe_iso[:4]}")
                            values.append(round(ttm / px * 100, 4))
                q += 1
                if q > 3:
                    q = 0
                    y += 1
            if len(labels) >= 2:
                sections.append({
                    "type": "chart",
                    "title": "Dividend Yield TTM ao longo do tempo (%)",
                    "description": "Proventos por ação nos 12 meses anteriores "
                                   "÷ preço de fechamento, amostrado ao fim de "
                                   "cada trimestre (MM/AAAA). A série começa "
                                   "onde há preço E eventos sincronizados — a "
                                   "janela da API da B3 limita o início (~2 "
                                   "anos; cresce com as re-sincronizações).",
                    "chart_data": {
                        "type": "line",
                        "data": {
                            "labels": labels,
                            "datasets": [{
                                "label": "Yield TTM (%)",
                                "data": values,
                                "borderColor": _C_YIELD,
                                "backgroundColor": "rgba(22, 163, 74, 0.12)",
                                "fill": True, "tension": 0.25,
                            }],
                        },
                        "options": {"scales": {"y": {"beginAtZero": True}}},
                    },
                })

        # ── [v1.26.1] IPE announcements — the CVM cross-reference ──
        # The events above are the per-share sources (B3 ∪ DDM agenda).
        # IPE carries the OFFICIAL filings (atas, avisos aos acionistas)
        # announcing each provento — no parsed per-share rate, but the
        # ground truth of what was announced and when. Surfacing them
        # here shows what the per-share sources may have missed (the
        # "way less proventos than it actually had" gap) with the
        # document link for manual confirmation.
        ipe_rows = self._ipe_announcements(tk)
        if ipe_rows:
            sections.append(self._ipe_section(ipe_rows))

        return {"ticker": tk, "status": "ok", "kpis": kpis, "sections": sections}

    # ── [v1.26.1] IPE announcements (CVM) ──────────────────────────────────

    def _ipe_announcements(self, tk: str) -> list[dict]:
        """Proventos-related IPE filings for the ticker's CNPJ, newest first.

        Matches the CVM category taxonomy: the dividend family lives in
        the categoria "Dividendos, Juros sobre o Capital Próprio e
        Outros" plus avisos/atas whose tipo mentions dividendos/juros.
        Degrades to [] (missing ipe.db / bridge miss / any error — the
        section simply doesn't render).
        """
        try:
            from data_sources.cvm._db import connect_ipe
            from data_sources.cvm._bridge import _resolve_via_bridge
        except ImportError:
            return []
        try:
            cnpj, _cd = _resolve_via_bridge(tk)
        except Exception:
            cnpj = None
        if not cnpj:
            return []
        try:
            conn = connect_ipe(read_only=True)
        except Exception:
            return []
        try:
            rows = conn.execute(
                "SELECT data_entrega, categoria, tipo, assunto, link_download "
                "FROM eventos WHERE cnpj = ? AND ("
                "  lower(categoria) LIKE '%dividend%'"
                "  OR lower(tipo) LIKE '%dividend%'"
                "  OR lower(categoria) LIKE '%juros%capital%'"
                "  OR lower(tipo) LIKE '%juros%capital%')"
                " ORDER BY data_entrega DESC LIMIT 40",
                (cnpj,),
            ).fetchall()
            return [dict(r) for r in rows]
        except Exception as e:
            _log_err("proventos ipe announcements", e)
            return []
        finally:
            conn.close()

    @staticmethod
    def _ipe_section(rows: list[dict]) -> dict[str, Any]:
        """'Anúncios de Proventos — CVM (IPE)' table section."""
        table_rows: list[list[Any]] = []
        for r in rows:
            entrega = r.get("data_entrega") or "—"
            assunto = (r.get("assunto") or "").strip()
            link = (r.get("link_download") or "").strip()
            table_rows.append([
                {"text": _fmt_date(entrega) if entrega != "—" else "—",
                 "tooltip": assunto or None, "link": link or None},
                r.get("categoria") or "—",
                r.get("tipo") or "—",
                assunto or "—",
            ])
        return {
            "type": "table",
            "title": f"Anúncios de Proventos — CVM ({len(rows)})",
            "description": (
                "Comunicados oficiais entregues à CVM (IPE — Informações "
                "Periódicas e Eventuais) que anunciam proventos: atas e "
                "avisos com dividendos/juros sobre capital próprio. É a "
                "referência cruzada dos eventos acima — se um anúncio "
                "não tem evento correspondente na lista, o valor por ação "
                "está no documento (a data abre o PDF no site da CVM)."
            ),
            "columns": ["Data Entrega", "Categoria", "Tipo", "Assunto"],
            "rows": table_rows,
            "note": "Fonte: CVM IPE — filtrada por categoria/tipo de "
                    "proventos. Não soma nos gráficos (sem valor por ação "
                    "estruturado).",
        }

    def historico(self, ticker: str) -> dict[str, Any]:
        """Full event list + corporate actions + subscriptions."""
        tk = ticker.upper()
        try:
            events = self._events(tk)
        except FileNotFoundError:
            return self._error(tk, None,
                "Sem dados de proventos — sincronize a fonte b3_dividends.")
        except Exception as e:
            return self._error(tk, e, "Falha ao consultar proventos.")

        if not events:
            return self._error(tk, None, "Nenhum provento encontrado para este ticker.")

        has_price = any(e["yield_ex"] is not None for e in events)

        # Corporate actions (bonificações / desdobramentos / grupamentos)
        # — deduped across share classes (the API returns one row per ISIN:
        # PETR3 ON + PETR4 PN → every desdobramento/bonificação twice).
        actions: list[dict] = []
        try:
            from data_sources.b3.dividends.catalog import connect
            conn = connect(read_only=True)
            try:
                rows = conn.execute(
                    "SELECT label, approved_on, last_date_prior, factor, asset_issued "
                    "FROM stock_dividends WHERE ticker=? "
                    "ORDER BY COALESCE(last_date_prior, approved_on) DESC",
                    (tk,),
                ).fetchall()
                seen: set[tuple] = set()
                for r in rows:
                    d = dict(r)
                    key = (d.get("label"), d.get("approved_on"),
                           d.get("last_date_prior"), _num_or_none(d.get("factor")))
                    if key in seen:
                        continue
                    seen.add(key)
                    actions.append({
                        "ex_date": d.get("last_date_prior") or "",
                        "approved_on": d.get("approved_on") or "",
                        "label": (d.get("label") or "").strip(),
                        "factor": _num_or_none(d.get("factor")),
                        "asset_issued": d.get("asset_issued") or "",
                    })
            finally:
                conn.close()
        except Exception as e:
            _log_err("proventos stock_dividends", e)

        # Subscriptions — deduped across share classes (same per-ISIN
        # duplication as stock_dividends).
        subs: list[dict] = []
        try:
            from data_sources.b3.dividends.catalog import connect
            conn = connect(read_only=True)
            try:
                rows = conn.execute(
                    "SELECT label, approved_on, last_date_prior, percentage, "
                    "       price_unit, subscription_date, trading_period "
                    "FROM subscriptions WHERE ticker=? "
                    "ORDER BY COALESCE(last_date_prior, approved_on) DESC",
                    (tk,),
                ).fetchall()
                seen_sub: set[tuple] = set()
                for r in rows:
                    d = dict(r)
                    key = (d.get("approved_on"), d.get("last_date_prior"),
                           _num_or_none(d.get("percentage")),
                           _num_or_none(d.get("price_unit")))
                    if key in seen_sub:
                        continue
                    seen_sub.add(key)
                    sub_date = d.get("subscription_date") or ""
                    subs.append({
                        "ex_date": d.get("last_date_prior") or "",
                        "approved_on": d.get("approved_on") or "",
                        "percentage": _num_or_none(d.get("percentage")),
                        "price_unit": _num_or_none(d.get("price_unit")),
                        # '9999-12-31' is B3's "no date" placeholder.
                        "subscription_date": "" if sub_date >= "9999" else sub_date,
                        "trading_period": d.get("trading_period") or "",
                    })
            finally:
                conn.close()
        except Exception as e:
            _log_err("proventos subscriptions", e)

        # Type counts (filter pills)
        counts: dict[str, int] = {}
        type_labels: dict[str, str] = {}
        for e in events:
            counts[e["type_key"]] = counts.get(e["type_key"], 0) + 1
            type_labels[e["type_key"]] = e["type"]

        years = sorted({e["year"] for e in events if e["year"]}, reverse=True)
        total_paid = sum(e["rate"] for e in events if e["rate"] is not None)

        return {
            "ticker": tk,
            "status": "ok",
            "has_price": has_price,
            "events": events,
            "actions": actions,
            "subscriptions": subs,
            "counts": counts,
            "type_labels": type_labels,
            "type_tooltips": _TYPE_TOOLTIPS,
            "years": years,
            "total_paid": round(total_paid, 6),
            "first_date": events[0]["event_date"] if events else "",
            "last_date": events[-1]["event_date"] if events else "",
        }

    # ══════════════════════════════════════════════════════════════════════
    # Subtab 3: Anual
    # ══════════════════════════════════════════════════════════════════════

    def anual(self, ticker: str) -> dict[str, Any]:
        """Per-ex-year aggregation table + stacked chart + DVA declarado."""
        tk = ticker.upper()
        try:
            events = self._events(tk)
        except FileNotFoundError:
            return self._error(tk, None,
                "Sem dados de proventos — sincronize a fonte b3_dividends.")
        except Exception as e:
            return self._error(tk, e, "Falha ao consultar proventos.")

        if not events:
            return self._error(tk, None, "Nenhum provento encontrado para este ticker.")

        today = date.today().isoformat()
        years = sorted({e["year"] for e in events if e["year"]})

        # Price context for year-end yields (graceful)
        try:
            dates, closes = self._price_map(tk, f"{years[0]}-01-01", today)
        except Exception as e:
            _log_err("proventos.anual price map", e)
            dates, closes = [], []

        # ── table: per-year aggregation (newest first) ──
        columns = ["Ano", "Eventos", "Dividendos", "JCP", "Rendimento",
                   "Total (R$/ação)", "Δ% ano anterior", "Yield no ano"]
        rows: list[list] = []
        prev_total: float | None = None
        for y in reversed(years):
            totals = self._type_totals(events, y)
            total = sum(totals.values())
            n_events = sum(1 for e in events if e["year"] == y)
            delta = ((total - prev_total) / prev_total) if prev_total else None
            yld = self._year_end_yield(events, dates, closes, y) if closes else None
            rows.append([
                str(y),
                n_events,
                _fmt_rate(totals.get("div")),
                _fmt_rate(totals.get("jcp")),
                _fmt_rate(totals.get("rend")),
                _fmt_rate(total),
                _fmt(delta, "pct") if delta is not None else "—",
                _fmt(yld, "pct") if yld is not None else "—",
            ])
            prev_total = total if total else prev_total
        sections: list[dict] = [{
            "type": "table",
            "title": "Proventos Recebidos por Ano (por data-ex)",
            "description": "Agregação anual por data-ex: quantos eventos, "
                           "quanto de cada tipo e o total por ação. "
                           "Δ% compara com o ano anterior; Yield no ano = "
                           "total ÷ fechamento de 31/12 (quando disponível).",
            "columns": columns,
            "rows": rows,
            "formats": {},
            "note": f"{len(years)} anos · {len(events)} eventos no histórico.",
        }]

        # ── chart: stacked per year ──
        by_type = {k: [] for k in ("div", "jcp", "rend", "outros")}
        for y in years:
            totals = self._type_totals(events, y)
            for k in by_type:
                by_type[k].append(round(totals.get(k, 0.0), 6))
        sections.append({
            "type": "chart",
            "title": "Composição Anual por Tipo (R$/ação)",
            "description": "Dividendo, JCP e Rendimento empilhados por ano — "
                           "a proporção entre as cores mostra o mix de "
                           "remuneração (JCP é dedutível de imposto).",
            "chart_data": {
                "type": "bar",
                "data": {
                    "labels": [str(y) for y in years],
                    "datasets": [
                        {"label": "Dividendo", "data": by_type["div"],
                         "backgroundColor": _C_DIVIDENDO, "borderWidth": 0},
                        {"label": "JCP", "data": by_type["jcp"],
                         "backgroundColor": _C_JCP, "borderWidth": 0},
                        {"label": "Rendimento", "data": by_type["rend"],
                         "backgroundColor": _C_RENDIMENTO, "borderWidth": 0},
                        {"label": "Outros", "data": by_type["outros"],
                         "backgroundColor": _C_OUTROS, "borderWidth": 0},
                    ],
                },
                "options": {"scales": {
                    "x": {"stacked": True},
                    "y": {"stacked": True, "beginAtZero": True},
                }},
            },
        })

        # ── chart: year-end yield (needs price) ──
        y_labels: list[str] = []
        y_vals: list[float] = []
        for y in years:
            yld = self._year_end_yield(events, dates, closes, y)
            if yld is not None:
                y_labels.append(str(y))
                y_vals.append(round(yld * 100, 4))
        if len(y_labels) >= 2:
            sections.append({
                "type": "chart",
                "title": "Yield de cada ano (%)",
                "description": "Total distribuído no ano ÷ preço de "
                               "fechamento de 31/12 — o retorno em proventos "
                               "que um investidor que comprou no fim do ano "
                               "obteria no ano seguinte.",
                "chart_data": {
                    "type": "line",
                    "data": {
                        "labels": y_labels,
                        "datasets": [{
                            "label": "Yield anual (%)",
                            "data": y_vals,
                            "borderColor": _C_YIELD,
                            "backgroundColor": "rgba(22, 163, 74, 0.12)",
                            "fill": True, "tension": 0.25,
                        }],
                    },
                    "options": {"scales": {"y": {"beginAtZero": True}}},
                },
            })

        # ── DVA declarado (DFP) — the multi-year history ──
        # [v1.6 fix1] B3 events cover only the API window (~2 anos); the
        # DVA (Demonstração de Valor Adicionado, DFP 7.08.04.*) covers
        # every synced exercise — bumped to 15 periods and now ALSO
        # rendered as a stacked chart (Dividendos + JCP por exercício),
        # so the Anual subtab shows the long history the user asked for.
        try:
            from skills.cvm.dividends.modes.annual import annual as _annual_mode
            dva = _annual_mode(company=tk, periods=15)
        except Exception as e:
            _log_err("proventos DVA annual", e)
            dva = {}
        if dva.get("status") == "ok":
            # periods come DESC (newest first) → chart needs ASC.
            dva_periods = list(reversed(dva.get("periods", [])))
            dva_labels = [(p.get("data_fim_exerc") or "")[:4] for p in dva_periods]
            dva_div: list[float] = []
            dva_jcp: list[float] = []
            for p in dva_periods:
                acc = p.get("accounts") or {}
                dva_div.append((acc.get("7.08.04.02") or {}).get("valor_brl") or 0.0)
                dva_jcp.append((acc.get("7.08.04.01") or {}).get("valor_brl") or 0.0)
            if len(dva_labels) >= 2 and any(v > 0 for v in dva_div + dva_jcp):
                # Dynamic unit: R$ bi for blue chips, R$ mi for the rest.
                peak = max(dva_div + dva_jcp)
                if peak >= 1e9:
                    div_, unit, decimals = 1e9, "R$ bilhões", 3
                else:
                    div_, unit, decimals = 1e6, "R$ milhões", 1
                sections.append({
                    "type": "chart",
                    "title": f"Proventos Declarados na DVA por Exercício ({unit})",
                    "description": "Valores CONTÁBEIS declarados em cada "
                                   "exercício social (DFP/DVA — contas "
                                   "7.08.04.02 Dividendos e 7.08.04.01 JCP, "
                                   "empilhados). Diferem dos eventos por ação "
                                   "acima (limitados à janela da API da B3): "
                                   "esta série cobre todo o histórico "
                                   "disponível no CVM e é o TOTAL declarado, "
                                   "não o valor por ação.",
                    "chart_data": {
                        "type": "bar",
                        "data": {
                            "labels": dva_labels,
                            "datasets": [
                                {"label": "Dividendos",
                                 "data": [round(v / div_, decimals) for v in dva_div],
                                 "backgroundColor": _C_DIVIDENDO, "borderWidth": 0},
                                {"label": "JCP",
                                 "data": [round(v / div_, decimals) for v in dva_jcp],
                                 "backgroundColor": _C_JCP, "borderWidth": 0},
                            ],
                        },
                        "options": {"scales": {
                            "x": {"stacked": True},
                            "y": {"stacked": True, "beginAtZero": True,
                                  "title": {"text": unit}},
                        }},
                    },
                })
            dva_rows = []
            for p in dva_periods:
                acc = p.get("accounts") or {}
                dva_rows.append([
                    (p.get("data_fim_exerc") or "")[:4],
                    _fmt((acc.get("7.08.04.02") or {}).get("valor_brl"), "brl"),
                    _fmt((acc.get("7.08.04.01") or {}).get("valor_brl"), "brl"),
                    _fmt((acc.get("7.08.04") or {}).get("valor_brl"), "brl"),
                ])
            if dva_rows:
                sections.append({
                    "type": "table",
                    "title": "Proventos Declarados na DVA (DFP 7.08.04.*)",
                    "description": "Valores CONTÁBEIS declarados por exercício "
                                   "social (R$ total, não por ação). Diferem da "
                                   "tabela acima porque a DVA registra o que foi "
                                   "declarado no exercício e os eventos da B3 "
                                   "registram o que foi pago por ação.",
                    "columns": ["Exercício", "Dividendos", "JCP", "Total"],
                    "rows": dva_rows,
                    "formats": {},
                    "note": "Fonte: DFP/DVA — conta 7.08.04 e subcontas.",
                })

        return {"ticker": tk, "status": "ok", "sections": sections}
