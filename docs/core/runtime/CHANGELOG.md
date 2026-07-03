<- Back to [RUNTIME Overview](../RUNTIME.md)

# 🗺️ Changelog

## 📝 Version History

| Version | Date | Changes |
|---------|------|---------|

*(Fill this section with relevant info from edits and refactors. Add version history as it is learned.)*

---

## ⚠️ Breaking Changes

*(No breaking changes recorded yet. Add entries here as they occur.)*

---

## ✅ Completed

| Feature | Status | Notes |
|---------|--------|-------|
| Activity tracker | ✅ Complete | Idle detection + inference slots |
| Cancellation guards | ✅ Complete | Ghost mutation prevention |
| Health checks | ✅ Complete | Full subsystem monitoring |
| Provider abstraction | ✅ Complete | LM Studio, Ollama, vLLM |
| Process watchdog | ✅ Complete | Auto-restart with cooldown |
| Background task executor | ✅ Complete | ThreadPoolExecutor + timeout |

---

## 🔄 In Progress / Next Up

| Feature | Notes | Priority |
|---------|-------|----------|
| Watchdog metrics | Track restart count, uptime, MTBF to Prometheus | P2 |
| Graceful model switching | Hot-swap models without full restart | P2 |
| Health-based routing | Skip unhealthy providers in multi-server setups | P2 |
| Watchdog alerts | Notify on persistent failures (email, webhook) | P3 |

---

## 🚫 Deferred / Out of Scope

| # | Feature | Why Deferred | Priority |
|---|---------|------------|----------|
| 1 | **Watchdog systemd/Docker integration** | Default restart commands are basic. Use `LM_STUDIO_RESTART_CMD` for custom setups. | Skip |
| 2 | **Activity tracker persistence** | In-memory state is intentional. Resets on restart are correct behavior. | Skip |
| 3 | **Unified health/watchdog probe** | Different timeouts and endpoints serve different purposes. Independence is a feature. | Skip |

---

*Last updated: 2026-07-04. See [ARCHITECTURE.md](ARCHITECTURE.md) for file maps, [API.md](API.md) for module details, [INSTRUCTIONS.md](INSTRUCTIONS.md) for AI editing rules.*
