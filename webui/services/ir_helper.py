"""webui/services/ir_helper.py — the IR/DARF month-by-month helper.

[v1.22.2] Roadmap item 3: what the Carteira replay engine already knows
(positions by custo médio) turned into the two numbers a B3 retail
investor actually needs per month — IR a pagar swing (15%, isenção até
R$ 20 mil de vendas) and day trade (20%, sem isenção), IRRF estimates,
loss carry-forward, and the DARF (6015/6120) due dates.

Replay semantics (documented, deterministic):
  - Day-trade carve-out FIRST: on each (conta, ticker, dia) with buys
    AND sells, the matched min(qtd compras, qtd vendas) is day trade —
    result = matched × (média venda − média compra) − taxas rateadas.
    The matched portion NEVER touches the ongoing PM position (a
    round-trip that starts and ends flat changes nothing you hold).
  - The residual side (compras ou vendas além do casado) follows the
    SAME engine semantics as _positions_raw: residual buys blend into
    the custo médio (fees included), residual sells realize against PM
    (fees charged to the result) and may open/cover shorts.
  - Swing loss pool and day loss pool are SEPARATE (Receita rule) and
    tracked chronologically across months at the USER (CPF) level —
    the walk replays every month in order, so the carry is computed,
    not stored.
  - IRRF is ESTIMATED: 0,005% × vendas swing (retido só a partir de
    R$ 1,00/mês) and 1% × resultado day POSITIVO por conta (a nota do
    BTG diz: "IR fonte Day Trade de 1% não é descontado no líquido da
    nota" — o débito vem na conta). Feriados não são considerados no
    vencimento.

Honest boundaries (surfaced in the payload notes): regras próprias de
FII/ETF/BDR; vendas a descoberto com posição ainda aberta não têm
resultado realizado aqui; isenção vale para AÇÕES (mercado à vista).
"""
from __future__ import annotations

from datetime import date
from typing import Any

from tools.report_ops.formats import fmt_num

# Aliquotas / limites (Lei 11.033 / regras B3 vigentes)
SWING_RATE = 0.15            # operações comuns acima da isenção
DAY_RATE = 0.20              # day trade
EXEMPT_LIMIT = 20_000.0      # vendas swing no mês ≤ R$ 20k → isento
SWING_IRRF = 0.00005         # 0,005% sobre vendas
DAY_IRRF = 0.01              # 1% sobre resultado day positivo (por conta)
DARF_SWING = "6015"
DARF_DAY = "6120"


def _order_key(t: dict) -> tuple:
    """[v1.22.3] Same total order as the engine's _tx_order_key —
    corporate actions first within their date (the session already
    trades post-action quantities/prices). The two walks must NEVER
    disagree (the INSTRUCTIONS rule)."""
    return (t.get("date") or "",
            0 if t.get("type") == "corp" else 1,
            t.get("created_at") or "",
            t.get("seq") or 0)


def _walk_account(txs: list[dict]) -> dict[str, dict[str, float]]:
    """One account's txs → month buckets (the day-trade carve-out walk).

    bucket = {buy_vol, swing_vol, swing_res, day_vol, day_res}.
    """
    out: dict[str, dict[str, float]] = {}

    def bucket(month: str) -> dict[str, float]:
        return out.setdefault(month, {"buy_vol": 0.0, "swing_vol": 0.0,
                                      "swing_res": 0.0, "day_vol": 0.0,
                                      "day_res": 0.0})

    by_tk: dict[str, list[dict]] = {}
    for t in txs:
        by_tk.setdefault(t.get("ticker") or "", []).append(t)

    for _tk, tlist in by_tk.items():
        pos = {"qty": 0.0, "pm": 0.0}
        by_date: dict[str, list[dict]] = {}
        for t in sorted(tlist, key=_order_key):
            by_date.setdefault(t.get("date") or "", []).append(t)
        for d, day in sorted(by_date.items()):
            b = bucket(d[:7])
            # [v1.22.3] Corporate actions apply BEFORE the day's trades
            # (the engine's corp-first semantics). No buy/sell volume,
            # no realized result — but the QUANTITY and the PM re-base,
            # so the day's sells realize against the post-action PM.
            for t in day:
                if t.get("type") == "corp":
                    f = float(t.get("factor") or 1.0)
                    if abs(pos["qty"]) > 1e-9 and f > 0:
                        pos["qty"] *= f
                        pos["pm"] = pos["pm"] / f
            day = [t for t in day if t.get("type") != "corp"]
            buys = [t for t in day if t.get("type") == "buy"]
            sells = [t for t in day if t.get("type") == "sell"]
            b_qty = sum(float(t.get("quantity") or 0) for t in buys)
            b_val = sum(float(t.get("quantity") or 0) *
                        float(t.get("price") or 0) for t in buys)
            b_fees = sum(float(t.get("fees") or 0) for t in buys)
            s_qty = sum(float(t.get("quantity") or 0) for t in sells)
            s_val = sum(float(t.get("quantity") or 0) *
                        float(t.get("price") or 0) for t in sells)
            s_fees = sum(float(t.get("fees") or 0) for t in sells)
            b["buy_vol"] += b_val

            # ── day-trade matched portion (never touches the position) ──
            matched = min(b_qty, s_qty)
            if matched > 1e-9:
                b_avg = b_val / b_qty
                s_avg = s_val / s_qty
                fee_day = (b_fees * matched / b_qty +
                           s_fees * matched / s_qty)
                b["day_res"] += matched * (s_avg - b_avg) - fee_day
                b["day_vol"] += matched * s_avg

            # ── residual side — the engine semantics ─────────────────────
            resid_b = b_qty - matched
            resid_s = s_qty - matched
            if resid_b > 1e-9:
                price = b_val / b_qty
                fees = b_fees * resid_b / b_qty
                if pos["qty"] >= -1e-9:
                    total_cost = pos["qty"] * pos["pm"] + \
                        resid_b * price + fees
                    pos["qty"] += resid_b
                    pos["pm"] = total_cost / pos["qty"] \
                        if pos["qty"] > 0 else 0.0
                else:
                    covered = min(resid_b, -pos["qty"])
                    excess = resid_b - covered
                    fee_cov = fees * (covered / resid_b)
                    fee_exc = fees - fee_cov
                    b["swing_res"] += covered * (pos["pm"] - price) - fee_cov
                    pos["qty"] += resid_b
                    if pos["qty"] > 1e-9:
                        pos["pm"] = ((price * excess + fee_exc) / excess
                                     if excess > 1e-9 else 0.0)
            if resid_s > 1e-9:
                price = s_val / s_qty
                fees = s_fees * resid_s / s_qty
                b["swing_vol"] += resid_s * price
                if pos["qty"] >= -1e-9:
                    covered = min(resid_s, pos["qty"])
                    b["swing_res"] += covered * (price - pos["pm"]) - fees
                    pos["qty"] -= resid_s
                    if pos["qty"] < -1e-9:
                        pos["pm"] = price
                else:
                    old = -pos["qty"]
                    pos["pm"] = (old * pos["pm"] + resid_s * price) / \
                        (old + resid_s)
                    pos["qty"] -= resid_s
                    b["swing_res"] -= fees
    return out


def _due_date(month: str) -> str:
    """Last business day of the FOLLOWING month (DARF vencimento).

    Weekend → previous Friday for the month END (vencimento never lands
    on a weekend; feriados are the user's to check — noted in the UI).
    """
    y, m = int(month[:4]), int(month[5:7])
    if m == 12:
        ny, nm = y + 1, 1
    else:
        ny, nm = y, m + 1
    # last day of next month: first day of the month AFTER it, minus 1
    if nm == 12:
        last = date(ny, 12, 31)
    else:
        last = date.fromordinal(date(ny, nm + 1, 1).toordinal() - 1)
    while last.weekday() >= 5:                    # Sat/Sun → back to Fri
        last = date.fromordinal(last.toordinal() - 1)
    return last.isoformat()


def _fmt_month(month: str) -> str:
    names = ["jan", "fev", "mar", "abr", "mai", "jun",
             "jul", "ago", "set", "out", "nov", "dez"]
    return f"{names[int(month[5:7]) - 1]}/{month[:4]}"


def _brl(v: float) -> str:
    return fmt_num(v, decimals=2)


def _user_rows(user: dict, accounts: list[dict],
               txs: list[dict]) -> dict[str, Any]:
    """One user's month rows (CPF-level: all their accounts summed)."""
    acc_ids = {a["id"] for a in accounts}
    buckets: dict[str, dict[str, float]] = {}
    per_account: dict[str, dict[str, dict[str, float]]] = {}
    for acc in accounts:
        acc_txs = [t for t in txs if t.get("account_id") == acc["id"]]
        if not acc_txs:
            continue
        walked = _walk_account(acc_txs)
        per_account[acc["id"]] = walked
        for month, b in walked.items():
            m = buckets.setdefault(month, {"buy_vol": 0.0, "swing_vol": 0.0,
                                           "swing_res": 0.0, "day_vol": 0.0,
                                           "day_res": 0.0})
            for k in m:
                m[k] += b[k]

    carry_s = 0.0
    carry_d = 0.0
    today = date.today()
    rows: list[dict[str, Any]] = []
    for month in sorted(buckets):
        b = buckets[month]
        swing_vol = b["swing_vol"]
        swing_res = b["swing_res"]
        day_res = b["day_res"]
        exempt = swing_vol <= EXEMPT_LIMIT + 1e-9

        swing_taxable = 0.0
        swing_tax = 0.0
        carry_used_s = 0.0
        if exempt:
            if swing_res < 0:
                carry_s += -swing_res
        elif swing_res > 0:
            carry_used_s = min(carry_s, swing_res)
            carry_s -= carry_used_s
            swing_taxable = swing_res - carry_used_s
            swing_tax = SWING_RATE * swing_taxable
        else:
            carry_s += -swing_res

        day_taxable = 0.0
        day_tax = 0.0
        carry_used_d = 0.0
        if day_res > 0:
            carry_used_d = min(carry_d, day_res)
            carry_d -= carry_used_d
            day_taxable = day_res - carry_used_d
            day_tax = DAY_RATE * day_taxable
        elif day_res < 0:
            carry_d += -day_res

        # IRRF estimates — swing withheld only from R$ 1,00/month; day
        # 1% per ACCOUNT on that account's positive day result.
        irrf_s_raw = round(swing_vol * SWING_IRRF, 2)
        irrf_s = irrf_s_raw if irrf_s_raw >= 1.0 else 0.0
        irrf_d = round(sum(
            max(0.0, w.get(month, {}).get("day_res", 0.0)) * DAY_IRRF
            for w in per_account.values()), 2)

        due_s = max(0.0, swing_tax - irrf_s)
        due_d = max(0.0, day_tax - irrf_d)
        darfs = []
        if due_s > 0.005:
            darfs.append({"code": DARF_SWING, "value": round(due_s, 2),
                          "value_br": _brl(due_s)})
        if due_d > 0.005:
            darfs.append({"code": DARF_DAY, "value": round(due_d, 2),
                          "value_br": _brl(due_d)})
        in_progress = (today.strftime("%Y-%m") == month)

        rows.append({
            "month": month,
            "month_br": _fmt_month(month),
            "buy_vol": round(b["buy_vol"], 2),
            "buy_vol_br": _brl(b["buy_vol"]),
            "swing_vol": round(swing_vol, 2),
            "swing_vol_br": _brl(swing_vol),
            "swing_res": round(swing_res, 2),
            "swing_res_br": _brl(swing_res),
            "exempt": exempt,
            "swing_taxable": round(swing_taxable, 2),
            "swing_tax": round(swing_tax, 2),
            "swing_tax_br": _brl(swing_tax),
            "carry_used_s": round(carry_used_s, 2),
            "day_vol": round(b["day_vol"], 2),
            "day_vol_br": _brl(b["day_vol"]),
            "day_res": round(day_res, 2),
            "day_res_br": _brl(day_res),
            "day_tax": round(day_tax, 2),
            "day_tax_br": _brl(day_tax),
            "carry_used_d": round(carry_used_d, 2),
            "irrf_s": irrf_s, "irrf_s_br": _brl(irrf_s),
            "irrf_d": irrf_d, "irrf_d_br": _brl(irrf_d),
            "due_s": round(due_s, 2), "due_s_br": _brl(due_s),
            "due_d": round(due_d, 2), "due_d_br": _brl(due_d),
            "due_total": round(due_s + due_d, 2),
            "due_total_br": _brl(due_s + due_d),
            "carry_after": round(carry_s + carry_d, 2),
            "carry_s_after": round(carry_s, 2),
            "carry_s_after_br": _brl(carry_s),
            "carry_d_after": round(carry_d, 2),
            "carry_d_after_br": _brl(carry_d),
            "due_date": _due_date(month),
            "in_progress": in_progress,
            "darfs": darfs,
        })

    return {"user_id": user.get("id"), "user_name": user.get("name"),
            "months": rows}


def ir_report(scope: str) -> dict[str, Any]:
    """The GET /ir payload for 'all' | 'user:<id>' | 'account:<id>'."""
    from webui.services.portfolio import portfolio_service
    snap = portfolio_service()._snapshot()          # same-package read

    partial = None
    if scope.startswith("account:"):
        aid = scope[8:]
        acc = next((a for a in snap["accounts"] if a.get("id") == aid),
                   None)
        if acc is None:
            return {"ok": False, "_error": "Conta não encontrada."}
        accounts = [acc]
        partial = acc.get("name") or ""
    elif scope.startswith("user:"):
        uid = scope[5:]
        accounts = [a for a in snap["accounts"] if a.get("user_id") == uid]
    else:
        accounts = list(snap["accounts"])

    user_ids: list[str] = []
    for a in accounts:
        uid = a.get("user_id") or ""
        if uid not in user_ids:
            user_ids.append(uid)
    users = [u for u in snap["users"] if u.get("id") in user_ids]

    out_users = [_user_rows(u, accounts, snap["txs"]) for u in users]
    out_users = [u for u in out_users if u["months"]]
    return {
        "ok": True,
        "scope": scope,
        "partial_account": partial,
        "users": out_users,
        "notes": [
            "Estimativas para AÇÕES (mercado à vista + fracionário) — "
            "FII, ETF e BDR têm regras próprias de isenção/alíquota.",
            "Isenção: vendas swing até R$ 20.000,00/mês com resultado "
            "POSITIVO (perdas continuam compensáveis).",
            "IRRF swing estimado em 0,005% das vendas (retido a partir "
            "de R$ 1,00/mês); IRRF day trade em 1% do resultado day "
            "positivo por conta — confira os extratos.",
            "Prejuízos swing e day trade são compensáveis só dentro da "
            "mesma categoria (pools separados, mês a mês).",
            "Vencimento: último dia útil do mês seguinte (feriados não "
            "considerados). DARF 6015 = swing · 6120 = day trade.",
            "Vendas a descoberto com short ainda aberto não geram "
            "resultado realizado aqui (cobertura futura).",
        ],
    }
