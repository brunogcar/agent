<- Back to [Router Overview](../ROUTER.md)

# 🗺️ Changelog

## 📝 Version History

| Version | Date | Notes |
|---------|------|-------|
| Pre-v1 | 2026-07-14 | **Swarm vote-based routing fallback.** When router confidence is low (heuristic fall-through) AND `ROUTER_SWARM_FALLBACK=1`, calls `swarm(action="vote", temperature=0)` for a second opinion. Requires unanimous/majority agreement + valid workflow type. Non-fatal — failures fall back to heuristic decision. New config flag `ROUTER_SWARM_FALLBACK=0` (default OFF). |
| Pre-v1 | 2026-07-11 | **Internal refactor — `_extract_first_json` delegation.** `_extract_first_json()` now delegates to `core/json_extract.extract_first_json()` (the new consolidated JSON extraction module introduced in autocode v2.0-alpha Phase 1). The router's 3-layer pipeline (direct parse → markdown fence strip → `json.JSONDecoder().raw_decode()`) is preserved as the implementation inside `core/json_extract.py`. No behavior change, no API change. The router's `core/router.py` now imports from `core/json_extract` instead of inlining the logic. |
| Pre-v1 | 2026-07-08 | **Hardening fix:** Router schema now includes `confidence` and `clarifying_questions` fields (was missing — `additionalProperties: False` blocked the model from generating those fields, silently breaking confidence-based routing logic). |
| Pre-v1 | 2026-07-08 | **JSON schema enforcement:** `_model_route()` now passes `json_schema` to `llm.complete()`. LM Studio enforces the routing schema (workflow, tool, complexity, reason, confidence, clarifying_questions) at generation time. Defensive JSON parsing stays as fallback. |
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
| Deterministic JSON extraction | ✅ Pre-v1 | 3-layer pipeline with `raw_decode()`. **[Pre-v1]** `_extract_first_json()` now delegates to `core/json_extract.extract_first_json()` — the consolidated JSON extraction module shared with `helpers._parse_json` in autocode. Internal refactor only; behavior unchanged. |
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
| Swarm vote-based routing fallback** | ✅ Pre-v1 | New `_swarm_fallback_route()` method on `TaskRouter`. When `_model_route()` returns `None` AND `_heuristic_route()` returns `confidence="low"` AND `cfg.router_swarm_fallback` is `True`, calls `swarm(action="vote", question=<one-word classification prompt>, temperature=0, max_tokens=20, timeout=15)`. Requires `agreement in {"unanimous", "majority"}` AND winner ∈ `{autocode, research, data, deep_research, understand, direct}`. Returns `RoutingDecision(workflow=winner, tool="workflow", complexity=5, confidence="medium")`. Non-fatal — any exception returns `None` and the heuristic decision stands. Gated by new config flag `ROUTER_SWARM_FALLBACK=0` (default OFF — opt-in via env var). 8 tests in `tests/core/test_router.py`. |
| **[Pre-v1] `_extract_first_json` delegation to `core/json_extract`** | ✅ Pre-v1 | `_extract_first_json()` in `core/router.py` now delegates to `core/json_extract.extract_first_json()` instead of inlining the 3-layer pipeline (direct parse → markdown fence strip → `json.JSONDecoder().raw_decode()`). The pipeline implementation moved to `core/json_extract.py` verbatim — no behavior change, no API change. The router's `core/router.py` adds `from core.json_extract import extract_first_json` and replaces the inline body with a one-line delegation. This unifies JSON extraction across the codebase: `helpers._parse_json` (autocode) and `router._extract_first_json` both now delegate to the same module. Internal refactor only — introduced alongside autocode v2.0-alpha Phase 1. |

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

*Last updated: 2026-07-14 ( — swarm vote-based routing fallback via `ROUTER_SWARM_FALLBACK=1` (default OFF); non-fatal, requires unanimous/majority agreement + valid workflow type; 8 new tests in `tests/core/test_router.py`). See [ARCHITECTURE.md](ARCHITECTURE.md) for file maps, [API.md](API.md) for method details, [INSTRUCTIONS.md](INSTRUCTIONS.md) for AI editing rules.*
