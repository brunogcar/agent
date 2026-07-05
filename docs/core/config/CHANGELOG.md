<- Back to [Config Overview](../CONFIG.md)

# 🗺️ Changelog

## 📝 Version History

| Version | Date | Changes |
|---------|------|---------|
| Pre-v1.0 | 2026-07-05 | Added `agent_cache_max` and `agent_cache_ttl_seconds` env vars (Bug #19) for configurable agent tool cache limits. Defaults: 100 entries, 300s TTL. |
| Pre-v1.0 | — | *(Fill this section with relevant info from edits and refactors. Add version history as it is learned.)* |

---

## ⚠️ Breaking Changes

### Pre-v1.0 — 2026-07-05

| Change | Impact | Migration |
|--------|--------|-----------|
| New env vars: `AGENT_CACHE_MAX`, `AGENT_CACHE_TTL_SECONDS` | Agent tool cache limits are now configurable. Defaults match old hardcoded values (100 / 300). | Optional — add to `.env` to customize. No action needed for default behavior. |

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
