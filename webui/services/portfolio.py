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
from types import MappingProxyType
from typing import Any

from core.atomic_write import atomic_write
from webui.adapters.contract import kpi
# [v1.28.3] The SHARED price-pill payload builder — the price
# color scheme everywhere (contract.price_pill, one palette, no forked
# colors): the observados' Preço and the positions' Valor Hoje ship it;
# Máx/Mín 52s and PM stay plain ("just apply to main price").
from webui.adapters.contract import price_pill as _pill
# [v1.22] ONE ticker definition for every layer (webui/validators.py) —
# the old letters-only stem rejected B3's own ticker (B3SA3) and BDRs.
from webui.validators import TICKER_RE as _TICKER_RE

# ── formatting helpers (macro.py owns the PT-BR numerics — no forks) ─────────
from webui.services.macro import _brl2, _fmt_date, _pct

from tools.report_ops.formats import fmt_num

# ── the skill's data layer (single source of truth — same DB the Painel
# cards read; no SQL duplication in the WebUI). [v1.21] quotes_for(): the
# per-symbol variant of market_snapshot() — illiquid papers silent for
# 10+ sessions still get their LAST TRADED price (portfolio valuation
# needs the honest "Valor Hoje", not the landing-page actives window).
# [v1.28.3] range_52w(): the trailing-52-week high/low — the Painel's
# Tickers Observados "Máx/Mín 52 sem" columns.
from data_sources.b3.cotahist.query_engine import (  # noqa: E401
    quotes_for as _quotes_for,
    range_52w as _range_52w,
    series_52w as _series_52w,
)

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
            "watchlist": [], "tickers": {}, "notas": [],
            "alerts": []}


class PortfolioStoreError(RuntimeError):
    """[v1.22] A mutation was attempted while the store is degraded
    (the file on disk is corrupt/unreadable and writes are refused)."""


_MAX_QUARANTINE = 7        # newest .corrupt-<ts> copies kept as evidence
_MAX_UNDO = 20              # [v1.22.3] undo-toast stack depth (in-memory)


def _parse_store(data: Any) -> dict[str, Any]:
    """Validated store shape — anything else is corruption.

    [v1.22] Pre-v1.22 loaded leniently: a wrong-typed key was silently
    DROPPED (``{"users": {...}}`` read as "no users") and the next
    save destroyed the data on disk. Wrong shapes now raise — the
    caller quarantines instead of ever answering with a partial store.

    [v1.22.3] TX RECONCILIATION at the boundary: every numeric field of
    every tx is checked FINITE and inside its magnitude cap (a hand
    edit that plants ``1e999`` — json.loads parses it to inf — used to
    sail into the replay). Numbers stored as strings that parse are
    NORMALIZED in place (the canonical store leaves this function);
    anything unparseable/out-of-range raises like any other corruption.
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
    # [v1.22.2] Nota-import registry (dedup + undo). Optional like
    # 'tickers' — pre-v1.22.2 stores simply have no notas yet.
    if "notas" in data:
        if not isinstance(data["notas"], list) or any(
                not isinstance(x, dict) for x in data["notas"]):
            raise ValueError("'notas' deve ser uma lista de objetos")
        store["notas"] = data["notas"]
    # [v1.22.3] Price alerts (roadmap 6). Optional like 'notas'.
    if "alerts" in data:
        if not isinstance(data["alerts"], list) or any(
                not isinstance(x, dict) for x in data["alerts"]):
            raise ValueError("'alerts' deve ser uma lista de objetos")
        store["alerts"] = data["alerts"]
    for t in store["txs"]:
        _reconcile_tx(t)
    _ensure_seq(store)
    return store


# [v1.22.3] Magnitude caps the CRUD itself enforces — the SAME numbers
# guard the load path now (a store is only as good as its worst hand
# edit). Factor is the corporate-action quantity multiplier.
_QTY_MAX = 1e12
_PX_MAX = 1e9
_FACTOR_MIN, _FACTOR_MAX = 0.001, 1000.0


def _reconcile_num(value: Any, cap: float, field: str) -> float:
    """Store-boundary number check: finite, ≤ cap; strings normalized.

    Returns the canonical float. Raises ValueError on anything the
    replay must never see (NaN/±inf, out-of-range, unparseable).
    """
    f = _num(value)
    if f is None or not math.isfinite(f) or f > cap or f < -cap:
        raise ValueError(
            f"número inválido em {field!r} ({value!r}) — campo fora "
            f"dos limites ou não numérico")
    return f


def _reconcile_tx(t: dict) -> None:
    """One tx normalized + range-checked IN PLACE (see _parse_store)."""
    ttype = t.get("type")
    if ttype not in ("buy", "sell", "corp"):
        raise ValueError(f"tipo de transação inválido: {ttype!r}")
    if ttype == "corp":
        # [v1.28.5] The corp family grows by two: INPLIT (grupamento
        # COM TROCA DE TICKER — RAIZ4 → RAIZ55, the position migrates
        # old→new with qty×=f and PM÷=f, custo total intact; fator 1
        # allowed = pure ticker rename) and RIGHTS (direitos de
        # subscrição recebidos de graça — the RIGHTS ticker is the
        # tx's own ticker and the qty is the absolute quantity; no
        # factor, price locked at 0).
        if t.get("action") not in ("split", "group", "bonus",
                                   "inplit", "rights"):
            raise ValueError(f"evento corporativo inválido: {t.get('action')!r}")
        if t.get("action") == "rights":
            q = _reconcile_num(t.get("quantity"), _QTY_MAX, "quantity")
            if q <= 0:
                raise ValueError(f"quantidade de direitos inválida: {q!r}")
            t["quantity"] = q
            t["price"] = 0.0
            t["fees"] = 0.0
            t.pop("factor", None)
            t.pop("new_ticker", None)
            return
        if t.get("action") == "inplit":
            f = _reconcile_num(t.get("factor"), _FACTOR_MAX, "factor")
            nt = str(t.get("new_ticker") or "").strip().upper()
            if f < _FACTOR_MIN or f > _FACTOR_MAX:
                raise ValueError(f"fator de inplit inválido: {f!r}")
            if not _TICKER_RE.match(nt) or \
                    nt == (t.get("ticker") or "").strip().upper():
                raise ValueError(f"novo ticker de inplit inválido: {nt!r}")
            t["factor"] = f
            t["new_ticker"] = nt
            t["quantity"] = 0.0
            t["price"] = 0.0
            t["fees"] = 0.0
            return
        f = _reconcile_num(t.get("factor"), _FACTOR_MAX, "factor")
        if f < _FACTOR_MIN or f == 1.0:
            raise ValueError(f"fator de evento corporativo inválido: {f!r}")
        t["factor"] = f
        # [v1.22.4] Corp rows are SELF-DESCRIBING: nothing was traded,
        # so quantity and price canonicalize to 0 (the form shows them
        # locked at 0; pre-v1.22.4 rows without the keys gain them).
        t["quantity"] = 0.0
        t["price"] = 0.0
        t["fees"] = 0.0
        return
    q = _reconcile_num(t.get("quantity"), _QTY_MAX, "quantity")
    if q <= 0:
        raise ValueError(f"quantidade inválida: {q!r}")
    t["quantity"] = q
    p = _reconcile_num(t.get("price"), _PX_MAX, "price")
    if p < 0:
        raise ValueError(f"preço inválido: {p!r}")
    t["price"] = p
    fees = _reconcile_num(t.get("fees") or 0.0, _PX_MAX, "fees")
    if fees < 0:
        raise ValueError(f"taxas inválidas: {fees!r}")
    t["fees"] = fees


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


def _factor_br(f: float) -> str:
    """[v1.22.3] Corporate-action factor, PT-BR, trailing zeros trimmed:
    2 → '×2' · 0.5 → '×0,5' · 1.1 → '×1,1' · 1.5625 → '×1,5625'."""
    s = fmt_num(f, decimals=4)
    if "," in s:
        s = s.rstrip("0").rstrip(",")
    return "×" + s


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
        # [v1.22.3] Store revision — bumped on every _save() and every
        # actual reload; the replay memo (below) keys on it, so any
        # mutation or external edit invalidates every cached walk.
        self._rev: int = 0
        # [v1.22.3] Replay memoization (roadmap 8): account_id →
        # (rev, raw positions, short ids). _positions_raw itself stays
        # pure; _replay_for() serves the memoized copy.
        self._replay_cache: dict[str, tuple[int, dict, frozenset]] = {}
        # Filtered quote map memoization (the v1.19-fix-1 single-flight idea,
        # scoped to the tiny ticker set the portfolio needs).
        self._q_lock = threading.Lock()
        # [v1.22.3] QuoteSet immutability: the published map is a
        # MappingProxyType — every refresh builds a NEW dict and swaps
        # the reference (readers see the old or the new set, never a
        # half-mutated one; nothing outside _refresh_quotes can write).
        self._quotes: MappingProxyType | None = None
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
        # [v1.22.3] In-memory undo stack (roadmap 7 — the undo toast):
        # token → restore data. Session-scoped by design (the toast lives
        # seconds); nota imports keep their PERSISTED registry instead.
        self._undo_stack: dict[str, dict] = {}
        self._undo_order: list[str] = []
        # [v1.22.4] One-shot boot backfill: tickers stored with an empty
        # name/sector (fetched when the CVM source had less data) get a
        # background re-fetch on the first read — the v1.22.4 fallback
        # chain fills what the first attempt missed, no 🔄 clicking.
        self._meta_backfill_done = False

    def _bump_rev(self) -> None:
        """[v1.22.3] New store generation — drop every replay memo."""
        self._rev += 1
        self._replay_cache.clear()

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
        self._bump_rev()          # [v1.22.3] external edit = new generation
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
        self._bump_rev()          # [v1.22.3] mutation = new generation
        try:
            self._loaded_mtime = path.stat().st_mtime_ns
        except OSError:
            pass

    def _write_guard(self) -> dict | None:
        """None = writable; otherwise the PT-BR error payload to return."""
        if self._load_error:
            return {"ok": False, "_error": self._load_error, "status": 503}
        return None

    def _maybe_backfill_meta(self) -> None:
        """[v1.22.4] First successful load: re-fetch incomplete metadata.

        Called under the lock from _snapshot(). Spawn ONE sequencer
        thread (staggered — a big book must not stampede sqlite) that
        walks the tickers with an empty name or sector through the
        same _spawn_meta_refresh path (dedup + never-clobber-empty
        semantics included). Once per process, degraded stores skip.
        """
        if self._meta_backfill_done or self._load_error:
            return
        self._meta_backfill_done = True
        pending = [tk for tk, meta in (self._store.get("tickers") or {}).items()
                   if not (meta or {}).get("sector")
                   or not (meta or {}).get("name")]
        if not pending:
            return

        def _sequencer() -> None:
            for i, tk in enumerate(sorted(pending)):
                time.sleep(0.35 * i)          # stagger the herd
                if self._load_error:
                    return
                self._spawn_meta_refresh(tk)

        threading.Thread(target=_sequencer, daemon=True,
                         name="portfolio-meta-backfill").start()

    def _snapshot(self) -> dict[str, Any]:
        """Deep-enough copy for readers (lists of dicts are re-copied)."""
        with self._lock:
            self._maybe_reload()
            self._maybe_backfill_meta()
            return {
                "users": [dict(u) for u in self._store["users"]],
                "accounts": [dict(a) for a in self._store["accounts"]],
                "txs": [dict(t) for t in self._store["txs"]],
                "watchlist": [dict(w) for w in self._store["watchlist"]],
                "tickers": {k: dict(v) for k, v in self._store["tickers"].items()},
                "notas": [dict(n) for n in self._store.get("notas") or []],
                "alerts": [dict(x) for x in self._store.get("alerts") or []],
                "rev": self._rev,       # [v1.22.3] memoization key carrier
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

        [v1.22.3] CORPORATE ACTIONS sort FIRST within their date (the
        0/1 type priority): a desdobramento/grupamento/bonificação is
        effective BEFORE the session — the day's own trades already
        happen in post-action quantities and prices (B3 ex-date
        semantics), so the factor must hit the position before any
        same-day buy/sell replays.
        """
        return (t.get("date") or "",
                0 if t.get("type") == "corp" else 1,
                t.get("created_at") or "",
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

        [v1.22.3] The published map is an immutable MappingProxyType:
        each refresh COPIES the live map, adds the new symbols to the
        copy, and swaps the reference under _q_lock — a published set
        is never mutated in place (readers race-free by GIL-atomic
        reference swap).
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
                    self._quotes = MappingProxyType({})
                self._quotes_ok = False
                self._quotes_at = time.monotonic()
                return
            quotes = dict(self._quotes or {})
            for s in res.get("symbols", []):
                quotes[s["ticker"]] = s
            self._quotes = MappingProxyType(quotes)
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
                    changed = False
                    if meta.get("name") and meta.get("name") != cur.get("name"):
                        cur["name"] = meta["name"]
                        changed = True
                    if meta.get("sector") and meta.get("sector") != cur.get("sector"):
                        cur["sector"] = meta["sector"]
                        changed = True
                    if not changed:
                        return            # [v1.22.4] no no-op store writes
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
        """Field validation → (coerced tx fields, errors).

        [v1.22.3] A third tx type — CORP (evento corporativo: roadmap
        5): {action: split|group|bonus, factor}. No quantity/price/
        fees (nothing was traded): the replay re-bases qty ×= factor,
        PM /= factor (the custo total qty·PM is invariant — a split
        keeps the cost, a bonificação's new shares enter de graça, a
        grupamento concentrates them). The old workaround (a manual
        buy at R$ 0,00 for bonificação, or editing every earlier tx
        for a split) is dead.
        """
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
        if ttype not in ("buy", "sell", "corp"):
            errs["type"] = "Tipo deve ser compra, venda ou evento corporativo."
        out["type"] = ttype

        if ttype == "corp":
            action = str(body.get("action") or "").strip().lower()
            if not action:
                errs["action"] = ("Selecione o tipo de evento — "
                                  "desdobramento, grupamento ou bonificação.")
            elif action not in ("split", "group", "bonus", "inplit", "rights"):
                errs["action"] = ("Evento inválido — desdobramento, "
                                  "grupamento ou bonificação.")
            else:
                out["action"] = action
            if action == "rights":
                # [v1.28.5] DIREITOS DE SUBSCRIÇÃO — the rights ticker
                # IS the tx ticker and the qty is the absolute quantity
                # received (de graça, PM 0 — sell at market or let them
                # expire: a venda a R$ 0,00 on a PM-0 position is the
                # expiry, now allowed).
                q = _num(body.get("quantity"))
                if q is None or q <= 0 or q > 1e12:
                    errs["quantity"] = ("Informe a quantidade de direitos "
                                        "recebida (maior que zero).")
                else:
                    out["quantity"] = q
                out["price"] = 0.0
                out["fees"] = 0.0
            elif action == "inplit":
                # [v1.28.5] INPLIT — grupamento COM TROCA DE TICKER
                # (RAIZ4 → RAIZ55): the position migrates to the new
                # ticker with qty×=f and PM÷=f — the custo total and
                # the patrimônio stay intact (registering a fake venda
                # + compra would book phantom P&L and break both).
                # Fator 1 = pure ticker rename (no qty change).
                nt = str(body.get("new_ticker") or "").strip().upper()
                if not _TICKER_RE.match(nt):
                    errs["new_ticker"] = ("Informe o novo ticker (o código "
                                          "pós-evento, ex: RAIZ55).")
                elif nt == ticker:
                    errs["new_ticker"] = ("O novo ticker deve ser diferente "
                                          "do atual.")
                else:
                    out["new_ticker"] = nt
                factor = _num(body.get("factor"))
                if factor is None or not math.isfinite(factor):
                    errs["factor"] = ("Fator deve ser um número (ex: 0,01 = "
                                      "cada 100 ações viram 1; 1 = só troca "
                                      "o código).")
                elif factor < _FACTOR_MIN or factor > _FACTOR_MAX:
                    errs["factor"] = ("Fator deve estar entre 0,001 e 1.000.")
                else:
                    out["factor"] = factor
                out["quantity"] = 0.0
                out["price"] = 0.0
                out["fees"] = 0.0
            else:
                factor = _num(body.get("factor"))
                if factor is None or not math.isfinite(factor):
                    errs["factor"] = "Fator deve ser um número (ex: 2 para 1→2)."
                elif factor < _FACTOR_MIN or factor > _FACTOR_MAX:
                    errs["factor"] = ("Fator deve estar entre 0,001 e 1.000.")
                elif abs(factor - 1.0) < 1e-9:
                    errs["factor"] = "Fator 1 não altera nada — informe a proporção real."
                elif action == "split" and factor <= 1.0:
                    errs["factor"] = ("Desdobramento aumenta a quantidade — "
                                      "fator maior que 1 (ex: 2 = cada ação vira 2).")
                elif action == "group" and factor >= 1.0:
                    errs["factor"] = ("Grupamento reduz a quantidade — fator "
                                      "menor que 1 (ex: 0,5 = 2 ações viram 1).")
                elif action == "bonus" and factor <= 1.0:
                    errs["factor"] = ("Bonificação entrega ações novas — fator "
                                      "maior que 1 (10% → 1,1).")
                else:
                    out["factor"] = factor
                # [v1.22.4] Corp rows carry quantity/price/fees = 0 —
                # nothing was traded; the numbers make the row
                # self-describing (the form shows them locked at 0).
                out["quantity"] = 0.0
                out["price"] = 0.0
                out["fees"] = 0.0
            # date/note shared below — corp rows carry no money fields.
        else:
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
            # [v1.28.5] …EXCEPT the worthless-rights expiry: when the
            # position's PM at that point is R$ 0,00 (direitos de
            # subscrição recebidos de graça), a venda a R$ 0,00 books
            # exactly zero and removes the position — the honest way to
            # register "venceu sem valor". The replay probe below checks
            # the position state at the tx's own point in the timeline.
            if p is None or p < 0 or p > 1e9:
                errs["price"] = ("Preço não pode ser negativo — use 0 para "
                                 "bonificação (sem custo).")
            elif p == 0 and ttype == "sell":
                # The probe must slot into the timeline EXACTLY where
                # the real tx would land: update carries the original
                # created_at/seq (the merged body has them); create
                # takes the next seq + now (the same stamp create_tx
                # would write — without them the probe sorted before
                # the same-date txs and read a stale position).
                _seq = body.get("seq") if isinstance(body.get("seq"), int) \
                    else self._next_seq(store)
                probe = {
                    "id": str(body.get("id") or "__cand__"),
                    "type": "sell", "ticker": ticker, "price": 0.0,
                    "account_id": out.get("account_id")
                        or str(body.get("account_id") or ""),
                    "date": str(body.get("date") or ""),
                    "quantity": _num(body.get("quantity")) or 0.0,
                    "fees": _num(body.get("fees")) or 0.0,
                    "created_at": str(body.get("created_at") or "")
                        or (date.today().isoformat() + "T"
                            + time.strftime("%H:%M:%S")),
                    "seq": _seq,
                }
                why = self._zero_sell_error(store, probe)
                if why:
                    errs["price"] = why
                else:
                    out["price"] = 0.0
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

    def _zero_sell_error(self, store: dict, cand: dict) -> str | None:
        """[v1.28.5] Replay-probe for a SELL at R$ 0,00.

        Valid ONLY as the worthless-rights expiry: the position at the
        candidate's own point in the timeline must cover the quantity
        (no short) with a R$ 0,00 PM (no cost basis → zero realized,
        the position just vanishes). Anything else is the v1.22 guard
        again: a zero sell on a costful position books the whole cost
        as a phantom loss. The probe rides _ticker_ladder (the engine's
        own per-tx walk — never a forked numeric): the candidate gets a
        sentinel id, slots into the account's timeline by the standard
        order key, and its row's post-state tells the verdict.
        """
        acc = str(cand.get("account_id") or "")
        tk = str(cand.get("ticker") or "")
        txs = [t for t in store.get("txs") or []
               if t.get("account_id") == acc and t.get("id") != cand.get("id")]
        txs.append(cand)
        try:
            for row in self._ticker_ladder(txs, tk):
                if row.get("id") == cand.get("id"):
                    if (row.get("run_qty") or 0.0) < -1e-9:
                        return ("Venda a R$ 0,00 não pode abrir posição "
                                "negativa — a quantidade excede a posição "
                                "do ticker na data.")
                    if (row.get("run_pm") or 0.0) > 1e-9:
                        return ("Venda a R$ 0,00 só é válida quando o "
                                "preço médio é R$ 0,00 (direitos de "
                                "subscrição vencidos sem valor) — nesta "
                                "data a posição tem custo, e a venda "
                                "zerada registraria todo ele como perda "
                                "fantasma. Use o preço real de venda.")
                    return None
        except Exception:  # noqa: BLE001 — probe must never 500 the save
            pass
        return ("Venda a R$ 0,00: não foi possível validar a posição do "
                "ticker nesta data — informe o preço real de venda.")

    def _push_undo(self, kind: str, label: str, restore: dict) -> str:
        """[v1.22.3] Register a restorable mutation (caller holds the
        lock, the mutation is already saved). Returns the undo token.

        The stack is session-scoped memory (cap _MAX_UNDO): the undo
        TOAST lives seconds — anything longer belongs to the persisted
        nota registry or the .bak file. Restore payloads are plain data
        the undo() method switches on.
        """
        token = uuid.uuid4().hex[:12]
        self._undo_stack[token] = {"kind": kind, "label": label,
                                   "restore": restore}
        self._undo_order.append(token)
        while len(self._undo_order) > _MAX_UNDO:
            old = self._undo_order.pop(0)
            self._undo_stack.pop(old, None)
        return token

    def undo_mutation(self, token: str) -> dict:
        """[v1.22.3] One-shot undo of the last mutation (undo toast).

        Supported: delete_tx (re-insert with the SAME id/seq — nota
        registry links stay valid), update_tx (restore the previous
        fields), create_tx (remove it). Undo is NOT itself undoable.
        """
        with self._lock:
            guard = self._write_guard()
            if guard:
                return guard
            self._maybe_reload()
            guard = self._write_guard()
            if guard:
                return guard
            entry = self._undo_stack.pop(token, None)
            if entry is None:
                return {"ok": False,
                        "_error": "Desfazer indisponível — a ação expirou "
                                  "(o servidor reiniciou ou outra ação "
                                  "a substituiu).", "status": 404}
            if token in self._undo_order:
                self._undo_order.remove(token)
            data = entry["restore"]
            try:
                if entry["kind"] == "delete_tx":
                    # Re-insert at the original seq position (insertion
                    # order = seq order — a stable sort restores it).
                    self._store["txs"].append(dict(data["tx"]))
                    self._store["txs"].sort(
                        key=lambda t: (t.get("seq") or 0))
                    self._ensure_ticker_meta(self._store,
                                             data["tx"]["ticker"])
                    self._save()
                elif entry["kind"] == "update_tx":
                    tx = next((t for t in self._store["txs"]
                               if t.get("id") == data["id"]), None)
                    if tx is None:
                        return {"ok": False, "_error":
                                "Transação não encontrada — nada a desfazer.",
                                "status": 404}
                    tx.update(data["before"])
                    self._save()
                elif entry["kind"] == "create_tx":
                    before = len(self._store["txs"])
                    self._store["txs"] = [t for t in self._store["txs"]
                                          if t.get("id") != data["id"]]
                    if len(self._store["txs"]) == before:
                        return {"ok": False, "_error":
                                "Transação não encontrada — nada a desfazer.",
                                "status": 404}
                    self._save()
                else:
                    return {"ok": False, "_error": "Ação não desfazível.",
                            "status": 400}
            except PortfolioStoreError as e:
                return {"ok": False, "_error": str(e), "status": 503}
        self._syslog("info", f"desfeito: {entry['label']}")
        out: dict[str, Any] = {"ok": True, "label": entry["label"]}
        shorts = self._short_flags(self._store)
        warnings = self._short_warnings(shorts)
        if warnings:
            out["warnings"] = warnings
        return out

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
            # [v1.28.5] An inplit also introduces the NEW ticker to
            # the metadata map (name/sector fetch) — the position lands
            # there the moment this tx exists.
            if tx.get("type") == "corp" and tx.get("action") == "inplit" \
                    and tx.get("new_ticker"):
                self._ensure_ticker_meta(self._store, tx["new_ticker"])
            self._save()
            # [v1.22.3] Undo toast — removing what was just created.
            label = self._tx_label(tx)
            token = self._push_undo("create_tx", label, {"id": tx["id"]})
        self._syslog("info", self._tx_log(tx, "registrada"))
        return {"ok": True, "tx": tx, "undo_token": token,
                "undo_label": label}

    @staticmethod
    def _tx_label(tx: dict) -> str:
        """[v1.22.3] Short PT-BR label for the undo toast."""
        if tx.get("type") == "corp":
            names = {"split": "desdobramento", "group": "grupamento",
                     "bonus": "bonificação",
                     # [v1.28.5] the two new corp actions
                     "inplit": "inplit", "rights": "direitos"}
            if tx.get("action") == "rights":
                return (f"direitos de subscrição: {_qty(tx['quantity'])} "
                        f"{tx['ticker']} ({_fmt_date(tx.get('date'))})")
            if tx.get("action") == "inplit":
                return (f"inplit {_factor_br(tx.get('factor') or 0.0)} "
                        f"{tx['ticker']} → {tx.get('new_ticker')} "
                        f"({_fmt_date(tx.get('date'))})")
            return (f"{names.get(tx.get('action'), 'evento')} "
                    f"{_factor_br(tx.get('factor') or 0.0)} {tx['ticker']} "
                    f"({_fmt_date(tx.get('date'))})")
        verb = "compra" if tx.get("type") == "buy" else "venda"
        return (f"{verb} de {_qty(tx['quantity'])} {tx['ticker']} "
                f"({_fmt_date(tx.get('date'))})")

    @staticmethod
    def _tx_log(tx: dict, verb: str) -> str:
        """[v1.22.3] syslog line for any tx type."""
        if tx.get("type") == "corp":
            if tx.get("action") == "rights":
                return (f"direitos de subscrição {verb}: "
                        f"{_qty(tx['quantity'])} {tx['ticker']} "
                        f"({_fmt_date(tx.get('date'))})")
            if tx.get("action") == "inplit":
                return (f"inplit {verb}: {tx['ticker']} → "
                        f"{tx.get('new_ticker')} "
                        f"{_factor_br(tx.get('factor') or 0.0)} "
                        f"({_fmt_date(tx.get('date'))})")
            return f"evento corporativo {verb}: {tx['ticker']} " \
                   f"{_factor_br(tx.get('factor') or 0.0)} " \
                   f"({_fmt_date(tx.get('date'))})"
        head = "compra" if tx.get("type") == "buy" else "venda"
        return (f"{head} {verb}: {_qty(tx['quantity'])} {tx['ticker']} "
                f"@ {_px(tx['price'])}"
                + (" (bonificação)" if not tx.get("price") else ""))

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
            before = dict(tx)                 # [v1.22.3] undo snapshot
            merged = dict(tx)
            merged.update({k: v for k, v in body.items()
                           if k in ("account_id", "ticker", "type",
                                    "quantity", "price", "fees", "date",
                                    "note", "action", "factor",
                                    "new_ticker")})
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
            # [v1.28.5] Corp-key sanitation: each action owns its own
            # key set (rights → quantity; inplit → factor + new_ticker;
            # the rest → factor). Editing one action into another must
            # DROP the stale keys from the STORED tx too — tx.update
            # only overwrites what merged still carries, so the pops
            # happen on BOTH dicts (a rights tx with a lingering
            # new_ticker would confuse the replay reconcile). A corp
            # edited into a buy/sell drops them all.
            stale = (("factor", "new_ticker")
                     if merged.get("type") == "corp"
                     else ("action", "factor", "new_ticker"))
            tx.update(merged)
            for _k in stale:
                # absent OR blank ("") — the form posts "" for the
                # fields the current action does not use
                if _k not in merged or merged[_k] in (None, ""):
                    tx.pop(_k, None)
                    merged.pop(_k, None)
            self._ensure_ticker_meta(self._store, tx["ticker"])
            if tx.get("type") == "corp" and tx.get("action") == "inplit" \
                    and tx.get("new_ticker"):
                self._ensure_ticker_meta(self._store, tx["new_ticker"])
            self._save()
            label = self._tx_label(tx)
            token = self._push_undo(
                "update_tx", label,
                {"id": tx_id, "before": before})
            warnings = self._short_warnings(shorts_before)
        self._syslog("info", f"transação atualizada: {tx['ticker']} "
                             f"{_fmt_date(tx['date'])}")
        out: dict[str, Any] = {"ok": True, "tx": tx,
                               "undo_token": token, "undo_label": label}
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
            label = self._tx_label(tx)
            token = self._push_undo(
                "delete_tx", label, {"tx": dict(tx)})
            warnings = self._short_warnings(shorts_before)
        self._syslog("info", f"transação excluída: {tx['ticker']} "
                             f"{_fmt_date(tx['date'])}")
        out: dict[str, Any] = {"ok": True, "undo_token": token,
                               "undo_label": label}
        if warnings:
            out["warnings"] = warnings
        return out

    # ════════════════════════════════════════════════════════════════════════
    # Notas de Corretagem — import (bulk, dedup, single save) / undo
    # [v1.22.2] webui/services/nota_import.py owns the PDF → trades
    # parsing; THIS method owns the write: all-or-nothing, one atomic
    # _save, a notas registry row keyed (cnpj|broker, nº nota, pregão)
    # for dedup + undo, and the per-trade validation reused verbatim
    # from _validate_tx (an import is just many txs born together).
    # ════════════════════════════════════════════════════════════════════════

    @staticmethod
    def _nota_key(cnpj: Any, nota: Any, pregao: Any) -> tuple[str, str, str]:
        """Dedup identity: broker CNPJ (falls back to broker name) +
        nº nota + pregão. The same nota in two layouts (XP vs modelo
        B3) lands on the SAME key — importing both is the classic
        double-count and gets refused."""
        return ((str(cnpj or "").strip() or "SEM-CNPJ"),
                str(nota or "").strip(), str(pregao or "").strip())

    def nota_dedup_status(self, cnpj: str, nota: str,
                          pregao: str) -> dict[str, Any]:
        """Read-only pre-check for the preview UI (commit re-checks
        under the lock — the preview is advisory, the commit is law)."""
        key = self._nota_key(cnpj, nota, pregao)
        for n in self._snapshot()["notas"]:
            if self._nota_key(n.get("broker_cnpj"), n.get("nota"),
                              n.get("pregao")) == key:
                return {"imported": True, "existing": n}
        return {"imported": False}

    def import_nota(self, body: dict) -> dict:
        """Bulk tx insert from a parsed nota — all-or-nothing.

        Body: {account_id, broker, broker_cnpj, nota, pregao (ISO),
        client_name?, fees_total?, irrf?, trades: [{ticker, type,
        quantity, price, fees, date, note?, day?}]}. Errors come back
        per trade row ({"errors": {"trades": {row: {field: msg}}}}) —
        the same PT-BR messages the single-tx form produces.
        """
        with self._lock:
            guard = self._write_guard()
            if guard:
                return guard
            self._maybe_reload()
            guard = self._write_guard()
            if guard:
                return guard
            store = self._store

            account = self._account(store, str(body.get("account_id") or ""))
            if account is None:
                return {"ok": False, "_error": "Selecione uma conta "
                        "válida para importar a nota."}
            trades = body.get("trades")
            if not isinstance(trades, list) or not trades:
                return {"ok": False, "_error": "Nenhuma negociação para "
                        "importar."}

            key = self._nota_key(body.get("broker_cnpj"), body.get("nota"),
                                 body.get("pregao"))
            for n in store.get("notas") or []:
                if self._nota_key(n.get("broker_cnpj"), n.get("nota"),
                                  n.get("pregao")) == key:
                    return {"ok": False, "status": 409,
                            "_error": "Esta nota já foi importada "
                            f"({n.get('nota')} · {n.get('broker')} · "
                            f"{_fmt_date(n.get('pregao'))}) — use "
                            "\u21a9 Desfazer na lista de notas se quiser "
                            "refazer."}

            # Validate every trade BEFORE writing anything (all-or-nothing).
            rows: list[dict] = []
            errs: dict[str, dict[str, str]] = {}
            for i, t in enumerate(trades):
                if not isinstance(t, dict):
                    errs[str(i)] = {"ticker": "Negócio inválido."}
                    continue
                fields, e = self._validate_tx(store, {
                    "account_id": account["id"],
                    "ticker": t.get("ticker"),
                    "type": t.get("type") or t.get("side"),
                    "quantity": t.get("quantity"),
                    "price": t.get("price"),
                    "fees": t.get("fees"),
                    "date": t.get("date") or body.get("pregao"),
                    "note": t.get("note") or "",
                })
                if e:
                    errs[str(i)] = e
                else:
                    rows.append(fields)
            if errs:
                return {"ok": False, "errors": {"trades": errs}}

            # One atomic save: txs + the notas registry row.
            nota_id = _new_id()
            tx_ids: list[str] = []
            seq = self._next_seq(store)
            stamp = date.today().isoformat() + "T" + \
                time.strftime("%H:%M:%S")
            note_tag = (f"NC {body.get('nota')} · "
                        f"{str(body.get('broker') or '')[:24]} · "
                        f"{_fmt_date(body.get('pregao'))}")
            for fields in rows:
                tx = {"id": _new_id(), "seq": seq,
                      "created_at": stamp, **fields,
                      "note": (fields.get("note") or note_tag)[:200]}
                tx_ids.append(tx["id"])
                seq += 1
                store["txs"].append(tx)
                self._ensure_ticker_meta(store, tx["ticker"])
            store.setdefault("notas", []).append({
                "id": nota_id,
                "broker": str(body.get("broker") or "")[:60],
                "broker_cnpj": key[0],
                "nota": key[1], "pregao": key[2],
                "client_name": str(body.get("client_name") or "")[:60],
                "account_id": account["id"],
                "tx_ids": tx_ids, "trade_count": len(tx_ids),
                "fees_total": round(float(body.get("fees_total") or 0.0), 2),
                "irrf": body.get("irrf"),
                "imported_at": stamp,
            })
            self._save()
        self._syslog("info", f"nota {key[1]} importada: {len(tx_ids)} "
                             f"negócios ({key[0]}, "
                             f"{_fmt_date(key[2])})")
        return {"ok": True, "created": len(tx_ids), "nota_id": nota_id}

    def undo_import(self, nota_id: str) -> dict:
        """Remove a nota's txs + its registry row (the import undo)."""
        with self._lock:
            guard = self._write_guard()
            if guard:
                return guard
            self._maybe_reload()
            guard = self._write_guard()
            if guard:
                return guard
            store = self._store
            nota = next((n for n in store.get("notas") or []
                         if n.get("id") == nota_id), None)
            if nota is None:
                return {"ok": False, "_error": "Nota importada não "
                        "encontrada.", "status": 404}
            shorts_before = self._short_flags(store)
            ids = set(nota.get("tx_ids") or [])
            alive = [t for t in store["txs"] if t.get("id") in ids]
            store["txs"] = [t for t in store["txs"]
                            if t.get("id") not in ids]
            store["notas"] = [n for n in store.get("notas") or []
                              if n.get("id") != nota_id]
            self._save()
            warnings = self._short_warnings(shorts_before)
        self._syslog("info", f"importação da nota {nota.get('nota')} "
                             "desfeita")
        # [v1.22.2] The honest count: txs actually removed (a manually
        # deleted tx is not removed again — the registry row still goes).
        out: dict[str, Any] = {"ok": True, "removed": len(alive)}
        if warnings:
            out["warnings"] = warnings
        return out

    def notas_registry(self, account_id: str | None = None) -> dict:
        """The imported-notas list for the account view (undo UI)."""
        snap = self._snapshot()
        acc_by_id = {a["id"]: a for a in snap["accounts"]}
        rows = []
        for n in snap["notas"]:
            if account_id and n.get("account_id") != account_id:
                continue
            acc = acc_by_id.get(n.get("account_id") or "")
            alive = sum(1 for t in snap["txs"]
                        if t.get("id") in set(n.get("tx_ids") or []))
            rows.append({**n, "account_name": acc["name"] if acc else "—",
                         "alive": alive,
                         "imported_at_br": (n.get("imported_at") or "")[:10]
                         .replace("-", "/")})
        rows.sort(key=lambda n: (n.get("pregao") or "",
                                 n.get("nota") or ""), reverse=True)
        return {"ok": True, "notas": rows}

    # ════════════════════════════════════════════════════════════════════════
    # Ledger — the paginated/filtered tx endpoint (roadmap 7)
    # [v1.22.3] positions() ships only page-1 (50 rows) + the count;
    # the Transações view pages through THIS from the filter bar.
    # ════════════════════════════════════════════════════════════════════════

    _TX_TYPES = ("buy", "sell", "corp")

    def txs_page(self, scope: str, page: int, per_page: int,
                 ticker: str = "", ttype: str = "",
                 date_from: str = "", date_to: str = "",
                 query: str = "") -> dict:
        """One ledger page + the short flags for the visible rows."""
        if ttype and ttype not in self._TX_TYPES:
            return {"ok": False, "_error": "Tipo inválido — compra, venda "
                                           "ou evento.", "status": 400}
        snap = self._snapshot()
        accounts = self._scope_accounts(snap, scope)
        account_ids = {a["id"] for a in accounts}
        if not account_ids:
            return {"ok": True, "rows": [], "total": 0, "page": 1,
                    "pages": 0, "per_page": per_page}
        # Short flags once per request (the memo makes this cheap).
        shorts: set[str] = set()
        by_acc: dict[str, list[dict]] = {}
        for t in snap["txs"]:
            if t.get("account_id") in account_ids:
                by_acc.setdefault(t.get("account_id") or "", []).append(t)
        for aid, txs in by_acc.items():
            shorts |= set(self._replay_for(aid, txs)[1])
        rows, total = self._tx_rows(
            snap, account_ids, limit=per_page, short_ids=shorts,
            page=page, ticker=ticker, ttype=ttype,
            date_from=date_from, date_to=date_to, query=query)
        pages = max(1, math.ceil(total / per_page)) if total else 0
        return {"ok": True, "rows": rows, "total": total,
                "page": min(page, pages) if pages else 1,
                "pages": pages, "per_page": per_page}

    # ════════════════════════════════════════════════════════════════════════
    # Export / restore — the Gerenciar backup pair (roadmap 7)
    # ════════════════════════════════════════════════════════════════════════

    def export_store(self) -> dict[str, Any]:
        """The raw store (JSON download — the client saves the file)."""
        return self._snapshot()

    def restore_store(self, payload: Any) -> dict:
        """Replace the whole store with a user-supplied JSON.

        [v1.22.3] Same contract as every write: validate EVERYTHING
        first (_parse_store — the tx reconciliation included), refuse
        on any error with the store untouched, then swap + ONE atomic
        save (the .bak of the current file is automatic in _save).
        """
        if not isinstance(payload, dict):
            return {"ok": False, "_error": "Conteúdo inválido — esperado "
                                           "um objeto JSON da carteira."}
        with self._lock:
            guard = self._write_guard()
            if guard:
                return guard
            try:
                candidate = _parse_store(json.loads(json.dumps(payload)))
            except Exception as e:
                return {"ok": False,
                        "_error": "Arquivo rejeitado — não é uma carteira "
                                  f"válida ({e}). Nada foi alterado."}
            self._store = candidate
            self._save()
        self._syslog("info", "carteira restaurada de um arquivo "
                             f"({len(candidate['txs'])} transações)")
        return {"ok": True,
                "counts": {"users": len(candidate["users"]),
                           "accounts": len(candidate["accounts"]),
                           "txs": len(candidate["txs"])}}

    # ════════════════════════════════════════════════════════════════════════
    # Alerts — price thresholds over the quote map (roadmap 6)
    # ════════════════════════════════════════════════════════════════════════

    def _validate_alert(self, store: dict, body: dict) -> tuple[dict, dict]:
        errs: dict[str, str] = {}
        out: dict[str, Any] = {}
        ticker = str(body.get("ticker") or "").strip().upper()
        if not _TICKER_RE.match(ticker):
            errs["ticker"] = "Ticker inválido — use o padrão B3."
        else:
            out["ticker"] = ticker
        op = str(body.get("op") or "").strip().lower()
        if op not in ("above", "below"):
            errs["op"] = "Condição inválida — acima ou abaixo."
        else:
            out["op"] = op
        price = _num(body.get("price"))
        if price is None or price <= 0 or price > _PX_MAX:
            errs["price"] = "Preço deve ser um número maior que zero."
        else:
            out["price"] = price
        return out, errs

    def add_alert(self, body: dict) -> dict:
        with self._lock:
            guard = self._write_guard()
            if guard:
                return guard
            self._maybe_reload()
            guard = self._write_guard()
            if guard:
                return guard
            fields, errs = self._validate_alert(self._store, body)
            if errs:
                return {"ok": False, "errors": errs}
            # One alert per (ticker, op) — the new price replaces the old
            # (two "PETR4 above" thresholds is a self-argument, not a need).
            self._store.setdefault("alerts", [])
            self._store["alerts"] = [
                a for a in self._store["alerts"]
                if not (a.get("ticker") == fields["ticker"]
                        and a.get("op") == fields["op"])]
            alert = {"id": _new_id(),
                     "note": str(body.get("note") or "").strip()[:120],
                     "created_at": date.today().isoformat(), **fields}
            self._store["alerts"].append(alert)
            self._save()
        self._syslog("info", f"alerta criado: {alert['ticker']} "
                             f"{'acima' if alert['op'] == 'above' else 'abaixo'} "
                             f"de {_px(alert['price'])}")
        return {"ok": True, "alert": alert}

    def delete_alert(self, alert_id: str) -> dict:
        with self._lock:
            guard = self._write_guard()
            if guard:
                return guard
            self._maybe_reload()
            guard = self._write_guard()
            if guard:
                return guard
            alerts = self._store.get("alerts") or []
            if not any(a.get("id") == alert_id for a in alerts):
                return {"ok": False, "_error": "Alerta não encontrado.",
                        "status": 404}
            self._store["alerts"] = [a for a in alerts
                                     if a.get("id") != alert_id]
            self._save()
        self._syslog("info", "alerta removido")
        return {"ok": True}

    def alerts_status(self) -> dict:
        """Every alert + its live evaluation (the quote map is warm)."""
        snap = self._snapshot()
        tickers = {a.get("ticker") for a in snap["alerts"] if a.get("ticker")}
        if tickers:
            self._refresh_quotes(set(tickers))
        quotes_ok = bool(self._quotes_ok)
        rows = []
        for a in snap["alerts"]:
            q = self._quote(a.get("ticker") or "")
            price = q.get("close") if q else None
            triggered = None
            if price is not None:
                triggered = (price >= a["price"] if a.get("op") == "above"
                             else price <= a["price"])
            rows.append({
                **a,
                "price_br": _px(a.get("price")),
                "current": _px(price),
                "triggered": triggered,   # None = no quote (unknown)
                "quote_date": (q.get("refdate") or None) if q else None,
            })
        rows.sort(key=lambda r: (r.get("triggered") is not True,
                                 r.get("ticker") or ""))
        out = {"ok": True, "alerts": rows, "quotes_ok": quotes_ok}
        if not quotes_ok:
            out["quotes_note"] = _COTAHIST_ERR
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
                # [v1.22.3] Price alerts (the Gerenciar + banner UI).
                "alerts": snap.get("alerts") or [],
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
            # [v1.22.3] CORPORATE ACTION — desdobramento / grupamento /
            # bonificação: re-base the quantity and the PM, keep the
            # cost (qty·pm) invariant. No money moved, nothing realized;
            # the SHORT side re-bases identically (a negative qty ×
            # factor stays negative, its entry PM divides). A corp event
            # on a FLAT position is a no-op (nothing to re-base — the
            # tx stays in the ledger for the record).
            # Same-day semantics: _tx_order_key replays corp BEFORE the
            # day's trades (the session already quotes post-action).
            # [v1.28.5] Two new actions:
            #   INPLIT — grupamento COM TROCA DE TICKER (RAIZ4 → RAIZ55):
            #     the position MIGRATES to the new ticker, qty×=f and
            #     PM÷=f (custo total and patrimônio intact — the very
            #     case a fake venda+compra would break). The realized
            #     P&L STAYS on the origin ticker's row (it is history
            #     that happened under the old code; the ladder and the
            #     IR walk mirror this). Factor 1 = pure ticker rename.
            #   RIGHTS — direitos de subscrição recebidos de graça: the
            #     tx's OWN ticker is the rights ticker; qty lands at
            #     PM R$ 0,00 (buy-at-zero math — cost only dilutes).
            if t.get("type") == "corp":
                action = t.get("action")
                f = float(t.get("factor") or 1.0)
                if action == "inplit":
                    nt = (t.get("new_ticker") or "").strip().upper()
                    if (nt and nt != tk and abs(pos["qty"]) > 1e-9
                            and f > 0):
                        tgt = out.setdefault(
                            nt, {"qty": 0.0, "pm": 0.0, "realized": 0.0})
                        moved_qty = pos["qty"] * f
                        moved_cost = pos["qty"] * pos["pm"]  # invariant
                        total_cost = tgt["qty"] * tgt["pm"] + moved_cost
                        tgt["qty"] += moved_qty
                        tgt["pm"] = (total_cost / tgt["qty"]
                                     if abs(tgt["qty"]) > 1e-9 else 0.0)
                        pos["qty"] = 0.0
                        pos["pm"] = 0.0
                elif action == "rights":
                    q = float(t.get("quantity") or 0.0)
                    if q > 0:
                        if pos["qty"] >= -1e-9:
                            total_cost = pos["qty"] * pos["pm"]
                            pos["qty"] += q
                            pos["pm"] = (total_cost / pos["qty"]
                                         if pos["qty"] > 0 else 0.0)
                        else:
                            # free shares against a short: cover at 0
                            covered = min(q, -pos["qty"])
                            pos["realized"] += covered * pos["pm"]
                            pos["qty"] += q
                            if pos["qty"] > 1e-9:
                                pos["pm"] = 0.0   # excess arrived free
                elif abs(pos["qty"]) > 1e-9 and f > 0:
                    pos["qty"] *= f
                    pos["pm"] = pos["pm"] / f
                continue
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

    def _ticker_ladder(self, txs: list[dict],
                       ticker: str) -> list[dict[str, Any]]:
        """[v1.22.3] Per-tx PM ladder for ONE ticker (the position-detail
        drawer, roadmap 7).

        Mirrors ``_positions_raw`` branch-for-branch (same file, same
        engine — never a forked numeric), emitting the running
        (qty, PM, realized delta) after EVERY step so the drawer shows
        how each trade moved the position. The final row's state MUST
        equal ``_positions_raw``'s output for the same txs — pinned by
        the regression suite (ladder final == engine final).
        """
        tk = (ticker or "").strip().upper()
        # [v1.28.5] INPLIT rows concern BOTH tickers: the origin (the
        # position leaves) and the TARGET (the position arrives — the
        # drawer of the new ticker must show where it came from; the
        # ladder's final state stays pinned to the engine's, which does
        # the same move). The ARRIVAL (qty, pm) only the origin's own
        # timeline knows — so it is replayed by the ENGINE ITSELF on
        # the txs strictly before the event (prefix walks; k events →
        # k replays, and no forked numeric ever exists).
        ordered = sorted(txs, key=self._tx_order_key)
        arrivals: dict[str, dict[str, float]] = {}
        for _i, _t in enumerate(ordered):
            if (_t.get("type") == "corp" and _t.get("action") == "inplit"
                    and (_t.get("new_ticker") or "").strip().upper() == tk
                    and (_t.get("ticker") or "").strip().upper() != tk):
                pre = self._positions_raw(ordered[:_i])
                og = pre.get((_t.get("ticker") or "").strip().upper()) or {}
                oq, op = float(og.get("qty") or 0.0), float(og.get("pm") or 0.0)
                f = float(_t.get("factor") or 1.0)
                if abs(oq) > 1e-9 and f > 0:
                    arrivals[_t.get("id") or ""] = {"qty": oq * f,
                                                    "pm": op / f}
        steps = [t for t in ordered
                 if (t.get("ticker") or "").upper() == tk
                 or (t.get("type") == "corp" and t.get("action") == "inplit"
                     and (t.get("new_ticker") or "").strip().upper() == tk)]
        pos = {"qty": 0.0, "pm": 0.0, "realized": 0.0}
        rows: list[dict[str, Any]] = []
        for t in steps:
            delta = 0.0
            row_note = t.get("note") or ""
            if t.get("type") == "corp":
                action = t.get("action") or ""
                f = float(t.get("factor") or 1.0)
                if action == "inplit":
                    nt = (t.get("new_ticker") or "").strip().upper()
                    if nt == tk:
                        # rendering the TARGET: the migrated position
                        # arrives (blended with anything already here)
                        arr = arrivals.get(t.get("id") or "")
                        if arr:
                            total_cost = (pos["qty"] * pos["pm"]
                                          + arr["qty"] * arr["pm"])
                            pos["qty"] += arr["qty"]
                            pos["pm"] = (total_cost / pos["qty"]
                                         if abs(pos["qty"]) > 1e-9 else 0.0)
                    elif abs(pos["qty"]) > 1e-9:
                        # rendering the ORIGIN: the position left
                        pos["qty"] = 0.0
                        pos["pm"] = 0.0
                elif action == "rights":
                    q = float(t.get("quantity") or 0.0)
                    if q > 0:
                        if pos["qty"] >= -1e-9:
                            total_cost = pos["qty"] * pos["pm"]
                            pos["qty"] += q
                            pos["pm"] = (total_cost / pos["qty"]
                                         if pos["qty"] > 0 else 0.0)
                        else:
                            covered = min(q, -pos["qty"])
                            delta = covered * pos["pm"]
                            pos["realized"] += delta
                            pos["qty"] += q
                            if pos["qty"] > 1e-9:
                                pos["pm"] = 0.0
                elif abs(pos["qty"]) > 1e-9 and f > 0:
                    pos["qty"] *= f
                    pos["pm"] = pos["pm"] / f
            else:
                q = float(t.get("quantity") or 0.0)
                p = float(t.get("price") or 0.0)
                fees = float(t.get("fees") or 0.0)
                if t.get("type") == "buy":
                    if pos["qty"] >= -1e-9:
                        total_cost = pos["qty"] * pos["pm"] + q * p + fees
                        pos["qty"] += q
                        pos["pm"] = total_cost / pos["qty"] \
                            if pos["qty"] > 0 else 0.0
                    else:
                        covered = min(q, -pos["qty"])
                        excess = q - covered
                        fee_cov = fees * (covered / q) if q > 0 else fees
                        fee_exc = fees - fee_cov
                        delta = covered * (pos["pm"] - p) - fee_cov
                        pos["realized"] += delta
                        pos["qty"] += q
                        if pos["qty"] > 1e-9:
                            pos["pm"] = ((p * excess + fee_exc) / excess
                                         if excess > 1e-9 else 0.0)
                else:
                    if pos["qty"] >= -1e-9:
                        covered = min(q, pos["qty"])
                        delta = covered * (p - pos["pm"]) - fees
                        pos["realized"] += delta
                        pos["qty"] -= q
                        if pos["qty"] < -1e-9:
                            pos["pm"] = p
                    else:
                        old = -pos["qty"]
                        pos["pm"] = (old * pos["pm"] + q * p) / (old + q)
                        pos["qty"] -= q
                        delta = -fees
                        pos["realized"] -= fees
            rows.append({
                "id": t.get("id") or "",
                "date": t.get("date") or "",
                "type": t.get("type") or "",
                "action": t.get("action") or "",
                "factor": t.get("factor"),
                # [v1.28.5] rights rows carry NO factor (the qty is the
                # story); inplit rows carry the destination ticker.
                "factor_br": _factor_br(t.get("factor") or 0.0)
                if t.get("type") == "corp"
                and t.get("action") != "rights" else None,
                "new_ticker": t.get("new_ticker")
                if t.get("type") == "corp" and t.get("action") == "inplit"
                else None,
                "qty": t.get("quantity"),
                "price": t.get("price"),
                "fees": t.get("fees") or 0.0,
                "delta_realized": round(delta, 2),
                "run_qty": pos["qty"],
                "run_pm": pos["pm"],
                "note": row_note,
            })
        return rows

    def _short_flags(self, store: dict) -> set[str]:
        """[v1.22] Tx ids that first pushed THEIR account's position
        below zero (per-account replay — a global replay would net
        longs against shorts across accounts and flag the wrong txs).

        [v1.22.3] Rides the replay memo (the flags depend only on the
        account's txs; the store revision invalidates with them).
        """
        flags: set[str] = set()
        by_acc: dict[str, list[dict]] = {}
        for t in store.get("txs") or []:
            by_acc.setdefault(t.get("account_id") or "", []).append(t)
        for aid, txs in by_acc.items():
            _, shorts = self._replay_for(aid, txs)
            flags |= set(shorts)
        return flags

    def _replay_for(self, account_id: str,
                    txs: list[dict]) -> tuple[dict[str, dict[str, float]],
                                              frozenset]:
        """[v1.22.3] Memoized per-account replay (roadmap 8).

        Key: (account_id, store revision) — every mutation/reload bumps
        the revision in _save()/_maybe_reload(), so a cached walk can
        never outlive the data it was computed from. Returns FRESH
        copies (the caller may not mutate the cache — the same rule as
        _snapshot). The pure _positions_raw stays the engine; this is
        only the serving layer.
        """
        hit = self._replay_cache.get(account_id)
        if hit is not None and hit[0] == self._rev:
            raw, shorts = hit[1], hit[2]
            return ({tk: dict(p) for tk, p in raw.items()}, shorts)
        shorts: set[str] = set()
        raw = self._positions_raw(txs, shorts)
        frozen = frozenset(shorts)
        self._replay_cache[account_id] = (self._rev, raw, frozen)
        # Cache the ORIGINALS (never handed out again) — the return
        # above/below is always a copy.
        return ({tk: dict(p) for tk, p in raw.items()}, frozen)

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
        # [v1.22.3] _replay_for: the memoized per-account walk (store-
        # revision keyed); merged aggregates collect into lists and sum
        # with math.fsum (catastrophic-cancellation-free accumulation).
        merged: dict[str, dict[str, Any]] = {}
        by_account: dict[str, dict[str, dict[str, float]]] = {}
        short_ids: set[str] = set()
        for acc in accounts:
            acc_txs = [t for t in txs if t.get("account_id") == acc["id"]]
            if not acc_txs:
                continue
            raw, acc_shorts = self._replay_for(acc["id"], acc_txs)
            by_account[acc["id"]] = raw
            short_ids |= set(acc_shorts)
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
            # [v1.22.3] Per-symbol quote date (roadmap 7): an illiquid
            # paper's "Valor Hoje" is its LAST TRADED session, which may
            # lag the map's session_date — the cell carries its own date
            # so the UI can say "cotação de 21/11".
            qdate = (q.get("refdate") or "") if q else ""
            row = {
                "ticker": tk,
                "name": meta.get("name") or (q.get("name") if q else "") or tk,
                "sector": meta.get("sector") or "—",
                "pm": None if mixed else
                      (_px(m["cost"] / m["qty"]) if m["qty"] else None),
                "price": _px(price),
                # [v1.28.3] the Valor Hoje (the row's MAIN price)
                # ships the price-band pill — PM stays plain text (the
                # "just apply to main price" rule; PM is a cost basis,
                # not a market price).
                "price_pill": _pill(price),
                "quote_date": qdate or None,
                "stale_quote": bool(qdate and self._session_date
                                    and qdate != self._session_date),
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
        # [v1.22.3] fsum aggregates + GROSS EXPOSURE KPIs (roadmap 7):
        # long = Σ positive market values, short = Σ |negative| — the
        # exposure story a short book needs (patrimônio nets them).
        total_cost = math.fsum(m["cost"] for m in merged.values())
        total_value = math.fsum(r["_v"] for r in rows
                                if r["_v"] is not None)
        total_realized = math.fsum(m["realized"] for m in merged.values())
        gross_long = math.fsum(r["_v"] for r in rows
                               if r["_v"] is not None and r["_v"] > 0)
        gross_short = math.fsum(-r["_v"] for r in rows
                                if r["_v"] is not None and r["_v"] < 0)
        has_short = any(m["qty"] < -1e-9 for m in merged.values())
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
                "(taxas de compra incluídas no PM; eventos corporativos "
                "re-basam quantidade e PM sem alterar o custo total)."),
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
        # [v1.22.3] Exposure cards only when a short book exists — for
        # a long-only book they would just repeat Patrimônio twice.
        if has_short:
            kpis.append(kpi("Exposição long",
                            _brl_auto(gross_long) if complete else "—",
                            "Soma dos valores de mercado das posições "
                            "compradas (bruto, sem abater os shorts)."))
            kpis.append(kpi("Exposição short",
                            _brl_auto(gross_short) if complete else "—",
                            "Soma dos valores absolutos das posições "
                            "vendidas a descoberto (entram negativas no "
                            "patrimônio)."))

        tx_rows, tx_total = self._tx_rows(snap, account_ids, limit=50,
                                          short_ids=short_ids)
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
                "gross_long": _brl_auto(gross_long) if complete else "—",
                "gross_short": _brl_auto(gross_short) if complete else "—",
            },
            # [v1.22.3] The ledger page-1 (50) + the full count — the
            # Transações view paginates via GET /txs from here on.
            "txs": tx_rows,
            "tx_total": tx_total,
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
                 limit: int = 200, short_ids: set[str] | None = None,
                 *, page: int = 1,
                 ticker: str = "", ttype: str = "",
                 date_from: str = "", date_to: str = "",
                 query: str = "") -> tuple[list[dict[str, Any]], int]:
        """Transactions for the scope — chronological ASC (oldest first).

        [v1.21 fix 1] The default order is date ASCENDING (the ledger
        reading order); the 200-row cap keeps the MOST RECENT 200 and
        then flips them for display. Flags: ``short`` (this sell first
        pushed the position below zero — 🚨) and ``zero`` (price
        R$ 0,00 — bonificação — ⚠️).

        [v1.22.3] FILTERS + PAGINATION (roadmap 7): ticker / type
        (buy|sell|corp) / date window / free-text (ticker or note,
        case-insensitive) narrow BEFORE paging; ``page`` is 1-based
        over the FILTERED list, newest-last, page size = limit. Returns
        (page rows, filtered total) so the UI can render "1 de 4 · 173
        transações". The old behavior (newest 200, oldest first) is
        page 1 with no filters and limit=200.
        """
        acc_by_id = {a["id"]: a for a in snap["accounts"]}
        user_by_id = {u["id"]: u for u in snap["users"]}
        rows = [t for t in snap["txs"] if t.get("account_id") in account_ids]
        # [v1.22.3] Filters (applied on the raw txs, before ordering).
        # [v1.22.4] The ticker filter is a PREFIX — "KL" lists KLBN4 and
        # KLBN11 while the user is still typing (the old exact match +
        # 4-8 char validation 400'd mid-keystroke and wiped the view).
        if ticker:
            up = ticker.upper()
            rows = [t for t in rows
                    if (t.get("ticker") or "").upper().startswith(up)]
        if ttype:
            rows = [t for t in rows if t.get("type") == ttype]
        if date_from:
            rows = [t for t in rows if (t.get("date") or "") >= date_from]
        if date_to:
            rows = [t for t in rows if (t.get("date") or "") <= date_to]
        if query:
            needle = query.strip().lower()
            if needle:
                rows = [t for t in rows
                        if needle in (t.get("ticker") or "").lower()
                        or needle in (t.get("note") or "").lower()]
        total = len(rows)
        # [v1.22] Ascending + stable, the SAME total order as the replay
        # (date, created_at, seq — the uuid tiebreak scrambled same-
        # second rows); paginate the NEWEST-last list from the END.
        rows.sort(key=self._tx_order_key)
        if page < 1:
            page = 1
        end = total - (page - 1) * limit      # slice end (exclusive)
        start = end - limit
        recent = rows[max(0, start):end] if end > 0 else []
        short_ids = short_ids or set()
        out = []
        for t in recent:
            acc = acc_by_id.get(t.get("account_id") or "")
            user = user_by_id.get(acc.get("user_id") or "") if acc else None
            if t.get("type") == "corp":
                # [v1.22.3] Corporate action row: the factor IS the cell
                # (×2,00 · ×0,50 · ×1,10) — no money columns exist.
                # [v1.28.5] rights: the qty of rights received is the
                # cell; inplit: the cell reads OLD → NEW with the factor.
                _act = t.get("action") or ""
                if _act == "rights":
                    _qty_cell = _qty(t.get("quantity") or 0.0)
                    _factor_cell = _qty_cell
                elif _act == "inplit":
                    _factor_cell = (
                        f"{(t.get('ticker') or '')} → "
                        f"{(t.get('new_ticker') or '')} "
                        f"{_factor_br(t.get('factor') or 0.0)}")
                    _qty_cell = _factor_cell
                else:
                    _factor_cell = _factor_br(t.get("factor") or 0.0)
                    _qty_cell = _factor_cell
                out.append({
                    "id": t["id"],
                    "date": _fmt_date(t.get("date")),
                    "date_iso": t.get("date") or "",
                    "ticker": t.get("ticker"),
                    "account": " · ".join(x for x in (
                        user["name"] if user else None,
                        acc.get("name") if acc else None) if x) or "—",
                    "account_id": t.get("account_id") or "",
                    "type": "corp",
                    "action": _act,
                    "factor": t.get("factor") or 0.0,
                    "factor_br": _factor_cell,
                    "new_ticker": t.get("new_ticker") if _act == "inplit"
                        else None,
                    "qty": _qty_cell,
                    "quantity": float(t.get("quantity") or 0.0),
                    "price": None,
                    "raw_price": None,
                    "zero": False,
                    "short": t.get("id") in short_ids,
                    "fees": "—",
                    "raw_fees": 0.0,
                    "total": "—",
                    "note": t.get("note") or "",
                })
                continue
            # [v1.22.3] row_total — the per-row money column (the
            # outer ``total`` is the FILTERED COUNT the pager returns;
            # the shadowing fed the count to the UI as 3000.0).
            row_total = (t["quantity"] * t["price"]
                         + (t["fees"] if t.get("type") == "buy"
                            else -t["fees"]))
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
                "total": _brl2(row_total),
                "note": t.get("note") or "",
            })
        return out, total

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
        # Pre-compute each watched account's raw positions ONCE (the
        # [v1.22.3] replay memo — same store revision, same walk).
        raw_by_acc: dict[str, dict[str, dict[str, float]]] = {}
        txs_by_acc: dict[str, list[dict]] = {}
        for acc in watched:
            txs = [t for t in snap["txs"] if t.get("account_id") == acc["id"]]
            txs_by_acc[acc["id"]] = txs
            raw_by_acc[acc["id"]] = self._replay_for(acc["id"], txs)[0]

        def _acc_kpis(acc: dict, raw: dict) -> dict[str, Any]:
            cost = math.fsum(p["qty"] * p["pm"] for p in raw.values())
            value_parts: list[float] = []
            complete = quotes_ok
            for tk, p in raw.items():
                if abs(p["qty"]) <= 1e-9:
                    continue
                q = self._quote(tk)
                if q and q.get("close") is not None:
                    value_parts.append(q["close"] * p["qty"])
                else:
                    complete = False
            value = math.fsum(value_parts)
            realized = math.fsum(p["realized"] for p in raw.values())
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
            g_cost_parts: list[float] = []
            g_value_parts: list[float] = []
            g_realized_parts: list[float] = []
            complete = quotes_ok
            for acc in watched:
                if acc.get("user_id") != uid:
                    continue
                raw = raw_by_acc[acc["id"]]
                g_cost_parts.extend(p["qty"] * p["pm"] for p in raw.values())
                g_realized_parts.extend(p["realized"] for p in raw.values())
                for tk, p in raw.items():
                    if abs(p["qty"]) <= 1e-9:
                        continue
                    q = self._quote(tk)
                    if q and q.get("close") is not None:
                        g_value_parts.append(q["close"] * p["qty"])
                    else:
                        complete = False
            g_cost = math.fsum(g_cost_parts)
            g_value = math.fsum(g_value_parts)
            g_realized = math.fsum(g_realized_parts)
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
        # [v1.28.3] the 52-week range joins the row ("add more info like
        # max and min 52 weeks") — ONE range_52w() call for the whole
        # watchlist; a symbol absent from the window degrades per-ticker
        # ("—" cells), and a down cotahist leaves the columns empty
        # without touching the rest of the box.
        # The row completes its read: SETOR (the cadastro's cached CVM
        # sector) + the day's Mín/Máx (the quote's own session high/low)
        # + the 52-week pair closed by Var. (52) — the table reads
        # Ticker · Nome · Setor · Preço · Mín (dia) · Máx (dia) ·
        # Var. (dia) · Mín (52) · Máx (52) · Var. (52).
        r52: dict[str, dict[str, Any]] = {}
        s52: dict[str, list[float]] = {}
        if watch_tickers:
            res = _range_52w(sorted(set(watch_tickers)))
            if res.get("status") == "ok":
                r52 = {r["ticker"]: r for r in res.get("symbols", [])}
            # [v1.28.3] the 52-week CLOSE series — the SAME window the
            # range reads (first point kept = the ~52-weeks-ago close,
            # last = the quoted price), ONE call for the whole list; it
            # feeds Var. (52) and degrades per-ticker like the range.
            res = _series_52w(sorted(set(watch_tickers)))
            if res.get("status") == "ok":
                s52 = {s["ticker"]: s["points"]
                       for s in res.get("symbols", []) if s.get("points")}
        tk_rows: list[dict[str, Any]] = []
        for tk in sorted(set(watch_tickers)):
            meta = snap["tickers"].get(tk) or {}
            q = self._quote(tk)
            rng = r52.get(tk) or {}
            pts52 = s52.get(tk) or []
            # Var. (52) — the 52-week variation: the window's first
            # close vs the last (None when the series is too short).
            var_52 = (pts52[-1] / pts52[0] - 1.0
                      if len(pts52) >= 2 and pts52[0] else None)
            tk_rows.append({
                "ticker": tk,
                "name": meta.get("name") or (q.get("name") if q else "") or tk,
                # SETOR after the name — the CVM/FCA sector cached in
                # the cadastro ("" until the background meta refresh
                # lands → the client renders "—").
                "sector": (meta.get("sector") or "").strip() or None,
                "price": _px(q.get("close")) if q else None,
                # the MAIN price's band pill — Máx/Mín (dia/52) stay
                # plain (the user's main-price-only rule).
                "price_pill": (_pill(q.get("close"))
                               if q and q.get("close") is not None else None),
                "variation": _signed_pct(
                    q.get("variation_pct") / 100.0
                    if q and q.get("variation_pct") is not None else None),
                # the day's Mín/Máx (the quote's OWN session high/low)
                # BEFORE the 52-week pair, which reads Mín-first.
                "low_day": _brl2(q.get("day_low"))
                    if q and q.get("day_low") is not None else None,
                "high_day": _brl2(q.get("day_high"))
                    if q and q.get("day_high") is not None else None,
                "low_52": _brl2(rng["low_52"])
                    if rng.get("low_52") is not None else None,
                "high_52": _brl2(rng["high_52"])
                    if rng.get("high_52") is not None else None,
                "var_52": _signed_pct(var_52) if var_52 is not None else None,
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
            raw = self._replay_for(acc["id"], txs)[0]
            cost_parts: list[float] = []
            value_parts: list[float] = []
            realized_parts: list[float] = []
            assets = 0
            complete = quotes_ok
            for tk, p in raw.items():
                realized_parts.append(p["realized"])
                if abs(p["qty"]) <= 1e-9:
                    continue
                assets += 1
                cost_parts.append(p["qty"] * p["pm"])
                q = self._quote(tk)
                if q and q.get("close") is not None:
                    value_parts.append(q["close"] * p["qty"])
                else:
                    complete = False
            cost = math.fsum(cost_parts)
            value = math.fsum(value_parts)
            realized = math.fsum(realized_parts)
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
            # [v1.22.3] The memo makes the second walk free (the
            # _account_row pass already replayed every account).
            u_cost_parts: list[float] = []
            u_value_parts: list[float] = []
            u_realized_parts: list[float] = []
            u_txs = 0
            u_assets: set[str] = set()
            complete = quotes_ok
            for acc in accs:
                raw = self._replay_for(acc["id"],
                                       txs_by_acc.get(acc["id"], []))[0]
                u_realized_parts.extend(p["realized"] for p in raw.values())
                u_txs += tx_count.get(acc["id"], 0)
                for tk, p in raw.items():
                    if abs(p["qty"]) <= 1e-9:
                        continue
                    u_assets.add(tk)
                    u_cost_parts.append(p["qty"] * p["pm"])
                    q = self._quote(tk)
                    if q and q.get("close") is not None:
                        u_value_parts.append(q["close"] * p["qty"])
                    else:
                        complete = False
            u_cost = math.fsum(u_cost_parts)
            u_value = math.fsum(u_value_parts)
            u_realized = math.fsum(u_realized_parts)
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
