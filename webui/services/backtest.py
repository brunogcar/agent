"""webui/services/backtest.py — the interactive Backtest tab data service.

[v1.25] The company page's Backtest tab — the static
``PETR4_backtest_dashboard.html`` (emitted by skills/cvm/backtest's
dashboard mode) reborn as an INTERACTIVE simulator. The static report
ran ONE fixed scenario per HTML file: strategy value_pe, thresholds
hard-coded in skills/cvm/backtest/helpers.py (P/L < 5, max holding 252),
no costs, no stop-loss, no position sizing. The user's v1.25 ask: "as
it's a static report there was no way to set the parameters, have
multiple options, different scenarios — now as an interactive dashboard
you can improve it a lot."

What ships here (one service, two endpoints):

  meta(ticker) → the FORM catalog: every strategy's parametrizable
      entry/exit conditions (key, label, default, min/max/step — the
      client renders the threshold inputs from this), the ticker's
      available price range (first/last session — the period presets
      clamp to it) and the engine defaults.

  run(ticker, params) → the parametrized engine:
      - 8 strategies: the static's 6 fundamental ones (value_pe,
        value_pvpa, quality_roe, quality_roic, income_dy, composite —
        same metrics, same *_history signal precompute, but with
        EDITABLE thresholds) + ma_cross (SMA fast × slow — the
        technical option that needs no DFP/ITR data) + buy_hold (the
        benchmark itself, runnable as a scenario row).
      - Engine params: período, capital inicial, % do capital por
        entrada, dias máximos de posição (0 = ilimitado), stop-loss %,
        take-profit % (both checked on the daily close — honest note in
        the form), corretagem fixa R$ por operação (buy and sell each
        pay), and exit_on_signal (sair quando o sinal reverter — the
        static exited ONLY by max holding / end of period).
      - Metrics: the static's set (CAGR, retorno total, max drawdown,
        Sharpe rf=0, win rate, trades, buy & hold, alpha) + profit
        factor, retorno médio por trade and tempo médio de posição.
      - Curves: equity (estratégia) × buy & hold on ONE chart,
        drawdown (underwater) and price-with-trade-markers side by
        side, trade log table.

Engine honesty (documented in the form footer + tooltips): decisions
are taken on the CLOSE of each session (no intraday fills), fundamental
signals are step functions (most recent *_history value ≤ the date —
the same convention as the static engine), proventos are NOT
reinvested, and stop/take are verified on the daily close.

Data quality hardening the static engine lacked: the price series is
fetched with ``bdi_code = 2`` (lote padrão) and ONE row per session
(the highest-volume row wins). COTAHIST carries DIR/REC subscription
rights and fractional-market rows under the same market_type=10 the
static engine filtered on — a rights row (close R$ 0,50) in the middle
of the equity series wrecks every metric downstream. Fallback: when a
ticker has NO bdi=2 rows at all, the old market_type-only filter runs
(then deduped) so exotic papers still backtest.

The skill's static modes are untouched (they keep their fixed-threshold
contract); this service shares the DATA layer — price via the same
cotahist.db, fundamental signals via
skills.cvm.backtest.helpers._precompute_signals — and owns the
parametrized loop the interactive tab needs.
"""
from __future__ import annotations

import sqlite3
import time
from datetime import datetime, timedelta
from typing import Any

# ── strategy catalog ────────────────────────────────────────────────────────
# Every condition: {key, metric, op, default, label, min, max, step, scale}.
#   metric — the signal key in skills.cvm.backtest.helpers._SIGNAL_METRIC_KEY
#   op     — "<" (value must be below threshold) | ">" (above)
#   scale  — 1.0 for ratios (P/L, P/VPA), 0.01 for %-entered thresholds
#            (ROE 20% in the form → 0.20 fraction to compare, the same
#            fraction units the engines emit)
# The static dashboard's hard-coded numbers live on as the DEFAULTS.

def _cond(key: str, metric: str, op: str, default: float, label: str,
          lo: float, hi: float, step: float, scale: float = 1.0,
          suffix: str = "") -> dict[str, Any]:
    return {"key": key, "metric": metric, "op": op, "default": default,
            "label": label, "min": lo, "max": hi, "step": step,
            "scale": scale, "suffix": suffix}


STRATEGY_SPECS: dict[str, dict[str, Any]] = {
    "value_pe": {
        "label": "Valor — P/L baixo",
        "description": "Compra quando o P/L fica abaixo do limite (valuation barata).",
        "kind": "fundamental",
        "entry": [_cond("pe_max", "pe", "<", 5.0, "P/L máximo de entrada", 0.5, 100, 0.5)],
        "exit": [_cond("pe_exit", "pe", ">", 10.0, "Sair se P/L acima de", 1.0, 200, 0.5)],
        "max_holding_default": 252,
    },
    "value_pvpa": {
        "label": "Valor — P/VPA abaixo do book",
        "description": "Compra quando o P/VPA fica abaixo do limite (negociando abaixo do patrimônio).",
        "kind": "fundamental",
        "entry": [_cond("pvpa_max", "pvpa", "<", 1.0, "P/VPA máximo de entrada", 0.1, 20, 0.1)],
        "exit": [_cond("pvpa_exit", "pvpa", ">", 1.5, "Sair se P/VPA acima de", 0.2, 40, 0.1)],
        "max_holding_default": 252,
    },
    "quality_roe": {
        "label": "Qualidade — ROE alto",
        "description": "Compra quando o ROE fica acima do limite (retorno sobre patrimônio).",
        "kind": "fundamental",
        "entry": [_cond("roe_min", "roe", ">", 20.0, "ROE mínimo de entrada (%)", 1.0, 100, 1.0, 0.01)],
        "exit": [_cond("roe_exit", "roe", "<", 12.0, "Sair se ROE abaixo de (%)", 0.0, 100, 1.0, 0.01)],
        "max_holding_default": 252,
    },
    "quality_roic": {
        "label": "Qualidade — ROIC alto",
        "description": "Compra quando o ROIC fica acima do limite (retorno sobre capital investido).",
        "kind": "fundamental",
        "entry": [_cond("roic_min", "roic", ">", 15.0, "ROIC mínimo de entrada (%)", 1.0, 100, 1.0, 0.01)],
        "exit": [_cond("roic_exit", "roic", "<", 10.0, "Sair se ROIC abaixo de (%)", 0.0, 100, 1.0, 0.01)],
        "max_holding_default": 252,
    },
    "income_dy": {
        "label": "Renda — Dividend Yield alto",
        "description": "Compra quando o Dividend Yield fica acima do limite.",
        "kind": "fundamental",
        "entry": [_cond("dy_min", "dy", ">", 6.0, "Div. Yield mínimo de entrada (%)", 0.5, 30, 0.5, 0.01)],
        "exit": [_cond("dy_exit", "dy", "<", 3.0, "Sair se Div. Yield abaixo de (%)", 0.0, 30, 0.5, 0.01)],
        "max_holding_default": 252,
    },
    "composite": {
        "label": "Composto — barata E rentável",
        "description": "Compra quando P/L < limite E ROE > mínimo (valor + qualidade juntos).",
        "kind": "fundamental",
        "entry": [
            _cond("pe_max", "pe", "<", 8.0, "P/L máximo", 0.5, 100, 0.5),
            _cond("roe_min", "roe", ">", 15.0, "ROE mínimo (%)", 1.0, 100, 1.0, 0.01),
        ],
        "exit": [
            _cond("pe_exit", "pe", ">", 12.0, "Sair se P/L acima de", 1.0, 200, 0.5),
            _cond("roe_exit", "roe", "<", 10.0, "Sair se ROE abaixo de (%)", 0.0, 100, 1.0, 0.01),
        ],
        "max_holding_default": 252,
    },
    "ma_cross": {
        "label": "Técnica — Cruzamento de médias",
        "description": "Compra quando a média rápida cruza acima da lenta; sai quando cruza abaixo. Não depende de dados fundamentalistas.",
        "kind": "technical",
        "entry": [_cond("sma_fast", "", "", 50.0, "Média rápida (dias)", 5, 250, 5),
                  _cond("sma_slow", "", "", 200.0, "Média lenta (dias)", 20, 500, 10)],
        "exit": [],  # inherent: fast < slow
        "max_holding_default": 0,   # ilimitado — o cruzamento é quem decide
    },
    "buy_hold": {
        "label": "Buy & Hold (referência)",
        "description": "Compra no primeiro pregão e mantém até o fim — a referência que as estratégias tentam bater.",
        "kind": "buy_hold",
        "entry": [],
        "exit": [],
        "max_holding_default": 0,
    },
}

# Engine-level defaults (the form's initial values).
DEFAULTS = {
    "initial_capital": 10000.0,
    "position_pct": 100.0,
    "max_holding_days": 252,
    "stop_loss_pct": 0.0,
    "take_profit_pct": 0.0,
    "fee_brl": 0.0,
    "exit_on_signal": False,
}

# ── engine-level bounds (validation) ────────────────────────────────────────
_BOUNDS = {
    "initial_capital": (100.0, 1_000_000_000.0),
    "position_pct": (5.0, 100.0),
    "max_holding_days": (0, 2520),
    "stop_loss_pct": (0.0, 95.0),
    "take_profit_pct": (0.0, 1000.0),
    "fee_brl": (0.0, 10_000.0),
}
_MAX_YEARS = 30          # cotahist window cap (the "Tudo" preset)
_MAX_CURVE_POINTS = 1200  # payload downsample target (charts stay smooth)
_PRICE_TTL = 60.0         # the PriceService OHLCV-cache convention


def _log_err(where: str, e: Exception) -> None:
    import sys
    import traceback
    print(f"[webui] backtest {where} failed: {e}\n{traceback.format_exc()}",
          file=sys.stderr)


class BacktestService:
    """meta() + run() — the interactive Backtest tab."""

    def __init__(self) -> None:
        # (ticker, date_from, date_to) → (monotonic_time, [(date, close)])
        self._price_cache: dict[tuple[str, str, str], tuple[float, list[tuple[str, float]]]] = {}

    # ── clean price fetch ───────────────────────────────────────────────────

    def _cotahist_path(self):
        from skills.cvm.calculations.engines.price import _cotahist_db
        return _cotahist_db()

    def _clean_prices(self, ticker: str, date_from: str, date_to: str
                      ) -> list[tuple[str, float]]:
        """COTAHIST closes, ONE row per session, rights/fractional rows out.

        bdi_code=2 (lote padrão) first; the highest-volume row wins when
        a session still yields several (defensive — the sync pipeline can
        emit ISIN-variant duplicates). Tickers with no bdi=2 rows fall
        back to the plain market_type=10 filter, then deduped.
        """
        key = (ticker.upper(), date_from, date_to)
        hit = self._price_cache.get(key)
        if hit and (time.monotonic() - hit[0]) < _PRICE_TTL:
            return hit[1]
        rows: list[tuple[str, float]] = []
        try:
            path = self._cotahist_path()
            if path.exists():
                conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
                try:
                    for bdi_filter in ("AND bdi_code = 2", ""):
                        rows = conn.execute(
                            "SELECT refdate, close, volume FROM cotahist "
                            "WHERE symbol = ? AND refdate >= ? AND refdate <= ? "
                            "AND market_type = 10 AND close IS NOT NULL AND close > 0 "
                            f"{bdi_filter} ORDER BY refdate ASC",
                            (ticker.upper(), date_from, date_to),
                        ).fetchall()
                        if rows:
                            break
                finally:
                    conn.close()
        except Exception as e:  # noqa: BLE001 — degrade to empty, meta reports it
            _log_err("price fetch", e)
            rows = []
        # one row per date — highest volume wins
        best: dict[str, tuple[float, float]] = {}
        for refdate, close, volume in rows:
            vol = float(volume or 0.0)
            prev = best.get(refdate)
            if prev is None or vol > prev[0]:
                best[refdate] = (vol, float(close))
        series = [(d, v[1]) for d, v in sorted(best.items())]
        self._price_cache[key] = (time.monotonic(), series)
        return series

    # ── meta: the form catalog ─────────────────────────────────────────────

    def meta(self, ticker: str) -> dict[str, Any]:
        """Everything the form needs before the first run."""
        t = ticker.upper()
        out: dict[str, Any] = {"ticker": t, "status": "ok",
                               "strategies": [], "defaults": dict(DEFAULTS),
                               "range": None, "presets": []}
        try:
            path = self._cotahist_path()
            first = last = None
            if path.exists():
                conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
                try:
                    row = conn.execute(
                        "SELECT MIN(refdate), MAX(refdate) FROM cotahist "
                        "WHERE symbol = ? AND market_type = 10 "
                        "AND close IS NOT NULL AND close > 0",
                        (t,),
                    ).fetchone()
                    first, last = row[0], row[1]
                finally:
                    conn.close()
            if not first or not last:
                return {"ticker": t, "_error":
                        f"Sem histórico de preços para {t} — sincronize a fonte "
                        "cotahist (B3) antes de rodar um backtest."}
            out["range"] = {"first": first, "last": last}
            # period presets (clamped by the ticker's own range)
            today = datetime.now().date()
            presets = []
            for years, label in ((1, "1A"), (3, "3A"), (5, "5A"), (10, "10A")):
                start = max((today - timedelta(days=int(years * 365.25))).isoformat(), first)
                presets.append({"label": label, "start": start, "end": last})
            presets.append({"label": "Máximo", "start": first, "end": last})
            out["presets"] = presets
            # default period = 3A (the static engine's default), clamped
            d3 = (today - timedelta(days=3 * 365)).isoformat()
            out["defaults"]["start_date"] = max(d3, first)
            out["defaults"]["end_date"] = last
            for name, spec in STRATEGY_SPECS.items():
                out["strategies"].append({
                    "name": name,
                    "label": spec["label"],
                    "description": spec["description"],
                    "kind": spec["kind"],
                    "entry": spec["entry"],
                    "exit": spec["exit"],
                    "defaults": {"max_holding_days": spec["max_holding_default"],
                                 "exit_on_signal": name == "ma_cross"},
                })
            return out
        except Exception as e:  # noqa: BLE001
            _log_err("meta", e)
            return {"ticker": t, "_error":
                    "Falha ao montar o catálogo do backtest (o erro foi "
                    "registrado no log do servidor)."}

    # ── param normalization + validation ───────────────────────────────────

    def _normalize(self, ticker: str, raw: dict[str, Any]
                   ) -> tuple[dict[str, Any] | None, str]:
        """raw body → normalized engine params, or (None, PT-BR error)."""
        spec = STRATEGY_SPECS.get(str(raw.get("strategy", "")).strip().lower())
        if not spec:
            return None, ("Estratégia inválida — use uma de: "
                          + ", ".join(STRATEGY_SPECS) + ".")
        p: dict[str, Any] = {"strategy": spec, "strategy_name":
                             str(raw.get("strategy")).strip().lower()}

        def _num(field: str, default: float, lo: float, hi: float) -> float | None:
            v = raw.get(field, default)
            try:
                v = float(v)
            except (TypeError, ValueError):
                return None
            return v if lo <= v <= hi else None

        for field, (lo, hi) in _BOUNDS.items():
            v = _num(field, DEFAULTS[field], lo, hi)
            if v is None:
                return None, (f"Parâmetro '{field}' fora do intervalo "
                              f"permitido ({lo} a {hi}).")
            p[field] = v
        p["max_holding_days"] = int(p["max_holding_days"])

        # dates
        def _date(field: str) -> str | None:
            v = str(raw.get(field, "")).strip()
            if not v:
                return None
            try:
                datetime.strptime(v, "%Y-%m-%d")
                return v
            except ValueError:
                return None

        rng = self._price_range(ticker)
        start = _date("start_date")
        end = _date("end_date")
        # absent dates → the 3A default (the static engine's convention);
        # malformed dates → the PT-BR error
        if start is None and "start_date" not in raw:
            start = (datetime.now() - timedelta(days=3 * 365)).date().isoformat()
        if end is None and "end_date" not in raw:
            end = datetime.now().date().isoformat()
        if start is None or end is None:
            return None, "Período inválido — use datas no formato aaaa-mm-dd."
        if start > end:
            return None, "A data inicial precisa ser anterior à final."
        if rng:
            start = max(start, rng[0])
            end = min(end, rng[1])
            if start > end:
                return None, ("O período não cruza o histórico disponível de "
                              f"{ticker} ({rng[0]} a {rng[1]}).")
        span_days = (datetime.strptime(end, "%Y-%m-%d")
                     - datetime.strptime(start, "%Y-%m-%d")).days
        if span_days > _MAX_YEARS * 366:
            return None, (f"Período máximo de {_MAX_YEARS} anos — reduza a janela.")
        p["start_date"], p["end_date"] = start, end

        # strategy thresholds — accept BOTH shapes: nested
        # {"thresholds": {"pe_max": 6}} (the client's POST body) and flat
        # top-level keys ({"pe_max": 6} — friendlier for API callers).
        # Nested wins on key collision.
        raw_th = raw.get("thresholds")
        raw_th = raw_th if isinstance(raw_th, dict) else {}
        p["thresholds"] = {}
        for cond in spec["entry"] + spec["exit"]:
            key = cond["key"]
            src = raw_th[key] if key in raw_th else raw.get(key, cond["default"])
            try:
                v = float(src)
            except (TypeError, ValueError):
                v = None
            if v is None or not (cond["min"] <= v <= cond["max"]):
                return None, (f"'{cond['label']}' fora do intervalo "
                              f"({cond['min']} a {cond['max']}).")
            p["thresholds"][key] = int(v) if key in ("sma_fast", "sma_slow") else v
        if spec["kind"] == "technical":
            fast = p["thresholds"].get("sma_fast", 50)
            slow = p["thresholds"].get("sma_slow", 200)
            if fast >= slow:
                return None, ("A média rápida precisa ser menor que a lenta "
                              "(ex.: 50 × 200).")
        p["exit_on_signal"] = bool(raw.get("exit_on_signal",
                                           spec["kind"] == "ma_cross"))
        return p, ""

    def _price_range(self, ticker: str) -> tuple[str, str] | None:
        """First/last session for the ticker (validation clamps)."""
        try:
            path = self._cotahist_path()
            if not path.exists():
                return None
            conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
            try:
                row = conn.execute(
                    "SELECT MIN(refdate), MAX(refdate) FROM cotahist "
                    "WHERE symbol = ? AND market_type = 10 "
                    "AND close IS NOT NULL AND close > 0",
                    (ticker.upper(),),
                ).fetchone()
                return (row[0], row[1]) if row and row[0] else None
            finally:
                conn.close()
        except Exception:  # noqa: BLE001
            return None

    # ── the engine ─────────────────────────────────────────────────────────

    def run(self, ticker: str, raw: dict[str, Any]) -> dict[str, Any]:
        """Run ONE parametrized scenario → the full interactive payload."""
        t = ticker.upper()
        params, err = self._normalize(t, raw)
        if params is None:
            return {"ticker": t, "_error": err}
        try:
            return self._run_engine(t, params)
        except Exception as e:  # noqa: BLE001 — never a plain-text 500
            _log_err("run", e)
            return {"ticker": t, "_error":
                    "Falha ao rodar o backtest (o erro foi registrado no "
                    "log do servidor)."}

    # signal helpers ------------------------------------------------------

    @staticmethod
    def _signal_ok(conds: list[dict[str, Any]], date: str,
                   signal_data: dict[str, dict[str, float]],
                   thresholds: dict[str, float],
                   mode: str) -> bool:
        """Evaluate a condition list at `date`.

        mode 'all' → every condition must hold (entries; composite exits
        use 'any' — reverting when EITHER leg breaks reads righter than
        demanding both).
        """
        from skills.cvm.backtest.helpers import _lookup_signal
        results = []
        for cond in conds:
            val = _lookup_signal(signal_data, cond["metric"], date)
            th = thresholds[cond["key"]] * cond.get("scale", 1.0)
            ok = val is not None and (val < th if cond["op"] == "<" else val > th)
            results.append(ok)
        if not results:
            return False
        return all(results) if mode == "all" else any(results)

    # the loop --------------------------------------------------------------

    def _run_engine(self, ticker: str, p: dict[str, Any]) -> dict[str, Any]:
        spec = p["strategy"]
        start, end = p["start_date"], p["end_date"]
        prices = self._clean_prices(ticker, start, end)
        if len(prices) < 2:
            return {"ticker": ticker, "_error":
                    f"Sem preços suficientes para {ticker} entre {start} e "
                    f"{end} — ajuste o período ou sincronize a fonte cotahist."}

        warnings: list[str] = []
        signal_data: dict[str, dict[str, float]] = {}
        smas: dict[str, list[float | None]] = {}
        missing: list[str] = []

        if spec["kind"] == "fundamental":
            from skills._base import engine_cache_scope
            from skills.cvm.backtest.helpers import _precompute_signals
            metric_names = sorted({c["metric"] for c in spec["entry"] + spec["exit"]
                                   if c["metric"]})
            with engine_cache_scope():
                signal_data = _precompute_signals(ticker, start, end, metric_names)
            missing = [m for m in metric_names if not signal_data.get(m)]
            if missing:
                pretty = {"pe": "P/L", "pvpa": "P/VPA", "roe": "ROE",
                          "roic": "ROIC", "dy": "Dividend Yield"}
                warnings.append(
                    "Sem histórico de " + " ou ".join(pretty.get(m, m) for m in missing)
                    + f" para {ticker} no período — sincronize a fonte CVM "
                    "(DFP/ITR) ou use a estratégia de cruzamento de médias. "
                    "Nenhum sinal dispara sem esses dados.")

        if spec["kind"] == "technical":
            fast_w = p["thresholds"]["sma_fast"]
            slow_w = p["thresholds"]["sma_slow"]
            smas = {"fast": _sma_series([c for _, c in prices], fast_w),
                    "slow": _sma_series([c for _, c in prices], slow_w)}

        # ── the backtest loop ──
        trades: list[dict[str, Any]] = []
        labels: list[str] = []
        equity_pts: list[float] = []
        cash = p["initial_capital"]
        position: dict[str, Any] | None = None
        peak = p["initial_capital"]
        max_dd = 0.0
        daily_returns: list[float] = []
        fee = p["fee_brl"]
        entry_marks: list[dict[str, Any]] = []
        exit_marks: list[dict[str, Any]] = []

        def _enter(i: int, date: str, price: float) -> None:
            nonlocal cash, position
            budget = cash * p["position_pct"] / 100.0
            shares = int(budget / price) if price > 0 else 0
            while shares > 0 and shares * price + fee > cash:
                shares -= 1  # the fee still has to fit inside the cash
            if shares <= 0:
                return
            cash -= shares * price + fee
            position = {"entry_date": date, "entry_price": price, "shares": shares,
                        "entry_index": i}

        def _exit(i: int, date: str, price: float, reason: str) -> None:
            nonlocal cash, position
            pos = position
            proceeds = pos["shares"] * price - fee
            pnl = proceeds - pos["shares"] * pos["entry_price"]
            cash += proceeds
            trades.append({
                "entry_date": pos["entry_date"],
                "entry_price": round(pos["entry_price"], 2),
                "exit_date": date,
                "exit_price": round(price, 2),
                "shares": pos["shares"],
                "pnl": round(pnl, 2),
                "return_pct": round((price / pos["entry_price"] - 1) * 100, 2),
                "holding_days": i - pos["entry_index"],
                "exit_reason": reason,
            })
            exit_marks.append({"date": date, "price": price, "reason": reason})
            position = None

        for i, (date, price) in enumerate(prices):
            # exits first
            if position is not None:
                reason = ""
                if spec["kind"] == "buy_hold":
                    pass  # never exits before the end
                else:
                    if (p["stop_loss_pct"] > 0
                            and price <= position["entry_price"]
                            * (1 - p["stop_loss_pct"] / 100.0)):
                        reason = "stop_loss"
                    elif (p["take_profit_pct"] > 0
                            and price >= position["entry_price"]
                            * (1 + p["take_profit_pct"] / 100.0)):
                        reason = "take_profit"
                    elif (spec["kind"] == "technical"
                          and smas["fast"][i] is not None
                          and smas["slow"][i] is not None
                          and smas["fast"][i] < smas["slow"][i]):
                        reason = "signal"
                    elif (p["exit_on_signal"] and spec["kind"] == "fundamental"
                          and spec["exit"]
                          and self._signal_ok(spec["exit"], date, signal_data,
                                              p["thresholds"], "any")):
                        reason = "signal"
                    elif (p["max_holding_days"] > 0
                          and i - position["entry_index"] >= p["max_holding_days"]):
                        reason = "max_holding"
                if reason:
                    _exit(i, date, price, reason)

            # entries
            if position is None:
                if spec["kind"] == "buy_hold":
                    _enter(i, date, price)
                    if position:
                        entry_marks.append({"date": date, "price": price})
                elif spec["kind"] == "technical":
                    if (smas["fast"][i] is not None and smas["slow"][i] is not None
                            and smas["fast"][i] > smas["slow"][i]):
                        _enter(i, date, price)
                        if position:
                            entry_marks.append({"date": date, "price": price})
                else:
                    if self._signal_ok(spec["entry"], date, signal_data,
                                       p["thresholds"], "all"):
                        _enter(i, date, price)
                        if position:
                            entry_marks.append({"date": date, "price": price})

            # mark-to-market equity
            equity = cash + (position["shares"] * price if position else 0.0)
            labels.append(date)
            equity_pts.append(equity)
            if equity > peak:
                peak = equity
            dd = (peak - equity) / peak if peak > 0 else 0.0
            if dd > max_dd:
                max_dd = dd
            # daily return — only while yesterday's equity is a real base
            # (> 1% of the initial capital). Below that the account is
            # destroyed and near-zero fractions explode the ratio (a
            # R$ 2,50 → R$ 10,00 bounce would fake +300% "daily returns"
            # and a positive Sharpe on a wiped account).
            if len(equity_pts) >= 2 and equity_pts[-2] > p["initial_capital"] * 0.01:
                daily_returns.append(equity / equity_pts[-2] - 1)

        if position is not None:  # close whatever is left at the last bar
            _exit(len(prices) - 1, prices[-1][0], prices[-1][1], "end_of_period")

        # ── metrics ──
        initial = p["initial_capital"]
        final_equity = cash
        total_return = (final_equity / initial - 1) * 100 if initial > 0 else 0.0
        days = (datetime.strptime(end, "%Y-%m-%d")
                - datetime.strptime(start, "%Y-%m-%d")).days
        years = days / 365.25 if days > 0 else 1.0
        ratio = final_equity / initial if initial > 0 else 0.0
        if ratio > 0 and years > 0:
            cagr = (ratio ** (1 / years) - 1) * 100
        else:
            cagr = -100.0
        if daily_returns:
            avg_r = sum(daily_returns) / len(daily_returns)
            std_r = (sum((r - avg_r) ** 2 for r in daily_returns)
                     / len(daily_returns)) ** 0.5
            sharpe = (avg_r / std_r * (252 ** 0.5)) if std_r > 0 else 0.0
        else:
            sharpe = 0.0
        wins = [t for t in trades if t["pnl"] > 0]
        losses = [t for t in trades if t["pnl"] <= 0]
        win_rate = (len(wins) / len(trades) * 100) if trades else 0.0
        gross_win = sum(t["pnl"] for t in wins)
        gross_loss = abs(sum(t["pnl"] for t in losses))
        profit_factor = None
        if gross_loss > 0:
            profit_factor = round(gross_win / gross_loss, 2)
        elif gross_win > 0:
            profit_factor = None  # no losses — the client shows "∞"
        bh_return = (prices[-1][1] / prices[0][1] - 1) * 100

        # buy & hold curve over the same window
        bh0 = initial / prices[0][1]
        buy_hold_pts = [round(bh0 * c, 2) for _, c in prices]
        # underwater = NEGATIVE percentages (0 = at the peak, −98 = 98%
        # below it) — the classic below-zero form the static dashboard
        # drew, so the filled area hangs under the axis instead of
        # reading like a positive mountain.
        drawdown_pts = _drawdown_series(equity_pts)

        # downsample the curves for the payload (charts, not ledgers)
        keep = _downsample_indices(len(prices), _MAX_CURVE_POINTS)
        d_labels = [labels[j] for j in keep]
        d_equity = [round(equity_pts[j], 2) for j in keep]
        d_bh = [buy_hold_pts[j] for j in keep]
        d_dd = [drawdown_pts[j] for j in keep]
        d_price = [round(prices[j][1], 2) for j in keep]

        if not trades and not (spec["kind"] == "fundamental" and missing):
            warnings.append(
                "Nenhuma entrada disparou no período — a condição de entrada "
                "nunca foi satisfeita. Ajuste os limiares ou amplie o período.")

        return {
            "ticker": ticker,
            "status": "ok",
            "strategy": p["strategy_name"],
            "label": spec["label"],
            "description": spec["description"],
            "params": {
                "strategy": p["strategy_name"],
                "start_date": start, "end_date": end,
                "initial_capital": initial,
                "position_pct": p["position_pct"],
                "max_holding_days": p["max_holding_days"],
                "stop_loss_pct": p["stop_loss_pct"],
                "take_profit_pct": p["take_profit_pct"],
                "fee_brl": fee,
                "exit_on_signal": p["exit_on_signal"],
                "thresholds": p["thresholds"],
            },
            "period": {"start": start, "end": end,
                       "years": round(years, 2), "bars": len(prices)},
            "performance": {
                "total_return_pct": round(total_return, 2),
                "cagr_pct": round(cagr, 2),
                "max_drawdown_pct": round(max_dd * 100, 2),
                "sharpe_ratio": round(sharpe, 2),
                "win_rate_pct": round(win_rate, 1),
                "num_trades": len(trades),
                "buy_hold_return_pct": round(bh_return, 2),
                "alpha_vs_buy_hold": round(total_return - bh_return, 2),
                "profit_factor": profit_factor,
                "avg_trade_pct": round(sum(t["return_pct"] for t in trades)
                                       / len(trades), 2) if trades else None,
                "avg_holding_days": round(sum(t["holding_days"] for t in trades)
                                          / len(trades), 1) if trades else None,
                "final_equity": round(final_equity, 2),
                "initial_capital": round(initial, 2),
            },
            "trades": trades,
            "curves": {
                "labels": d_labels,
                "equity": d_equity,
                "buy_hold": d_bh,
                "drawdown": d_dd,
                "price": d_price,
                "entries": entry_marks,
                "exits": exit_marks,
            },
            "warnings": warnings,
        }


# ── pure helpers (module-level: directly testable) ──────────────────────────

def _sma_series(closes: list[float], window: int) -> list[float | None]:
    """Trailing SMA — None until the window fills (no half-window lies)."""
    out: list[float | None] = []
    run = 0.0
    for i, c in enumerate(closes):
        run += c
        if i >= window:
            run -= closes[i - window]
        out.append(run / window if i >= window - 1 else None)
    return out


def _drawdown_series(equity: list[float]) -> list[float]:
    """Underwater curve: NEGATIVE % below the running peak (0 = at the
    peak). The static dashboard's convention — the filled area hangs
    under the zero line, the classic underwater read."""
    out: list[float] = []
    peak = 0.0
    for e in equity:
        if e > peak:
            peak = e
        out.append(-round((peak - e) / peak * 100, 2) if peak > 0 else 0.0)
    return out


def _downsample_indices(n: int, max_points: int) -> list[int]:
    """Even-stride indices 0..n-1 (≤ max_points), first and last always kept."""
    if n <= max_points:
        return list(range(n))
    stride = (n + max_points - 1) // max_points
    idx = list(range(0, n, stride))
    if idx[-1] != n - 1:
        idx.append(n - 1)
    return idx
