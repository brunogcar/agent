"""webui/services/portfolio_views.py — allocation & concentration +
the what-if simulator.

[v1.22.3] Roadmap 6. Two read-only views over the same replayed book
(the portfolio service's engine — no numerics forked here):

  - ALLOCATION: market-value weights per SETOR (the CVM sector cached
    in the store's ticker metadata) and per TICKER, the HHI
    concentration index (Σ weight² — the antitrust-familiar number:
    10.000 = one asset, ~1.667 = a perfectly flat 6-asset book), and
    the "maior posição" / "top 3" concentration lines. LONG positions
    feed the weights (a short has no "allocation" — it is a bet
    against; the short book sums into its own exposure line).
  - WHAT-IF: hypothetical trades applied to the CURRENT book without
    a single store write — sells realize against the live PM (the
    engine's own formula) and buys blend into it; the response is the
    before/after KPI pair + per-ticker deltas, with the simulation's
    assumed price replacing the quote for the traded ticker. The
    user's answer to "what happens if I sell half of PETR4 at 35?".
"""
from __future__ import annotations

import math
from typing import Any

from tools.report_ops.formats import fmt_num

from webui.services.portfolio import portfolio_service
from webui.services.macro import _brl2, _fmt_date


def _scope_accounts(snap: dict, scope: str) -> list[dict]:
    if scope.startswith("user:"):
        uid = scope[5:]
        return [a for a in snap["accounts"] if a.get("user_id") == uid]
    if scope.startswith("account:"):
        aid = scope[8:]
        return [a for a in snap["accounts"] if a.get("id") == aid]
    return list(snap["accounts"])


def _brl(v: float | None) -> str | None:
    return _brl2(v) if v is not None else None


def _pct_br(v: float | None) -> str | None:
    return fmt_num(v * 100.0, decimals=1) + "%" if v is not None else None


# ── allocation & concentration (roadmap 6) ───────────────────────────────────

def allocation_report(scope: str) -> dict[str, Any]:
    """The 🥧 Alocação view: per-setor / per-ticker weights + HHI."""
    svc = portfolio_service()
    snap = svc._snapshot()
    accounts = _scope_accounts(snap, scope)
    if not snap["users"]:
        return {"ok": True, "empty": "no_users"}
    if not accounts:
        return {"ok": True, "empty": "no_accounts"}
    account_ids = {a["id"] for a in accounts}
    txs = [t for t in snap["txs"] if t.get("account_id") in account_ids]
    if not txs:
        return {"ok": True, "empty": "no_txs"}

    merged: dict[str, dict[str, float]] = {}
    for acc in accounts:
        acc_txs = [t for t in txs if t.get("account_id") == acc["id"]]
        if not acc_txs:
            continue
        raw = svc._replay_for(acc["id"], acc_txs)[0]
        for tk, p in raw.items():
            m = merged.setdefault(tk, {"qty": 0.0, "cost": 0.0})
            m["qty"] += p["qty"]
            m["cost"] += p["qty"] * p["pm"]
    held = [tk for tk, m in merged.items() if abs(m["qty"]) > 1e-9]
    if not held:
        return {"ok": True, "empty": "no_txs"}

    svc._refresh_quotes(set(held))
    quotes_ok = bool(svc._quotes_ok)

    # LONG market values drive the weights; shorts sum separately.
    values: dict[str, float] = {}
    missing: list[str] = []
    short_value = 0.0
    for tk in sorted(held):
        q = svc._quote(tk)
        px = q.get("close") if q else None
        if px is None:
            missing.append(tk)
            continue
        v = px * merged[tk]["qty"]
        if v > 0:
            values[tk] = v
        elif v < 0:
            short_value += -v
    total_long = math.fsum(values.values())
    complete = quotes_ok and not missing

    by_sector: dict[str, dict[str, Any]] = {}
    for tk, v in values.items():
        meta = snap["tickers"].get(tk) or {}
        sector = meta.get("sector") or "Sem setor"
        s = by_sector.setdefault(sector, {"value": 0.0, "tickers": []})
        s["value"] += v
        s["tickers"].append(tk)
    sector_rows = []
    for sector, s in sorted(by_sector.items(),
                            key=lambda kv: -kv[1]["value"]):
        w = s["value"] / total_long if total_long > 1e-9 else None
        sector_rows.append({
            "sector": sector,
            "value": round(s["value"], 2),
            "value_br": _brl(s["value"]),
            "weight": w,
            "weight_br": _pct_br(w),
            "tickers": sorted(s["tickers"]),
            "count": len(s["tickers"]),
        })

    ticker_rows = []
    for tk, v in sorted(values.items(), key=lambda kv: -kv[1]):
        meta = snap["tickers"].get(tk) or {}
        w = v / total_long if total_long > 1e-9 else None
        q = svc._quote(tk)
        ticker_rows.append({
            "ticker": tk,
            "name": meta.get("name") or (q.get("name") if q else "") or tk,
            "sector": meta.get("sector") or "Sem setor",
            "value": round(v, 2),
            "value_br": _brl(v),
            "weight": w,
            "weight_br": _pct_br(w),
            "cost_br": _brl(merged[tk]["cost"]) if merged[tk]["qty"] > 0
            else None,
            "profit_br": _brl(v - merged[tk]["cost"])
            if merged[tk]["qty"] > 0 else None,
        })

    # HHI over the long weights (Σ w², w as 0-1 fractions → ×10.000
    # reads like the antitrust scale).
    hhi = None
    top_w = None
    top3 = None
    if total_long > 1e-9 and not missing:
        ws = [v / total_long for v in values.values()]
        hhi = math.fsum(w * w for w in ws) * 10_000.0
        ws_sorted = sorted(ws, reverse=True)
        top_w = ws_sorted[0]
        top3 = math.fsum(ws_sorted[:3])

    def _conc_label(h: float | None) -> str:
        if h is None:
            return "—"
        if h >= 5_000:
            return "muito concentrada"
        if h >= 2_500:
            return "concentrada"
        if h >= 1_500:
            return "moderada"
        return "diversificada"

    kpis = [
        {"label": "Patrimônio long", "value": _brl(total_long) if complete
         else "—", "tooltip": "Soma dos valores de mercado das posições "
         "compradas (os shorts ficam na linha de exposição)."},
        {"label": "Exposição short", "value": _brl(short_value)
         if complete and short_value > 0 else
         ("R$ 0,00" if complete else "—"),
         "tooltip": "Soma dos valores absolutos das posições vendidas a "
                    "descoberto."},
        {"label": "HHI", "value": fmt_num(hhi, decimals=0) if hhi is not None
         else "—", "tooltip": "Índice de concentração Herfindahl-"
         "Hirschman sobre os pesos long (10.000 = um ativo só; abaixo de "
         "1.500 = diversificada). Carteira " + _conc_label(hhi) + "."},
        {"label": "Maior posição",
         "value": _pct_br(top_w) if top_w is not None else "—",
         "tooltip": "Peso do maior ativo no patrimônio long."},
        {"label": "Top 3",
         "value": _pct_br(top3) if top3 is not None else "—",
         "tooltip": "Peso somado dos 3 maiores ativos."},
    ]

    payload: dict[str, Any] = {
        "ok": True,
        "empty": None,
        "kpis": kpis,
        "by_sector": sector_rows,
        "by_ticker": ticker_rows,
        "concentration": _conc_label(hhi),
        "chart": {
            # doughnut over the sector weights (the client mounts it
            # with the vendored Chart.js — same pattern as the Índices
            # composition rings).
            "labels": [r["sector"] for r in sector_rows],
            "data": [round(r["value"], 2) for r in sector_rows],
        },
    }
    if not quotes_ok:
        payload["quotes_note"] = ("Cotações indisponíveis — sincronize a "
                                  "fonte cotahist na página Sincronização.")
    elif missing:
        payload["quotes_note"] = ("Sem cotação para " + ", ".join(missing)
                                  + " — os pesos excluem esses ativos.")
    return payload


# ── what-if simulator (roadmap 6) ────────────────────────────────────────────

def simulate(scope: str, trades: list[dict]) -> dict[str, Any]:
    """Hypothetical trades over the current book — NOTHING is written.

    Body trades: [{ticker, type: sell|buy, quantity, price}] (fees 0 —
    the simulator is a direction check, not a nota). Sells realize
    against the scope's live PM (the engine's formula, feeless), buys
    blend into it; the traded ticker's after-value uses the SIM price.
    """
    svc = portfolio_service()
    snap = svc._snapshot()
    accounts = _scope_accounts(snap, scope)
    if not accounts:
        return {"ok": False, "_error": "Nenhuma conta no escopo.",
                "status": 400}
    account_ids = {a["id"] for a in accounts}
    txs = [t for t in snap["txs"] if t.get("account_id") in account_ids]
    if not txs:
        return {"ok": False, "_error": "Sem transações para simular.",
                "status": 400}

    # Validate + normalize the trades.
    clean: list[dict[str, Any]] = []
    for i, t in enumerate(trades or []):
        tk = str(t.get("ticker") or "").strip().upper()
        ttype = str(t.get("type") or "").strip().lower()
        try:
            q = float(t.get("quantity") or 0)
            p = float(t.get("price") or 0)
        except (TypeError, ValueError):
            q = p = 0.0
        if ttype not in ("buy", "sell") or q <= 0 or p < 0 or not tk:
            return {"ok": False,
                    "_error": f"Simulação Nº{i + 1} inválida — informe "
                              "ticker, tipo (compra/venda), quantidade > 0 "
                              "e preço ≥ 0.", "status": 400}
        clean.append({"ticker": tk, "type": ttype, "qty": q, "price": p})
    if not clean:
        return {"ok": False, "_error": "Informe ao menos uma operação "
                                       "simulada.", "status": 400}

    # Scope-merged positions per ticker.
    merged: dict[str, dict[str, float]] = {}
    for acc in accounts:
        acc_txs = [t for t in txs if t.get("account_id") == acc["id"]]
        if not acc_txs:
            continue
        raw = svc._replay_for(acc["id"], acc_txs)[0]
        for tk, pos in raw.items():
            m = merged.setdefault(tk, {"qty": 0.0, "cost": 0.0,
                                       "realized": 0.0})
            m["qty"] += pos["qty"]
            m["cost"] += pos["qty"] * pos["pm"]
            m["realized"] += pos["realized"]

    all_tickers = set(merged) | {t["ticker"] for t in clean}
    svc._refresh_quotes(all_tickers)
    quotes_ok = bool(svc._quotes_ok)

    def _book_value(sim_prices: dict[str, float]) -> tuple[float, bool]:
        total = 0.0
        complete = quotes_ok
        for tk, m in merged.items():
            if abs(m["qty"]) < 1e-9:
                continue
            px = sim_prices.get(tk)
            if px is None:
                q = svc._quote(tk)
                px = q.get("close") if q else None
            if px is None:
                complete = False
                continue
            total += px * m["qty"]
        return total, complete

    sim_prices = {t["ticker"]: t["price"] for t in clean}
    before_value, before_complete = _book_value({})
    before_cost = math.fsum(m["cost"] for m in merged.values())
    before_realized = math.fsum(m["realized"] for m in merged.values())

    # Apply the simulated trades (scope-merged book — the same weighted-
    # PM semantics as positions()).
    per_ticker: list[dict[str, Any]] = []
    for t in clean:
        tk = t["ticker"]
        m = merged.setdefault(tk, {"qty": 0.0, "cost": 0.0,
                                   "realized": 0.0})
        before_m = dict(m)
        delta_realized = 0.0
        if t["type"] == "sell":
            if m["qty"] >= -1e-9:
                covered = min(t["qty"], m["qty"])
                delta_realized = covered * (t["price"] - (m["cost"] / m["qty"]
                                         if abs(m["qty"]) > 1e-9 else 0.0))
                m["qty"] -= t["qty"]
                if m["qty"] < -1e-9:
                    m["cost"] = m["qty"] * t["price"]   # short at the sim px
                else:
                    m["cost"] = m["qty"] * (before_m["cost"] /
                                            before_m["qty"]
                                            if abs(before_m["qty"]) > 1e-9
                                            else 0.0)
            else:
                old = -m["qty"]
                pm = abs(m["cost"] / m["qty"]) if old > 1e-9 else 0.0
                new_pm = (old * pm + t["qty"] * t["price"]) / (old + t["qty"])
                m["qty"] -= t["qty"]
                m["cost"] = m["qty"] * new_pm
                delta_realized = 0.0
        else:   # buy
            if m["qty"] >= -1e-9:
                total_cost = m["cost"] + t["qty"] * t["price"]
                m["qty"] += t["qty"]
                m["cost"] = total_cost
            else:
                covered = min(t["qty"], -m["qty"])
                excess = t["qty"] - covered
                pm = abs(m["cost"] / m["qty"]) if m["qty"] < -1e-9 else 0.0
                delta_realized = covered * (pm - t["price"])
                m["qty"] += t["qty"]
                if m["qty"] > 1e-9:
                    m["cost"] = m["qty"] * t["price"]
                else:
                    m["cost"] = m["qty"] * pm
        m["realized"] += delta_realized
        per_ticker.append({
            "ticker": tk,
            "type": t["type"],
            "qty_br": fmt_num(t["qty"], decimals=0)
            if float(t["qty"]).is_integer() else
            fmt_num(t["qty"], decimals=2),
            "price_br": fmt_num(t["price"], decimals=2),
            "delta_realized": round(delta_realized, 2),
            "delta_realized_br": ("+" if delta_realized > 0 else "")
                                 + _brl2(delta_realized),
            "qty_before": round(before_m["qty"], 4),
            "qty_after": round(m["qty"], 4),
            "qty_after_br": fmt_num(m["qty"], decimals=0)
            if float(m["qty"]).is_integer() else
            fmt_num(m["qty"], decimals=2),
        })

    after_value, after_complete = _book_value(sim_prices)
    after_cost = math.fsum(m["cost"] for m in merged.values())
    after_realized = math.fsum(m["realized"] for m in merged.values())
    complete = before_complete and after_complete

    def _kpi_row(label: str, before: str | None, after: str | None,
                 tooltip: str) -> dict[str, Any]:
        return {"label": label, "before": before, "after": after,
                "tooltip": tooltip}

    kpis = [
        _kpi_row("Patrimônio", _brl(before_value) if before_complete else "—",
                 _brl(after_value) if complete else "—",
                 "Valor de mercado das posições — o ativo simulado usa o "
                 "preço da simulação."),
        _kpi_row("Custo (PM)", _brl(before_cost), _brl(after_cost),
                 "Quantidade × preço médio das posições abertas."),
        _kpi_row("Lucro não realizado",
                 _brl(before_value - before_cost) if before_complete else "—",
                 _brl(after_value - after_cost) if complete else "—",
                 "Patrimônio − custo."),
        _kpi_row("Lucro realizado", _brl(before_realized),
                 _brl(after_realized),
                 "Vendas efetuadas acumuladas — a simulação adiciona o "
                 "resultado sobre o PM (sem taxas)."),
    ]
    notes = ["Simulação sem taxas — o resultado real depende da nota "
             "(corretagem, emolumentos, ISS).",
             "Nada foi gravado — a carteira só muda ao registrar a "
             "transação de verdade."]
    if not complete:
        notes.append("⚠️ Sem cotação para algum ativo — os valores "
                     "parciais estão marcados com —.")

    return {
        "ok": True,
        "kpis": kpis,
        "trades": per_ticker,
        "notes": notes,
    }
