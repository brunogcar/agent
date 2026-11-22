"""webui/services/preflight.py — system pre-flight checks.

[v1.7] Health checks surfaced in the UI BEFORE things break at render
time: DB existence + schema + WAL + row sanity, sync coverage, runtime
(vendor assets, Python, disk, write access), the v1.7 adapter registry,
and launch configuration. Errors used to surface deep inside engines
("FileNotFoundError: dfp.db — Run sync first" mid-dashboard); the
preflight panel shows the same diagnosis on ONE page.

Checklist model:
  - Every check returns {id, label, status: ok|warn|fail, detail, hint?}.
  - Groups: bancos (per-DB), dados (sync coverage), sistema, adapters,
    configuracao. Overall status = worst check.
  - PT-BR labels/details (content language — same convention as the
    sync page partials).

Side-effect policy: diagnostics must not mutate anything. The canonical
``data_sources._base.catalog.data_dir()`` CREATES directories; this
service resolves the memory root WITHOUT mkdir so a missing DB never
leaves empty domain folders behind.

DB inventory: paths mirror the sync engines' catalogs (single source of
truth upstream); expected tables mirror the CREATE TABLE statements in
``data_sources/*/catalog.py``. Row sanity uses ``MAX(rowid)`` (O(1) —
COUNT(*) would full-scan multi-GB tables).
"""
from __future__ import annotations

import os
import shutil
import sqlite3
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

_OK, _WARN, _FAIL = "ok", "warn", "fail"
_WORST = {_OK: 0, _WARN: 1, _FAIL: 2}

# Vendor assets the shell loads on every page (base.html) — a broken
# install (missing file) means a blank page, so this is a hard fail.
_VENDOR_ASSETS = (
    "vendor/htmx.min.js",
    "vendor/alpine.min.js",
    "vendor/chart.umd.min.js",
    "vendor/hammer.min.js",
    "vendor/chartjs-plugin-zoom.min.js",
    "css/app.css",
    "js/app.js",
)

_MIN_PY = (3, 10)          # codebase uses PEP 604 unions (int | None)
_MIN_FREE_GB = 2           # syncs download CVM ZIPs (hundreds of MB)


# ── DB inventory ─────────────────────────────────────────────────────────────
# (domain, file, sync source key, PT-BR label, expected tables, rows table,
#  core?, rekey?) — core DBs fail the panel when missing; feature DBs only
#  warn. rekey=True → the DB carries a user_version marker that must be
#  >= _REKEY_VERSION (see tools/migrations/rekey_itr_snapshots.py).

_REKEY_VERSION = 2  # ITR snapshot re-key marker [v1.7.1]

def _db_inventory() -> list[dict[str, Any]]:
    return [
        # CVM
        dict(domain="cvm", file="dfp.db", source="dfp",
             label="DFP — demonstrações anuais",
             tables=["empresas", "contas", "sync_state"],
             rows_table="contas", core=True),
        dict(domain="cvm", file="itr.db", source="itr",
             label="ITR — demonstrações trimestrais",
             tables=["empresas", "contas", "sync_state"],
             rows_table="contas", core=True, rekey=True),
        dict(domain="cvm", file="fre.db", source="fre",
             label="FRE — formulário de referência",
             tables=["documentos", "posicao_acionaria", "sync_state"],
             rows_table="documentos", core=True),
        dict(domain="cvm", file="fca.db", source="fca",
             label="FCA — formulário cadastral",
             tables=["fca_geral", "fca_valor_mobiliario", "sync_state"],
             rows_table="fca_valor_mobiliario", core=True),
        dict(domain="cvm", file="cad.db", source="cad",
             label="CAD — cadastro de companhias",
             tables=["cia_aberta", "sync_state"],
             rows_table="cia_aberta", core=True),
        dict(domain="cvm", file="bridge.db", source="bridge",
             label="Bridge — ticker ↔ CNPJ",
             tables=["ticker_map", "sync_log"],
             rows_table="ticker_map", core=True),
        dict(domain="cvm", file="ipe.db", source="ipe",
             label="IPE — eventos corporativos",
             tables=["eventos", "sync_state"], rows_table="eventos"),
        dict(domain="cvm", file="vlmo.db", source="vlmo",
             label="VLMO — atividade de insiders",
             tables=["vlmo_documents", "vlmo_movements", "sync_state"],
             rows_table="vlmo_movements"),
        dict(domain="cvm", file="cgvn.db", source="cgvn",
             label="CGVN — práticas de governança",
             tables=["cgvn_documents", "cgvn_practices", "sync_state"],
             rows_table="cgvn_practices"),
        # B3
        dict(domain="b3", file="cotahist.db", source="cotahist",
             label="COTAHIST — cotações históricas",
             tables=["cotahist", "sync_state"],
             rows_table="cotahist", core=True),
        dict(domain="b3", file="dividends.db", source="b3_dividends",
             label="Proventos B3 (API)",
             tables=["company_info", "cash_dividends", "stock_dividends",
                     "subscriptions", "sync_state"],
             rows_table="cash_dividends"),
        dict(domain="b3", file="instruments.db", source="b3-api-instruments",
             label="B3 API — instrumentos",
             tables=["instruments", "sync_state"],
             rows_table="instruments"),
        dict(domain="b3", file="trades.db", source="b3-api-trades",
             label="B3 API — trades",
             tables=["trades", "sync_state"], rows_table="trades"),
        dict(domain="b3", file="after_hours.db", source="b3-api-after-hours",
             label="B3 API — after-hours",
             tables=["after_hours", "sync_state"],
             rows_table="after_hours"),
        dict(domain="b3", file="derivatives.db", source="b3-api-derivatives",
             label="B3 API — derivativos (posições em aberto)",
             tables=["derivatives", "sync_state"],
             rows_table="derivatives"),
        dict(domain="b3", file="index.db", source="b3-index",
             label="Índices B3",
             tables=["index_catalog", "index_constituents", "sync_state"],
             rows_table="index_constituents"),
        dict(domain="b3", file="isin_index.db", source="b3-isin",
             label="Índice ISIN (ponte B3)",
             tables=["isin_cnpj", "sync_state"], rows_table="isin_cnpj"),
        # BCB
        dict(domain="bcb", file="sgs.db", source="sgs",
             label="SGS — séries (Selic, IPCA, CDI…)",
             tables=["series_observations", "series_catalog", "sync_state"],
             rows_table="series_observations"),
        dict(domain="bcb", file="focus.db", source="focus",
             label="Focus BCB — expectativas de mercado",
             tables=["expectations_monthly", "expectations_annual",
                     "sync_state"],
             rows_table="expectations_annual"),
        # DDM
        dict(domain="ddm", file="inflation.db", source="ddm-inflation",
             label="DDM — índices de preços",
             tables=["index_observations", "index_catalog", "sync_state"],
             rows_table="index_observations"),
        dict(domain="ddm", file="juros.db", source="ddm-juros",
             label="DDM — juros",
             tables=["juros_observations", "juros_catalog", "sync_state"],
             rows_table="juros_observations"),
        dict(domain="ddm", file="poupanca.db", source="ddm-poupanca",
             label="DDM — poupança",
             tables=["poupanca_observations", "poupanca_catalog",
                     "sync_state"],
             rows_table="poupanca_observations"),
        dict(domain="ddm", file="acoes.db", source="ddm-acoes",
             label="DDM — ações B3",
             tables=["stocks", "stocks_history", "sync_state"],
             rows_table="stocks"),
        dict(domain="ddm", file="focus.db", source="ddm-focus",
             label="DDM — boletim Focus",
             tables=["focus_observations", "sync_state"],
             rows_table="focus_observations"),
        dict(domain="ddm", file="fluxo.db", source="ddm-fluxo",
             label="DDM — fluxo de investidores",
             tables=["fluxo_observations", "sync_state"],
             rows_table="fluxo_observations"),
        dict(domain="ddm", file="dividends.db", source="ddm-dividends",
             label="DDM — dividendos",
             tables=["dividends", "sync_state"], rows_table="dividends"),
    ]


def _memory_root() -> Path:
    """Resolve the memory_db root WITHOUT creating it (mirrors
    data_sources._base.catalog.data_dir's resolution chain minus mkdir)."""
    try:
        from core.config import cfg
        root = getattr(cfg, "memory_root", None)
    except Exception:
        root = None
    return Path(root) if root else Path.cwd() / "memory_db"


def _fmt_size(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{n:.0f} {unit}" if unit in ("B", "KB") else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


def _fmt_rows(n: int | None) -> str:
    if not n:
        return "0"
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f} mi"
    if n >= 1_000:
        return f"{n / 1_000:.1f} mil"
    return str(n)


class PreflightService:
    """Runs the pre-flight checklist on demand (cheap — file stats,
    sqlite pragmas and MAX(rowid) probes; ~20 DBs in well under a second)."""

    # ── check helpers ───────────────────────────────────────────────────

    @staticmethod
    def _check(cid: str, label: str, status: str, detail: str,
               hint: str = "") -> dict[str, str]:
        out = {"id": cid, "label": label, "status": status, "detail": detail}
        if hint:
            out["hint"] = hint
        return out

    # ── group: bancos ───────────────────────────────────────────────────

    def _check_db(self, spec: dict[str, Any], root: Path) -> dict[str, str]:
        path = root / spec["domain"] / spec["file"]
        cid = f"db:{spec['source']}"
        label = f"{spec['file']} ({spec['domain']})"

        if not path.exists():
            status = _FAIL if spec.get("core") else _WARN
            return self._check(
                cid, label, status, "arquivo não encontrado",
                hint=f"{spec['label']} — sincronize a fonte "
                     f"'{spec['source']}' na página Sync")

        parts: list[str] = []
        try:
            size = _fmt_size(path.stat().st_size)
        except OSError:
            size = "?"
        parts.append(size)

        # Schema + rows + WAL + re-key marker through ONE read-only connection.
        missing_main: list[str] = []
        wal = ""
        rows_txt = ""
        rekey_pending = False
        try:
            conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=3)
            try:
                names = {r[0] for r in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'")}
                for tbl in spec["tables"]:
                    if tbl not in names and tbl != "sync_state":
                        missing_main.append(tbl)
                if "sync_state" not in names:
                    parts.append("sem sync_state")
                mode = conn.execute("PRAGMA journal_mode").fetchone()
                wal = (mode[0] if mode else "").lower()
                if spec.get("rows_table") in names:
                    r = conn.execute(
                        f"SELECT MAX(rowid) FROM {spec['rows_table']}"
                    ).fetchone()
                    rows_txt = _fmt_rows(r[0] if r else None)
                if spec.get("rekey"):
                    uv = conn.execute("PRAGMA user_version").fetchone()
                    rekey_pending = bool(uv and uv[0] < _REKEY_VERSION)
            finally:
                conn.close()
        except sqlite3.Error as e:
            return self._check(cid, label, _FAIL,
                               f"{size} · banco ilegível ({e})")

        if rows_txt:
            parts.append(f"{rows_txt} linhas")
        if wal and wal != "wal":
            parts.append(f"journal={wal}")

        if missing_main:
            return self._check(
                cid, label, _FAIL,
                f"{size} · tabelas ausentes: {', '.join(missing_main)}",
                hint="esquema divergente — re-sincronize a fonte "
                     f"'{spec['source']}'")
        if rekey_pending:
            return self._check(
                cid, label, _WARN, " · ".join(parts) + " · re-key pendente",
                hint="balanços trimestrais exibem valores de fim de ano — "
                     "rode `python -m tools.migrations.rekey_itr_snapshots "
                     "--apply` (veja CHANGELOG v1.7.1)")
        if rows_txt == "0":
            return self._check(
                cid, label, _WARN,
                f"{size} · tabela principal vazia",
                hint=f"sincronize a fonte '{spec['source']}'")
        if wal and wal != "wal":
            return self._check(
                cid, label, _WARN, " · ".join(parts),
                hint="WAL desativado — rode `python -m core.db_wal` "
                     "(leitores podem bloquear durante syncs)")
        return self._check(cid, label, _OK, " · ".join(parts))

    # ── group: dados (sync coverage) ────────────────────────────────────

    def _sync_checks(self) -> list[dict[str, str]]:
        checks: list[dict[str, str]] = []
        try:
            from skills._freshness import get_freshness
            fresh = get_freshness()
        except Exception as e:
            return [self._check("dados:erro", "Sincronizações", _FAIL,
                                f"indisponível ({e})")]

        never = sorted(k for k, ts in fresh.items() if not ts)
        if never:
            checks.append(self._check(
                "dados:never", "Fontes jamais sincronizadas", _WARN,
                f"{len(never)} de {len(fresh)}: {', '.join(never[:8])}"
                + ("…" if len(never) > 8 else ""),
                hint="fontes sem registro de sync — dados dessas fontes "
                     "não existem localmente"))
        else:
            checks.append(self._check(
                "dados:never", "Fontes jamais sincronizadas", _OK,
                f"todas as {len(fresh)} fontes têm registro de sync"))

        try:
            from skills._base.sync_guard import _SYNC_REGISTRY
            n_registry = len(_SYNC_REGISTRY)
        except Exception:
            n_registry = len(fresh)
        checks.append(self._check(
            "dados:registry", "Fontes registradas", _OK,
            f"{n_registry} fontes no sync guard — a tabela acima mostra "
            "a idade de cada uma"))
        return checks

    # ── group: sistema ──────────────────────────────────────────────────

    def _system_checks(self, root: Path) -> list[dict[str, str]]:
        checks: list[dict[str, str]] = []

        checks.append(self._check(
            "sys:python", "Python", _OK if sys.version_info >= _MIN_PY else _FAIL,
            f"{sys.version_info.major}.{sys.version_info.minor}."
            f"{sys.version_info.micro} ({sys.platform})",
            hint="" if sys.version_info >= _MIN_PY
                 else "o código usa uniões PEP 604 — requer 3.10+"))

        static = Path(__file__).resolve().parent.parent / "static"
        missing = [a for a in _VENDOR_ASSETS if not (static / a).exists()]
        checks.append(self._check(
            "sys:assets", "Assets estáticos (vendor + css + js)",
            _OK if not missing else _FAIL,
            "todos presentes" if not missing
            else f"ausentes: {', '.join(missing)}",
            hint="" if not missing else "instalação quebrada — restaure "
                 "webui/static/"))

        if root.exists():
            free = shutil.disk_usage(root).free
            gb = free / (1024 ** 3)
            checks.append(self._check(
                "sys:disk", "Espaço em disco (memory_db)",
                _OK if gb >= _MIN_FREE_GB else _WARN,
                f"{gb:.1f} GB livres",
                hint="" if gb >= _MIN_FREE_GB
                     else "syncs CVM baixam centenas de MB"))
            probe = root / ".preflight_probe"
            try:
                probe.write_text("ok", encoding="ascii")
                probe.unlink()
                checks.append(self._check(
                    "sys:write", "Escrita no memory_db", _OK,
                    "permissão de escrita confirmada"))
            except OSError as e:
                checks.append(self._check(
                    "sys:write", "Escrita no memory_db", _FAIL,
                    f"sem permissão ({e})",
                    hint="syncs precisam gravar nesta pasta"))
        else:
            checks.append(self._check(
                "sys:disk", "Espaço em disco (memory_db)", _FAIL,
                f"raiz inexistente: {root}",
                hint="a pasta memory_db será criada no primeiro sync"))
        return checks

    # ── group: adapters ─────────────────────────────────────────────────

    def _adapter_checks(self) -> list[dict[str, str]]:
        try:
            from webui.adapters import adapter_keys, adapters_info
            keys = adapter_keys()
            info = adapters_info()
        except Exception as e:
            return [self._check("adapt:erro", "Registry de adapters", _FAIL,
                                f"import falhou ({e})")]
        families = sorted({a["family"] for a in info})
        generic = sum(1 for a in info if a.get("generic"))
        return [
            self._check("adapt:registry", "Registry de adapters", _OK,
                        f"{len(keys)} subtabs em {len(families)} famílias "
                        f"({', '.join(families)})"),
            self._check("adapt:contract", "Contrato de seções", _OK,
                        f"{generic} payloads genéricos validados em "
                        "runtime (webui/adapters/contract.py)"),
        ]

    # ── group: configuração ─────────────────────────────────────────────

    def _config_checks(self, root: Path) -> list[dict[str, str]]:
        checks: list[dict[str, str]] = []
        lan = os.environ.get("WEBUI_ALLOW_LAN", "") == "1"
        checks.append(self._check(
            "cfg:binding", "Bind de rede",
            _WARN if lan else _OK,
            "LAN liberada (WEBUI_ALLOW_LAN=1)" if lan
            else "somente loopback (127.0.0.1)",
            hint="as rotas do gateway (/task, /chat) rodam sem "
                 "autenticação" if lan else ""))
        no_sync = os.environ.get("WEBUI_NO_SYNC", "") == "1"
        checks.append(self._check(
            "cfg:nosync", "Sync na inicialização",
            _WARN if no_sync else _OK,
            "desativado (--no-sync)" if no_sync
            else "verificação de freshness no startup",
            hint="fontes não são sincronizadas automaticamente"
                 if no_sync else ""))
        checks.append(self._check(
            "cfg:root", "Raiz de dados (memory_db)",
            _OK if root.exists() else _FAIL,
            str(root)))
        return checks

    # ── entry point ─────────────────────────────────────────────────────

    def run(self) -> dict[str, Any]:
        """Run every check. Cheap (<1s), stateless, side-effect free."""
        t0 = time.perf_counter()
        root = _memory_root()

        groups: list[dict[str, Any]] = [
            {"id": "bancos", "name": "Bancos de Dados",
             "checks": [self._check_db(s, root)
                        for s in _db_inventory()]},
            {"id": "dados", "name": "Sincronizações",
             "checks": self._sync_checks()},
            {"id": "sistema", "name": "Sistema",
             "checks": self._system_checks(root)},
            {"id": "adapters", "name": "Adapters",
             "checks": self._adapter_checks()},
            {"id": "configuracao", "name": "Configuração",
             "checks": self._config_checks(root)},
        ]

        all_checks = [c for g in groups for c in g["checks"]]
        counts = {s: sum(1 for c in all_checks if c["status"] == s)
                  for s in (_OK, _WARN, _FAIL)}
        worst = max((_WORST[c["status"]] for c in all_checks), default=0)

        return {
            "status": {0: _OK, 1: _WARN, 2: _FAIL}[worst],
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "duration_ms": int((time.perf_counter() - t0) * 1000),
            "memory_root": str(root),
            "summary": {"ok": counts[_OK], "warn": counts[_WARN],
                        "fail": counts[_FAIL],
                        "total": len(all_checks)},
            "groups": groups,
        }
