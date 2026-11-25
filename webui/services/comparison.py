"""webui/services/comparison.py — the Comparação tool (Ferramentas page) [v1.27].

The first tool of the new Ferramentas main tab: pick 2-4 companies and
compare them side by side, the online-shop way — one COLUMN per company,
metric rows grouped by theme, the BEST value of each row highlighted.

Data layer = the same engines the company pages use (direct imports, no
MCP dispatcher — the webui/services precedent):
  - valuation ratios mode   → multiples, ROE/ROA/margins, liquidity,
                              leverage, DY, market cap, EV (fractions as
                              fractions; apply_fmt does the ×100).
  - financials summary mode → latest ANNUAL statement metrics (Receita,
                              EBITDA, Lucro, Balanço lines, payout).
  - dividends summary mode  → B3 event count, DPA médio, DVA annual
                              remuneration (the v1.26.1 share-class
                              correct, DDM-merged DPA engine).
  - financials quarterly(8) → QoQ/YoY growth via the comparison skill's
                              _compute_growth (sign-change guarded).
  - price engine (cotahist) → FULL-history month-end closes + the last
                              ~13 months of daily closes (price_hist —
                              the Cotação Histórica cards and the base-100
                              performance chart both read it) + the day
                              change on the column header.
  - CAD via the bridge      → sector per ticker.

Per-ticker fetches run in a ThreadPoolExecutor (max 4 — the tool caps at
4 companies anyway). The engine cache is ContextVar-backed (thread-local),
so each worker wraps its OWN engine_cache_scope — the ratios + summary +
quarterly calls inside one worker share statement fetches.

[v1.26.1 foundation cashed in] the whole payload rides the
webui_payloads cache (namespace "tools_comparison_v2" — the payload
shape moved with the two-resolution price_hist and the leader cards
cut, so no v1-shaped stale cache can ever serve) keyed by the
COMPOSITE of every ticker's DFP+ITR × COTAHIST fingerprint — any new
demonstração or cotação for ANY of the compared companies invalidates
the set and rebuilds it; repeat visits return in ~1ms with the ⚡
provenance line.

The payload is rendered by a CUSTOM client renderer (initToolsPage in
app.js — the online-shop grid + picker are interactive state, like the
backtest tab, not the generic sections contract).
"""
from __future__ import annotations

import re
import sys
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, timedelta
from typing import Any

from webui.services.company import CompanyService

# B3 ticker shape (same rule as api.py's Ticker path param).
_TICKER_RE = re.compile(r"^[A-Z0-9]{4,6}$")

# The tool's hard bounds (the user's ask: "up to 4 companies").
MIN_TICKERS = 2
MAX_TICKERS = 4

# Per-company color roster (index = position in the picker). Teal/amber/
# violet/rose — the app's chart palette, no two adjacent columns alike.
COLORS = ["#0d9488", "#f59e0b", "#8b5cf6", "#e11d48"]

# Price-history resolutions: month-ends over the WHOLE cotahist range
# (the Tudo/10A/5A pills) + daily closes for the last ~13 months (the
# 1A/6M/3M/1M pills). The Cotação Histórica cards and the base-100
# chart slice this client-side — the payload ships both raw.
_HIST_DAILY_DAYS = 396


class ComparisonService:
    """Comparação tool — one compare() call, one JSON payload."""

    # v2: the payload shape moved (price_hist in, leader KPIs out) — the
    # bumped namespace keeps any v1-shaped cached payload from serving.
    _NS = "tools_comparison_v2"

    def __init__(self) -> None:
        self._company = CompanyService()

    # ── validation ───────────────────────────────────────────────────────────

    @staticmethod
    def validate(tickers: Any) -> tuple[list[str], str]:
        """Normalize the raw ticker list → (clean_list, error_message).

        Dedupes (keeping first occurrence), uppercases, validates the B3
        shape and the 2-4 bound. The error message is PT-BR and ready to
        reach the UI; an empty error means valid.
        """
        if isinstance(tickers, str):
            tickers = [t for t in re.split(r"[,\s+.]+", tickers) if t]
        if not isinstance(tickers, (list, tuple)):
            return [], "informe os tickers a comparar"
        seen: list[str] = []
        for t in tickers:
            tk = str(t or "").strip().upper()
            if tk and tk not in seen:
                seen.append(tk)
        if len(seen) < MIN_TICKERS:
            return [], f"escolha ao menos {MIN_TICKERS} empresas para comparar"
        if len(seen) > MAX_TICKERS:
            return [], f"máximo de {MAX_TICKERS} empresas por comparação"
        bad = [t for t in seen if not _TICKER_RE.match(t)]
        if bad:
            return [], f"ticker inválido: {bad[0]}"
        return seen, ""

    # ── public entry point ───────────────────────────────────────────────────

    def compare(self, tickers: Any) -> dict[str, Any]:
        """Build the full comparison payload for 2-4 tickers."""
        tks, err = self.validate(tickers)
        if err:
            return {"status": "error", "error": err}

        # ── [v1.26.1 foundation] payload cache ──
        cache_key = ",".join(tks)
        fp = self._fingerprint(tks)
        if fp:
            try:
                from data_sources import _cache as _dc
                cached = _dc.get_webui_payload(self._NS, cache_key, fp)
            except Exception:
                cached = None
            if cached is not None:
                note = self._cache_note(cached.pop("_cached_at", None))
                if note:
                    cached["cache_note"] = note
                return cached

        entries = self._fetch_all(tks)
        payload = self._assemble(tks, entries)

        if fp and payload.get("status") == "ok":
            try:
                from data_sources import _cache as _dc
                _dc.set_webui_payload(self._NS, cache_key, fp, payload)
            except Exception:
                pass
        return payload

    # ── cache helpers (financials.py pattern) ────────────────────────────────

    @staticmethod
    def _fingerprint(tks: list[str]) -> str | None:
        """Composite of every ticker's DFP+ITR × COTAHIST fingerprint.

        None when ANY ticker resolves to none (unknown everywhere → skip
        the cache entirely, build fresh every time — conservative: a
        partial fingerprint could serve a stale column).
        """
        try:
            from data_sources import _cache as _dc
            parts = []
            for tk in tks:
                fp = _dc.webui_fingerprint(tk)
                if not fp:
                    return None
                parts.append(f"{tk}:{fp}")
            return "|".join(parts)
        except Exception:
            return None

    @staticmethod
    def _cache_note(cached_at: str | None) -> str | None:
        if not cached_at:
            return None
        ts = str(cached_at)
        try:
            from datetime import datetime as _dt
            ts = _dt.fromisoformat(ts).strftime("%d/%m/%Y %H:%M")
        except Exception:
            pass
        return (f"Pré-calculado em {ts} — a comparação só muda com novas "
                "demonstrações (DFP/ITR) ou cotações de qualquer empresa "
                "selecionada; recalcula automaticamente após a sincronização.")

    # ── per-ticker fetch (worker thread) ─────────────────────────────────────

    def _fetch_all(self, tks: list[str]) -> list[dict[str, Any]]:
        """Fetch every ticker concurrently, preserving input order."""
        by_ticker: dict[str, dict[str, Any]] = {}
        with ThreadPoolExecutor(max_workers=MAX_TICKERS) as executor:
            futures = {executor.submit(self._fetch_one, tk): tk for tk in tks}
            for future in as_completed(futures):
                tk = futures[future]
                try:
                    by_ticker[tk] = future.result()
                except Exception as e:  # defensive — _fetch_one never raises
                    by_ticker[tk] = self._empty_entry(tk, f"fetch: {e}")
        return [by_ticker[tk] for tk in tks]

    @staticmethod
    def _empty_entry(tk: str, error: str = "") -> dict[str, Any]:
        return {"ticker": tk, "val": {}, "fin": {}, "div": {}, "grw": {},
                "mkt": {}, "hist_monthly": [], "hist_daily": [],
                "error": error}

    def _fetch_one(self, tk: str) -> dict[str, Any]:
        """All per-ticker data, best-effort. Never raises.

        Each source failure is recorded in entry["error"] (the first one
        wins) but leaves the other sources in place — a company without
        cotações still shows its annual statement metrics.
        """
        entry = self._empty_entry(tk)
        try:
            from skills._base import engine_cache_scope
            with engine_cache_scope():
                self._fetch_ratios(entry)
                self._fetch_financials(entry)
                self._fetch_dividends(entry)
                self._fetch_growth(entry)
        except Exception as e:
            if not entry["error"]:
                entry["error"] = str(e)
        self._fetch_series(entry)
        return entry

    # ── individual sources ───────────────────────────────────────────────────

    @staticmethod
    def _fetch_ratios(entry: dict[str, Any]) -> None:
        try:
            from skills.cvm.valuation.modes.ratios import ratios as _ratios_mode
            r = _ratios_mode(entry["ticker"])
            if isinstance(r, dict) and r.get("status") == "ok":
                rd = r.get("ratios")
                if isinstance(rd, dict) and "status" not in rd:
                    entry["val"] = rd
                elif isinstance(rd, dict):
                    if not entry["error"]:
                        entry["error"] = (rd.get("note") or
                                          rd.get("error") or "valuation indisponível")
            elif not entry["error"]:
                entry["error"] = "valuation indisponível"
        except Exception as e:
            if not entry["error"]:
                entry["error"] = f"valuation: {e}"

    @staticmethod
    def _fetch_financials(entry: dict[str, Any]) -> None:
        try:
            from skills.cvm.financials.modes.summary import summary as _fin_summary
            r = _fin_summary(company=entry["ticker"], consolidado=1)
            if isinstance(r, dict) and r.get("status") == "ok":
                latest = (r.get("sections") or {}).get("latest_annual") or {}
                if latest.get("metrics"):
                    entry["fin"] = {**(latest.get("metrics") or {}),
                                    **(latest.get("ratios") or {})}
        except Exception:
            pass  # annual statement metrics are complements, not blockers

    @staticmethod
    def _fetch_dividends(entry: dict[str, Any]) -> None:
        try:
            from skills.cvm.dividends.modes.summary import summary as _div_summary
            from skills.cvm.comparison.fetchers import _extract_dividend_metrics
            r = _div_summary(company=entry["ticker"])
            if isinstance(r, dict) and r.get("status") == "ok":
                entry["div"] = _extract_dividend_metrics(r.get("sections") or {})
        except Exception:
            pass

    @staticmethod
    def _fetch_growth(entry: dict[str, Any]) -> None:
        try:
            from skills.cvm.financials.modes.quarterly import quarterly as _fin_q
            from skills.cvm.comparison.helpers import _compute_growth
            r = _fin_q(company=entry["ticker"], periods=8, consolidado=1)
            if isinstance(r, dict) and r.get("status") == "ok":
                entry["grw"] = _compute_growth(r) or {}
        except Exception:
            pass

    @staticmethod
    def _fetch_series(entry: dict[str, Any]) -> None:
        """Full-history month-end closes + recent dailies + day change.

        Two resolutions feed the client charts (the Cotação Histórica
        cards and the base-100 line): month-ends over the WHOLE cotahist
        range (the Tudo/10A/5A pills) and daily closes for the last
        ~13 months (the 1A/6M/3M/1M pills).

        The v1.25 backtest hardening applies here too: COTAHIST carries
        DIR/REC subscription-rights and fractional rows under the same
        market_type=10 (a R$ 0,50 right next to the real close made the
        raw engine's "day change" read +22.506%) — so the query prefers
        bdi_code=2 (lote padrão) and keeps ONE row per session (highest
        volume), falling back to the plain market filter for tickers
        with no lote-padrão rows.
        """
        tk = entry["ticker"]
        rows: list[tuple] = []
        try:
            import sqlite3
            from skills.cvm.calculations.engines.price import _cotahist_db
            path = _cotahist_db()
            if path and path.exists():
                import contextlib
                with contextlib.closing(sqlite3.connect(
                        f"file:{path}?mode=ro", uri=True)) as conn:
                    for bdi_filter in ("AND bdi_code = 2", ""):
                        rows = conn.execute(
                            "SELECT refdate, close, volume FROM cotahist "
                            "WHERE symbol = ? AND market_type = 10 "
                            "AND close IS NOT NULL AND close > 0 "
                            f"{bdi_filter} ORDER BY refdate ASC",
                            (tk,),
                        ).fetchall()
                        if rows:
                            break
        except Exception:
            rows = []
        if not rows:
            return
        # one row per date — highest volume wins
        best: dict[str, tuple[float, float]] = {}
        for refdate, close, volume in rows:
            vol = float(volume or 0.0)
            prev = best.get(refdate)
            if prev is None or vol > prev[0]:
                best[refdate] = (vol, float(close))
        # ISO dates sort lexicographically = chronologically
        daily_all = sorted(best.items())  # [(date, (vol, close)), …]
        # month-end downsample over the whole range (last close of each
        # month — daily_all is ascending)
        by_month: dict[str, float] = {}
        for d, (_vol, close) in daily_all:
            by_month[str(d)[:7]] = close
        entry["hist_monthly"] = [{"date": m, "close": c}
                                 for m, c in sorted(by_month.items())]
        cutoff = (date.today() -
                  timedelta(days=_HIST_DAILY_DAYS)).isoformat()
        entry["hist_daily"] = [{"date": d, "close": v[1]}
                               for d, v in daily_all if str(d) >= cutoff]
        last_date, (_, last_close) = daily_all[-1]
        entry["mkt"] = {
            "price": last_close,
            "price_date": last_date,
            "var_day": ((last_close - daily_all[-2][1][1]) / daily_all[-2][1][1])
            if len(daily_all) > 1 and daily_all[-2][1][1] else None,
        }

    # ── assembly ─────────────────────────────────────────────────────────────

    def _assemble(self, tks: list[str], entries: list[dict[str, Any]]) -> dict[str, Any]:
        names = self._names(tks)
        sectors = self._sectors(tks)

        companies = []
        for i, (tk, entry) in enumerate(zip(tks, entries)):
            mkt = entry.get("mkt") or {}
            price = mkt.get("price")
            if price is None:
                price = (entry.get("val") or {}).get("price")
            # [v1.5 precedent] English engine internals never reach the UI:
            # the raw per-source error is logged server-side, the UI gets a
            # short PT-BR "dados parciais" note.
            raw_err = (entry.get("error") or "").strip()
            if raw_err:
                print(f"[webui] comparison {tk} partial: {raw_err}",
                      file=sys.stderr)
            companies.append({
                "ticker": tk,
                "name": names.get(tk, ""),
                "sector": sectors.get(tk, ""),
                "color": COLORS[i % len(COLORS)],
                "price": price,
                "price_date": mkt.get("price_date", ""),
                "var_day": mkt.get("var_day"),
                "error": "dados parciais" if raw_err else "",
            })

        groups = _build_groups(entries)
        payload = {
            "status": "ok",
            "tickers": tks,
            "companies": companies,
            "groups": groups,
            "charts": _build_charts(entries, tks),
            "price_hist": _build_price_hist(entries),
            "errors": [f"{c['ticker']}: algumas fontes falharam "
                       f"(indicadores parciais — veja o log do sistema)"
                       for c in companies if c["error"]],
        }
        if not any(g["rows"] for g in groups):
            return {
                "status": "error",
                "error": ("nenhum indicador encontrado para "
                          f"{', '.join(tks)} — sincronize as fontes CVM "
                          "(DFP/ITR) e Cotações na página Sincronização"),
            }
        return payload

    # ── names + sectors ──────────────────────────────────────────────────────

    @staticmethod
    def _names(tks: list[str]) -> dict[str, str]:
        """Trading names from the bridge DB (one batch query, read-only)."""
        out: dict[str, str] = {tk: "" for tk in tks}
        try:
            import contextlib
            import sqlite3
            from data_sources.cvm._db import bridge_db_path
            db = bridge_db_path()
            if not db.exists():
                return out
            ph = ",".join("?" * len(tks))
            with contextlib.closing(sqlite3.connect(f"file:{db}?mode=ro", uri=True)) as conn:
                conn.row_factory = sqlite3.Row
                rows = conn.execute(
                    f"SELECT ticker, trading_name FROM ticker_map "
                    f"WHERE ticker IN ({ph})", tks,
                ).fetchall()
            for r in rows:
                out[r["ticker"]] = (r["trading_name"] or "").strip()
        except Exception:
            pass
        return out

    @staticmethod
    def _sectors(tks: list[str]) -> dict[str, str]:
        try:
            from skills.cvm.comparison.fetchers import _fetch_one_sector
            out: dict[str, str] = {}
            with ThreadPoolExecutor(max_workers=MAX_TICKERS) as executor:
                futures = {executor.submit(_fetch_one_sector, tk): tk for tk in tks}
                for future in as_completed(futures):
                    tk = futures[future]
                    try:
                        out[tk] = future.result()[1]
                    except Exception:
                        out[tk] = ""
            return out
        except Exception:
            return {tk: "" for tk in tks}


# ═════════════════════════════════════════════════════════════════════════════
# Row specs — the comparison grid's backbone.
#
# Each row: (group_key, label, candidates, fmt, best, pos_only, tip)
#   candidates = ordered [(source_dict_key, metric_key), …] — first hit wins
#   fmt        = apply_fmt spec ("brl", "num", "pct", …)
#   best       = None | "min" | "max" — highlight direction for the row
#   pos_only   = multiples/debt ranks skip non-positive values (a negative
#                P/L is a loss, not a bargain; negative coverage is distress)
#   tip        = PT-BR tooltip with the formula
# ═════════════════════════════════════════════════════════════════════════════

_ROWS: list[tuple[str, str, list[tuple[str, str]], str, str | None, bool, str]] = [
    # ── Mercado ──
    ("mercado", "Última Cotação",
     [("mkt", "price"), ("val", "price")], "brl_full", None, False,
     "Fechamento do último pregão com negócio (COTAHIST)."),
    ("mercado", "Var. Dia",
     [("mkt", "var_day")], "pct", "max", False,
     "Variação percentual do último pregão."),
    ("mercado", "Market Cap",
     [("val", "market_cap")], "brl", None, False,
     "Cotação × total de ações = valor de mercado da companhia."),
    ("mercado", "Enterprise Value (EV)",
     [("val", "ev")], "brl", None, False,
     "Market cap + dívida líquida — o custo total para comprar a companhia."),
    ("mercado", "Total de Ações",
     [("val", "total_shares")], "int", None, False,
     "Ações emitidas em circulação."),

    # ── Valuation ──
    ("valuation", "P/L",
     [("val", "p_l")], "num", "min", True,
     "Preço / Lucro por Ação — quanto o mercado paga por R$ 1 de lucro."),
    ("valuation", "P/VPA",
     [("val", "p_vpa")], "num", "min", True,
     "Preço / Valor Patrimonial por Ação."),
    ("valuation", "P/EBIT",
     [("val", "p_ebit")], "num", "min", True,
     "Preço / EBIT por ação."),
    ("valuation", "EV/EBITDA",
     [("val", "ev_ebitda")], "num", "min", True,
     "Enterprise Value / EBITDA — múltiplo neutro quanto à estrutura de capital."),
    ("valuation", "PSR",
     [("val", "psr")], "num", "min", True,
     "Preço / Receita por ação."),
    ("valuation", "EV/Receita",
     [("val", "ev_sales")], "num", "min", True,
     "Enterprise Value / Receita Líquida."),

    # ── Rentabilidade ──
    ("rentabilidade", "ROE",
     [("val", "roe"), ("fin", "roe")], "pct", "max", False,
     "Lucro Líquido / Patrimônio Líquido — retorno sobre o capital próprio."),
    ("rentabilidade", "ROA",
     [("val", "roa"), ("fin", "roa")], "pct", "max", False,
     "Lucro Líquido / Ativo Total — retorno sobre os ativos."),
    ("rentabilidade", "Marg. Bruta",
     [("fin", "marg_bruta")], "pct", "max", False,
     "Lucro Bruto / Receita Líquida (último anual)."),
    ("rentabilidade", "Marg. EBITDA",
     [("val", "marg_ebitda"), ("fin", "marg_ebitda"), ("grw", "marg_ebitda")],
     "pct", "max", False,
     "EBITDA / Receita Líquida."),
    ("rentabilidade", "Marg. Líquida",
     [("val", "margem_liquida"), ("fin", "marg_liquida")], "pct", "max", False,
     "Lucro Líquido / Receita Líquida."),
    ("rentabilidade", "Marg. FCO",
     [("val", "ocf_margin")], "pct", "max", False,
     "Fluxo de Caixa Operacional / Receita Líquida."),

    # ── Crescimento (trimestral) ──
    ("crescimento", "Receita YoY",
     [("grw", "receita_yoy")], "pct", "max", False,
     "Último trimestre vs mesmo trimestre do ano anterior."),
    ("crescimento", "EBITDA YoY",
     [("grw", "ebitda_yoy")], "pct", "max", False,
     "Último trimestre vs mesmo trimestre do ano anterior."),
    ("crescimento", "Lucro Líq. YoY",
     [("grw", "lucro_yoy")], "pct", "max", False,
     "Último trimestre vs mesmo trimestre do ano anterior."),
    ("crescimento", "Receita QoQ",
     [("grw", "receita_qoq")], "pct", "max", False,
     "Último trimestre vs trimestre imediatamente anterior."),
    ("crescimento", "EBITDA QoQ",
     [("grw", "ebitda_qoq")], "pct", "max", False,
     "Último trimestre vs trimestre imediatamente anterior."),
    ("crescimento", "Lucro Liq. QoQ",
     [("grw", "lucro_qoq")], "pct", "max", False,
     "Último trimestre vs trimestre imediatamente anterior."),

    # ── Dividendos ──
    ("dividendos", "Div Yield",
     [("val", "dividend_yield")], "pct", "max", False,
     "Proventos dos últimos 12 meses / cotação atual."),
    ("dividendos", "DPA",
     [("val", "dpa")], "brl_full", None, False,
     "Dividendos por ação (12 meses)."),
    ("dividendos", "Payout",
     [("fin", "payout")], "pct", None, False,
     "Proventos / Lucro Líquido — quanto do lucro é distribuído."),
    ("dividendos", "Eventos (B3)",
     [("div", "event_count")], "int", None, False,
     "Eventos de proventos registrados na B3."),
    ("dividendos", "Remun. Total (últ. ano)",
     [("div", "annual_total")], "brl", None, False,
     "Dividendos + JCP pagos no último exercício (DVA)."),

    # ── Endividamento e Liquidez ──
    ("endividamento", "Dívida Bruta",
     [("fin", "divida_bruta")], "brl", None, False,
     "Empréstimos e financiamentos (último anual)."),
    ("endividamento", "Dívida/PL",
     [("val", "divida_pl")], "num", "min", True,
     "Dívida bruta / Patrimônio Líquido."),
    ("endividamento", "Dívida Líq./EBITDA",
     [("val", "divida_liquida_ebitda")], "num", "min", True,
     "Dívida líquida / EBITDA — anos de EBITDA para quitar a dívida."),
    ("endividamento", "Liquidez Corrente",
     [("val", "liquidez_corrente")], "num", "max", False,
     "Ativo circulante / Passivo circulante."),
    ("endividamento", "Liquidez Seca",
     [("val", "quick_ratio")], "num", "max", False,
     "(Ativo circulante − estoques) / Passivo circulante."),
    ("endividamento", "Cobertura de Juros",
     [("val", "interest_coverage")], "num", "max", True,
     "EBIT / despesa financeira — quantas vezes o lucro operacional cobre os juros."),
    ("endividamento", "FCO/Dívida",
     [("val", "cash_flow_to_debt")], "num", "max", False,
     "Fluxo de caixa operacional / dívida bruta."),

    # ── Demonstrativos (último anual) — the annual-statement rows rank
    # MAX like every other row (the biggest Receita/EBITDA/Lucro/… wins
    # the line, ✓ included — the user's ask); only the MERCADO size rows
    # (market cap, EV, total de ações) stay unranked. ──
    ("demonstrativos", "Receita Líquida",
     [("fin", "receita_liquida")], "brl", "max", False,
     "Receita líquida do último exercício anual fechado."),
    ("demonstrativos", "EBITDA",
     [("fin", "ebitda")], "brl", "max", False,
     "EBITDA do último exercício anual fechado."),
    ("demonstrativos", "Lucro Líquido",
     [("fin", "lucro_liquido")], "brl", "max", False,
     "Lucro líquido do último exercício anual fechado."),
    ("demonstrativos", "Ativo Total",
     [("fin", "ativo_total")], "brl", "max", False,
     "Ativo total do último balanço anual."),
    ("demonstrativos", "Patrimônio Líquido",
     [("fin", "patrimonio_liquido")], "brl", "max", False,
     "Patrimônio líquido do último balanço anual."),
    ("demonstrativos", "Caixa",
     [("fin", "caixa")], "brl", "max", False,
     "Caixa e equivalentes do último balanço anual."),
    ("demonstrativos", "FCO",
     [("fin", "fco")], "brl", "max", False,
     "Fluxo de caixa operacional do último exercício anual fechado."),
]

_GROUP_ORDER = [
    ("mercado", "Mercado"),
    ("valuation", "Valuation"),
    ("rentabilidade", "Rentabilidade"),
    ("crescimento", "Crescimento (trimestral)"),
    ("dividendos", "Dividendos"),
    ("endividamento", "Endividamento e Liquidez"),
    ("demonstrativos", "Demonstrativos (último anual)"),
]

def _row_value(entry: dict[str, Any], candidates: list[tuple[str, str]]) -> Any:
    """First non-None candidate across the ordered (source, key) pairs."""
    for src, key in candidates:
        v = (entry.get(src) or {}).get(key)
        if v is not None:
            try:
                if v == v:  # NaN guard (NaN != NaN)
                    return v
            except Exception:
                return v
    return None


def _best_indices(values: list[Any], best: str | None, pos_only: bool) -> list[int]:
    """Indices holding the best value (min/max), honoring eligibility.

    pos_only rows (multiples, debt ranks, coverage) consider only values
    > 0 — a negative P/L is a loss, not a bargain. Highlighting requires
    2+ eligible values (a single value can't win a comparison).
    """
    if not best:
        return []
    idxs = [i for i, v in enumerate(values) if v is not None]
    if pos_only:
        idxs = [i for i in idxs if values[i] > 0]
    if len(idxs) < 2:
        return []
    if best == "min":
        target = min(values[i] for i in idxs)
    else:
        target = max(values[i] for i in idxs)
    return [i for i in idxs if values[i] == target]


def _fmt(value: Any, spec: str) -> str:
    """apply_fmt that never raises ("—" on None/garbage)."""
    try:
        from tools.report_ops.formats import apply_fmt
        return apply_fmt(value, spec)
    except Exception:
        return "—" if value is None else str(value)


def _build_groups(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Assemble the row groups: raw + formatted values + best indices."""
    groups: dict[str, dict[str, Any]] = {
        key: {"key": key, "name": name, "rows": []}
        for key, name in _GROUP_ORDER
    }
    for group_key, label, candidates, spec, best, pos_only, tip in _ROWS:
        raw = [_row_value(e, candidates) for e in entries]
        if all(v is None for v in raw):
            continue  # row not applicable to ANY of the compared companies
        groups[group_key]["rows"].append({
            "label": label,
            "fmt": spec,
            "raw": raw,
            "values": [_fmt(v, spec) for v in raw],
            "best": _best_indices(raw, best, pos_only),
            "tip": tip,
        })
    return [g for g in groups.values() if g["rows"]]


def _normalize_pct(values: list[Any]) -> list[Any]:
    """Scale a metric to 0-100 vs the best value (radar axis).

    Negative/missing values → 0/None; the max is taken over POSITIVE
    values only (a single outlier with a huge value flattens the others,
    but that IS the comparison story).
    """
    mx = 0.0
    for v in values:
        if v is not None and isinstance(v, (int, float)) and v > mx:
            mx = float(v)
    if mx <= 0:
        return [None] * len(values)
    out = []
    for v in values:
        if v is None:
            out.append(None)
        else:
            try:
                out.append(round(max(0.0, float(v)) / mx * 100.0, 1))
            except Exception:
                out.append(None)
    return out


# Radar axes: (axis_label, [(source, key), …]) — fractions, normalized 0-100.
_RADAR_AXES = [
    ("ROE", [("val", "roe"), ("fin", "roe")]),
    ("Marg. EBITDA", [("val", "marg_ebitda"), ("fin", "marg_ebitda"), ("grw", "marg_ebitda")]),
    ("Marg. Líquida", [("val", "margem_liquida"), ("fin", "marg_liquida")]),
    ("Div Yield", [("val", "dividend_yield")]),
    ("ROA", [("val", "roa"), ("fin", "roa")]),
    ("Cresc. Receita", [("grw", "receita_yoy")]),
]

# Grouped-bar charts: (chart_id, title, description, row_labels, y_title,
#                      scale) — values come from the same _ROWS labels.
_BAR_CHART_DEFS = [
    ("multiplos", "Múltiplos de Valuation",
     "Barras agrupadas por múltiplo — valores nulos ou negativos ficam fora "
     "(múltiplo negativo é prejuízo, não barato).",
     ["P/L", "P/VPA", "EV/EBITDA", "PSR"], "múltiplos (×)", 1.0),
    ("margens", "Margens",
     "Margem bruta, EBITDA, líquida e do fluxo operacional — valores em %.",
     ["Marg. Bruta", "Marg. EBITDA", "Marg. Líquida", "Marg. FCO"], "%", 100.0),
    ("crescimento", "Crescimento YoY (trimestral)",
     "Receita, EBITDA e lucro líquido — último trimestre vs mesmo trimestre "
     "do ano anterior, em %.",
     ["Receita YoY", "EBITDA YoY", "Lucro Líq. YoY"], "%", 100.0),
    ("dividendos", "Dividendos",
     "Dividend yield dos últimos 12 meses e payout do último exercício, em %.",
     ["Div Yield", "Payout"], "%", 100.0),
]


def _build_charts(entries: list[dict[str, Any]],
                  tks: list[str]) -> list[dict[str, Any]]:
    """Server-built Chart.js configs (renderValChart draws them as-is).

    Datasets are PER COMPANY (one color each — companies[i].color); a
    chart with a single company still renders (the legend suppression is
    client-side per the v1.26.1 rule).
    """
    # A rows-shaped lookup so the charts read the same values as the grid.
    rows_by_label: dict[str, list[Any]] = {}
    for _gk, label, candidates, _spec, _best, _pos, _tip in _ROWS:
        rows_by_label[label] = [_row_value(e, candidates) for e in entries]

    charts: list[dict[str, Any]] = []

    # 1. Radar — normalized profile.
    radar_labels: list[str] = []
    radar_data: list[list[Any]] = [[] for _ in tks]
    for axis_label, candidates in _RADAR_AXES:
        vals = [_row_value(e, candidates) for e in entries]
        norm = _normalize_pct(vals)
        if all(v is None for v in norm):
            continue
        radar_labels.append(axis_label)
        for i in range(len(tks)):
            radar_data[i].append(norm[i])
    if radar_labels:
        datasets = []
        for i, tk in enumerate(tks):
            # a company with no data on ANY axis stays out — an all-None
            # dataset is legend noise (the bar charts do the same).
            if all(v is None for v in radar_data[i]):
                continue
            datasets.append({
                "label": tk,
                "data": radar_data[i],
                "borderColor": COLORS[i % len(COLORS)],
                "backgroundColor": COLORS[i % len(COLORS)] + "26",
            })
        charts.append({
            "id": "radar",
            "title": "Perfil Comparado",
            "desc": ("Cada eixo normalizado pelo melhor valor entre as "
                     "empresas (100 = líder). Valores negativos contam como 0."),
            "cd": {"type": "radar", "data": {"labels": radar_labels,
                                             "datasets": datasets}},
        })

    # 2. Grouped bars (multiples / margins / growth / dividends).
    for chart_id, title, desc, labels, y_title, scale in _BAR_CHART_DEFS:
        datasets = []
        for i, tk in enumerate(tks):
            data = []
            for lbl in labels:
                v = rows_by_label.get(lbl, [None] * len(tks))[i]
                if v is None:
                    data.append(None)
                else:
                    try:
                        data.append(round(float(v) * scale, 2))
                    except Exception:
                        data.append(None)
            # Multiples: negative = loss → chart nothing (the note explains).
            if chart_id == "multiplos":
                data = [v if (v is not None and v > 0) else None for v in data]
            if all(v is None for v in data):
                continue
            datasets.append({
                "label": tk,
                "data": data,
                "backgroundColor": COLORS[i % len(COLORS)] + "cc",
                "borderColor": COLORS[i % len(COLORS)],
                "borderWidth": 1,
            })
        if not datasets:
            continue
        charts.append({
            "id": chart_id,
            "title": title,
            "desc": desc,
            "cd": {
                "type": "bar",
                "data": {"labels": labels, "datasets": datasets},
                "options": {"scales": {
                    "y": {"beginAtZero": True, "title": {"text": y_title}},
                }},
            },
        })

    return charts


def _build_price_hist(entries: list[dict[str, Any]]) -> dict[str, Any]:
    """Two-resolution price series per ticker for the client charts.

    monthly = month-end closes over the WHOLE cotahist history (the
    Tudo/10A/5A pills); daily = the last ~13 months (the 1A/6M/3M/1M
    pills). The Cotação Histórica cards and the base-100 Desempenho
    line both read this — the client owns the range pills, slices the
    window and (base-100) re-normalizes to each company's first
    visible close.
    """
    return {
        "monthly": {e["ticker"]: list(e.get("hist_monthly") or [])
                    for e in entries},
        "daily": {e["ticker"]: list(e.get("hist_daily") or [])
                  for e in entries},
    }
