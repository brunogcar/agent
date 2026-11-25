"""webui/services/screener.py — the Screener tool (Ferramentas page) [v1.28].

The Ferramentas tab's SECOND tool: screen ONE ticker against its whole
SECTOR — not just the peers side by side, but the sector MEDIANS (the
user's ask: "its not just to compare with sector piers but sector
median… borrow ideas from comparison, expand").

Three layers, mirroring the PETR4_screener_dashboard.html concept and
expanding it:

  1. THE SUBJECT — ticker header (name, sector, last close, day change)
     + the sector-median KPI row (Mediana P/L / P/VPA / EV/EBITDA / ROE /
     Div Yield) + the Cotação Histórica card with the standard range
     pills (month-ends long, dailies short — the same two-resolution
     price_hist the comparison tool ships, subject only).
  2. THE SECTOR — every company of the subject's sector in one table
     (one class per company — the MOST LIQUID share, deduped by CNPJ
     root so PETR3/PETR4 never count twice), sorted by P/L
     cheapest-first, the subject row highlighted; then the P/L and ROE
     position charts (bars sorted, the subject in amber, the median as
     a dashed line — where the company sits inside its sector).
  3. THE VERDICT — the Meu Valor × Mediana do Setor table: each metric
     with my value, the sector median, the delta % and a verdict badge —
     cheap/expensive for valuation multiples and leverage (lower is
     better), above/below for quality metrics (ROE, ROA, margins, DY,
     growth — higher is better); then the grouped-bars chart of my
     value vs the median per metric.

Peer discovery = the bridge DB's ticker_map.setor_ativ (synced from CAD
/ FCA — one query for the whole sector). The subject's own sector falls
back to the CAD lookup when its bridge row has no setor_ativ yet.
Medians are computed over the sector companies INCLUDING the subject
(the median is a property of the SECTOR — consistent no matter which
ticker is screened; robust to outliers, that's why median not mean),
over AVAILABLE values only (a missing DY never drags the median), and
valuation multiples take POSITIVE values only (a negative P/L is a
loss, not a bargain — the v1.27 comparison rule).

Data layer = the same engines as the comparison tool (imported from
webui.services.comparison — one implementation of the engine reads):
ratios mode + financials summary + quarterly growth per company, in a
ThreadPoolExecutor (max 8, engine_cache_scope per worker). Sector sizes
are bounded at 40 companies by liquidity (the subject always stays).

The payload rides the webui_payloads cache (namespace
"tools_screener_v1") keyed by the ticker on the composite fingerprint
of EVERY sector company PLUS the peer list itself — a new demonstração
of any peer rebuilds the medians, and a bridge resync that changes the
sector membership invalidates too. Rendered by a custom client renderer
(the initScreener half of initToolsPage in app.js).
"""
from __future__ import annotations

import re
import statistics
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from webui.services.comparison import (
    ComparisonService,
    _fmt,
    _row_value,
)

# B3 ticker shape (same rule as comparison.py / api.py).
_TICKER_RE = re.compile(r"^[A-Z0-9]{4,6}$")

# Sector size bound — by cotahist liquidity (last 365 days of volume),
# the subject always kept. The B3 listed universe per sector stays well
# under this; the cap just bounds the FIRST build.
MAX_COMPANIES = 40

# Metric fetch concurrency.
_MAX_WORKERS = 8

# The only "cheap" metric where a NEGATIVE value is GOOD (net cash).
_NET_DEBT_LABEL = "Dívida Líq./EBITDA"

# Valuation multiples — median and verdict consider POSITIVE values
# only (a negative P/L is a loss, not a bargain).
_POSITIVE_ONLY_LABELS = {"P/L", "P/VPA", "EV/EBITDA", "PSR", "P/EBIT"}


class ScreenerService:
    """Screener tool — one screen(ticker) call, one JSON payload."""

    _NS = "tools_screener_v1"

    def __init__(self) -> None:
        self._cmp = ComparisonService()

    # ── validation ───────────────────────────────────────────────────────────

    @staticmethod
    def validate(ticker: Any) -> tuple[str, str]:
        """Normalize the raw ticker → (clean_ticker, error_message)."""
        tk = str(ticker or "").strip().upper()
        if not tk:
            return "", "informe o ticker a analisar"
        if not _TICKER_RE.match(tk):
            return "", f"ticker inválido: {tk}"
        return tk, ""

    # ── public entry point ───────────────────────────────────────────────────

    def screen(self, ticker: Any) -> dict[str, Any]:
        """Build the full screener payload for one ticker."""
        tk, err = self.validate(ticker)
        if err:
            return {"status": "error", "error": err}

        sector, peers = self._sector_companies(tk)
        if not peers:
            return {
                "status": "error",
                "error": (f"não foi possível identificar o setor de {tk} — "
                          "sincronize a Bridge (Sincronização → Bridge) e o "
                          "CAD para o mapeamento ticker → setor"),
            }
        if len(peers) < 2:
            return {
                "status": "error",
                "error": ("o setor da empresa não tem outras companhias "
                          "listadas na Bridge — sincronize a Bridge para o "
                          "setor completo"),
            }

        # ── payload cache ──
        # The key is the ticker, but the fingerprint composites EVERY
        # sector company (the medians read them all) plus the peer list
        # itself — a bridge resync that adds/removes a sector member
        # invalidates the cached payload too.
        tks = [p["ticker"] for p in peers]
        fp = self._fingerprint(tks)
        if fp:
            try:
                from data_sources import _cache as _dc
                cached = _dc.get_webui_payload(self._NS, tk, fp)
            except Exception:
                cached = None
            if cached is not None:
                note = self._cache_note(cached.pop("_cached_at", None))
                if note:
                    cached["cache_note"] = note
                return cached

        payload = self._build(tk, sector, peers)

        if fp and payload.get("status") == "ok":
            try:
                from data_sources import _cache as _dc
                _dc.set_webui_payload(self._NS, tk, fp, payload)
            except Exception:
                pass
        return payload

    # ── cache helpers (comparison.py pattern) ────────────────────────────────

    @staticmethod
    def _fingerprint(tks: list[str]) -> str | None:
        """Composite of every sector company's DFP+ITR × COTAHIST
        fingerprint + the peer list (membership changes invalidate)."""
        try:
            from data_sources import _cache as _dc
            parts = []
            for tk in tks:
                fp = _dc.webui_fingerprint(tk)
                if not fp:
                    return None
                parts.append(f"{tk}:{fp}")
            return "|".join(parts) + f"|members={','.join(tks)}"
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
        return (f"Pré-calculado em {ts} — as medianas do setor só mudam "
                "com novas demonstrações (DFP/ITR), cotações ou companhias "
                "do setor; recalcula automaticamente após a sincronização.")

    # ── sector discovery (the bridge DB's ticker_map.setor_ativ) ─────────────

    @staticmethod
    def _sector_of(ticker: str) -> str:
        """The subject's sector — bridge setor_ativ, CAD fallback."""
        # 1. the bridge row (synced from CAD / FCA)
        try:
            import contextlib
            import sqlite3
            from data_sources.cvm._db import bridge_db_path
            db = bridge_db_path()
            if db.exists():
                with contextlib.closing(sqlite3.connect(
                        f"file:{db}?mode=ro", uri=True)) as conn:
                    row = conn.execute(
                        "SELECT setor_ativ FROM ticker_map WHERE ticker = ?",
                        (ticker,),
                    ).fetchone()
                    if row and (row[0] or "").strip():
                        return row[0].strip()
        except Exception:
            pass
        # 2. CAD via bridge → CNPJ (the comparison skill's resolver)
        try:
            from skills.cvm.comparison.fetchers import _fetch_one_sector
            return (_fetch_one_sector(ticker) or ("", ""))[1] or ""
        except Exception:
            return ""

    @staticmethod
    def _norm_sector(s: str) -> str:
        """Accent/case-insensitive sector key ('Petróleo e Gás' ==
        'PETROLEO E GAS') — the subject's sector can come from CAD while
        the bridge rows carry the sync-time string."""
        import unicodedata
        s = unicodedata.normalize("NFKD", str(s or "")).encode(
            "ascii", "ignore").decode("ascii")
        return " ".join(s.upper().split())

    def _sector_companies(self, subject: str) -> tuple[str, list[dict[str, Any]]]:
        """Every company of the subject's sector, one class per company.

        Returns (sector_display_name, [{ticker, name, is_subject}]) —
        the subject FIRST, then the rest by liquidity. Empty peers when
        the sector can't be resolved.
        """
        sector = self._sector_of(subject)
        if not sector:
            return "", []
        key = self._norm_sector(sector)
        rows: list[dict[str, str]] = []
        try:
            import contextlib
            import sqlite3
            from data_sources.cvm._db import bridge_db_path
            db = bridge_db_path()
            if not db.exists():
                return sector, []
            with contextlib.closing(sqlite3.connect(
                    f"file:{db}?mode=ro", uri=True)) as conn:
                conn.row_factory = sqlite3.Row
                for r in conn.execute(
                        "SELECT ticker, issuing, cnpj, trading_name, "
                        "denom_comerc, setor_ativ FROM ticker_map "
                        "WHERE setor_ativ IS NOT NULL AND setor_ativ != ''"):
                    tk = (r["ticker"] or "").strip().upper()
                    if not _TICKER_RE.match(tk):
                        continue  # ISIN/odd rows never carry a clean B3 shape
                    if self._norm_sector(r["setor_ativ"]) != key:
                        continue
                    rows.append({
                        "ticker": tk,
                        "issuing": (r["issuing"] or "").strip().upper(),
                        "cnpj": re.sub(r"\D", "", r["cnpj"] or ""),
                        "name": ((r["trading_name"] or "").strip() or
                                 (r["denom_comerc"] or "").strip()),
                    })
        except Exception:
            return sector, []

        if not rows:
            return sector, []

        # ── one class per company: group by CNPJ root (first 8 digits =
        #    the legal entity; falls back to the issuing root, then the
        #    ticker's 4 first chars) and keep the MOST LIQUID ticker of
        #    each group — PETR3/PETR4 never count twice in the medians. ──
        def _group_key(r: dict[str, str]) -> str:
            if r["cnpj"] and len(r["cnpj"]) >= 8:
                return r["cnpj"][:8]
            return r["issuing"] or r["ticker"][:4]

        liquidity = self._liquidity([r["ticker"] for r in rows])
        groups: dict[str, list[dict[str, str]]] = {}
        for r in rows:
            groups.setdefault(_group_key(r), []).append(r)

        # share-class preference when cotahist has no series at all:
        # 4=PN, 3=ON, 6=PNB, 5=PNA, then units/anything, then alphabetical.
        _SUFFIX_PREF = {"4": 0, "3": 1, "6": 2, "5": 3, "11": 4}

        def _pick(members: list[dict[str, str]]) -> dict[str, str]:
            def _rank(r: dict[str, str]) -> tuple:
                suffix = r["ticker"][4:] if len(r["ticker"]) > 4 else ""
                pref = _SUFFIX_PREF.get(suffix, 9)
                return (-liquidity.get(r["ticker"], 0.0), pref, r["ticker"])
            return sorted(members, key=_rank)[0]

        picked = [_pick(m) for m in groups.values()]

        # ── cap by liquidity (the subject always stays) ──
        picked.sort(key=lambda r: (-liquidity.get(r["ticker"], 0.0),
                                   r["ticker"]))
        if not any(r["ticker"] == subject for r in picked):
            # the subject's own row lives outside the setor_ativ rows
            # (its sector came from the CAD fallback) — it still joins
            # its sector as the screened company.
            picked.insert(0, {"ticker": subject, "issuing": subject[:4],
                              "cnpj": "", "name": ""})
        if len(picked) > MAX_COMPANIES:
            others = [r for r in picked if r["ticker"] != subject][:MAX_COMPANIES - 1]
            picked = [r for r in picked if r["ticker"] == subject] + others

        # subject first, then liquidity — the table re-sorts by P/L.
        picked.sort(key=lambda r: (not (r["ticker"] == subject),
                                   -liquidity.get(r["ticker"], 0.0),
                                   r["ticker"]))
        return sector, [{"ticker": r["ticker"], "name": r["name"],
                         "is_subject": r["ticker"] == subject}
                        for r in picked]

    @staticmethod
    def _liquidity(tickers: list[str]) -> dict[str, float]:
        """Total cotahist volume per ticker over the last 365 days
        (one batch query, index-backed). Missing series → 0.0."""
        out = {tk: 0.0 for tk in tickers}
        if not tickers:
            return out
        try:
            import contextlib
            import sqlite3
            from skills.cvm.calculations.engines.price import _cotahist_db
            path = _cotahist_db()
            if not path or not path.exists():
                return out
            ph = ",".join("?" * len(tickers))
            with contextlib.closing(sqlite3.connect(
                    f"file:{path}?mode=ro", uri=True)) as conn:
                sql = (f"SELECT symbol, SUM(volume) AS v FROM cotahist "
                       f"WHERE symbol IN ({ph}) AND market_type = 10 "
                       f"AND refdate >= ? GROUP BY symbol")
                from datetime import date, timedelta
                cutoff = (date.today() - timedelta(days=365)).isoformat()
                for sym, v in conn.execute(sql, (*tickers, cutoff)).fetchall():
                    out[str(sym)] = float(v or 0.0)
        except Exception:
            pass
        return out

    # ── metrics fetch (the comparison tool's engines) ────────────────────────

    def _fetch_all(self, peers: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Fetch every sector company concurrently (input order kept)."""
        by_ticker: dict[str, dict[str, Any]] = {}
        with ThreadPoolExecutor(max_workers=_MAX_WORKERS) as executor:
            futures = {executor.submit(self._fetch_one, p["ticker"]): p["ticker"]
                       for p in peers}
            for future in as_completed(futures):
                tk = futures[future]
                try:
                    by_ticker[tk] = future.result()
                except Exception as e:  # defensive — _fetch_one never raises
                    by_ticker[tk] = {"ticker": tk, "val": {}, "fin": {},
                                     "grw": {}, "mkt": {}, "hist_monthly": [],
                                     "hist_daily": [], "error": f"fetch: {e}"}
        return [by_ticker[p["ticker"]] for p in peers]

    @staticmethod
    def _fetch_one(tk: str) -> dict[str, Any]:
        """ratios + annual summary + quarterly growth (the engines the
        comparison grid reads — imported, not duplicated). Never raises."""
        entry = {"ticker": tk, "val": {}, "fin": {}, "grw": {}, "mkt": {},
                 "hist_monthly": [], "hist_daily": [], "error": ""}
        try:
            from skills._base import engine_cache_scope
            with engine_cache_scope():
                ComparisonService._fetch_ratios(entry)
                ComparisonService._fetch_financials(entry)
                ComparisonService._fetch_growth(entry)
        except Exception as e:
            if not entry["error"]:
                entry["error"] = str(e)
        # the price series (last close + day change + the two-resolution
        # history) feeds the subject's Cotação Histórica card — and the
        # peers table's last price. One cheap local query per ticker.
        try:
            ComparisonService._fetch_series(entry)
        except Exception:
            pass
        return entry

    # ── the metric contract ──────────────────────────────────────────────────

    # (label, candidates, fmt, direction, tip)
    #   direction = "cheap" (lower is better — valuation multiples and
    #               leverage) or "above" (higher is better — quality).
    #   candidates/fmt/tip follow the comparison grid's row spec.
    _METRICS: list[tuple[str, list[tuple[str, str]], str, str, str]] = [
        ("P/L", [("val", "p_l")], "num", "cheap",
         "Preço / Lucro por Ação — quanto o mercado paga por R$ 1 de lucro."),
        ("P/VPA", [("val", "p_vpa")], "num", "cheap",
         "Preço / Valor Patrimonial por Ação."),
        ("EV/EBITDA", [("val", "ev_ebitda")], "num", "cheap",
         "Enterprise Value / EBITDA — múltiplo neutro quanto à estrutura "
         "de capital."),
        ("PSR", [("val", "psr")], "num", "cheap",
         "Preço / Receita por ação."),
        ("P/EBIT", [("val", "p_ebit")], "num", "cheap",
         "Preço / EBIT por ação."),
        ("Dívida/PL", [("val", "divida_pl")], "num", "cheap",
         "Dívida bruta / Patrimônio Líquido — menor = menos alavancado."),
        (_NET_DEBT_LABEL, [("val", "divida_liquida_ebitda")], "num", "cheap",
         "Dívida líquida / EBITDA — anos de EBITDA para quitar a dívida "
         "(negativo = caixa líquido, melhor ainda)."),
        ("ROE", [("val", "roe"), ("fin", "roe")], "pct", "above",
         "Lucro Líquido / Patrimônio Líquido — retorno sobre o capital próprio."),
        ("ROA", [("val", "roa"), ("fin", "roa")], "pct", "above",
         "Lucro Líquido / Ativo Total — retorno sobre os ativos."),
        ("Marg. EBITDA",
         [("val", "marg_ebitda"), ("fin", "marg_ebitda"), ("grw", "marg_ebitda")],
         "pct", "above", "EBITDA / Receita Líquida."),
        ("Marg. Líquida",
         [("val", "margem_liquida"), ("fin", "marg_liquida")],
         "pct", "above", "Lucro Líquido / Receita Líquida."),
        ("Div Yield", [("val", "dividend_yield")], "pct", "above",
         "Proventos dos últimos 12 meses / cotação atual."),
        ("Cresc. Receita YoY", [("grw", "receita_yoy")], "pct", "above",
         "Último trimestre vs mesmo trimestre do ano anterior."),
    ]

    @staticmethod
    def _median(values: list[Any], positive_only: bool = False) -> float | None:
        """Median over the AVAILABLE numeric values (missing never drags
        the median; positive-only for multiples — a negative P/L is a
        loss, not a bargain). None when no eligible value."""
        nums = []
        for v in values:
            if v is None or isinstance(v, bool):
                continue
            try:
                f = float(v)
            except Exception:
                continue
            if f != f:  # NaN guard
                continue
            if positive_only and f <= 0:
                continue
            nums.append(f)
        if not nums:
            return None
        return statistics.median(nums)

    @staticmethod
    def _verdict(direction: str, my: Any, med: float | None,
                 positive_only: bool) -> str:
        """cheap / expensive / above / below / na — the badge logic.

        Valuation + leverage rows (lower is better): below the median →
        cheap, above → expensive. A non-positive value on a pos-only row
        is a loss / broken multiple → 'na' (not comparable) — EXCEPT net
        debt, where negative IS the best case (caixa líquido). Quality
        rows (higher is better): above / below. Ties and missing medians
        → 'na'.
        """
        if med is None or my is None:
            return "na"
        try:
            m = float(my)
        except Exception:
            return "na"
        if m != m:  # NaN
            return "na"
        if direction == "cheap":
            if positive_only and m <= 0:
                return "na"
            if m < med:
                return "cheap"
            return "expensive" if m > med else "na"
        if m > med:
            return "above"
        return "below" if m < med else "na"

    def _vs_rows(self, subject: dict[str, Any],
                 entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """The Meu Valor × Mediana table — one row per metric."""
        rows = []
        for label, candidates, spec, direction, tip in self._METRICS:
            mine = _row_value(subject, candidates)
            vals = [_row_value(e, candidates) for e in entries]
            positive_only = (label in _POSITIVE_ONLY_LABELS or
                             (direction == "cheap" and label != _NET_DEBT_LABEL))
            med = self._median(vals, positive_only=positive_only)
            if mine is None and med is None:
                continue  # metric unknown everywhere — not a row
            delta = None
            if mine is not None and med not in (None, 0):
                try:
                    delta = float(mine) / float(med) - 1.0
                except Exception:
                    delta = None
            rows.append({
                "label": label,
                "tip": tip,
                "fmt": spec,
                "my": mine,
                "my_fmt": _fmt(mine, spec),
                "med": med,
                "med_fmt": _fmt(med, spec),
                "delta": delta,
                "delta_fmt": _fmt(delta, "pct") if delta is not None else "—",
                "verdict": self._verdict(direction, mine, med, positive_only),
                "direction": direction,
            })
        return rows

    # ── assembly ─────────────────────────────────────────────────────────────

    def _build(self, tk: str, sector: str,
               peers: list[dict[str, Any]]) -> dict[str, Any]:
        entries = self._fetch_all(peers)
        by_ticker = {e["ticker"]: e for e in entries}
        subject = by_ticker.get(tk) or {
            "ticker": tk, "val": {}, "fin": {}, "grw": {}, "mkt": {},
            "hist_monthly": [], "hist_daily": [], "error": ""}

        # the PT-BR contract — English engine internals never reach the UI
        # (the raw error is logged server-side, the UI says "parciais").
        for e in entries:
            raw = (e.get("error") or "").strip()
            if raw:
                print(f"[webui] screener {e['ticker']} partial: {raw}",
                      file=sys.stderr)
                e["error"] = "dados parciais"

        names = self._names(peers)
        segments = self._segments([p["ticker"] for p in peers])

        # KPI medians (formatted server-side — the cards are strings).
        def _median_of(label: str) -> str:
            for lbl, candidates, _spec, _d, _t in self._METRICS:
                if lbl == label:
                    vals = [_row_value(e, candidates) for e in entries]
                    med = self._median(
                        vals, positive_only=label in _POSITIVE_ONLY_LABELS)
                    return _fmt(med, _spec)
            return "—"

        kpis = [{"label": f"Mediana {label}", "value": _median_of(label)}
                for label in ("P/L", "P/VPA", "EV/EBITDA", "ROE", "Div Yield")]

        # peers table — P/L cheapest-first, the subject row marked.
        table = []
        for p in peers:
            e = by_ticker.get(p["ticker"]) or {}
            val = e.get("val") or {}
            fin = e.get("fin") or {}
            grw = e.get("grw") or {}
            mkt = e.get("mkt") or {}
            price = mkt.get("price")
            if price is None:
                price = val.get("price")
            table.append({
                "ticker": p["ticker"],
                "name": p["name"] or names.get(p["ticker"], ""),
                "is_subject": p["is_subject"],
                "price": _fmt(price, "brl_full"),
                "market_cap": _fmt(val.get("market_cap"), "brl"),
                "p_l": _fmt(val.get("p_l"), "num"),
                "p_l_raw": val.get("p_l"),
                "p_vpa": _fmt(val.get("p_vpa"), "num"),
                "ev_ebitda": _fmt(val.get("ev_ebitda"), "num"),
                "roe": _fmt(val.get("roe") or fin.get("roe"), "pct"),
                "dy": _fmt(val.get("dividend_yield"), "pct"),
                "receita": _fmt(fin.get("receita_liquida"), "brl"),
                "ebitda": _fmt(fin.get("ebitda"), "brl"),
                "marg_ebitda": _fmt(
                    val.get("marg_ebitda") or fin.get("marg_ebitda")
                    or grw.get("marg_ebitda"), "pct"),
                "cresc": _fmt(grw.get("receita_yoy"), "pct"),
                "segmento": segments.get(p["ticker"], ""),
                "partial": bool(e.get("error")),
            })

        def _pl_key(r: dict[str, Any]) -> tuple:
            v = r.get("p_l_raw")
            try:
                v = float(v)
            except Exception:
                return (2, 0.0)  # missing → last
            if v > 0:
                return (0, v)    # cheapest first
            return (1, 0.0)      # losses after the positive ones
        table.sort(key=_pl_key)

        vs_rows = self._vs_rows(subject, entries)
        mkt = subject.get("mkt") or {}
        val = subject.get("val") or {}
        price = mkt.get("price")
        if price is None:
            price = val.get("price")

        payload = {
            "status": "ok",
            "ticker": tk,
            "name": names.get(tk, ""),
            "sector": sector,
            "company_count": len(peers),
            "price": price,
            "price_date": mkt.get("price_date", ""),
            "var_day": mkt.get("var_day"),
            "kpis": kpis,
            "table": table,
            "vs_rows": vs_rows,
            "charts": self._build_charts(tk, entries, vs_rows),
            "price_hist": {
                "monthly": {tk: list(subject.get("hist_monthly") or [])},
                "daily": {tk: list(subject.get("hist_daily") or [])},
            },
            "errors": [f"{e['ticker']}: algumas fontes falharam "
                       f"(indicadores parciais — veja o log do sistema)"
                       for e in entries if e.get("error")],
        }
        if not vs_rows:
            return {
                "status": "error",
                "error": (f"nenhum indicador encontrado para o setor de "
                          f"{tk} — sincronize as fontes CVM (DFP/ITR) e "
                          "Cotações na página Sincronização"),
            }
        return payload

    # ── names + segments ─────────────────────────────────────────────────────

    @staticmethod
    def _names(peers: list[dict[str, Any]]) -> dict[str, str]:
        """Trading names from the bridge DB (one batch query)."""
        tks = [p["ticker"] for p in peers]
        out = {tk: "" for tk in tks}
        try:
            import contextlib
            import sqlite3
            from data_sources.cvm._db import bridge_db_path
            db = bridge_db_path()
            if not db.exists():
                return out
            ph = ",".join("?" * len(tks))
            with contextlib.closing(sqlite3.connect(
                    f"file:{db}?mode=ro", uri=True)) as conn:
                rows = conn.execute(
                    f"SELECT ticker, trading_name FROM ticker_map "
                    f"WHERE ticker IN ({ph})", tks).fetchall()
            for r in rows:
                out[r[0]] = (r[1] or "").strip()
        except Exception:
            pass
        return out

    @staticmethod
    def _segments(tks: list[str]) -> dict[str, str]:
        """B3 listing segment per ticker ('Novo Mercado', 'Nível 2'…).

        B3 dividends company_info first (one batch query), FCA's
        fca_valor_mobiliario filling the gaps (latest Data_Referencia
        per ticker).
        """
        out: dict[str, str] = {tk: "" for tk in tks}
        try:
            import contextlib
            from data_sources.b3.dividends.catalog import connect as _b3div
            ph = ",".join("?" * len(tks))
            with contextlib.closing(_b3div(read_only=True)) as conn:
                rows = conn.execute(
                    f"SELECT ticker, segment FROM company_info "
                    f"WHERE ticker IN ({ph})", tks).fetchall()
            for r in rows:
                if r[1]:
                    out[r[0]] = r[1]
        except Exception:
            pass
        missing = [tk for tk, v in out.items() if not v]
        if not missing:
            return out
        try:
            import contextlib
            import sqlite3
            from data_sources.cvm._db import fca_db_path
            db = fca_db_path()
            if not db.exists():
                return out
            ph = ",".join("?" * len(missing))
            with contextlib.closing(sqlite3.connect(
                    f"file:{db}?mode=ro", uri=True)) as conn:
                conn.row_factory = sqlite3.Row
                rows = conn.execute(
                    f"SELECT Codigo_Negociacao AS tk, Segmento AS seg "
                    f"FROM fca_valor_mobiliario "
                    f"WHERE UPPER(Codigo_Negociacao) IN ({ph}) "
                    f"ORDER BY Data_Referencia ASC",
                    [m.upper() for m in missing]).fetchall()
            for r in rows:  # ascending dates → the LAST write wins
                if r["seg"]:
                    out[(r["tk"] or "").upper()] = r["seg"]
        except Exception:
            pass
        return out

    # ── charts ───────────────────────────────────────────────────────────────

    def _build_charts(self, subject: str, entries: list[dict[str, Any]],
                      vs_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Server-built Chart.js configs (renderValChart draws as-is).

        1. pl_setor — every company's P/L, cheapest-first bars, the
           subject in amber, the sector median as a dashed line.
        2. roe_setor — the same for ROE (descending — higher is better).
        3. vs_mediana — my value (teal) vs the sector median (amber)
           grouped bars per metric.
        """
        teal, amber, grey = "#0d9488", "#f59e0b", "#64748b"
        charts: list[dict[str, Any]] = []

        def _position_chart(chart_id: str, title: str, desc: str,
                            candidates: list[tuple[str, str]],
                            scale: float, descending: bool,
                            positive_only: bool, y_title: str) -> None:
            data: list[tuple[str, float]] = []
            for e in entries:
                v = _row_value(e, candidates)
                if v is None:
                    continue
                try:
                    f = round(float(v) * scale, 2)
                except Exception:
                    continue
                if positive_only and f <= 0:
                    continue
                data.append((e["ticker"], f))
            if len(data) < 2:
                return
            data.sort(key=lambda d: d[1], reverse=descending)
            med = self._median([d[1] for d in data])
            labels = [d[0] for d in data]
            datasets: list[dict[str, Any]] = [{
                "label": subject,
                "data": [d[1] for d in data],
                "backgroundColor": [amber if t == subject else teal + "cc"
                                    for t in labels],
                "borderColor": teal,
                "borderWidth": 1,
            }]
            if med is not None:
                datasets.append({
                    "type": "line",
                    "label": "Mediana do setor",
                    "data": [round(med, 2)] * len(labels),
                    "borderColor": grey,
                    "borderDash": [6, 4],
                    "pointRadius": 0,
                    "fill": False,
                })
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

        _position_chart(
            "pl_setor", "P/L no Setor",
            "Cada empresa do setor pelo P/L, da mais barata à mais cara "
            "(empresas com prejuízo ficam de fora) — a empresa analisada "
            "em destaque e a mediana do setor como linha tracejada.",
            [("val", "p_l")], 1.0, False, True, "múltiplos (×)")
        _position_chart(
            "roe_setor", "ROE no Setor",
            "Cada empresa do setor pelo ROE, da maior à menor — a empresa "
            "analisada em destaque e a mediana do setor como linha tracejada.",
            [("val", "roe"), ("fin", "roe")], 100.0, True, False, "%")

        # my value vs the median — curated metric subset (the full set
        # lives in the table above), scaled like the comparison bars.
        bar_defs = [
            ("P/L", "num", 1.0), ("P/VPA", "num", 1.0),
            ("EV/EBITDA", "num", 1.0),
            ("ROE", "pct", 100.0), ("Div Yield", "pct", 100.0),
            ("Marg. Líquida", "pct", 100.0),
        ]
        rows_by_label = {r["label"]: r for r in vs_rows}
        labels: list[str] = []
        mine: list[Any] = []
        meds: list[Any] = []
        for label, spec, scale in bar_defs:
            r = rows_by_label.get(label)
            if not r:
                continue
            labels.append(label)
            for src, bucket, is_multiple in ((r["my"], mine, spec == "num"),
                                             (r["med"], meds, spec == "num")):
                if src is None:
                    bucket.append(None)
                    continue
                try:
                    v = round(float(src) * scale, 2)
                except Exception:
                    v = None
                # a non-positive multiple is a loss — chart nothing (the
                # table carries it; the v1.27 bar rule).
                if is_multiple and (v is None or v <= 0):
                    v = None
                bucket.append(v)
        if labels:
            charts.append({
                "id": "vs_mediana",
                "title": "Meu Valor × Mediana do Setor",
                "desc": ("Barras agrupadas — a empresa analisada (teal) "
                         "contra a mediana do setor (laranja) por métrica. "
                         "Métricas em % estão escaladas; múltiplos "
                         "negativos ficam de fora."),
                "cd": {
                    "type": "bar",
                    "data": {"labels": labels, "datasets": [
                        {"label": subject, "data": mine,
                         "backgroundColor": teal + "cc",
                         "borderColor": teal, "borderWidth": 1},
                        {"label": "Mediana do setor", "data": meds,
                         "backgroundColor": amber + "cc",
                         "borderColor": amber, "borderWidth": 1},
                    ]},
                    "options": {"scales": {
                        "y": {"beginAtZero": True},
                    }},
                },
            })
        return charts
