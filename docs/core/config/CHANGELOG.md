<- Back to [Config Overview](../CONFIG.md)

# 🗺️ Changelog

## 📝 Version History

| Version | Date | Changes |
|---------|------|---------|
| Pre-v1.0 | 2026-07-05 | Added `agent_cache_max` and `agent_cache_ttl_seconds` env vars (Bug #19) for configurable agent tool cache limits. Defaults: 100 entries, 300s TTL. Added path traversal guard to `resolve_workspace_path` (Bug #1) — mirrors `resolve_agent_path`. Added 3 new `validate_config()` checks (Bug #17): model_registry entry completeness, agent role llm_role existence, allowed_internal_hosts type validation. |
| Pre-v1.0 | — | *(Fill this section with relevant info from edits and refactors. Add version history as it is learned.)* |

---

## ⚠️ Breaking Changes

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

*(No completed milestones yet. This is a pre-v1 document. Add completed features here as they ship.)*

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

*Last updated: 2026-07-03. See [ARCHITECTURE.md](ARCHITECTURE.md) for file maps, [API.md](API.md) for config reference, [INSTRUCTIONS.md](INSTRUCTIONS.md) for AI editing rules.*
