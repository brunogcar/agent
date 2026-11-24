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
  PUT    /txs/{id}                     → update
  DELETE /txs/{id}                     → delete (replay-checked)
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

router = APIRouter(prefix="/api/webui/portfolio", tags=["webui-portfolio"])

_svc = portfolio_service()

# Path-param shapes validated at the boundary (the api.py posture —
# garbage never reaches the store or the engines). ANNOTATED types, the
# api.py pattern — a SHARED Path(...) default gets its alias mutated per
# route by FastAPI (the txs route started demanding "user_id"), so the
# plain-default form is off limits here.
_ID_RE = re.compile(r"^[a-f0-9]{10}$")          # uuid4().hex[:10]
_TICKER_RE = re.compile(r"^[A-Za-z]{4,6}\d{1,2}[A-Za-z]?$")

# scope: "all" | "user:<10-hex>" | "account:<10-hex>"
_SCOPE_RE = re.compile(r"^(all|user:[a-f0-9]{10}|account:[a-f0-9]{10})$")

Id = Annotated[str, Path(pattern=r"^[a-f0-9]{10}$")]
Ticker = Annotated[str, Path(pattern=r"^[A-Za-z]{4,6}\d{1,2}[A-Za-z]?$")]


def _bad(body: dict, status: int = 400) -> JSONResponse:
    """Validation-failure response (the settings.py error shape)."""
    return JSONResponse(body, status_code=status)


async def _json_body(request: Request) -> dict | None:
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
    return res if res.get("ok") else _bad(res)


@router.put("/users/{user_id}")
async def update_user(request: Request, user_id: Id):
    body = await _json_body(request)
    if body is None:
        return _bad({"_error": "Corpo inválido — esperado um objeto JSON."})
    res = _svc.update_user(user_id, body)
    return res if res.get("ok") else _bad(res)


@router.delete("/users/{user_id}")
def delete_user(user_id: Id):
    res = _svc.delete_user(user_id)
    return res if res.get("ok") else _bad(res, status_code=404)


# ── accounts ─────────────────────────────────────────────────────────────────

@router.post("/accounts")
async def create_account(request: Request):
    body = await _json_body(request)
    if body is None:
        return _bad({"_error": "Corpo inválido — esperado um objeto JSON."})
    res = _svc.create_account(body)
    return res if res.get("ok") else _bad(res)


@router.put("/accounts/{account_id}")
async def update_account(request: Request, account_id: Id):
    body = await _json_body(request)
    if body is None:
        return _bad({"_error": "Corpo inválido — esperado um objeto JSON."})
    res = _svc.update_account(account_id, body)
    return res if res.get("ok") else _bad(res)


@router.delete("/accounts/{account_id}")
def delete_account(account_id: Id):
    res = _svc.delete_account(account_id)
    return res if res.get("ok") else _bad(res, status_code=404)


# ── transactions ─────────────────────────────────────────────────────────────

@router.post("/txs")
async def create_tx(request: Request):
    body = await _json_body(request)
    if body is None:
        return _bad({"_error": "Corpo inválido — esperado um objeto JSON."})
    res = _svc.create_tx(body)
    return res if res.get("ok") else _bad(res)


@router.put("/txs/{tx_id}")
async def update_tx(request: Request, tx_id: Id):
    body = await _json_body(request)
    if body is None:
        return _bad({"_error": "Corpo inválido — esperado um objeto JSON."})
    res = _svc.update_tx(tx_id, body)
    return res if res.get("ok") else _bad(res)


@router.delete("/txs/{tx_id}")
def delete_tx(tx_id: Id):
    res = _svc.delete_tx(tx_id)
    return res if res.get("ok") else _bad(res, status_code=400)


# ── watchlist ────────────────────────────────────────────────────────────────

@router.post("/watchlist")
async def add_watch(request: Request):
    body = await _json_body(request)
    if body is None:
        return _bad({"_error": "Corpo inválido — esperado um objeto JSON."})
    res = _svc.add_watch(body)
    return res if res.get("ok") else _bad(res)


@router.delete("/watchlist/{ticker}")
def remove_watch(ticker: Ticker):
    res = _svc.remove_watch(ticker)
    return res if res.get("ok") else _bad(res, status_code=404)


# ── ticker metadata ──────────────────────────────────────────────────────────

@router.post("/tickers/{ticker}/refresh")
def refresh_ticker(ticker: Ticker):
    """Re-fetch the CVM name/sector for one ticker (background thread)."""
    res = _svc.refresh_ticker_meta(ticker)
    return res if res.get("ok") else _bad(res)
