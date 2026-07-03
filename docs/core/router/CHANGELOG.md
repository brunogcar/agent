<- Back to [Router Overview](../ROUTER.md)

# 🗺️ Changelog

## 📝 Version History

| Version | Date | Notes |
|---------|------|-------|
| Pre-v1 | 2026-07-04 | Initial implementation. Model-based + heuristic routing, confidence guard, complexity scoring, 15s timeout, 15 tools, 5 workflows. |

---

## ⚠️ Breaking Changes

*(No breaking changes yet. Add entries here when versions are released.)*

---

## ✅ Completed

| Feature | Status | Notes |
|---------|--------|-------|
| Model-based routing | ✅ Pre-v1 | Router LLM with 15s timeout |
| Heuristic fallback | ✅ Pre-v1 | Pre-compiled regex, O(1) matching |
| Confidence Guard | ✅ Pre-v1 | Low-confidence interception + clarifying questions |
| Deterministic JSON extraction | ✅ Pre-v1 | 3-layer pipeline with `raw_decode()` |
| Browser routing | ✅ Pre-v1 | `_RE_DIRECT_BROWSER` for browse/fill form/click keywords |
| CLI routing | ✅ Pre-v1 | `_RE_DIRECT_CLI` for shell command keywords |
| Tavily routing | ✅ Pre-v1 | `_RE_DIRECT_TAVILY` for AI search keywords |
| Consult routing | ✅ Pre-v1 | `_RE_DIRECT_CONSULT` for LLM consultation keywords |
| Parallel routing | ✅ Pre-v1 | `_RE_DIRECT_PARALLEL` for concurrent execution keywords |
| Deep Research workflow | ✅ Pre-v1 | `deep_research` in workflow list and heuristic |
| Understand workflow | ✅ Pre-v1 | `understand` in workflow list and heuristic |
| Vision routing | ✅ Pre-v1 | `_RE_DIRECT_VISION` for image analysis keywords |
| Agent routing | ✅ Pre-v1 | `_RE_DIRECT_AGENT` for sub-agent delegation keywords |
| Tool registry sync | ✅ Pre-v1 | Router prompt lists all 15 registered tools |
| False-positive regression tests | ✅ Pre-v1 | Adversarial tests for known misrouting cases |
| Module-level prompt constant | ✅ Pre-v1 | `ROUTER_SYSTEM_PROMPT` extracted for direct test import |

---

## 🔄 In Progress / Next Up

| Feature | Notes | Priority |
|---------|-------|----------|
| Routing telemetry | Log heuristic vs LLM route disagreements to identify real-world routing failures | P2 |
| Dynamic workflow composition | Chain multiple workflows (e.g., research → data) | P3 |
| Adaptive complexity thresholds | Require `high` confidence for complexity > 7 | P2 |

---

## 🚫 Deferred / Out of Scope

*(No deferred items yet. Add entries here as decisions are made.)*

---

*Last updated: 2026-07-04. See [ARCHITECTURE.md](ARCHITECTURE.md) for file maps, [API.md](API.md) for method details, [INSTRUCTIONS.md](INSTRUCTIONS.md) for AI editing rules.*
