"""webui/services/portfolio.py — Carteira (portfolio) data service.

[v1.21] The user's own money: multiple USUÁRIOS → multiple CONTAS
(brokerage accounts) → TRANSAÇÕES (buys/sells), consolidated into
positions with the Brazilian PREÇO MÉDIO method, plus a WATCHLIST the
Painel summarizes.

[v1.21 fix 1] The management rework:
  - SHORTS: a sell may exceed the position — qty goes NEGATIVE (the
    engine no longer clamps, the CRUD no longer rejects; the rows flag
    ``short`` and the tx that first crossed zero flags ``short`` too).
  - PRICE 0: buys at R$ 0,00 are valid (bonificações) — rows flag
    ``zero``; only NEGATIVE prices are rejected.
  - ``directory()``: the users → accounts tree with live KPIs (the
    Carteira landing/user pages; per-USER sums only — never across
    users).
  - ``overview()``: the Painel widget groups watched accounts BY USER
    with per-user subtotals (no cross-user “Geral”) — and the Lucro %
    double-×100 bug is gone (``_signed_pct`` takes the RATIO).
  - ``_tx_rows()``: chronological ASC (oldest → newest) by default.

Model (one JSON file, the settings.py storage pattern — atomic_write +
mtime refresh + in-memory cache under a lock):

    users    [{id, name, created_at}]
    accounts [{id, user_id, name, broker, watch, created_at}]
    txs      [{id, account_id, ticker, type: buy|sell, quantity, price,
               fees, date, note, created_at}]
    watchlist [{ticker, added_at}]
    tickers  {TICKER: {name, sector, updated_at}}   # cached metadata

Position engine (per account, chronological replay):
    buy  → pm = (qty·pm + q·price + fees) / (qty + q)   [fees enter the PM]
    sell → realized += q·(price − pm) − fees; qty −= q   [PM unchanged;
           qty may go NEGative — short a descoberto]
    Consolidated scopes merge per-account positions by
    pm_merged = Σ(qty·pm) / Σqty (weighted — no forked numerics: ONE
    engine, the scope only chooses which accounts feed it).

Quotes ("Valor Hoje") come from the cotahist quotes_for() query (the
[v1.21] per-symbol variant of the landing page's market_snapshot),
memoized 30s. Names/sectors are cached per ticker: fetched
ONCE from build_company_header (FCA/CAD — "Material Rodoviário"-style
CVM sectors) in a background thread when a ticker first appears, with a
manual refresh endpoint; cotahist's corp_name is the live fallback.

Every number is a PRE-FORMATTED PT-BR string (the v1.7+ house rule —
the client only colorizes by the leading sign). Scope degradation: no
quotes → the price/value/lucro cells degrade to "—" with one note
naming the cotahist source; no users/accounts → the payload says so
(the client renders the setup guide).

CRUD is validated ALL-OR-NOTHING (settings.py pattern: every field
checked before anything is written; PT-BR error per field). Sells are
free to short (negative position — flagged, never rejected); only
negative prices/quantities and future dates are refused.
"""
from __future__ import annotations

import json
import re
import threading
import time
import traceback
import uuid
from datetime import date
from pathlib import Path
from typing import Any

from core.atomic_write import atomic_write
from webui.adapters.contract import kpi

# ── formatting helpers (macro.py owns the PT-BR numerics — no forks) ─────────
from webui.services.macro import _brl2, _fmt_date, _pct

from tools.report_ops.formats import fmt_num

# The skill's data layer (single source of truth — same DB the Painel
# cards read; no SQL duplication in the WebUI). [v1.21] quotes_for(): the
# per-symbol variant of market_snapshot() — illiquid papers silent for
# 10+ sessions still get their LAST TRADED price (portfolio valuation
# needs the honest "Valor Hoje", not the landing-page actives window).
from data_sources.b3.cotahist.query_engine import quotes_for as _quotes_for

_TICKER_RE = re.compile(r"^[A-Z]{4,6}\d{1,2}[A-Z]?$")   # B3 symbol (api.py's pattern)
_ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_QUOTE_TTL = 30.0            # seconds the filtered quote map stays memoized
_COTAHIST_ERR = ("Cotações do pregão indisponíveis — sincronize a fonte "
                 "cotahist (B3 — COTAHIST) na página Sincronização para "
                 "ver Valor Hoje e Lucro.")


# ── storage path (same resolution chain as settings.py) ──────────────────────
def _portfolio_path() -> Path:
    """memory_db/webui_portfolio.json (cfg.memory_root, cwd fallback)."""
    try:
        from core.config import cfg
        memory_root = getattr(cfg, "memory_root", None)
    except Exception:
        memory_root = None
    if memory_root:
        return Path(memory_root) / "webui_portfolio.json"
    return Path.cwd() / "memory_db" / "webui_portfolio.json"


def _empty_store() -> dict[str, Any]:
    return {"users": [], "accounts": [], "txs": [],
            "watchlist": [], "tickers": {}}


def _now_iso() -> str:
    return date.today().isoformat()


def _new_id() -> str:
    return uuid.uuid4().hex[:10]


def _px(v: float | None) -> str | None:
    """Adaptive price decimals: >= 1 → 2 ('2,44'), < 1 → 4 ('0,0432').

    COTAHIST closes carry 4+ decimals on penny stocks; the 2-decimal
    _brl2 would round a R$ 0,0432 entry to R$ 0,04.
    """
    if v is None:
        return None
    return fmt_num(v, decimals=2 if v >= 1.0 else 4)


def _qty(q: float) -> str:
    """3000 → '3.000'; 12.5 → '12,50' (fractional-market lots)."""
    return fmt_num(q, decimals=0 if float(q).is_integer() else 2)


def _signed_pct(v: float | None) -> str | None:
    """0.4837 → '+48,37%'; -0.045 → '-4,50%'; None → None."""
    if v is None:
        return None
    body = fmt_num(abs(v) * 100.0, decimals=2)
    sign = "+" if v > 0 else ("-" if v < 0 else "")
    return f"{sign}{body}%"


def _signed_brl(v: float | None) -> str | None:
    """1234.5 → '+R$ 1.234,50'; -45.1 → '-R$ 45,10'."""
    if v is None:
        return None
    body = _brl2(abs(v))
    sign = "+" if v > 0 else ("-" if v < 0 else "")
    return f"{sign}{body}"


def _brl_auto(v: float | None) -> str | None:
    """Positive (or zero) as 'R$ 1.234,50'; NEGATIVE as '-R$ 45,10'.

    [v1.21 fix 1] Shorts carry negative cost / market value — the plain
    _brl2 would print 'R$ -3.800,00' (an odd hybrid the client's sign
    parser doesn't color either); this keeps the house style.
    """
    if v is None:
        return None
    return _signed_brl(v) if v < 0 else _brl2(v)


def _num(value: Any) -> float | None:
    """JSON value → float; None if not one.

    [v1.21 fix 1] Strings: PT-BR aware — a COMMA means decimals and any
    DOTS before it are thousands ("1.234,56" → 1234.56, the BR money
    mask output); a dot-only string stays a plain decimal ("3.65"). The
    WebUI form itself sends JSON numbers (parseBr client-side) — this
    branch covers direct API calls.
    """
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        s = value.strip()
        if "," in s:
            s = s.replace(".", "").replace(",", ".")
        try:
            return float(s)
        except ValueError:
            return None
    return None


class PortfolioService:
    """Carteira store + PM position engine + quote enrichment."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._store: dict[str, Any] = _empty_store()
        self._loaded_mtime: float | None = None
        # Filtered quote map memoization (the v1.19-fix-1 single-flight idea,
        # scoped to the tiny ticker set the portfolio needs).
        self._q_lock = threading.Lock()
        self._quotes: dict[str, dict[str, Any]] | None = None
        self._quotes_at: float = 0.0
        self._session_date: str = ""
        self._quotes_ok: bool | None = None
        # Background ticker-metadata refreshes (dedup in-flight).
        self._meta_inflight: set[str] = set()

    # ── store plumbing ───────────────────────────────────────────────────────

    def _maybe_reload(self) -> None:
        """Re-read the JSON when its mtime changed (external edit / reload)."""
        path = _portfolio_path()
        try:
            mtime = path.stat().st_mtime
        except OSError:
            if self._store != _empty_store():
                self._store = _empty_store()
                self._loaded_mtime = None
            return
        if mtime == self._loaded_mtime:
            return
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            store = _empty_store()
            for key in ("users", "accounts", "txs", "watchlist"):
                if isinstance(data.get(key), list):
                    store[key] = data[key]
            if isinstance(data.get("tickers"), dict):
                store["tickers"] = data["tickers"]
            self._store = store
            self._loaded_mtime = mtime
        except Exception:
            # Corrupt file — keep defaults (the next save rewrites it clean).
            self._store = _empty_store()
            self._loaded_mtime = mtime

    def _save(self) -> None:
        """Persist the store (caller holds the lock)."""
        atomic_write(_portfolio_path(),
                     json.dumps(self._store, indent=2, ensure_ascii=False))
        try:
            self._loaded_mtime = _portfolio_path().stat().st_mtime
        except OSError:
            pass

    def _snapshot(self) -> dict[str, Any]:
        """Deep-enough copy for readers (lists of dicts are re-copied)."""
        with self._lock:
            self._maybe_reload()
            return {
                "users": [dict(u) for u in self._store["users"]],
                "accounts": [dict(a) for a in self._store["accounts"]],
                "txs": [dict(t) for t in self._store["txs"]],
                "watchlist": [dict(w) for w in self._store["watchlist"]],
                "tickers": {k: dict(v) for k, v in self._store["tickers"].items()},
            }

    # ── lookups ──────────────────────────────────────────────────────────────

    @staticmethod
    def _user(store: dict, user_id: str) -> dict | None:
        return next((u for u in store["users"] if u.get("id") == user_id), None)

    @staticmethod
    def _account(store: dict, account_id: str) -> dict | None:
        return next((a for a in store["accounts"] if a.get("id") == account_id), None)

    @staticmethod
    def _tx_order_key(t: dict) -> tuple:
        """Chronological replay order: date, then insertion."""
        return (t.get("date") or "", t.get("created_at") or "", t.get("id") or "")

    # ── quotes (cotahist quotes_for, memoized) ────────────────────────────────

    def _refresh_quotes(self, tickers: set[str]) -> None:
        """Populate the memoized quote map for ``tickers`` (30s TTL).

        ONE quotes_for() call covers the requested set (symbol-indexed,
        sub-second). A missing DB degrades to quotes_ok=False + the
        cotahist note; a symbol simply absent from the synced history
        degrades PER-TICKER — the row shows "—" and the payload names
        the stragglers.
        """
        with self._q_lock:
            if (self._quotes is not None
                    and time.monotonic() - self._quotes_at < _QUOTE_TTL
                    and tickers.issubset(self._quotes.keys())):
                return
            res = _quotes_for(sorted(tickers))
            if res.get("status") != "ok":
                # Keep the old map (if any) for the tickers it covers; the
                # NEW tickers get no quote and the note names the source.
                if self._quotes is None:
                    self._quotes = {}
                self._quotes_ok = False
                self._quotes_at = time.monotonic()
                return
            quotes = dict(self._quotes or {})
            for s in res.get("symbols", []):
                quotes[s["ticker"]] = s
            self._quotes = quotes
            self._quotes_ok = True
            self._quotes_at = time.monotonic()
            self._session_date = res.get("session_date") or ""

    def _quote(self, ticker: str) -> dict[str, Any] | None:
        return (self._quotes or {}).get(ticker)

    # ── ticker metadata (name + CVM sector, cached) ─────────────────────────

    def _ensure_ticker_meta(self, store: dict, ticker: str) -> None:
        """Seed name/sector for a NEW ticker (caller holds the lock).

        Best-effort synchronous seed from cotahist's corp_name (instant —
        the quote map is usually warm); the full CVM lookup (FCA sector)
        runs in a background thread and lands on the next render.
        """
        if ticker in store["tickers"]:
            return
        store["tickers"][ticker] = {"name": "", "sector": "",
                                    "updated_at": _now_iso()}
        self._spawn_meta_refresh(ticker)

    def _spawn_meta_refresh(self, ticker: str) -> None:
        """Background FCA/CAD metadata fetch (deduped, daemon thread)."""
        if ticker in self._meta_inflight:
            return
        self._meta_inflight.add(ticker)

        def _work() -> None:
            try:
                meta = self._fetch_meta(ticker)
                if not meta:
                    return
                with self._lock:
                    self._maybe_reload()
                    cur = dict(self._store["tickers"].get(ticker) or {})
                    # Never clobber a manual edit with empty values.
                    if meta.get("name"):
                        cur["name"] = meta["name"]
                    if meta.get("sector"):
                        cur["sector"] = meta["sector"]
                    cur["updated_at"] = _now_iso()
                    self._store["tickers"][ticker] = cur
                    self._save()
                self._syslog("info", f"cadastro do {ticker} atualizado "
                                     f"({meta.get('sector') or 'sem setor'})")
            except Exception as e:  # never raise in a daemon thread
                print(f"[webui] portfolio meta({ticker}) failed: {e}\n"
                      f"{traceback.format_exc()}")
            finally:
                self._meta_inflight.discard(ticker)

        threading.Thread(target=_work, daemon=True,
                         name=f"portfolio-meta-{ticker}").start()

    @staticmethod
    def _fetch_meta(ticker: str) -> dict[str, str] | None:
        """CVM name + sector for one ticker (FCA first, CAD fallback)."""
        try:
            from skills.cvm._shared_report.company_header import (
                build_company_header,
            )
            h = build_company_header(ticker)
            if not isinstance(h, dict):
                return None
            return {
                "name": (h.get("company_name") or h.get("name") or "").strip(),
                "sector": (h.get("sector") or "").strip(),
            }
        except Exception:
            return None

    # ── syslog ───────────────────────────────────────────────────────────────

    @staticmethod
    def _syslog(level: str, message: str) -> None:
        try:
            from webui.services.syslog import syslog
            syslog.log(level, "carteira", message)
        except Exception:
            pass

    # ════════════════════════════════════════════════════════════════════════
    # CRUD — users
    # ════════════════════════════════════════════════════════════════════════

    def create_user(self, body: dict) -> dict:
        errs: dict[str, str] = {}
        name = str(body.get("name") or "").strip()
        if not (1 <= len(name) <= 60):
            errs["name"] = "Informe um nome de 1 a 60 caracteres."
        if errs:
            return {"ok": False, "errors": errs}
        with self._lock:
            self._maybe_reload()
            user = {"id": _new_id(), "name": name, "created_at": _now_iso()}
            self._store["users"].append(user)
            self._save()
        self._syslog("info", f"usuário criado: {name}")
        return {"ok": True, "user": user}

    def update_user(self, user_id: str, body: dict) -> dict:
        with self._lock:
            self._maybe_reload()
            user = self._user(self._store, user_id)
            if user is None:
                return {"ok": False, "_error": "Usuário não encontrado."}
            errs: dict[str, str] = {}
            name = str(body.get("name") or "").strip()
            if not (1 <= len(name) <= 60):
                errs["name"] = "Informe um nome de 1 a 60 caracteres."
            if errs:
                return {"ok": False, "errors": errs}
            user["name"] = name
            self._save()
        self._syslog("info", f"usuário renomeado: {name}")
        return {"ok": True, "user": user}

    def delete_user(self, user_id: str) -> dict:
        with self._lock:
            self._maybe_reload()
            user = self._user(self._store, user_id)
            if user is None:
                return {"ok": False, "_error": "Usuário não encontrado."}
            acc_ids = {a["id"] for a in self._store["accounts"]
                       if a.get("user_id") == user_id}
            self._store["accounts"] = [a for a in self._store["accounts"]
                                       if a.get("user_id") != user_id]
            before = len(self._store["txs"])
            self._store["txs"] = [t for t in self._store["txs"]
                                  if t.get("account_id") not in acc_ids]
            self._store["users"] = [u for u in self._store["users"]
                                    if u.get("id") != user_id]
            self._save()
            removed_txs = before - len(self._store["txs"])
        self._syslog("info", f"usuário excluído: {user.get('name')} "
                             f"({len(acc_ids)} conta(s), {removed_txs} "
                             f"transação(ões))")
        return {"ok": True, "removed_accounts": len(acc_ids),
                "removed_txs": removed_txs}

    # ════════════════════════════════════════════════════════════════════════
    # CRUD — accounts
    # ════════════════════════════════════════════════════════════════════════

    def _validate_account(self, store: dict, body: dict) -> dict:
        """Shared field validation for create/update. {} = valid."""
        errs: dict[str, str] = {}
        user = self._user(store, str(body.get("user_id") or ""))
        if user is None:
            errs["user_id"] = "Selecione um usuário válido."
        name = str(body.get("name") or "").strip()
        if not (1 <= len(name) <= 60):
            errs["name"] = "Informe um nome de 1 a 60 caracteres."
        broker = str(body.get("broker") or "").strip()
        if len(broker) > 40:
            errs["broker"] = "Corretora: no máximo 40 caracteres."
        return errs

    def create_account(self, body: dict) -> dict:
        with self._lock:
            self._maybe_reload()
            errs = self._validate_account(self._store, body)
            if errs:
                return {"ok": False, "errors": errs}
            account = {
                "id": _new_id(),
                "user_id": str(body.get("user_id")),
                "name": str(body.get("name")).strip(),
                "broker": str(body.get("broker") or "").strip(),
                "watch": bool(body.get("watch", False)),
                "created_at": _now_iso(),
            }
            self._store["accounts"].append(account)
            self._save()
        self._syslog("info", f"conta criada: {account['name']}")
        return {"ok": True, "account": account}

    def update_account(self, account_id: str, body: dict) -> dict:
        with self._lock:
            self._maybe_reload()
            account = self._account(self._store, account_id)
            if account is None:
                return {"ok": False, "_error": "Conta não encontrada."}
            merged = dict(account)
            merged.update({k: v for k, v in body.items()
                           if k in ("user_id", "name", "broker")})
            errs = self._validate_account(self._store, merged)
            if errs:
                return {"ok": False, "errors": errs}
            account.update(merged)
            if "watch" in body:
                account["watch"] = bool(body.get("watch"))
            self._save()
        self._syslog("info", f"conta atualizada: {account.get('name')}"
                             + (" (observada no Painel)"
                                if account.get("watch") else ""))
        return {"ok": True, "account": account}

    def delete_account(self, account_id: str) -> dict:
        with self._lock:
            self._maybe_reload()
            account = self._account(self._store, account_id)
            if account is None:
                return {"ok": False, "_error": "Conta não encontrada."}
            before = len(self._store["txs"])
            self._store["txs"] = [t for t in self._store["txs"]
                                  if t.get("account_id") != account_id]
            self._store["accounts"] = [a for a in self._store["accounts"]
                                       if a.get("id") != account_id]
            self._save()
            removed = before - len(self._store["txs"])
        self._syslog("info", f"conta excluída: {account.get('name')} "
                             f"({removed} transação(ões))")
        return {"ok": True, "removed_txs": removed}

    # ════════════════════════════════════════════════════════════════════════
    # CRUD — transactions
    # ════════════════════════════════════════════════════════════════════════

    def _validate_tx(self, store: dict, body: dict) -> tuple[dict, dict[str, str]]:
        """Field validation → (coerced tx fields, errors)."""
        errs: dict[str, str] = {}
        out: dict[str, Any] = {}

        account = self._account(store, str(body.get("account_id") or ""))
        if account is None:
            errs["account_id"] = "Selecione uma conta válida."
        else:
            out["account_id"] = account["id"]

        ticker = str(body.get("ticker") or "").strip().upper()
        if not _TICKER_RE.match(ticker):
            errs["ticker"] = ("Ticker inválido — use o padrão B3 "
                              "(ex: POMO4, PETR4, BOVA11).")
        out["ticker"] = ticker

        ttype = str(body.get("type") or "").strip().lower()
        if ttype not in ("buy", "sell"):
            errs["type"] = "Tipo deve ser compra ou venda."
        out["type"] = ttype

        q = _num(body.get("quantity"))
        if q is None or q <= 0 or q > 1e12:
            errs["quantity"] = "Quantidade deve ser um número maior que zero."
        else:
            out["quantity"] = q

        p = _num(body.get("price"))
        # [v1.21 fix 1] price 0 is a bonificação — valid; only negative
        # (or absurd) prices are rejected.
        if p is None or p < 0 or p > 1e9:
            errs["price"] = ("Preço não pode ser negativo — use 0 para "
                             "bonificação (sem custo).")
        else:
            out["price"] = p

        fees = _num(body.get("fees"))
        if fees is None:
            fees = 0.0
        if fees < 0 or fees > 1e9:
            errs["fees"] = "Taxas não podem ser negativas."
        else:
            out["fees"] = fees

        d = str(body.get("date") or "").strip()
        if not _ISO_DATE_RE.match(d):
            errs["date"] = "Data inválida — use o formato AAAA-MM-DD."
        else:
            try:
                if date.fromisoformat(d) > date.today():
                    errs["date"] = "A data não pode ser no futuro."
                else:
                    out["date"] = d
            except ValueError:
                errs["date"] = "Data inválida — use o formato AAAA-MM-DD."

        out["note"] = str(body.get("note") or "").strip()[:200]
        return out, errs

    def create_tx(self, body: dict) -> dict:
        with self._lock:
            self._maybe_reload()
            fields, errs = self._validate_tx(self._store, body)
            if errs:
                return {"ok": False, "errors": errs}
            tx = {"id": _new_id(), "created_at": date.today().isoformat() +
                   "T" + time.strftime("%H:%M:%S"), **fields}
            self._store["txs"].append(tx)
            self._ensure_ticker_meta(self._store, tx["ticker"])
            self._save()
        self._syslog("info", f"{'compra' if tx['type'] == 'buy' else 'venda'} "
                             f"registrada: {_qty(tx['quantity'])} "
                             f"{tx['ticker']} @ {_px(tx['price'])}"
                             + (" (bonificação)" if not tx["price"] else ""))
        return {"ok": True, "tx": tx}

    def update_tx(self, tx_id: str, body: dict) -> dict:
        with self._lock:
            self._maybe_reload()
            tx = next((t for t in self._store["txs"]
                       if t.get("id") == tx_id), None)
            if tx is None:
                return {"ok": False, "_error": "Transação não encontrada."}
            merged = dict(tx)
            merged.update({k: v for k, v in body.items()
                           if k in ("account_id", "ticker", "type",
                                    "quantity", "price", "fees", "date",
                                    "note")})
            fields, errs = self._validate_tx(self._store, merged)
            if errs:
                return {"ok": False, "errors": errs}
            merged.update(fields)
            tx.update(merged)
            self._ensure_ticker_meta(self._store, tx["ticker"])
            self._save()
        self._syslog("info", f"transação atualizada: {tx['ticker']} "
                             f"{_fmt_date(tx['date'])}")
        return {"ok": True, "tx": tx}

    def delete_tx(self, tx_id: str) -> dict:
        with self._lock:
            self._maybe_reload()
            tx = next((t for t in self._store["txs"]
                       if t.get("id") == tx_id), None)
            if tx is None:
                return {"ok": False, "_error": "Transação não encontrada."}
            self._store["txs"] = [t for t in self._store["txs"]
                                  if t.get("id") != tx_id]
            self._save()
        self._syslog("info", f"transação excluída: {tx['ticker']} "
                             f"{_fmt_date(tx['date'])}")
        return {"ok": True}

    # ════════════════════════════════════════════════════════════════════════
    # CRUD — watchlist (tickers followed on the Painel)
    # ════════════════════════════════════════════════════════════════════════

    def add_watch(self, body: dict) -> dict:
        ticker = str(body.get("ticker") or "").strip().upper()
        if not _TICKER_RE.match(ticker):
            return {"ok": False,
                    "errors": {"ticker": "Ticker inválido — use o padrão B3 "
                                         "(ex: PETR4, BOVA11)."}}
        with self._lock:
            self._maybe_reload()
            if any(w.get("ticker") == ticker for w in self._store["watchlist"]):
                return {"ok": True, "watch": {"ticker": ticker},
                        "already": True}
            watch = {"ticker": ticker, "added_at": _now_iso()}
            self._store["watchlist"].append(watch)
            self._ensure_ticker_meta(self._store, ticker)
            self._save()
        self._syslog("info", f"{ticker} adicionado à lista de observados")
        return {"ok": True, "watch": watch}

    def remove_watch(self, ticker: str) -> dict:
        ticker = (ticker or "").strip().upper()
        with self._lock:
            self._maybe_reload()
            before = len(self._store["watchlist"])
            self._store["watchlist"] = [w for w in self._store["watchlist"]
                                        if w.get("ticker") != ticker]
            if len(self._store["watchlist"]) == before:
                return {"ok": False, "_error": "Ticker não está na lista."}
            self._save()
        self._syslog("info", f"{ticker} removido da lista de observados")
        return {"ok": True}

    def refresh_ticker_meta(self, ticker: str) -> dict:
        """Manual re-fetch of a ticker's CVM name/sector (the ↻ button)."""
        ticker = (ticker or "").strip().upper()
        if not _TICKER_RE.match(ticker):
            return {"ok": False, "_error": "Ticker inválido."}
        with self._lock:
            self._maybe_reload()
            self._store["tickers"].setdefault(
                ticker, {"name": "", "sector": "", "updated_at": _now_iso()})
            self._save()
        self._spawn_meta_refresh(ticker)
        return {"ok": True, "refreshing": ticker}

    # ════════════════════════════════════════════════════════════════════════
    # Reads — state (manage UI) + positions + overview
    # ════════════════════════════════════════════════════════════════════════

    def state(self) -> dict:
        """Everything the manage UI + selectors need (no computation).

        Warms the quote map for the held/watched tickers first (ONE fast
        quotes_for) so the ticker table can fall back to cotahist's
        corp_name when the CVM metadata is still empty/partial.
        """
        snap = self._snapshot()
        needed = {t.get("ticker") for t in snap["txs"]}
        needed.update(w.get("ticker") for w in snap["watchlist"])
        needed = {t for t in needed if t}
        if needed:
            self._refresh_quotes(needed)
        tx_counts: dict[str, int] = {}
        for t in snap["txs"]:
            tx_counts[t.get("account_id") or ""] = \
                tx_counts.get(t.get("account_id") or "", 0) + 1
        users = sorted(snap["users"], key=lambda u: u.get("created_at") or "")
        accounts = []
        for a in sorted(snap["accounts"],
                        key=lambda a: (a.get("created_at") or "", a.get("name") or "")):
            user = next((u for u in snap["users"]
                         if u.get("id") == a.get("user_id")), None)
            accounts.append({**a, "user_name": user["name"] if user else "—",
                             "tx_count": tx_counts.get(a["id"], 0)})
        tickers = self._ticker_table(snap)
        return {"users": users, "accounts": accounts,
                "watchlist": sorted(snap["watchlist"],
                                    key=lambda w: w.get("ticker") or ""),
                "tickers": tickers}

    def _ticker_table(self, snap: dict) -> list[dict]:
        """Held + watched tickers with their cached metadata (manage UI).

        Name falls back to the live quote's corp_name when the CVM
        metadata is empty (partial CAD / fetch still running).
        """
        seen: set[str] = set()
        rows: list[dict] = []
        for t in snap["txs"]:
            seen.add(t.get("ticker") or "")
        for w in snap["watchlist"]:
            seen.add(w.get("ticker") or "")
        for ticker in sorted(seen):
            meta = snap["tickers"].get(ticker) or {}
            q = self._quote(ticker)
            rows.append({"ticker": ticker,
                         "name": meta.get("name") or (q.get("name") if q else "") or "",
                         "sector": meta.get("sector") or "",
                         "updated_at": meta.get("updated_at") or ""})
        return rows

    # ── the PM engine ────────────────────────────────────────────────────────

    def _positions_raw(self, txs: list[dict],
                       short_ids: set[str] | None = None) -> dict[str, dict[str, float]]:
        """Chronological PM walk over ONE account's transactions.

        Returns {ticker: {qty, pm, realized}}. Buys blend fees into the
        PM (the Brazilian custo médio); sells realize (price − PM)·q −
        fees and keep the PM on the covered portion.

        [v1.21 fix 1] SHORTS (venda a descoberto) are first-class:
          - a sell beyond the position OPENS a short — the sell price
            becomes the short's PM (its "entry"), so cost = qty·pm is
            negative and lucro = valor − custo prices the open short
            correctly (price down → profit up);
          - a buy against a short COVERS it: realized += (PM − preço)·q;
            an excess buy flips the position long at the buy price;
          - sells adding to an existing short blend the entry prices.
        The transaction id that first pushed the position below zero
        lands on ``short_ids``.
        """
        out: dict[str, dict[str, float]] = {}
        for t in sorted(txs, key=self._tx_order_key):
            tk = t.get("ticker") or ""
            pos = out.setdefault(tk, {"qty": 0.0, "pm": 0.0, "realized": 0.0})
            q = float(t.get("quantity") or 0.0)
            p = float(t.get("price") or 0.0)
            fees = float(t.get("fees") or 0.0)
            if t.get("type") == "buy":
                if pos["qty"] >= -1e-9:
                    # Long (or flat): the Brazilian custo médio blend.
                    total_cost = pos["qty"] * pos["pm"] + q * p + fees
                    pos["qty"] += q
                    pos["pm"] = total_cost / pos["qty"] if pos["qty"] > 0 else 0.0
                else:
                    # Covering a short (possibly flipping long).
                    covered = min(q, -pos["qty"])
                    pos["realized"] += covered * (pos["pm"] - p) - fees
                    pos["qty"] += q
                    if pos["qty"] > 1e-9:
                        pos["pm"] = p        # the excess opens a long at p
                    # still short → the average entry price stands
            else:
                if pos["qty"] >= -1e-9:
                    # Selling long (possibly opening a short).
                    covered = min(q, pos["qty"])
                    pos["realized"] += covered * (p - pos["pm"]) - fees
                    pos["qty"] -= q
                    if pos["qty"] < -1e-9:
                        pos["pm"] = p        # the excess opens a short at p
                else:
                    # Adding to an existing short — blend the entries.
                    old = -pos["qty"]
                    pos["pm"] = (old * pos["pm"] + q * p) / (old + q)
                    pos["qty"] -= q
                    pos["realized"] -= fees
                if short_ids is not None and pos["qty"] < -1e-9:
                    short_ids.add(t.get("id") or "")
        return out

    @staticmethod
    def _scope_accounts(snap: dict, scope: str) -> list[dict]:
        """Accounts selected by 'all' | 'user:<id>' | 'account:<id>'."""
        if scope.startswith("user:"):
            uid = scope[5:]
            return [a for a in snap["accounts"] if a.get("user_id") == uid]
        if scope.startswith("account:"):
            aid = scope[8:]
            return [a for a in snap["accounts"] if a.get("id") == aid]
        return list(snap["accounts"])

    def positions(self, scope: str) -> dict:
        """The Carteira page payload: KPIs + position rows + totals + txs."""
        snap = self._snapshot()
        accounts = self._scope_accounts(snap, scope)
        account_ids = {a["id"] for a in accounts}
        user_by_id = {u["id"]: u for u in snap["users"]}

        # Empty-state guidance (the client renders the setup steps).
        if not snap["users"]:
            return {"status": "ok", "empty": "no_users", "positions": [],
                    "txs": [], "kpis": []}
        if not accounts:
            return {"status": "ok", "empty": "no_accounts", "positions": [],
                    "txs": [], "kpis": []}

        txs = [t for t in snap["txs"] if t.get("account_id") in account_ids]
        if not txs:
            return {"status": "ok", "empty": "no_txs", "positions": [],
                    "txs": [], "kpis": []}

        # Per-account positions → merged by ticker (weighted PM).
        # [v1.21 fix 1] short_ids: txs that first pushed a position below
        # zero (the 🚨 flag on the transactions table).
        merged: dict[str, dict[str, float]] = {}
        by_account: dict[str, dict[str, dict[str, float]]] = {}
        short_ids: set[str] = set()
        for acc in accounts:
            acc_txs = [t for t in txs if t.get("account_id") == acc["id"]]
            if not acc_txs:
                continue
            raw = self._positions_raw(acc_txs, short_ids)
            by_account[acc["id"]] = raw
            for tk, pos in raw.items():
                m = merged.setdefault(tk, {"qty": 0.0, "cost": 0.0,
                                           "realized": 0.0})
                m["qty"] += pos["qty"]
                m["cost"] += pos["qty"] * pos["pm"]
                m["realized"] += pos["realized"]

        # Quotes for the union of held tickers (shorts included — a
        # negative position still needs its Valor Hoje).
        held = [tk for tk, m in merged.items() if abs(m["qty"]) > 1e-9]
        self._refresh_quotes(set(held))
        quotes_ok = bool(self._quotes_ok)
        missing = [tk for tk in held if self._quote(tk) is None]
        complete = quotes_ok and not missing

        rows: list[dict[str, Any]] = []
        for tk in sorted(held):
            m = merged[tk]
            meta = snap["tickers"].get(tk) or {}
            q = self._quote(tk)
            price = q.get("close") if q else None
            value = price * m["qty"] if price is not None else None
            profit = (value - m["cost"]) if value is not None else None
            # Account label: which accounts hold it (consolidated scopes).
            holders = []
            for acc in accounts:
                pos = by_account.get(acc["id"], {}).get(tk)
                if pos and abs(pos["qty"]) > 1e-9:
                    user = user_by_id.get(acc.get("user_id"))
                    holders.append(" · ".join(x for x in (
                        user["name"] if user else None,
                        acc.get("name")) if x))
            row = {
                "ticker": tk,
                "name": meta.get("name") or (q.get("name") if q else "") or tk,
                "sector": meta.get("sector") or "—",
                "pm": _px(m["cost"] / m["qty"]) if m["qty"] else None,
                "price": _px(price),
                "qty": _qty(m["qty"]),
                "raw_qty": m["qty"],
                "short": m["qty"] < -1e-9,
                "cost": _brl_auto(m["cost"]),
                "value": _brl_auto(value),
                "profit": _signed_brl(profit),
                "profit_pct": _signed_pct(
                    profit / abs(m["cost"]) if profit is not None
                    and abs(m["cost"]) > 1e-9 else None),
                "accounts": holders,
                # sort keys (raw floats; the formatted cells also parse)
                "_v": value if value is not None else -1.0,
            }
            rows.append(row)
        rows.sort(key=lambda r: -r["_v"])

        # Totals + KPIs — "—" whenever ANY held ticker lacks a quote (a
        # partial patrimônio would read as a fake loss). Shorts enter
        # with negative qty/value/cost (|cost| anchors the %).
        total_cost = sum(m["cost"] for m in merged.values())
        total_value = sum(r["_v"] for r in rows if r["_v"] >= 0)
        total_realized = sum(m["realized"] for m in merged.values())
        lucro = total_value - total_cost if complete else None
        lucro_pct = (lucro / abs(total_cost) * 100.0
                     if lucro is not None and abs(total_cost) > 1e-9 else None)

        kpis = [
            kpi("Patrimônio", _brl_auto(total_value) if complete else "—",
                "Soma das posições ao último pregão com cotação"
                + (f" ({_fmt_date(self._session_date)})"
                   if quotes_ok and self._session_date else "")
                + ". Posições vendidas a descoberto entram negativas."),
            kpi("Custo (PM)", _brl_auto(total_cost),
                "Total original — quantidade × preço médio de compra "
                "(taxas de compra incluídas no PM; bonificações entram "
                "a R$ 0,00)."),
            kpi("Lucro não realizado",
                _signed_brl(lucro) if complete else "—",
                "Patrimônio − custo das posições abertas."),
            kpi("Lucro %",
                _signed_pct(lucro_pct / 100.0 if lucro_pct is not None
                            else None) if complete else "—",
                "Lucro não realizado sobre o custo."),
            kpi("Lucro realizado", _signed_brl(total_realized),
                "Vendas já efetuadas: (preço de venda − PM) × quantidade "
                "− taxas, acumulado."),
        ]

        payload: dict[str, Any] = {
            "status": "ok",
            "empty": None,
            "scope_label": self._scope_label(snap, scope, accounts),
            "session_date": _fmt_date(self._session_date) if quotes_ok and
                            self._session_date else None,
            "quotes_ok": quotes_ok,
            "kpis": kpis,
            "positions": rows,
            "totals": {
                "cost": _brl_auto(total_cost),
                "value": _brl_auto(total_value) if complete else "—",
                "profit": _signed_brl(lucro) if complete else "—",
                "profit_pct": _signed_pct(lucro_pct / 100.0
                                          if lucro_pct is not None else None)
                if complete else "—",
            },
            "txs": self._tx_rows(snap, account_ids, limit=200,
                                 short_ids=short_ids),
        }
        if not quotes_ok:
            payload["quotes_note"] = _COTAHIST_ERR
        elif missing:
            payload["quotes_note"] = (
                "Sem cotação no cotahist para " + ", ".join(missing)
                + " — o papel pode não ter negócios no histórico "
                "sincronizado (os totais exigem todas as cotações).")
        return payload

    def _scope_label(self, snap: dict, scope: str, accounts: list[dict]) -> str:
        if scope.startswith("account:"):
            acc = accounts[0] if accounts else {}
            user = next((u for u in snap["users"]
                         if u.get("id") == acc.get("user_id")), None)
            parts = [user["name"] if user else "", acc.get("name") or ""]
            if acc.get("broker"):
                parts.append(acc["broker"])
            return " · ".join(p for p in parts if p) or "Carteira"
        if scope.startswith("user:"):
            user = next((u for u in snap["users"]
                         if u.get("id") == scope[5:]), None)
            return (user["name"] if user else "Usuário") + " · todas as contas"
        return "Geral — todos os usuários e contas"

    def _tx_rows(self, snap: dict, account_ids: set[str],
                 limit: int = 200,
                 short_ids: set[str] | None = None) -> list[dict[str, Any]]:
        """Transactions for the scope — chronological ASC (oldest first).

        [v1.21 fix 1] The default order is date ASCENDING (the ledger
        reading order); the 200-row cap keeps the MOST RECENT 200 and
        then flips them for display. Flags: ``short`` (this sell first
        pushed the position below zero — 🚨) and ``zero`` (price
        R$ 0,00 — bonificação — ⚠️).
        """
        acc_by_id = {a["id"]: a for a in snap["accounts"]}
        user_by_id = {u["id"]: u for u in snap["users"]}
        rows = [t for t in snap["txs"] if t.get("account_id") in account_ids]
        rows.sort(key=lambda t: (t.get("date") or "", t.get("created_at") or "",
                                 t.get("id") or ""), reverse=True)
        recent = rows[:limit]
        recent.reverse()                     # oldest → newest
        short_ids = short_ids or set()
        out = []
        for t in recent:
            acc = acc_by_id.get(t.get("account_id") or "")
            user = user_by_id.get(acc.get("user_id") or "") if acc else None
            total = (t["quantity"] * t["price"]
                     + (t["fees"] if t.get("type") == "buy" else -t["fees"]))
            out.append({
                "id": t["id"],
                "date": _fmt_date(t.get("date")),
                "date_iso": t.get("date") or "",
                "ticker": t.get("ticker"),
                "account": " · ".join(x for x in (
                    user["name"] if user else None,
                    acc.get("name") if acc else None) if x) or "—",
                "account_id": t.get("account_id") or "",
                "type": t.get("type"),
                "qty": _qty(t["quantity"]),
                "quantity": t["quantity"],
                "price": _px(t["price"]),
                "raw_price": t["price"],
                "zero": not t.get("price"),
                "short": t.get("id") in short_ids,
                "fees": _brl2(t["fees"]) if t.get("fees") else "—",
                "raw_fees": t.get("fees") or 0.0,
                "total": _brl2(total),
                "note": t.get("note") or "",
            })
        return out

    # ── the Painel widget payload ────────────────────────────────────────────

    def overview(self) -> dict:
        """[v1.21] Watched accounts + watchlist tickers for the Painel.

        Rendered by loadPortfolioWidget() (app.js) — the section hides
        itself entirely when nothing is watched (the landing page stays
        exactly as v1.19 left it for users without carteira data).

        [v1.21 fix 1] The watched accounts are GROUPED BY USER with a
        per-user subtotal (2+ accounts) — different users are never
        summed together. The Lucro % is the RATIO through _signed_pct
        (the old call pre-multiplied by 100 — a -29,11% read as
        -2.911,00%).
        """
        snap = self._snapshot()
        watched = [a for a in snap["accounts"] if a.get("watch")]
        watch_tickers = [w.get("ticker") for w in snap["watchlist"]]
        if not watched and not watch_tickers:
            return {"status": "ok", "has_data": False}

        user_by_id = {u["id"]: u for u in snap["users"]}
        held_tickers = {t.get("ticker") for t in snap["txs"]}
        needed = set(watch_tickers) | (held_tickers if watched else set())
        self._refresh_quotes(needed)
        quotes_ok = bool(self._quotes_ok)

        # ── watched accounts, grouped by user ──
        # Pre-compute each watched account's raw positions ONCE.
        raw_by_acc: dict[str, dict[str, dict[str, float]]] = {}
        txs_by_acc: dict[str, list[dict]] = {}
        for acc in watched:
            txs = [t for t in snap["txs"] if t.get("account_id") == acc["id"]]
            txs_by_acc[acc["id"]] = txs
            raw_by_acc[acc["id"]] = self._positions_raw(txs)

        def _acc_kpis(acc: dict, raw: dict) -> dict[str, Any]:
            cost = sum(p["qty"] * p["pm"] for p in raw.values())
            value = 0.0
            complete = quotes_ok
            for tk, p in raw.items():
                if abs(p["qty"]) <= 1e-9:
                    continue
                q = self._quote(tk)
                if q and q.get("close") is not None:
                    value += q["close"] * p["qty"]
                else:
                    complete = False
            realized = sum(p["realized"] for p in raw.values())
            lucro = (value - cost) if complete else None
            return {
                "value": _brl_auto(value) if complete else None,
                "profit": _signed_brl(lucro) if complete else None,
                # _signed_pct takes the RATIO — no ×100 here (the fix);
                # |cost| anchors the % (short books carry negative cost).
                "profit_pct": _signed_pct(
                    lucro / abs(cost) if lucro is not None
                    and abs(cost) > 1e-9 else None),
                "realized": _signed_brl(realized),
            }

        # Group rows by user (creation order), then account name.
        groups: dict[str, dict[str, Any]] = {}
        order: list[str] = []
        for acc in sorted(watched,
                          key=lambda a: (a.get("created_at") or "",
                                         a.get("name") or "")):
            uid = acc.get("user_id") or "?"
            if uid not in groups:
                user = user_by_id.get(uid)
                groups[uid] = {"user": user["name"] if user else "—",
                               "accounts": []}
                order.append(uid)
            user = user_by_id.get(uid)
            label = " · ".join(x for x in (user["name"] if user else None,
                                           acc.get("name")) if x)
            groups[uid]["accounts"].append({
                "id": acc["id"],
                "label": label,
                **_acc_kpis(acc, raw_by_acc[acc["id"]]),
            })

        # Per-user subtotal (2+ watched accounts) — NEVER across users.
        for uid in order:
            g = groups[uid]
            if len(g["accounts"]) < 2:
                g["subtotal"] = None
                continue
            g_cost = 0.0
            g_value = 0.0
            g_realized = 0.0
            complete = quotes_ok
            for acc in watched:
                if acc.get("user_id") != uid:
                    continue
                raw = raw_by_acc[acc["id"]]
                g_cost += sum(p["qty"] * p["pm"] for p in raw.values())
                g_realized += sum(p["realized"] for p in raw.values())
                for tk, p in raw.items():
                    if abs(p["qty"]) <= 1e-9:
                        continue
                    q = self._quote(tk)
                    if q and q.get("close") is not None:
                        g_value += q["close"] * p["qty"]
                    else:
                        complete = False
            g_lucro = (g_value - g_cost) if complete else None
            g["subtotal"] = {
                "id": None,
                "label": groups[uid]["user"] + " · subtotal",
                "value": _brl_auto(g_value) if complete else None,
                "profit": _signed_brl(g_lucro) if complete else None,
                "profit_pct": _signed_pct(
                    g_lucro / abs(g_cost) if g_lucro is not None
                    and abs(g_cost) > 1e-9 else None),
                "realized": _signed_brl(g_realized),
            }

        # ── watchlist tickers (live KPIs) ──
        tk_rows: list[dict[str, Any]] = []
        for tk in sorted(set(watch_tickers)):
            meta = snap["tickers"].get(tk) or {}
            q = self._quote(tk)
            tk_rows.append({
                "ticker": tk,
                "name": meta.get("name") or (q.get("name") if q else "") or tk,
                "price": _px(q.get("close")) if q else None,
                "variation": _signed_pct(
                    q.get("variation_pct") / 100.0
                    if q and q.get("variation_pct") is not None else None),
            })
        tk_rows = [r for r in tk_rows if r["ticker"]]

        payload: dict[str, Any] = {
            "status": "ok",
            "has_data": True,
            "session_date": _fmt_date(self._session_date)
            if quotes_ok and self._session_date else None,
            "groups": [groups[uid] for uid in order],
            "tickers": tk_rows,
        }
        if not quotes_ok:
            payload["quotes_note"] = _COTAHIST_ERR
        return payload

    # ── the Carteira landing/user pages payload ──────────────────────────────

    def directory(self) -> dict:
        """[v1.21 fix 1] Users → accounts tree with live KPIs.

        Powers the Carteira landing page (the USERS cards — totals of
        their accounts) and the user page (the ACCOUNTS cards). Sums are
        PER USER ONLY (accounts of the same user add up; users never do).
        """
        snap = self._snapshot()
        if not snap["users"]:
            return {"status": "ok", "empty": "no_users", "users": []}

        held = {t.get("ticker") for t in snap["txs"] if t.get("ticker")}
        if held:
            self._refresh_quotes(held)
        quotes_ok = bool(self._quotes_ok)

        tx_count: dict[str, int] = {}
        txs_by_acc: dict[str, list[dict]] = {}
        for t in snap["txs"]:
            aid = t.get("account_id") or ""
            txs_by_acc.setdefault(aid, []).append(t)
            tx_count[aid] = tx_count.get(aid, 0) + 1

        def _account_row(acc: dict) -> dict[str, Any]:
            txs = txs_by_acc.get(acc["id"], [])
            raw = self._positions_raw(txs)
            cost = 0.0
            value = 0.0
            realized = 0.0
            assets = 0
            complete = quotes_ok
            for tk, p in raw.items():
                realized += p["realized"]
                if abs(p["qty"]) <= 1e-9:
                    continue
                assets += 1
                cost += p["qty"] * p["pm"]
                q = self._quote(tk)
                if q and q.get("close") is not None:
                    value += q["close"] * p["qty"]
                else:
                    complete = False
            lucro = (value - cost) if complete else None
            return {
                "id": acc["id"],
                "name": acc.get("name") or "",
                "broker": acc.get("broker") or "",
                "watch": bool(acc.get("watch")),
                "tx_count": tx_count.get(acc["id"], 0),
                "asset_count": assets,
                "cost": _brl_auto(cost),
                "value": _brl_auto(value) if complete else None,
                "profit": _signed_brl(lucro) if complete else None,
                "profit_pct": _signed_pct(
                    lucro / abs(cost) if lucro is not None
                    and abs(cost) > 1e-9 else None),
                "realized": _signed_brl(realized),
            }

        users_out: list[dict[str, Any]] = []
        for user in sorted(snap["users"], key=lambda u: u.get("created_at") or ""):
            accs = sorted((a for a in snap["accounts"]
                           if a.get("user_id") == user["id"]),
                          key=lambda a: (a.get("created_at") or "",
                                         a.get("name") or ""))
            account_rows = [_account_row(a) for a in accs]

            # Per-USER consolidation (sum of THEIR accounts only).
            u_cost = u_value = u_realized = 0.0
            u_txs = 0
            u_assets: set[str] = set()
            complete = quotes_ok
            for acc in accs:
                raw = self._positions_raw(txs_by_acc.get(acc["id"], []))
                u_realized += sum(p["realized"] for p in raw.values())
                u_txs += tx_count.get(acc["id"], 0)
                for tk, p in raw.items():
                    if abs(p["qty"]) <= 1e-9:
                        continue
                    u_assets.add(tk)
                    u_cost += p["qty"] * p["pm"]
                    q = self._quote(tk)
                    if q and q.get("close") is not None:
                        u_value += q["close"] * p["qty"]
                    else:
                        complete = False
            lucro = (u_value - u_cost) if complete else None
            users_out.append({
                "id": user["id"],
                "name": user.get("name") or "",
                "account_count": len(accs),
                "tx_count": u_txs,
                "asset_count": len(u_assets),
                "cost": _brl_auto(u_cost),
                "value": _brl_auto(u_value) if complete else None,
                "profit": _signed_brl(lucro) if complete else None,
                "profit_pct": _signed_pct(
                    lucro / abs(u_cost) if lucro is not None
                    and abs(u_cost) > 1e-9 else None),
                "realized": _signed_brl(u_realized),
                "accounts": account_rows,
            })

        payload: dict[str, Any] = {
            "status": "ok",
            "empty": None,
            "users": users_out,
            "session_date": _fmt_date(self._session_date)
            if quotes_ok and self._session_date else None,
            "quotes_ok": quotes_ok,
        }
        if not quotes_ok:
            payload["quotes_note"] = _COTAHIST_ERR
        return payload


# ── module-level singleton (the settings.py/syslog.py pattern) ───────────────
_portfolio_service = PortfolioService()


def portfolio_service() -> PortfolioService:
    return _portfolio_service
