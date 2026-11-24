"""webui/services/settings.py — schema-driven settings (SDNext-style).

[v1.20] Settings as data: every setting is ONE dict entry in SCHEMA below
(key, section, label, type, default + type-specific extras). The Settings
page renders itself from ``as_schema()`` (GET /api/webui/settings) and
saves through ``update()`` (PUT /api/webui/settings) — adding a setting
means adding a dict entry, nothing else (no template edits, no route
edits, no form HTML).

Wiring (every setting below actually does something — no dead knobs):
  - sync.auto_on_startup  → webui/app.py lifespan (stale sources sync at boot)
  - sync.stale_hours      → SyncService.freshness() (the staleness threshold
                            everywhere: Painel box, Sincronização page,
                            "Sincronizar tudo", the startup check)
  - sync.schedule_hours   → SyncService.start_scheduler() (periodic stale
                            sync while the server runs; 0 = off)
  - home.card_rows        → HomeService (rows per ranking card)
  - home.cache_seconds    → HomeService (the v1.19 fix 1 memoization TTL)
  - ui.theme / ui.locale  → cookies (Set-Cookie on save + reload; the FOUC
                            script and negotiate_locale read them — the
                            cookie stays the single source of truth)
  - logs.level            → SystemLog minimum captured level
  - logs.buffer           → SystemLog ring-buffer size (applies live)

Storage: ONE JSON file (``memory_db/webui_settings.json`` — the same
memory_root every data_source DB lives under), written via
core.atomic_write (temp file + os.replace — readers never see a partial
file). Reads are an in-memory dict refreshed on mtime change; the file is
tiny so a full re-read per change is free.

Labels/help are PT-BR by design (the WebUI's stated i18n position: the
shell is bilingual, content is pt-BR — these are content).
"""
from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any

from core.atomic_write import atomic_write

# ── storage path (same resolution chain as data_sources/_base/catalog) ───────
def _settings_path() -> Path:
    """memory_db/webui_settings.json (cfg.memory_root, cwd fallback)."""
    try:
        from core.config import cfg
        memory_root = getattr(cfg, "memory_root", None)
    except Exception:
        memory_root = None
    if memory_root:
        return Path(memory_root) / "webui_settings.json"
    return Path.cwd() / "memory_db" / "webui_settings.json"


# ── THE schema — adding a setting = one dict entry here ──────────────────────
# type: "bool" (toggle) | "number" (int input, min/max/unit) | "select"
#       (options: [{value, label}]) | "string" (text input)
SCHEMA: list[dict[str, Any]] = [
    # ── Sincronização ──
    {
        "key": "sync.auto_on_startup", "section": "Sincronização",
        "label": "Sincronizar ao iniciar",
        "type": "bool", "default": False,
        "help": "Sincroniza automaticamente as fontes desatualizadas quando "
                "o WebUI inicia (mesmo efeito do botão \"Sincronizar tudo\").",
    },
    {
        "key": "sync.stale_hours", "section": "Sincronização",
        "label": "Limite de desatualização",
        "type": "number", "default": 24, "min": 1, "max": 720, "unit": "h",
        "help": "Uma fonte é considerada desatualizada quando a última "
                "sincronização passou deste limite (Painel, página "
                "Sincronização e \"Sincronizar tudo\").",
    },
    {
        "key": "sync.schedule_hours", "section": "Sincronização",
        "label": "Agenda automática",
        "type": "number", "default": 0, "min": 0, "max": 168, "unit": "h",
        "help": "Sincroniza as fontes desatualizadas a cada N horas "
                "enquanto o WebUI estiver rodando (0 = desligado). "
                "Aplica sem reiniciar.",
    },
    # ── Painel ──
    {
        "key": "home.card_rows", "section": "Painel",
        "label": "Linhas por card",
        "type": "number", "default": 10, "min": 5, "max": 25, "unit": "linhas",
        "help": "Quantas ações aparecem em cada card de ranking do Painel "
                "(IBOV, SMLL, Mais Negócios, Altas, Baixas).",
    },
    {
        "key": "home.cache_seconds", "section": "Painel",
        "label": "Cache do Painel",
        "type": "number", "default": 60, "min": 5, "max": 600, "unit": "s",
        "help": "Por quanto tempo o payload do Painel fica memoizado no "
                "servidor (o conteúdo só muda quando uma sincronização roda).",
    },
    # ── Aparência (cookie-backed — o cookie continua a fonte da verdade) ──
    {
        "key": "ui.theme", "section": "Aparência",
        "label": "Tema",
        "type": "select", "default": "dark",
        "options": [{"value": "dark", "label": "Escuro"},
                    {"value": "light", "label": "Claro"}],
        "help": "Aplica ao salvar (os gráficos amostram as cores no render).",
    },
    {
        "key": "ui.locale", "section": "Aparência",
        "label": "Idioma",
        "type": "select", "default": "pt-BR",
        "options": [{"value": "pt-BR", "label": "Português (BR)"},
                    {"value": "en-US", "label": "English (US)"}],
        "help": "Traduz o shell da interface (o conteúdo de dados é pt-BR).",
    },
    # ── Logs ──
    {
        "key": "logs.level", "section": "Logs",
        "label": "Nível mínimo",
        "type": "select", "default": "info",
        "options": [{"value": "info", "label": "Info (tudo)"},
                    {"value": "warning", "label": "Aviso e acima"},
                    {"value": "error", "label": "Somente erros"}],
        "help": "O que o log do sistema (ícone 📜 no topo) captura. "
                "Aplica imediatamente.",
    },
    {
        "key": "logs.buffer", "section": "Logs",
        "label": "Buffer do log",
        "type": "number", "default": 500, "min": 100, "max": 5000,
        "unit": "linhas",
        "help": "Quantas linhas ficam em memória por processo (o histórico "
                "antes do boot não existe — é um tail, não um arquivo).",
    },
]

_SCHEMA_BY_KEY: dict[str, dict[str, Any]] = {s["key"]: s for s in SCHEMA}


class SettingsService:
    """Schema-driven settings store — one JSON file, in-memory cache."""

    def __init__(self) -> None:
        # [v1.22.1] RLock (B118): get()/values()/update() all take the
        # lock and call _maybe_reload() inside it — a future nested call
        # (get inside update, a settings-read helper) would deadlock on a
        # plain Lock. Reentrant defuses the armed trap.
        self._lock = threading.RLock()
        self._values: dict[str, Any] = {}       # stored overrides only
        # [v1.22.1] st_mtime_ns (int nanoseconds): the float st_mtime
        # loses precision on fast successive saves — a same-second
        # atomic_write could read as "unchanged" and serve stale values.
        self._loaded_mtime: int | None = None

    # ── reads ────────────────────────────────────────────────────────────────

    def _maybe_reload(self) -> None:
        """Re-read the file when its mtime changed (external edit / reload)."""
        path = _settings_path()
        try:
            mtime = path.stat().st_mtime_ns    # [v1.22.1] int, not float
        except OSError:
            # No file yet — defaults everywhere (a fresh install).
            if self._values:
                self._values = {}
                self._loaded_mtime = None
            return
        if mtime == self._loaded_mtime:
            return
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            self._values = {k: v for k, v in data.items()
                            if k in _SCHEMA_BY_KEY} if isinstance(data, dict) else {}
            self._loaded_mtime = mtime
        except Exception:
            # Corrupt file — keep defaults (the next save rewrites it clean).
            self._values = {}
            self._loaded_mtime = mtime

    def get(self, key: str, default: Any = None) -> Any:
        """One setting, validated against the schema (defaults for absent)."""
        spec = _SCHEMA_BY_KEY.get(key)
        if spec is None:
            return default
        with self._lock:
            self._maybe_reload()
            if key in self._values:
                return self._values[key]
        return spec["default"]

    def values(self) -> dict[str, Any]:
        """Every setting merged over its default (a copy — safe to hold)."""
        out: dict[str, Any] = {}
        with self._lock:
            self._maybe_reload()
            stored = dict(self._values)
        for spec in SCHEMA:
            out[spec["key"]] = stored.get(spec["key"], spec["default"])
        return out

    # ── writes ───────────────────────────────────────────────────────────────

    def update(self, patch: dict[str, Any]) -> dict[str, Any]:
        """Validate + persist a {key: value} patch.

        Returns {"ok": True, "applied": [keys], "values": {...}} or
        {"ok": False, "errors": {key: PT-BR message}} — ALL keys are
        validated BEFORE anything is written (no partial saves).
        """
        errors: dict[str, str] = {}
        coerced: dict[str, Any] = {}
        for key, value in (patch or {}).items():
            spec = _SCHEMA_BY_KEY.get(key)
            if spec is None:
                errors[key] = "Configuração desconhecida."
                continue
            ok, val_or_msg = self._coerce(spec, value)
            if ok:
                coerced[key] = val_or_msg
            else:
                errors[key] = val_or_msg
        if errors:
            return {"ok": False, "errors": errors}

        with self._lock:
            self._maybe_reload()
            merged = dict(self._values)
            merged.update(coerced)
            atomic_write(_settings_path(),
                         json.dumps(merged, indent=2, ensure_ascii=False))
            self._values = merged
            # The atomic write's mtime becomes the new baseline.
            try:
                self._loaded_mtime = _settings_path().stat().st_mtime_ns
            except OSError:
                pass
        return {"ok": True, "applied": sorted(coerced.keys()),
                "values": self.values()}

    @staticmethod
    def _coerce(spec: dict[str, Any], value: Any) -> tuple[bool, Any | str]:
        """Validate one value against its spec. (ok, value | PT-BR error)."""
        t = spec["type"]
        if t == "bool":
            if isinstance(value, bool):
                return True, value
            if isinstance(value, str) and value.lower() in ("true", "false"):
                return True, value.lower() == "true"
            if isinstance(value, int) and value in (0, 1):
                return True, bool(value)
            return False, "Esperado verdadeiro/falso."
        if t == "number":
            try:
                n = int(value) if not isinstance(value, bool) else None
                if n is None:
                    raise ValueError
            except (TypeError, ValueError):
                return False, "Esperado um número inteiro."
            if spec.get("min") is not None and n < spec["min"]:
                return False, f"Mínimo {spec['min']}."
            if spec.get("max") is not None and n > spec["max"]:
                return False, f"Máximo {spec['max']}."
            return True, n
        if t == "select":
            opts = {o["value"] for o in spec.get("options", [])}
            if value in opts:
                return True, value
            return False, "Opção inválida."
        if t == "string":
            s = str(value)[:200]
            return True, s
        return False, "Tipo não suportado."

    # ── rendering ────────────────────────────────────────────────────────────

    def as_schema(self, overrides: dict[str, Any] | None = None) -> list[dict]:
        """Render-ready schema: sections with settings + current values.

        ``overrides`` win over stored values (the settings page seeds
        ui.theme/ui.locale from the request cookies — the cookie is the
        truth for those, the file only mirrors the last save).
        """
        vals = self.values()
        if overrides:
            vals.update({k: v for k, v in overrides.items()
                         if k in _SCHEMA_BY_KEY})
        sections: list[dict] = []
        by_section: dict[str, list[dict]] = {}
        for spec in SCHEMA:
            entry = dict(spec)
            entry["value"] = vals.get(spec["key"], spec["default"])
            by_section.setdefault(spec["section"], []).append(entry)
        for name, settings in by_section.items():
            sections.append({"name": name, "settings": settings})
        return sections


# ── module-level singleton (imported by syslog, sync, home, app, routes) ─────
_settings_service = SettingsService()


def settings_service() -> SettingsService:
    return _settings_service
