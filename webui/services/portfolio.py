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

[v1.22] HARDENING (the adversarial-review wave — money math + store):
  - SHORTS count in the totals: ``positions()`` used to drop negative
    market values from Patrimônio while keeping their negative cost —
    the KPIs lied about the whole book (``directory``/``overview``
    didn't). The ``-1.0`` "no quote" sentinel died with it (it
    collided with any real negative value).
  - the store NEVER answers a corrupt file with an empty store (the
    next save would silently destroy the portfolio): the damaged file
    is quarantined (``.corrupt-<ts>`` copies, capped at 7), the last
    good in-memory store keeps serving reads, the ``.bak`` of the
    previous good save is a boot fallback, and writes are refused
    with a PT-BR error until the file on disk parses again.
  - NaN/Infinity are rejected at the ``_num()`` boundary (they passed
    every range comparison — ``nan <= 0`` is False — got persisted as
    bare ``NaN`` tokens and poisoned every position of the account).
  - same-second transactions replay in INSERTION order (monotonic
    ``seq``; the uuid tiebreak made PM/realized nondeterministic).
  - a buy that covers a short and flips long SPLITS its fees between
    the realized cover and the new long's PM (the "buy fees enter
    the PM" rule applied to the flip — sell fees stay in realized,
    the short-open convention).
  - sells at R$ 0,00 are rejected (bonificação is a BUY at 0).
  - a never-traded ticker no longer defeats the 30s quote cache.
  - consolidated scopes with a long AND a short leg of the same ticker
    show PM/Lucro % as "—" (the blended number existed in no broker).
  - ``update_tx`` refuses moving a transaction to ANOTHER USER's
    account; edits/deletes that leave shorts open return warnings.

Model (one JSON file, the settings.py storage pattern — atomic_write +
mtime refresh + in-memory cache under a lock):

    users    [{id, name, created_at}]
    accounts [{id, user_id, name, broker, watch, created_at}]
    txs      [{id, account_id, ticker, type: buy|sell, quantity, price,
               fees, date, note, created_at, seq}]
               (seq: [v1.22] monotonic insertion order — the
               same-second replay tiebreak; never the uuid)
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
negative prices/quantities, zero-price SELLS and future dates are
refused.
"""
from __future__ import annotations

import json
import math
import re
import shutil
import threading
import time
import traceback
import uuid
from datetime import date
from pathlib import Path
from typing import Any

from core.atomic_write import atomic_write
from webui.adapters.contract import kpi
# [v1.22] ONE ticker definition for every layer (webui/validators.py) —
# the old letters-only stem rejected B3's own ticker (B3SA3) and BDRs.
from webui.validators import TICKER_RE as _TICKER_RE

# ── formatting helpers (macro.py owns the PT-BR numerics — no forks) ─────────
from webui.services.macro import _brl2, _fmt_date, _pct

from tools.report_ops.formats import fmt_num

# The skill's data layer (single source of truth — same DB the Painel
# cards read; no SQL duplication in the WebUI). [v1.21] quotes_for(): the
# per-symbol variant of market_snapshot() — illiquid papers silent for
# 10+ sessions still get their LAST TRADED price (portfolio valuation
# needs the honest "Valor Hoje", not the landing-page actives window).
from data_sources.b3.cotahist.query_engine import quotes_for as _quotes_for

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


class PortfolioStoreError(RuntimeError):
    """[v1.22] A mutation was attempted while the store is degraded
    (the file on disk is corrupt/unreadable and writes are refused)."""


_MAX_QUARANTINE = 7        # newest .corrupt-<ts> copies kept as evidence


def _parse_store(data: Any) -> dict[str, Any]:
    """Validated store shape — anything else is corruption.

    [v1.22] Pre-v1.22 loaded leniently: a wrong-typed key was silently
    DROPPED (``{"users": {...}}`` read as "no users") and the next
    save destroyed the data on disk. Wrong shapes now raise — the
    caller quarantines instead of ever answering with a partial store.
    """
    if not isinstance(data, dict):
        raise ValueError("store deve ser um objeto JSON")
    store = _empty_store()
    for key in ("users", "accounts", "txs", "watchlist"):
        val = data.get(key, [])
        if not isinstance(val, list) or any(not isinstance(x, dict) for x in val):
            raise ValueError(f"{key!r} deve ser uma lista de objetos")
        store[key] = val
    if "tickers" in data:
        if not isinstance(data["tickers"], dict):
            raise ValueError("'tickers' deve ser um objeto")
        store["tickers"] = data["tickers"]
    _ensure_seq(store)
    return store


def _ensure_seq(store: dict) -> None:
    """[v1.22] Backfill a monotonic insertion ``seq`` on transactions.

    The txs list IS insertion order (append-only store; filters keep
    relative order), so pre-v1.22 files get seq = list position —
    idempotent when seq is already present, and the random uuid is
    never a replay tiebreak again.
    """
    txs = store.get("txs") or []
    nxt = 1 + max((t.get("seq") for t in txs
                   if isinstance(t.get("seq"), int)), default=-1)
    for t in txs:
        if not isinstance(t.get("seq"), int):
            t["seq"] = nxt
            nxt += 1


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
    f: float | None = None
    if isinstance(value, (int, float)):
        try:
            f = float(value)
        except (ValueError, OverflowError):     # absurd ints
            return None
    elif isinstance(value, str):
        s = value.strip()
        if "," in s:
            s = s.replace(".", "").replace(",", ".")
        elif re.fullmatch(r"-?\d{1,3}(\.\d{3})+", s):
            # [v1.22.1] Dot-only BUT strictly 3-digit groups is PT-BR
            # thousands ("1.234" → 1234) — the SAME rule the client's
            # parseBr applies on paste (v1.22); the server half of the
            # "'1.234' stays thousands" promise (it parsed as 1,234 —
            # caught by the regression suite). "3.65"/"0.0432" (not
            # 3-digit groups) stay US decimals.
            s = s.replace(".", "")
        try:
            f = float(s)
        except ValueError:
            return None
    # [v1.22] NaN/±inf pass EVERY range comparison (nan <= 0 is False,
    # nan > 1e9 is False) — they sailed through validation, persisted
    # as bare NaN tokens (invalid strict JSON) and poisoned whole
    # accounts. The coercion boundary is the one place to stop them.
    return f if f is not None and math.isfinite(f) else None


class PortfolioService:
    """Carteira store + PM position engine + quote enrichment."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._store: dict[str, Any] = _empty_store()
        self._loaded_mtime: int | None = None      # st_mtime_ns
        # [v1.22] Degraded mode: the file on disk failed to parse.
        # Reads keep serving the last good store; writes are refused.
        self._load_error: str | None = None
        # Filtered quote map memoization (the v1.19-fix-1 single-flight idea,
        # scoped to the tiny ticker set the portfolio needs).
        self._q_lock = threading.Lock()
        self._quotes: dict[str, dict[str, Any]] | None = None
        self._quotes_at: float = 0.0
        # [v1.22] Requested-set memo: tickers ALREADY looked up (found or
        # not) — a never-traded paper no longer defeats the TTL cache.
        self._quotes_seen: set[str] = set()
        self._session_date: str = ""
        self._quotes_ok: bool | None = None
        # Background ticker-metadata refreshes (dedup in-flight).
        self._meta_inflight: set[str] = set()
        # [v1.22.1] The inflight check-then-add raced: _ensure_ticker_meta
        # runs under the MAIN lock but refresh_ticker spawns OUTSIDE it —
        # two concurrent calls could both see "not inflight" and fetch
        # twice. A dedicated lock makes the dedup atomic from every caller
        # (and never nests with the main lock, so no ordering exists).
        self._meta_lock = threading.Lock()

    # ── store plumbing ───────────────────────────────────────────────────────

    def _maybe_reload(self) -> None:
        """Re-read the JSON when its mtime changed (external edit / reload).

        [v1.22] A file that cannot be read/parsed is NEVER answered with
        an empty store — the next mutation would save that emptiness and
        silently destroy the portfolio. See ``_degrade``.
        """
        path = _portfolio_path()
        try:
            mtime = path.stat().st_mtime_ns
        except FileNotFoundError:
            # No file on disk. Degraded mode keeps serving the last good
            # store (the damaged file was quarantined away); otherwise a
            # missing file is simply the empty portfolio.
            if not self._load_error:
                self._store = _empty_store()
                self._loaded_mtime = None
            return
        except OSError:
            # Transient stat failure (AV / backup locks on Windows) —
            # keep whatever we have; never reset memory on unknown I/O.
            return
        if mtime == self._loaded_mtime:
            return
        try:
            store = _parse_store(json.loads(path.read_text(encoding="utf-8")))
        except Exception as e:
            self._degrade(path, mtime, e)
            return
        self._store = store
        self._loaded_mtime = mtime
        if self._load_error:
            self._syslog("info", "arquivo da carteira voltou a ler — "
                                 "modo degradado encerrado")
        self._load_error = None

    def _degrade(self, path: Path, mtime: int, err: Exception) -> None:
        """Corrupt/unreadable store — the [v1.22] never-wipe contract.

        1. quarantine a copy (``webui_portfolio.json.corrupt-<ts>``,
           newest 7 kept) so nothing is ever overwritten away;
        2. keep the last good in-memory store serving reads — or boot
           from the ``.bak`` of the previous good save when memory is
           empty (fresh start against a damaged file);
        3. refuse every mutation (``_load_error`` → PT-BR 503) until
           the file on disk parses again — replacing it (the .bak
           serves) changes the mtime and self-heals.
        """
        qname = ""
        try:
            q = path.with_name(f"{path.name}.corrupt-{int(time.time())}")
            shutil.copy2(path, q)
            qname = q.name
            olds = sorted(path.parent.glob(f"{path.name}.corrupt-*"))
            for old in olds[:-_MAX_QUARANTINE]:
                try:
                    old.unlink()
                except OSError:
                    pass
        except Exception:
            qname = ""
        self._loaded_mtime = mtime      # same mtime → no re-parse loop
        served = ""
        empty_now = not self._store.get("txs") and not self._store.get("users")
        bak = path.with_name(path.name + ".bak")
        if empty_now and bak.exists():
            try:
                self._store = _parse_store(
                    json.loads(bak.read_text(encoding="utf-8")))
                served = "Servindo, em modo leitura, o último backup (.bak). "
            except Exception:
                pass
        self._load_error = (
            "Arquivo da carteira corrompido ou ilegível — "
            + (f"cópia preservada em {qname}. " if qname
               else "não foi possível preservar uma cópia. ")
            + served
            + "As alterações estão desativadas: substitua o arquivo por uma "
            "cópia válida (o .bak serve) e o erro se limpa sozinho.")
        self._syslog("error", f"arquivo da carteira ilegível: {err!r}"
                              + (f" — cópia em {qname}" if qname else ""))

    def _save(self) -> None:
        """Persist the store (caller holds the lock).

        [v1.22] Never writes while degraded (overwriting a file we
        could not read is the data-loss bug), and keeps a ``.bak`` of
        the previous good file on every write (best-effort — a locked
        .bak logs a warning but must not block the save).
        """
        if self._load_error:
            raise PortfolioStoreError(self._load_error)
        path = _portfolio_path()
        try:
            if path.exists():
                shutil.copy2(path, path.with_name(path.name + ".bak"))
        except OSError as e:
            self._syslog("warning", f"backup .bak da carteira falhou: {e}")
        atomic_write(path, json.dumps(self._store, indent=2, ensure_ascii=False))
        try:
            self._loaded_mtime = path.stat().st_mtime_ns
        except OSError:
            pass

    def _write_guard(self) -> dict | None:
        """None = writable; otherwise the PT-BR error payload to return."""
        if self._load_error:
            return {"ok": False, "_error": self._load_error, "status": 503}
        return None

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
        """Chronological replay order: date, then created_at, then seq.

        [v1.22] The final tiebreak is the monotonic insertion ``seq`` —
        NEVER the uuid id: created_at has 1-second resolution, and two
        txs inside the same second used to replay in RANDOM order
        (same trades, different PM/realized). Callers pass lists in
        store (= insertion) order and sorted() is stable on top of seq.
        """
        return (t.get("date") or "", t.get("created_at") or "",
                t.get("seq") or 0)

    @staticmethod
    def _next_seq(store: dict) -> int:
        """[v1.22] Next insertion sequence (see ``_tx_order_key``)."""
        txs = store.get("txs") or []
        return 1 + max((t.get("seq") for t in txs
                        if isinstance(t.get("seq"), int)), default=-1)

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
            # [v1.22] The memo covers the tickers already LOOKED UP
            # (found or not): a delisted/never-traded/typo ticker used
            # to fail ``issubset(self._quotes)`` forever and re-query
            # cotahist on every single request.
            if (self._quotes is not None
                    and time.monotonic() - self._quotes_at < _QUOTE_TTL
                    and tickers.issubset(self._quotes_seen)):
                return
            res = _quotes_for(sorted(tickers))
            self._quotes_seen |= set(tickers)
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
            self._quotes_seen = set(quotes.keys()) | set(tickers)
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
        with self._meta_lock:                    # [v1.22.1] atomic dedup
            if ticker in self._meta_inflight:
                return
            self._meta_inflight.add(ticker)

        def _work() -> None:
            try:
                if self._load_error:
                    return                # degraded store — writes refused
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
                with self._meta_lock:            # [v1.22.1] matched discard
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
            guard = self._write_guard()
            if guard:
                return guard
            self._maybe_reload()
            guard = self._write_guard()      # reload may have degraded us
            if guard:
                return guard
            user = {"id": _new_id(), "name": name, "created_at": _now_iso()}
            self._store["users"].append(user)
            self._save()
        self._syslog("info", f"usuário criado: {name}")
        return {"ok": True, "user": user}

    def update_user(self, user_id: str, body: dict) -> dict:
        with self._lock:
            guard = self._write_guard()
            if guard:
                return guard
            self._maybe_reload()
            guard = self._write_guard()
            if guard:
                return guard
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
            guard = self._write_guard()
            if guard:
                return guard
            self._maybe_reload()
            guard = self._write_guard()
            if guard:
                return guard
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
            guard = self._write_guard()
            if guard:
                return guard
            self._maybe_reload()
            guard = self._write_guard()
            if guard:
                return guard
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
            guard = self._write_guard()
            if guard:
                return guard
            self._maybe_reload()
            guard = self._write_guard()
            if guard:
                return guard
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
            guard = self._write_guard()
            if guard:
                return guard
            self._maybe_reload()
            guard = self._write_guard()
            if guard:
                return guard
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
        # [v1.21 fix 1] price 0 is a bonificação — valid for BUYS; only
        # negative (or absurd) prices are rejected.
        # [v1.22] …but a SELL at R$ 0,00 books the whole position cost
        # as a phantom realized loss (one blank price field away).
        if p is None or p < 0 or p > 1e9:
            errs["price"] = ("Preço não pode ser negativo — use 0 para "
                             "bonificação (sem custo).")
        elif p == 0 and ttype == "sell":
            errs["price"] = ("Preço de venda não pode ser R$ 0,00 — "
                             "bonificação se registra como COMPRA a "
                             "R$ 0,00.")
        else:
            out["price"] = p

        # [v1.22.1] A PRESENT-but-unparseable fees value errors like
        # quantity/price — it used to fall into the absent-fees default
        # and silently book R$ 0,00 (NaN string → None → 0.0; caught by
        # the regression suite). Absent/blank keeps meaning "no fees".
        raw_fees = body.get("fees")
        fees = _num(raw_fees)
        if raw_fees is None or (isinstance(raw_fees, str)
                                and not raw_fees.strip()):
            fees = 0.0
        elif fees is None:
            errs["fees"] = "Taxas devem ser um número maior ou igual a zero."
        if "fees" not in errs:
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
            guard = self._write_guard()
            if guard:
                return guard
            self._maybe_reload()
            guard = self._write_guard()
            if guard:
                return guard
            fields, errs = self._validate_tx(self._store, body)
            if errs:
                return {"ok": False, "errors": errs}
            tx = {"id": _new_id(), "seq": self._next_seq(self._store),
                  "created_at": date.today().isoformat() +
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
            guard = self._write_guard()
            if guard:
                return guard
            self._maybe_reload()
            guard = self._write_guard()
            if guard:
                return guard
            tx = next((t for t in self._store["txs"]
                       if t.get("id") == tx_id), None)
            if tx is None:
                return {"ok": False, "_error": "Transação não encontrada."}
            merged = dict(tx)
            merged.update({k: v for k, v in body.items()
                           if k in ("account_id", "ticker", "type",
                                    "quantity", "price", "fees", "date",
                                    "note")})
            # [v1.22] A tx may move between accounts of the SAME user
            # only — a cross-user move silently changes every per-user
            # sum (the tx vanishes from one user's series and appears
            # in another's, with no trace).
            new_aid = str(merged.get("account_id") or "")
            old_aid = str(tx.get("account_id") or "")
            if new_aid != old_aid:
                old_acc = self._account(self._store, old_aid)
                new_acc = self._account(self._store, new_aid)
                if old_acc and new_acc and \
                        old_acc.get("user_id") != new_acc.get("user_id"):
                    return {"ok": False, "errors": {
                        "account_id": "A conta de destino pertence a outro "
                                      "usuário — mova a transação apenas "
                                      "entre contas do mesmo usuário."}}
            shorts_before = self._short_flags(self._store)
            fields, errs = self._validate_tx(self._store, merged)
            if errs:
                return {"ok": False, "errors": errs}
            merged.update(fields)
            tx.update(merged)
            self._ensure_ticker_meta(self._store, tx["ticker"])
            self._save()
            warnings = self._short_warnings(shorts_before)
        self._syslog("info", f"transação atualizada: {tx['ticker']} "
                             f"{_fmt_date(tx['date'])}")
        out: dict[str, Any] = {"ok": True, "tx": tx}
        if warnings:
            out["warnings"] = warnings
        return out

    def delete_tx(self, tx_id: str) -> dict:
        with self._lock:
            guard = self._write_guard()
            if guard:
                return guard
            self._maybe_reload()
            guard = self._write_guard()
            if guard:
                return guard
            tx = next((t for t in self._store["txs"]
                       if t.get("id") == tx_id), None)
            if tx is None:
                return {"ok": False, "_error": "Transação não encontrada."}
            shorts_before = self._short_flags(self._store)
            self._store["txs"] = [t for t in self._store["txs"]
                                  if t.get("id") != tx_id]
            self._save()
            warnings = self._short_warnings(shorts_before)
        self._syslog("info", f"transação excluída: {tx['ticker']} "
                             f"{_fmt_date(tx['date'])}")
        out: dict[str, Any] = {"ok": True}
        if warnings:
            out["warnings"] = warnings
        return out

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
            guard = self._write_guard()
            if guard:
                return guard
            self._maybe_reload()
            guard = self._write_guard()
            if guard:
                return guard
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
            guard = self._write_guard()
            if guard:
                return guard
            self._maybe_reload()
            guard = self._write_guard()
            if guard:
                return guard
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
            guard = self._write_guard()
            if guard:
                return guard
            self._maybe_reload()
            guard = self._write_guard()
            if guard:
                return guard
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
        with self._lock:
            store_error = self._load_error
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
                "tickers": tickers,
                # [v1.22] Degraded-store banner (corrupt file on disk —
                # writes refused). Null when healthy.
                "store_error": store_error}

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
                    excess = q - covered
                    # [v1.22] Fee split on the flip: the covered share
                    # goes to realized; the excess share enters the new
                    # long's PM — the "buy fees enter the PM" rule
                    # applied to the flip (it used to charge the WHOLE
                    # fee to realized and open the long feeless).
                    fee_cov = fees * (covered / q) if q > 0 else fees
                    fee_exc = fees - fee_cov
                    pos["realized"] += covered * (pos["pm"] - p) - fee_cov
                    pos["qty"] += q
                    if pos["qty"] > 1e-9:
                        # the excess opens a long at p + its fee share
                        pos["pm"] = ((p * excess + fee_exc) / excess
                                     if excess > 1e-9 else 0.0)
                    # still short → the average entry price stands
            else:
                if pos["qty"] >= -1e-9:
                    # Selling long (possibly opening a short). ALL sell
                    # fees stay in realized — including the share of a
                    # short-opening sell: that is the pure-short-open
                    # convention (the entry price is the SELL price; the
                    # fee is a cost of getting into the trade), so a
                    # flip decomposes exactly into covered-sell + open.
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

    def _short_flags(self, store: dict) -> set[str]:
        """[v1.22] Tx ids that first pushed THEIR account's position
        below zero (per-account replay — a global replay would net
        longs against shorts across accounts and flag the wrong txs)."""
        flags: set[str] = set()
        by_acc: dict[str, list[dict]] = {}
        for t in store.get("txs") or []:
            by_acc.setdefault(t.get("account_id") or "", []).append(t)
        for txs in by_acc.values():
            self._positions_raw(txs, flags)
        return flags

    def _short_warnings(self, shorts_before: set[str]) -> list[str]:
        """[v1.22] PT-BR warnings when an edit/delete left new shorts
        open (caller holds the lock, the mutation already happened)."""
        new = self._short_flags(self._store) - shorts_before
        if not new:
            return []
        tickers = sorted({(t.get("ticker") or "") for t in self._store["txs"]
                          if t.get("id") in new})
        return ["Atenção: esta alteração deixou {} transação(ões) em venda "
                "a descoberto ({}) — posições negativas, linhas 🚨 na "
                "tabela de transações.".format(
                    len(new), ", ".join(tickers) or "?")]

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
                                           "realized": 0.0,
                                           "long": 0.0, "short": 0.0})
                m["qty"] += pos["qty"]
                m["cost"] += pos["qty"] * pos["pm"]
                m["realized"] += pos["realized"]
                if pos["qty"] > 1e-9:
                    m["long"] += pos["qty"]
                elif pos["qty"] < -1e-9:
                    m["short"] += -pos["qty"]

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
            # [v1.22] A ticker held LONG in one account and SHORT in
            # another has no consolidated PM — Σ(qty·pm)/Σqty blends a
            # long base with a short entry into a number that exists in
            # no broker. Honest "—" for PM and Lucro % (qty/cost/value/
            # profit stay: value − cost is still the per-leg profit sum).
            mixed = m["long"] > 1e-9 and m["short"] > 1e-9
            row = {
                "ticker": tk,
                "name": meta.get("name") or (q.get("name") if q else "") or tk,
                "sector": meta.get("sector") or "—",
                "pm": None if mixed else
                      (_px(m["cost"] / m["qty"]) if m["qty"] else None),
                "price": _px(price),
                "qty": _qty(m["qty"]),
                "raw_qty": m["qty"],
                "short": m["qty"] < -1e-9,
                "mixed": mixed,
                "cost": _brl_auto(m["cost"]),
                "value": _brl_auto(value),
                "profit": _signed_brl(profit),
                "profit_pct": None if mixed else _signed_pct(
                    profit / abs(m["cost"]) if profit is not None
                    and abs(m["cost"]) > 1e-9 else None),
                "accounts": holders,
                # sort keys (raw floats; the formatted cells also parse)
                "_v": value,          # None = no quote → sorts last
            }
            rows.append(row)
        rows.sort(key=lambda r: -(r["_v"] if r["_v"] is not None
                                  else float("-inf")))

        # Totals + KPIs — "—" whenever ANY held ticker lacks a quote (a
        # partial patrimônio would read as a fake loss). Shorts enter
        # with negative qty/value/cost (|cost| anchors the %).
        # [v1.22] SIGNED sum: shorts have NEGATIVE market value and
        # must enter the Patrimônio — the old `if _v >= 0` filter was
        # built to skip the (now dead) -1.0 no-quote sentinel and
        # silently DROPPED every short while keeping its negative cost.
        # `complete` already gates the display when quotes are missing.
        total_cost = sum(m["cost"] for m in merged.values())
        total_value = sum(r["_v"] for r in rows if r["_v"] is not None)
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
        # [v1.22] Ascending + stable, the SAME total order as the replay
        # (date, created_at, seq — the uuid tiebreak scrambled same-
        # second rows); keep the NEWEST `limit`.
        rows.sort(key=self._tx_order_key)
        recent = rows[-limit:]               # newest `limit`, oldest first
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
