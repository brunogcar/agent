"""webui/routes/portfolio.py — the Carteira (portfolio) REST surface.

[v1.21] User-owned data (users / accounts / transactions / watchlist) +
the computed views (positions with the PM engine, the Painel overview
widget). The system.py precedent: ONE dedicated router per feature
surface, service singleton below.

Routes (all under /api/webui/portfolio):
  GET    /state                        → users + accounts + watchlist +
                                         ticker metadata (manage UI +
                                         selectors; no computation)
  GET    /directory                    → [fix 1] users → accounts tree
                                         with live KPIs (the Carteira
                                         landing + user pages)
  GET    /positions?scope=all|user:ID|account:ID
                                      → KPI cards + position rows (PM
                                         method) + totals + recent txs
  GET    /overview                     → the Painel widget payload
                                         (watched accounts grouped by
                                         user + watchlist tickers)
  POST   /users                        → create  {name}
  PUT    /users/{id}                   → rename
  DELETE /users/{id}                   → cascade (accounts + txs)
  POST   /accounts                     → create  {user_id, name, broker,
                                                  watch}
  PUT    /accounts/{id}                → update (any field incl. watch)
  DELETE /accounts/{id}                → cascade (txs)
  POST   /txs                          → create  {account_id, ticker,
                                                  type, quantity, price,
                                                  fees?, date, note?}
  PUT    /txs/{id}                     → update (same-user accounts
                                         only; warnings when the edit
                                         leaves shorts open)
  DELETE /txs/{id}                     → delete (PM/lucro recalculated
                                         by the replay; warnings when
                                         the delete leaves shorts open)
  POST   /watchlist                    → add ticker {ticker}
  DELETE /watchlist/{ticker}           → remove ticker
  POST   /tickers/{ticker}/refresh     → re-fetch CVM name/sector

Handler style follows api.py/system.py: GETs are plain `def` (the
positions/overview GETs run the cotahist snapshot — threadpool, never
the event loop); mutations are `async def` (the body must be awaited;
the write itself is a sub-millisecond atomic replace of a tiny JSON —
the put_settings precedent). Validation is all-or-nothing with PT-BR
errors per field ({"_error": summary, "errors": {field: message}}).
"""
from __future__ import annotations

import re
from typing import Annotated

from fastapi import APIRouter, Path, Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from webui.services.portfolio import portfolio_service
# [v1.22] ONE ticker definition (webui/validators.py) — the local copy
# had drifted into rejecting B3SA3/BDRs, same as api.py's.
from webui.validators import TICKER_PATTERN

router = APIRouter(prefix="/api/webui/portfolio", tags=["webui-portfolio"])

_svc = portfolio_service()

# Path-param shapes validated at the boundary (the api.py posture —
# garbage never reaches the store or the engines). ANNOTATED types, the
# api.py pattern — a SHARED Path(...) default gets its alias mutated per
# route by FastAPI (the txs route started demanding "user_id"), so the
# plain-default form is off limits here.

# scope: "all" | "user:<10-hex>" | "account:<10-hex>"
_SCOPE_RE = re.compile(r"^(all|user:[a-f0-9]{10}|account:[a-f0-9]{10})$")

Id = Annotated[str, Path(pattern=r"^[a-f0-9]{10}$")]
Ticker = Annotated[str, Path(pattern=TICKER_PATTERN)]


def _bad(body: dict, status_code: int = 400) -> JSONResponse:
    """Validation-failure response (the settings.py error shape).

    [v1.22] The parameter used to be ``status`` while four callers
    passed ``status_code=`` → TypeError → HTTP 500 on every
    delete-not-found (stale tab / double click). The name now matches
    the callers (and JSONResponse itself).
    """
    return JSONResponse(body, status_code=status_code)


async def _json_body(request: Request) -> dict | None:
    # [v1.22 CSRF] request.json() parses ANY content type — a
    # cross-site page can POST text/plain (a CORS-SIMPLE request, no
    # preflight) and still have the body parsed. Demanding
    # application/json forces the preflight, which the localhost-only
    # CORS allow-list rejects. (The app-level CrossSiteGuardMiddleware
    # covers Sec-Fetch-Site/Origin for every router.)
    if "application/json" not in (request.headers.get("content-type")
                                   or "").lower():
        return None
    try:
        body = await request.json()
    except Exception:
        return None
    return body if isinstance(body, dict) else None


# [v1.22.3] THE THREADPOOL RULE (roadmap 8): a mutation handler stays
# async ONLY to await the body — the service call (file I/O under the
# store lock + the replay) runs via run_in_threadpool, so the event
# loop never blocks on a write. The GETs are plain `def` (FastAPI's
# own threadpool) — the posture api.py/system.py already had.


# ── reads ────────────────────────────────────────────────────────────────────

@router.get("/state")
def get_state():
    """Users + accounts + watchlist + ticker metadata — the manage UI."""
    return JSONResponse(_svc.state())


@router.get("/directory")
def get_directory():
    """[v1.21 fix 1] Users → accounts tree with live KPIs.

    Powers the Carteira landing page (user cards) and the user page
    (account cards). Per-USER sums only — never across users.
    """
    return JSONResponse(_svc.directory())


@router.get("/positions")
def get_positions(scope: str = "all"):
    """PM positions + KPIs + totals + recent transactions for a scope."""
    if not _SCOPE_RE.match(scope or ""):
        return JSONResponse(
            {"_error": "Escopo inválido — use all, user:<id> ou "
                       "account:<id>."}, status_code=400)
    return JSONResponse(_svc.positions(scope))


@router.get("/txs")
def get_txs(scope: str = "all", page: int = 1, per_page: int = 50,
            ticker: str = "", type: str = "",
            date_from: str = "", date_to: str = "", q: str = ""):
    """[v1.22.3] The paginated/filtered ledger (roadmap 7).

    Filters: ticker (PREFIX — "KL" matches KLBN4/KLBN11 while you're
    still typing; [v1.22.4] the old 4-8 full-ticker rule 400'd on
    every partial keystroke and nuked the whole view), type
    (buy|sell|corp), date window (ISO), q (free text over ticker +
    note). Pages are NEWEST-last (page 1 = the most recent per_page
    rows, oldest-first inside the page — the ledger reading order).
    """
    if not _SCOPE_RE.match(scope or ""):
        return JSONResponse(
            {"_error": "Escopo inválido — use all, user:<id> ou "
                       "account:<id>."}, status_code=400)
    per_page = max(1, min(per_page, 200))
    page = max(1, page)
    if ticker and not re.match(r"^[A-Za-z0-9]{1,8}$", ticker):
        return JSONResponse({"_error": "Ticker inválido."}, status_code=400)
    if date_from and not re.match(r"^\d{4}-\d{2}-\d{2}$", date_from):
        return JSONResponse({"_error": "Data inicial inválida."},
                            status_code=400)
    if date_to and not re.match(r"^\d{4}-\d{2}-\d{2}$", date_to):
        return JSONResponse({"_error": "Data final inválida."},
                            status_code=400)
    res = _svc.txs_page(scope, page, per_page,
                        ticker=ticker.strip().upper(), ttype=(type or "").strip(),
                        date_from=date_from, date_to=date_to,
                        query=(q or "")[:80])
    return res if res.get("ok") else _bad(res, status_code=res.get("status", 400))


@router.get("/overview")
def get_overview():
    """The Painel widget: watched accounts + watchlist tickers, live."""
    return JSONResponse(_svc.overview())


# ── users ────────────────────────────────────────────────────────────────────

@router.post("/users")
async def create_user(request: Request):
    body = await _json_body(request)
    if body is None:
        return _bad({"_error": "Corpo inválido — esperado um objeto JSON."})
    res = await run_in_threadpool(_svc.create_user, body)
    return res if res.get("ok") else _bad(res, status_code=res.get("status", 400))


@router.put("/users/{user_id}")
async def update_user(request: Request, user_id: Id):
    body = await _json_body(request)
    if body is None:
        return _bad({"_error": "Corpo inválido — esperado um objeto JSON."})
    res = await run_in_threadpool(_svc.update_user, user_id, body)
    return res if res.get("ok") else _bad(res, status_code=res.get("status", 400))


@router.delete("/users/{user_id}")
def delete_user(user_id: Id):
    res = _svc.delete_user(user_id)
    return res if res.get("ok") else _bad(res, status_code=res.get("status", 404))


# ── accounts ─────────────────────────────────────────────────────────────────

@router.post("/accounts")
async def create_account(request: Request):
    body = await _json_body(request)
    if body is None:
        return _bad({"_error": "Corpo inválido — esperado um objeto JSON."})
    res = await run_in_threadpool(_svc.create_account, body)
    return res if res.get("ok") else _bad(res, status_code=res.get("status", 400))


@router.put("/accounts/{account_id}")
async def update_account(request: Request, account_id: Id):
    body = await _json_body(request)
    if body is None:
        return _bad({"_error": "Corpo inválido — esperado um objeto JSON."})
    res = await run_in_threadpool(_svc.update_account, account_id, body)
    return res if res.get("ok") else _bad(res, status_code=res.get("status", 400))


@router.delete("/accounts/{account_id}")
def delete_account(account_id: Id):
    res = _svc.delete_account(account_id)
    return res if res.get("ok") else _bad(res, status_code=res.get("status", 404))


# ── transactions ─────────────────────────────────────────────────────────────

@router.post("/txs")
async def create_tx(request: Request):
    body = await _json_body(request)
    if body is None:
        return _bad({"_error": "Corpo inválido — esperado um objeto JSON."})
    res = await run_in_threadpool(_svc.create_tx, body)
    return res if res.get("ok") else _bad(res, status_code=res.get("status", 400))


@router.put("/txs/{tx_id}")
async def update_tx(request: Request, tx_id: Id):
    body = await _json_body(request)
    if body is None:
        return _bad({"_error": "Corpo inválido — esperado um objeto JSON."})
    res = await run_in_threadpool(_svc.update_tx, tx_id, body)
    return res if res.get("ok") else _bad(res, status_code=res.get("status", 400))


@router.delete("/txs/{tx_id}")
def delete_tx(tx_id: Id):
    res = _svc.delete_tx(tx_id)
    return res if res.get("ok") else _bad(res, status_code=res.get("status", 404))


# ── notas de corretagem — import (PDF → preview → commit) [v1.22.2] ──────────

@router.post("/import/nota")
async def import_nota_preview(request: Request):
    """base64 PDF → parsed preview (NO store write — the dry-run).

    Body: {pdf_b64}. The response merges the dedup pre-check
    (advisory) — the commit endpoint re-checks under the lock.
    """
    body = await _json_body(request)
    if body is None:
        return _bad({"_error": "Corpo inválido — esperado um objeto JSON."})
    from webui.services.nota_import import preview_from_b64
    # [v1.22.3] The PDF parse is the heaviest call in the router —
    # threadpool, never the event loop.
    out = await run_in_threadpool(
        preview_from_b64, str(body.get("pdf_b64") or ""))
    if not out.get("ok"):
        return _bad(out, status_code=400)
    dedup = _svc.nota_dedup_status(out.get("broker_cnpj") or "",
                                   out.get("nota") or "",
                                   out.get("pregao") or "")
    out["dedup"] = dedup
    return JSONResponse(out)


@router.post("/import/commit")
async def import_nota_commit(request: Request):
    """Parsed nota (mapped by the user in the preview) → txs, one save."""
    body = await _json_body(request)
    if body is None:
        return _bad({"_error": "Corpo inválido — esperado um objeto JSON."})
    res = await run_in_threadpool(_svc.import_nota, body)
    return res if res.get("ok") else _bad(res, status_code=res.get("status", 400))


@router.get("/import/notas")
def get_imported_notas(account_id: str | None = None):
    """The imported-notas registry (dedup/undo UI) — optionally one account."""
    return JSONResponse(_svc.notas_registry(account_id))


@router.delete("/import/nota/{nota_id}")
def undo_import(nota_id: Id):
    """Undo an import: removes the nota's txs + registry row."""
    res = _svc.undo_import(nota_id)
    return res if res.get("ok") else _bad(res, status_code=res.get("status", 404))


# ── IR / DARF helper [v1.22.2] ───────────────────────────────────────────────

@router.get("/ir")
def get_ir(scope: str = "all"):
    """Month-by-month swing × day-trade IR estimate per user (CPF)."""
    if not _SCOPE_RE.match(scope or ""):
        return JSONResponse(
            {"_error": "Escopo inválido — use all, user:<id> ou "
                       "account:<id>."}, status_code=400)
    from webui.services.ir_helper import ir_report
    out = ir_report(scope)
    return JSONResponse(out if out.get("ok") else out,
                        status_code=200 if out.get("ok") else 400)


# ── undo / export / restore / alerts [v1.22.3] ───────────────────────────────

@router.post("/undo")
async def undo_mutation(request: Request):
    """Undo-toast restore: {token} from a mutation response."""
    body = await _json_body(request)
    if body is None:
        return _bad({"_error": "Corpo inválido — esperado um objeto JSON."})
    token = str(body.get("token") or "").strip()
    if not re.match(r"^[a-f0-9]{6,16}$", token):
        return _bad({"_error": "Token inválido."})
    res = await run_in_threadpool(_svc.undo_mutation, token)
    return res if res.get("ok") else _bad(res, status_code=res.get("status", 404))


@router.get("/export")
def export_store():
    """The whole store JSON (the Gerenciar download button)."""
    return JSONResponse(_svc.export_store())


@router.post("/restore")
async def restore_store(request: Request):
    """Replace the whole store from a JSON file (validate-then-swap)."""
    if "application/json" not in (request.headers.get("content-type")
                                  or "").lower():
        return _bad({"_error": "Corpo inválido — esperado um objeto JSON "
                               "(o arquivo exportado)."})
    try:
        payload = await request.json()
    except Exception:
        return _bad({"_error": "JSON ilegível — o arquivo pode estar "
                               "corrompido."})
    res = await run_in_threadpool(_svc.restore_store, payload)
    return res if res.get("ok") else _bad(res, status_code=res.get("status", 400))


@router.get("/alerts")
def get_alerts():
    """Every alert + its live evaluation against the quote map."""
    return JSONResponse(_svc.alerts_status())


@router.post("/alerts")
async def add_alert(request: Request):
    """Create a price alert {ticker, op: above|below, price, note?}."""
    body = await _json_body(request)
    if body is None:
        return _bad({"_error": "Corpo inválido — esperado um objeto JSON."})
    res = await run_in_threadpool(_svc.add_alert, body)
    return res if res.get("ok") else _bad(res, status_code=res.get("status", 400))


@router.delete("/alerts/{alert_id}")
def delete_alert(alert_id: Id):
    res = _svc.delete_alert(alert_id)
    return res if res.get("ok") else _bad(res, status_code=res.get("status", 404))


# ── proventos / position detail / performance / allocation [v1.22.3] ─────────

def _scope_or_400(scope: str | None):
    if not _SCOPE_RE.match(scope or ""):
        return JSONResponse(
            {"_error": "Escopo inválido — use all, user:<id> ou "
                       "account:<id>."}, status_code=400)
    return None


def _report(get, *args):
    """[v1.22.4] Run a report builder, JSON on ANY failure.

    The v1.22.3 report GETs computed straight into JSONResponse — an
    unexpected data-shaped bug escaped as Starlette's PLAIN-TEXT 500,
    which the client's r.json() then blew up on ("Erro: Unexpected
    token 'I'"). The compute bugs are fixed (the TWR complex-power
    guard), but the belt stays: these endpoints always answer JSON
    (ok:false + the exception class server-logged), so the UI can
    always render a PT-BR error instead of a parse crash.
    """
    try:
        return JSONResponse(get(*args))
    except Exception as e:  # noqa: BLE001 — the never-plain-text-500 rule
        import sys
        print(f"[webui] report {getattr(get, '__name__', get)} failed: "
              f"{e!r}", file=sys.stderr)
        return JSONResponse(
            {"ok": False,
             "_error": "Falha ao calcular este relatório "
                       f"({type(e).__name__}). Verifique o log do sistema."},
            status_code=500)


@router.get("/proventos")
def get_proventos(scope: str = "all"):
    """Proventos per position / yield-on-cost (roadmap 2)."""
    bad = _scope_or_400(scope)
    if bad:
        return bad
    from webui.services.portfolio_provents import proventos_report
    return _report(proventos_report, scope)


@router.get("/position-detail")
def get_position_detail(scope: str = "all", ticker: str = ""):
    """The PM ladder drawer for one ticker (roadmap 7)."""
    bad = _scope_or_400(scope)
    if bad:
        return bad
    if not re.match(r"^[A-Za-z0-9]{4,8}$", ticker or ""):
        return JSONResponse({"_error": "Ticker inválido."}, status_code=400)
    from webui.services.portfolio_provents import position_detail
    return _report(position_detail, scope, ticker.upper())


@router.get("/performance")
def get_performance(scope: str = "all"):
    """TWR/XIRR vs CDI/IBOV/S&P500 + the patrimônio curve (roadmap 4)."""
    bad = _scope_or_400(scope)
    if bad:
        return bad
    from webui.services.portfolio_perf import performance_report
    return _report(performance_report, scope)


@router.get("/allocation")
def get_allocation(scope: str = "all"):
    """Per-setor/per-ticker concentration + HHI (roadmap 6)."""
    bad = _scope_or_400(scope)
    if bad:
        return bad
    from webui.services.portfolio_views import allocation_report
    return _report(allocation_report, scope)


@router.post("/simulate")
async def simulate(request: Request):
    """What-if simulator — hypothetical trades, NOTHING written."""
    body = await _json_body(request)
    if body is None:
        return _bad({"_error": "Corpo inválido — esperado um objeto JSON "
                               "{scope, trades: [{ticker, type, quantity, "
                               "price}]}."})
    from webui.services.portfolio_views import simulate as _simulate
    trades = body.get("trades")
    if not isinstance(trades, list):
        return _bad({"_error": "Informe a lista 'trades' "
                               "(ticker, tipo, quantidade, preço)."})
    scope = str(body.get("scope") or "all")
    if not _SCOPE_RE.match(scope):
        return _bad({"_error": "Escopo inválido — use all, user:<id> ou "
                               "account:<id>."})
    res = await run_in_threadpool(_simulate, scope, trades[:10])
    return res if res.get("ok") else _bad(res, status_code=res.get("status", 400))


# ── watchlist ────────────────────────────────────────────────────────────────

@router.post("/watchlist")
async def add_watch(request: Request):
    body = await _json_body(request)
    if body is None:
        return _bad({"_error": "Corpo inválido — esperado um objeto JSON."})
    res = await run_in_threadpool(_svc.add_watch, body)
    return res if res.get("ok") else _bad(res, status_code=res.get("status", 400))


@router.delete("/watchlist/{ticker}")
def remove_watch(ticker: Ticker):
    res = _svc.remove_watch(ticker)
    return res if res.get("ok") else _bad(res, status_code=res.get("status", 404))


# ── ticker metadata ──────────────────────────────────────────────────────────

@router.post("/tickers/{ticker}/refresh")
def refresh_ticker(ticker: Ticker):
    """Re-fetch the CVM name/sector for one ticker (background thread)."""
    res = _svc.refresh_ticker_meta(ticker)
    return res if res.get("ok") else _bad(res, status_code=res.get("status", 400))
