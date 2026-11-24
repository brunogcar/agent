"""webui/services/portfolio_provents.py — proventos per position /
yield-on-cost + the position-detail PM ladder.

[v1.22.3] Roadmap 2 ("the data is two joins away") + the roadmap-7
position-detail drawer. The Carteira txs × dividends.db events join:

  ENTITLEMENT (the join key): the B3 "data com" (last_date_prior) is
  the LAST session a buyer still carries the right — so the entitled
  quantity of an event is the position AFTER every tx dated ≤ data com
  (buys on the cum-date receive, sells on it don't; corporate actions
  re-base the quantity before the day's trades — the engine's own
  corp-first order). The per-(account, ticker) ladder
  (PortfolioService._ticker_ladder — the ENGINE, same file as the PM
  math, never a forked numeric) carries the running qty each step; a
  bisect over its rows answers "what did this account hold at date D".

  YIELD ON COST: Σ(rate × entitled qty) over the events ÷ the CURRENT
  cost basis (qty × PM) of the position — the number a buy-and-hold
  investor reads as "how much of my cost the company already paid me
  back". Closed positions keep their received total (yield shows "—":
  there is no current cost to divide by — honest, not a fake 0).

  SHORTS don't receive — they PAY the provento (B3 debits the lender's
  dividend to the short seller). Negative entitlements sum into a
  separate "debitado" bucket and a payload note; never into "recebido".

Boundaries surfaced in the payload: JCP rates are GROSS (the 15% IRRF
shows on the nota); rates are per-share NET-of-nothing values from
dividends.db (the proventos tab's own source); a missing dividends.db
degrades to the empty report with the sync hint.
"""
from __future__ import annotations

import math
from bisect import bisect_right
from datetime import date
from typing import Any

from tools.report_ops.formats import fmt_num

from webui.services.portfolio import portfolio_service

# [v1.22.3] Formatting: the portfolio.py house style (macro.py owns
# the PT-BR numerics — no forks).
from webui.services.macro import _brl2, _fmt_date, _pct

_MAX_EVENT_ROWS = 300          # the events table cap (newest first)

# Module-level ProventosService (its per-ticker events cache is the
# same 60s TTL the Proventos tab rides).
_prov_svc = None


def _events(ticker: str) -> list[dict]:
    global _prov_svc
    if _prov_svc is None:
        from webui.services.proventos import ProventosService
        _prov_svc = ProventosService()
    return _prov_svc.events_for(ticker)


def _brl(v: float | None) -> str | None:
    return _brl2(v) if v is not None else None


def _pct_br(v: float | None) -> str | None:
    return _pct(v * 100.0) if v is not None else None


# ── the entitlement ladder ───────────────────────────────────────────────────

def _qty_at(ladder_rows: list[dict], dates: list[str], when: str) -> float:
    """Position after every tx dated ≤ ``when`` (0 when nothing yet).

    ``dates`` is the ladder's date column (already in replay order).
    """
    i = bisect_right(dates, when)
    if i == 0:
        return 0.0
    return float(ladder_rows[i - 1]["run_qty"])


def _scope_accounts(snap: dict, scope: str) -> list[dict]:
    if scope.startswith("user:"):
        uid = scope[5:]
        return [a for a in snap["accounts"] if a.get("user_id") == uid]
    if scope.startswith("account:"):
        aid = scope[8:]
        return [a for a in snap["accounts"] if a.get("id") == aid]
    return list(snap["accounts"])


def _scope_label(snap: dict, scope: str) -> str:
    svc = portfolio_service()
    accounts = _scope_accounts(snap, scope)
    return svc._scope_label(snap, scope, accounts)


# ── proventos per position (roadmap 2) ───────────────────────────────────────

def proventos_report(scope: str) -> dict[str, Any]:
    """The 🪙 Proventos view payload for a scope."""
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

    today = date.today().isoformat()
    user_by_id = {u["id"]: u for u in snap["users"]}

    # Per-account raw positions (the memoized engine) + the tickers set.
    raw_by_acc: dict[str, dict[str, dict[str, float]]] = {}
    tickers: set[str] = set()
    for acc in accounts:
        acc_txs = [t for t in txs if t.get("account_id") == acc["id"]]
        if not acc_txs:
            continue
        raw_by_acc[acc["id"]] = svc._replay_for(acc["id"], acc_txs)[0]
        tickers |= set(raw_by_acc[acc["id"]].keys())

    # The join: per ticker, every account's ladder × the events window.
    per_ticker: dict[str, dict[str, Any]] = {}
    events_out: list[dict[str, Any]] = []
    monthly: dict[str, float] = {}
    any_db = False
    for tk in sorted(tickers):
        ladders: list[tuple[dict, list[dict], list[str]]] = []
        for acc in accounts:
            if acc["id"] not in raw_by_acc:
                continue
            if tk not in raw_by_acc[acc["id"]]:
                continue
            acc_txs = [t for t in txs if t.get("account_id") == acc["id"]]
            rows = svc._ticker_ladder(acc_txs, tk)
            if rows:
                user = user_by_id.get(acc.get("user_id"))
                label = " · ".join(x for x in (user["name"] if user else None,
                                               acc.get("name")) if x)
                ladders.append((acc, rows, [r["date"] for r in rows]))
        if not ladders:
            continue

        events = _events(tk)
        if events:
            any_db = True
        received = 0.0
        debited = 0.0
        pending = 0.0
        tk_events: list[dict[str, Any]] = []
        for ev in events:
            ex = ev.get("ex_date") or ""
            if not ex or ex > today:
                continue            # no firm entitlement yet (future ex)
            rate = ev.get("rate")
            if rate is None:
                continue
            entitled = math.fsum(
                max(0.0, _qty_at(rows, dates, ex))
                for _acc, rows, dates in ladders)
            short_qty = math.fsum(
                max(0.0, -_qty_at(rows, dates, ex))
                for _acc, rows, dates in ladders)
            if abs(entitled) < 1e-9 and abs(short_qty) < 1e-9:
                continue            # not held at the cum-date
            valor = rate * entitled
            debit = rate * short_qty
            pay = ev.get("pay_date") or ""
            future = bool(pay and pay > today)
            if future:
                pending += valor + debit
            else:
                received += valor
                debited += debit
                month = (pay or ex)[:7]
                monthly[month] = monthly.get(month, 0.0) + valor - debit
            tk_events.append({
                "ex_date": ex, "ex_br": _fmt_date(ex),
                "pay_date": pay, "pay_br": _fmt_date(pay) if pay else None,
                "type": ev.get("type") or "—",
                "rate": rate,
                "rate_br": fmt_num(rate, decimals=4)
                if rate < 1 else fmt_num(rate, decimals=2),
                "qty": entitled,
                "qty_br": fmt_num(entitled, decimals=0)
                if float(entitled).is_integer() else
                fmt_num(entitled, decimals=2),
                "short_qty": short_qty,
                "valor": round(valor, 2),
                "valor_br": _brl(valor),
                "debit_br": _brl(debit) if debit > 1e-9 else None,
                "future": future,
            })
        if not tk_events:
            continue

        # Current position (scope-merged, weighted PM — same math as
        # positions()).
        qty = pm_cost = realized = 0.0
        for acc in accounts:
            p = raw_by_acc.get(acc["id"], {}).get(tk)
            if p:
                qty += p["qty"]
                pm_cost += p["qty"] * p["pm"]
                realized += p["realized"]
        meta = snap["tickers"].get(tk) or {}
        pm = pm_cost / qty if abs(qty) > 1e-9 else None
        open_cost = pm_cost if qty > 1e-9 else 0.0
        total_received = math.fsum(e["valor"] for e in tk_events
                                   if not e["future"])
        yoc = total_received / open_cost if open_cost > 1e-9 else None

        per_ticker[tk] = {
            "ticker": tk,
            "name": meta.get("name") or tk,
            "sector": meta.get("sector") or "—",
            "events": len(tk_events),
            "received": round(total_received, 2),
            "received_br": _brl(total_received),
            "pending": round(pending, 2),
            "pending_br": _brl(pending) if abs(pending) > 1e-9 else None,
            "yoc": yoc,
            "yoc_br": _pct_br(yoc),
            "qty": qty,
            "qty_br": fmt_num(qty, decimals=0)
            if float(qty).is_integer() else fmt_num(qty, decimals=2),
            "pm_br": fmt_num(pm, decimals=4 if (pm or 0) < 1 else 2)
            if pm is not None else None,
            "open_cost": round(open_cost, 2),
            "open_cost_br": _brl(open_cost) if open_cost else None,
            "realized_br": _brl(realized) if abs(realized) > 1e-9 else None,
            "first_ex_br": tk_events[0]["ex_br"],
            "last_ex_br": tk_events[-1]["ex_br"],
        }
        for e in tk_events:
            events_out.append({"ticker": tk, **e,
                               "name": meta.get("name") or tk})

    rows = sorted(per_ticker.values(),
                  key=lambda r: -r["received"])
    events_out.sort(key=lambda e: e["ex_date"], reverse=True)
    total_received = math.fsum(r["received"] for r in rows)
    total_pending = math.fsum(r["pending"] for r in rows)
    one_year_ago = date.today().replace(year=date.today().year - 1)
    one_year_ago_iso = one_year_ago.isoformat()
    received_12m = math.fsum(
        e["valor"] for e in events_out
        if not e["future"] and (e.get("pay_date") or e["ex_date"])
        >= one_year_ago_iso)
    open_cost_all = math.fsum(r["open_cost"] for r in rows)
    yoc_all = total_received / open_cost_all if open_cost_all > 1e-9 else None
    total_debit = math.fsum(
        (e.get("short_qty", 0.0) * e["rate"]) for e in events_out
        if not e["future"])

    kpis = [
        {"label": "Recebido no período", "value": _brl(total_received),
         "tooltip": "Dividendos + JCP creditados conforme a posição de "
                    "cada data com (data com = last_date_prior da B3)."},
        {"label": "Últimos 12 meses", "value": _brl(received_12m),
         "tooltip": "Proventos com pagamento nos últimos 12 meses."},
        {"label": "A receber", "value": _brl(total_pending),
         "tooltip": "Direito já garantido (data com passada), pagamento "
                    "futuro."},
        {"label": "Yield sobre o custo",
         "value": _pct_br(yoc_all),
         "tooltip": "Total recebido ÷ custo das posições ainda abertas "
                    "(yield-on-cost)."},
    ]
    month_rows = [{"month": m, "total_br": _brl(v)}
                  for m, v in sorted(monthly.items(), reverse=True)]

    notes = [
        "Direito ao provento = posição na DATA COM (compras do dia "
        "contam, vendas não) — campo data com (last_date_prior) da B3.",
        "JCP é o valor BRUTO por ação — o IRRF de 15% aparece na nota "
        "da corretora.",
        "Posições vendidas a descoberto PAGAM o provento ao emprestador "
        "(debitado pela B3) — não entram no recebido.",
    ]
    if total_debit > 0.009:
        notes.append(f"⚠️ Proventos debitados por shorts no período: "
                     f"{_brl(total_debit)}.")
    if not any_db:
        notes.insert(0, "Sem eventos de proventos no dividends.db — "
                        "sincronize a fonte dividendos na página "
                        "Sincronização.")

    return {
        "ok": True,
        "empty": None,
        "scope_label": _scope_label(snap, scope),
        "kpis": kpis,
        "by_ticker": rows,
        "events": events_out[:_MAX_EVENT_ROWS],
        "events_total": len(events_out),
        "monthly": month_rows[:24],
        "notes": notes,
    }


# ── position detail — the PM ladder drawer (roadmap 7) ───────────────────────

def position_detail(scope: str, ticker: str) -> dict[str, Any]:
    """One ticker's full story in the scope: per-account PM ladder +
    merged position + live quote + the proventos it paid."""
    svc = portfolio_service()
    snap = svc._snapshot()
    tk = (ticker or "").strip().upper()
    accounts = _scope_accounts(snap, scope)
    account_ids = {a["id"] for a in accounts}
    user_by_id = {u["id"]: u for u in snap["users"]}

    txs = [t for t in snap["txs"]
           if t.get("account_id") in account_ids
           and (t.get("ticker") or "").upper() == tk]
    if not txs:
        return {"ok": False, "_error": "Nenhuma transação deste ticker "
                                       "neste escopo.", "status": 404}

    ladders = []
    merged = {"qty": 0.0, "cost": 0.0, "realized": 0.0}
    for acc in accounts:
        acc_txs = [t for t in snap["txs"] if t.get("account_id") == acc["id"]]
        rows = svc._ticker_ladder(acc_txs, tk)
        if not rows:
            continue
        raw = svc._replay_for(acc["id"], acc_txs)[0].get(tk)
        if raw:
            merged["qty"] += raw["qty"]
            merged["cost"] += raw["qty"] * raw["pm"]
            merged["realized"] += raw["realized"]
        user = user_by_id.get(acc.get("user_id"))
        ladders.append({
            "account": " · ".join(x for x in (
                user["name"] if user else None, acc.get("name")) if x),
            "rows": rows,
        })

    svc._refresh_quotes({tk})
    q = svc._quote(tk)
    price = q.get("close") if q else None
    value = price * merged["qty"] if price is not None else None
    meta = snap["tickers"].get(tk) or {}

    # The ticker's proventos (same join, one ticker).
    today = date.today().isoformat()
    prov_rows = []
    for ev in _events(tk):
        ex = ev.get("ex_date") or ""
        rate = ev.get("rate")
        if not ex or ex > today or rate is None:
            continue
        entitled = math.fsum(
            max(0.0, _qty_at(l["rows"], [r["date"] for r in l["rows"]], ex))
            for l in ladders)
        if entitled < 1e-9:
            continue
        prov_rows.append({
            "ex": ex,
            "ex_br": _fmt_date(ex),
            "pay_br": _fmt_date(ev.get("pay_date") or "") or None,
            "type": ev.get("type") or "—",
            "rate_br": fmt_num(rate, decimals=4 if rate < 1 else 2),
            "qty_br": fmt_num(entitled, decimals=0)
            if float(entitled).is_integer() else
            fmt_num(entitled, decimals=2),
            "valor": round(rate * entitled, 2),
            "valor_br": _brl(rate * entitled),
            "future": bool(ev.get("pay_date") and ev["pay_date"] > today),
        })
    prov_rows.sort(key=lambda r: r["ex"], reverse=True)

    pm = merged["cost"] / merged["qty"] if abs(merged["qty"]) > 1e-9 else None
    prov_total = math.fsum(
        r.get("valor", 0.0) for r in prov_rows if not r["future"])
    return {
        "ok": True,
        "ticker": tk,
        "name": meta.get("name") or (q.get("name") if q else "") or tk,
        "sector": meta.get("sector") or "—",
        "qty_br": fmt_num(merged["qty"], decimals=0)
        if float(merged["qty"]).is_integer() else
        fmt_num(merged["qty"], decimals=2),
        "short": merged["qty"] < -1e-9,
        "pm_br": fmt_num(pm, decimals=4 if (pm or 0) < 1 else 2)
        if pm is not None else None,
        "cost_br": _brl(merged["cost"]) if abs(merged["cost"]) > 1e-9 else None,
        "price_br": fmt_num(price, decimals=4 if (price or 0) < 1 else 2)
        if price is not None else None,
        "value_br": _brl(value) if value is not None else None,
        "realized_br": _brl(merged["realized"]),
        "ladders": ladders,
        "proventos": prov_rows[:60],
        "proventos_total": round(prov_total, 2),
        "proventos_total_br": _brl(prov_total),
    }
