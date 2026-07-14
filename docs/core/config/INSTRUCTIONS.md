<- Back to [Config Overview](../CONFIG.md)

# 🛡️ AI Instructions

## ❌ NEVER DO

1. **Never hardcode model names** — always use `cfg.planner_model`, `cfg.executor_model`, etc. Never write `"gemma"` or `"qwen"` in code.
2. **Preserve validation** — never remove or weaken the validation rules. Pre-v1.0 they lived in `__init__()`; v1.0 splits them across `config_backend/validators.py::_validate_config(cfg)` (construction-time, called as the last step of `__init__`) and `config_backend/validation.py::validate_config()` (startup-time, called by `server.py` via the shim). Both prevent the server from starting with invalid config.
3. **Protected files** — never remove files from `cfg.protected_files` without explicit user approval. These protect core infrastructure.
4. **Pathlib throughout** — all new path attributes must be `pathlib.Path` objects, not strings.
5. **Environment variables** — all new config values must come from `os.getenv()` with sensible defaults. Never hardcode production values.
6. **Singleton pattern** — never instantiate `Config` directly. Always use the `cfg` singleton at module level.
7. **SSRF warning** — never remove the SSRF warning function. It alerts users to production security risks.
8. **Type hints** — all new attributes must have proper type hints.
9. **Update this doc** — when adding new config attributes, update this CONFIG.md.
10. **Backward compatibility** — when renaming env variables, support both old and new names for at least one release cycle.
11. **Sub-role fallback chain** — new sub-role models must fall back to `executor_model`, not `planner_model`. Planner is expensive and reserved for complex reasoning. **Exception:** `classify` and `route` fall back to `router_model`, not `executor_model` — they're routing-adjacent sub-roles, not execution-adjacent ones. Don't assume all sub-roles share one fallback group.
12. **Timeout validation** — new timeouts must be validated against `autocode_graph_timeout`.
13. **Timeout single source of truth** — timeout lives in `core/config_backend/models.py` (`_init_models`) only. Never add timeout to `llm_backend/config.py`. The LLM backend reads it from `cfg.model_registry[role]["timeout"]`.
14. **Never add attributes directly to `Config.__init__`** — `__init__` is now a 25-line dispatcher that calls 9 builders in `core/config_backend/`. New attributes belong in the matching builder: paths → `paths.py`, models → `models.py`, providers → `providers.py`, services → `services.py`, memory → `memory.py`, execution → `execution.py`, limits → `limits.py`, security → `security.py`. Range checks go in `validators.py` (construction-time, raises immediately) or `validation.py` (startup-time, aggregates errors). Adding to `__init__` directly will be lost on the next `reload()` and bypasses the construction-time validators.
15. **Never import from `core.config_backend` directly in application code** — always use `from core.config import cfg` (or `from core.config import Config` for typing). The `config_backend/` package is an internal implementation detail; its module layout may change in future versions. The only sanctioned exception is tests that need to patch `core.config_backend.validation.cfg` / `.tracer` (the shim in `core/config_validation.py` re-exports only `validate_config`, not `cfg` / `tracer`).
16. **Never delete `core/config_validation.py`** — it's an 18-line backwards-compat shim that re-exports `validate_config` from `core/config_backend/validation.py`. `server.py` and existing tests import `validate_config` via `from core.config_validation import validate_config`. Deleting the shim breaks those call sites. The actual implementation lives in `config_backend/validation.py` — edit there.

## ✅ ALWAYS DO

17. **Always use `cfg` singleton** — `from core.config import cfg`, never `Config()`.
18. **Always validate at import time** — new config fields must have validation in `validators.py` (construction-time range checks) or `validation.py` (startup-time checks). Both run automatically — `validators.py` from `Config.__init__`, `validation.py` from `server.py`.
19. **Always add to `.env.example`** — new env vars must be documented with defaults.
20. **Always update this doc** — when adding config attributes, update the relevant table in API.md.
21. **Always test validation** — error paths for invalid config must be tested. Tests that need to mock `cfg` / `tracer` for `validate_config()` must patch `core.config_backend.validation.cfg` / `.tracer` (not the old `core.config_validation.*` paths — the shim re-exports only `validate_config`).

---

## 🚫 Anti-Patterns & Lessons Learned

*(No entries yet. Add lessons here as they are learned from future refactors and bug fixes. When an AI assistant encounters a bug, fix, or architectural insight during editing, add it here with:*

> - **What happened:** The symptom or bug
> - **Why it matters:** The impact
> - **Fix:** The solution or pattern to follow

*Fill this section with relevant information during edits and refactors.)*

---

*Last updated: 2026-07-14 (v1.0). See [ARCHITECTURE.md](ARCHITECTURE.md) for file maps, [API.md](API.md) for config reference, [CHANGELOG.md](CHANGELOG.md) for version history.*
