<- Back to [Config Overview](../CONFIG.md)

# 🗺️ Changelog

## 📝 Version History

| Version | Date | Changes |
|---------|------|---------|
| **v1.1** | 2026-07-22 | **Workflow env var additions.** Since v1.0, three workflows added env vars to `_init_execution()` in `execution.py`: (1) autoresearch v1.4-v1.9 added 7 env vars (`AUTORESEARCH_MAX_ITERATIONS`, `AUTORESEARCH_CONVERGENCE_WINDOW`, `AUTORESEARCH_CONVERGENCE_EPSILON`, `AUTORESEARCH_REFLECT_INTERVAL`, `AUTORESEARCH_PARALLEL_COUNT`, `AUTORESEARCH_RECURSION_LIMIT`, `AUTORESEARCH_LOG_DIR_MAX_MB`). (2) understand v1.4.1-v1.7 added 3 env vars (`UNDERSTAND_EMBED_BATCH_SIZE`, `UNDERSTAND_SKIP_DIRS`, `UNDERSTAND_TIMEOUT_SECONDS`). (3) autocode (already in v1.0). No structural changes to the config package — just new env var registrations. See per-workflow docs for details. See [API.md](API.md) → "Workflow-Specific Environment Variables" for the full table. |
| **Pre-v1.1** | 2026-07-16 | Added `cfg.timezone` attribute (env `AGENT_TZ`, default = system local) to `_init_execution(cfg)` in `core/config_backend/execution.py`. Single source of truth for tz-aware datetime operations across the agent (`core/time_utils.py`, `notify_ops`, `schedule_ops`). Empty string means "use system local timezone" (resolved lazily by `core.time_utils.get_timezone()`). Also added `AGENT_TZ=` documentation line to `.env.example`. |
| **v1.0** | 2026-07-14 | **First versioned release.** Split the monolithic `Config.__init__` (~430 lines, 515-line `core/config.py`) into a 12-file `core/config_backend/` package following the LLM / memory / gateway / router pattern. Builder dispatch: `Config.__init__` now imports and calls `_init_paths(cfg)` → `_init_providers(cfg)` → `_init_models(cfg)` → `_init_services(cfg)` → `_init_memory(cfg)` → `_init_execution(cfg)` → `_init_limits(cfg)` → `_init_security(cfg)` → `_validate_config(cfg)` in section order. `core/config.py` is now 168 lines (was 515). `core/config_validation.py` is now an 18-line backwards-compat shim — `validate_config()` impl moved to `core/config_backend/validation.py`. Split is purely structural — no behavior changes; all 213 callers doing `from core.config import cfg` continue to work unchanged. |
| Pre-v1.0 | 2026-07-05 | Added `agent_cache_max` and `agent_cache_ttl_seconds` env vars (Bug #19) for configurable agent tool cache limits. Defaults: 100 entries, 300s TTL. Added path traversal guard to `resolve_workspace_path` (Bug #1) — mirrors `resolve_agent_path`. Added 3 new `validate_config()` checks (Bug #17): model_registry entry completeness, agent role llm_role existence, allowed_internal_hosts type validation. |

---

## ⚠️ Breaking Changes

### v1.0 — 2026-07-14

The **public surface is unchanged** — `from core.config import cfg`, `from core.config import Config`, and `from core.config_validation import validate_config` all continue to work. The breakage is purely internal (test patch targets + the location of the `validate_config()` implementation).

| Change | Impact | Migration |
|--------|--------|-----------|
| `validate_config()` impl moved from `core/config_validation.py` → `core/config_backend/validation.py` | The old module is now an 18-line shim that re-exports `validate_config`. The shim re-exports **only** `validate_config` — not `cfg` or `tracer`. | No action for callers using `from core.config_validation import validate_config`. Tests that patched `core.config_validation.cfg` or `core.config_validation.tracer` must update to `core.config_backend.validation.cfg` / `.tracer` — `validate_config()` looks up those names in its defining module's globals. |
| `Config.__init__` no longer sets attributes inline | The ~430-line `__init__` is now a 25-line dispatcher that calls 9 builders. Adding a new attribute directly to `__init__` will not work — it must go in the appropriate `config_backend/` builder. | When adding a new config attribute, put it in the matching builder (`paths.py` for paths, `models.py` for models, etc.). See [INSTRUCTIONS.md](INSTRUCTIONS.md) rule #14. |
| Two distinct validators now coexist | `validators.py::_validate_config(cfg)` runs at construction time (raises immediately, 22 range checks). `validation.py::validate_config()` runs at startup (aggregates all errors into one RuntimeError, 7 check groups). | If you previously added a check to `validate_config()`, decide whether it's a construction-time range check (→ `validators.py`) or a startup check (→ `validation.py`). See [ARCHITECTURE.md](ARCHITECTURE.md) → Key Design Decisions. |

### Pre-v1.0 — 2026-07-05

| Change | Impact | Migration |
|--------|--------|-----------|
| New env vars: `AGENT_CACHE_MAX`, `AGENT_CACHE_TTL_SECONDS` | Agent tool cache limits are now configurable. Defaults match old hardcoded values (100 / 300). | Optional — add to `.env` to customize. No action needed for default behavior. |
| `resolve_workspace_path` now raises `PermissionError` on path traversal | Paths like `../../secrets.txt` that escape `WORKSPACE_ROOT` now raise instead of silently resolving outside the sandbox. Mirrors the existing `resolve_agent_path` behavior. | Fix any callers passing traversal paths — they were a security hole. Valid relative paths are unaffected. |
| `validate_config()` now checks model_registry entries | Entries with empty `model`, empty `provider`, or `timeout <= 0` now fail startup validation. | Fix any malformed `*_MODEL` env vars in `.env` — they would have failed at runtime anyway. |
| `validate_config()` now checks agent role `llm_role` against model_registry | Typos like `llm_role='cod'` instead of `'code'` now fail startup validation. Opt-in roles (consultor when `CONSULTOR_MODEL` is unset) are skipped. | Fix any invalid `llm_role` values in `tools/agent_ops/roles/*.py`. |
| `validate_config()` now checks `allowed_internal_hosts` type | Non-set/list types or entries with non-string/empty values now fail startup validation. | Fix malformed `ALLOWED_INTERNAL_HOSTS` env var in `.env`. |

---

## ✅ Completed

| Feature | Version | Notes |
|---------|---------|-------|
| `config_backend/` package split | v1.0 | Monolithic `Config.__init__` (~430 lines) split into 12-file `core/config_backend/` package (builder pattern). Mirrors the LLM / memory / gateway / router split. 213 callers unaffected. |
| `config_validation.py` consolidation | v1.0 | Merged into `config_backend/` as a backwards-compat shim. `validate_config()` impl now in `config_backend/validation.py`. Two validators now coexist with clear separation: `validators.py::_validate_config(cfg)` (construction-time, raises immediately) vs `validation.py::validate_config()` (startup-time, aggregates all errors). |

---

## 🔄 In Progress / Next Up

| Feature | Notes | Priority |
|---------|-------|----------|
| Config Hot-Reload | Watch `.env` for changes and reload without restart | p1 |
| Config Validation Schema | Use Pydantic for declarative validation rules | p1 |
| Config Secrets Manager | Integrate with HashiCorp Vault or AWS Secrets Manager | p2 |
| Config Diff Tool | Show what changed between `.env` versions | p2 |
| Config Migration | Automatic upgrade of old `.env` formats | p2 |

---

## 🚫 Deferred / Out of Scope

*(No deferred items yet. Add out-of-scope decisions here as they are made.)*

---

*Last updated: 2026-07-22 (v1.1). See [ARCHITECTURE.md](ARCHITECTURE.md) for file maps, [API.md](API.md) for config reference, [INSTRUCTIONS.md](INSTRUCTIONS.md) for AI editing rules.*
