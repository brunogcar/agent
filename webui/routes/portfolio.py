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
    res = _svc.create_user(body)
    return res if res.get("ok") else _bad(res, status_code=res.get("status", 400))


@router.put("/users/{user_id}")
async def update_user(request: Request, user_id: Id):
    body = await _json_body(request)
    if body is None:
        return _bad({"_error": "Corpo inválido — esperado um objeto JSON."})
    res = _svc.update_user(user_id, body)
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
    res = _svc.create_account(body)
    return res if res.get("ok") else _bad(res, status_code=res.get("status", 400))


@router.put("/accounts/{account_id}")
async def update_account(request: Request, account_id: Id):
    body = await _json_body(request)
    if body is None:
        return _bad({"_error": "Corpo inválido — esperado um objeto JSON."})
    res = _svc.update_account(account_id, body)
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
    res = _svc.create_tx(body)
    return res if res.get("ok") else _bad(res, status_code=res.get("status", 400))


@router.put("/txs/{tx_id}")
async def update_tx(request: Request, tx_id: Id):
    body = await _json_body(request)
    if body is None:
        return _bad({"_error": "Corpo inválido — esperado um objeto JSON."})
    res = _svc.update_tx(tx_id, body)
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
    out = preview_from_b64(str(body.get("pdf_b64") or ""))
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
    res = _svc.import_nota(body)
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


# ── watchlist ────────────────────────────────────────────────────────────────

@router.post("/watchlist")
async def add_watch(request: Request):
    body = await _json_body(request)
    if body is None:
        return _bad({"_error": "Corpo inválido — esperado um objeto JSON."})
    res = _svc.add_watch(body)
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
