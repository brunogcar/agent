<- Back to [Config Overview](../CONFIG.md)

# 🛡️ AI Instructions

## ❌ NEVER DO

1. **Never hardcode model names** — always use `cfg.planner_model`, `cfg.executor_model`, etc. Never write `"gemma"` or `"qwen"` in code.
2. **Preserve validation** — never remove or weaken the validation rules in `__init__()`. They prevent the server from starting with invalid config.
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
13. **Timeout single source of truth** — timeout lives in `core/config.py` only. Never add timeout to `llm_backend/config.py`. The LLM backend reads it from `cfg.model_registry[role]["timeout"]`.

## ✅ ALWAYS DO

14. **Always use `cfg` singleton** — `from core.config import cfg`, never `Config()`.
15. **Always validate at import time** — new config fields must have validation in `__init__()`.
16. **Always add to `.env.example`** — new env vars must be documented with defaults.
17. **Always update this doc** — when adding config attributes, update the relevant table in API.md.
18. **Always test validation** — error paths for invalid config must be tested.

---

## 🚫 Anti-Patterns & Lessons Learned

*(No entries yet. Add lessons here as they are learned from future refactors and bug fixes. When an AI assistant encounters a bug, fix, or architectural insight during editing, add it here with:*

> - **What happened:** The symptom or bug
> - **Why it matters:** The impact
> - **Fix:** The solution or pattern to follow

*Fill this section with relevant information during edits and refactors.)*

---

*Last updated: 2026-07-03. See [ARCHITECTURE.md](ARCHITECTURE.md) for file maps, [API.md](API.md) for config reference, [CHANGELOG.md](CHANGELOG.md) for version history.*
