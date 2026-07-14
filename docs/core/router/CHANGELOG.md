<- Back to [Router Overview](../ROUTER.md)

# 🗺️ Changelog

## 📝 Version History

| Version | Date | Notes |
|---------|------|-------|
| **v1.0** | 2026-07-14 | **First versioned release (Pre-v1 → v1.0).** Split `core/router.py` (710-line single file) into a `core/router_backend/` package (10 files) following the LLM/memory/gateway pattern: `decision.py`, `constants.py`, `heuristics.py`, `model_route.py`, `swarm_fallback.py`, `complexity.py`, `telemetry.py` (**NEW**), `adaptive.py` (**NEW**), `router.py` (orchestrator), `__init__.py`. `core/router.py` is now a **36-line thin facade** re-exporting the 7 public symbols (`router`, `TaskRouter`, `RoutingDecision`, `ROUTER_SYSTEM_PROMPT`, `ROUTER_FEW_SHOT_EXAMPLES`, `ROUTER_TOOLS`, `ROUTER_WORKFLOWS`) — all `from core.router import X` callers (workflow tool, dispatcher, gateway, tests) continue to work unchanged. **Routing telemetry** (P2 roadmap): `log_routing_telemetry()` is called from `route()` after every non-empty-goal decision; `heuristic_route()` is always invoked (cheap regex) so we can compare what it WOULD have returned against what the model actually returned. Disagreements (`model_workflow is not None and != heuristic_workflow`) are flagged in a bounded FIFO in-memory log (`_MAX_LOG_ENTRIES=100`). Query API: `get_telemetry()`, `get_telemetry_summary()` (returns `total` / `disagreements` / `disagreement_rate`), `clear_telemetry()`. **Adaptive complexity thresholds** (P2 roadmap): `apply_adaptive_thresholds(decision)` — if `complexity > 7` (strict, `COMPLEXITY_THRESHOLD = 7`) AND `confidence != "high"`, downgrade confidence to `"medium"` + add a clarifying question. Called from `route()` on every non-empty-goal decision (model success, swarm fallback, heuristic fallback). Strict `>` so existing complexity=7 test cases are unaffected. |
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
| **`core/router_backend/` package split (thin facade pattern)** | ✅ v1.0 | `core/router.py` (710-line single file) split into `core/router_backend/` package (10 files): `decision.py` (RoutingDecision), `constants.py` (prompts/tools/workflows), `heuristics.py` (16 pre-compiled regex patterns + `heuristic_route()`), `model_route.py` (`model_route()` + `_extract_first_json()`), `swarm_fallback.py` (`swarm_fallback_route()`), `complexity.py` (`classify_complexity()`), `telemetry.py` (NEW v1.0), `adaptive.py` (NEW v1.0), `router.py` (TaskRouter orchestrator), `__init__.py`. `core/router.py` is now a 36-line thin facade re-exporting the 7 public symbols — all `from core.router import X` callers (workflow tool, dispatcher, gateway, tests) continue to work unchanged. Follows the LLM/memory/gateway pattern. |
| **Routing telemetry** | ✅ v1.0 | `core/router_backend/telemetry.py`. `log_routing_telemetry()` called from `route()` after every non-empty-goal decision. `heuristic_route()` is always invoked (cheap regex, microseconds) so we can compare what it WOULD have returned against what the model actually returned. Disagreements (`model_workflow is not None and != heuristic_workflow`) flagged in bounded FIFO in-memory log (`_MAX_LOG_ENTRIES=100`). Query API: `get_telemetry()`, `get_telemetry_summary()` (returns `total` / `disagreements` / `disagreement_rate`), `clear_telemetry()`. |
| **Adaptive complexity thresholds** | ✅ v1.0 | `core/router_backend/adaptive.py`. `apply_adaptive_thresholds(decision)`: if `complexity > 7` (strict `>`, `COMPLEXITY_THRESHOLD = 7`) AND `confidence != "high"`, downgrade to `"medium"` + add a clarifying question. Called from `route()` on every non-empty-goal decision (model success, swarm fallback, heuristic fallback). Mutates in place AND returns for fluent chaining. Strict `>` (not `>=`) so existing complexity=7 test cases (autocode-with-file-extension) are unaffected. |

---

## 🔄 In Progress / Next Up

| Feature | Notes | Priority |
|---------|-------|----------|
| Dynamic workflow composition | Chain multiple workflows (e.g., research → data). Deferred — not a router feature (requires workflow-engine coordination). | P3 |

---

## 🚫 Deferred / Out of Scope

*(No deferred items yet. Add entries here as decisions are made.)*

---

*Last updated: 2026-07-14 (v1.0 — first versioned release: split `core/router.py` into `core/router_backend/` package (10 files, thin facade pattern); added routing telemetry (`log_routing_telemetry()` + `get_telemetry()` / `get_telemetry_summary()` / `clear_telemetry()`) + adaptive complexity thresholds (`apply_adaptive_thresholds()` — `complexity > 7` + non-`high` confidence → downgrade + clarifying question); moved 2 P2 roadmap items to ✅ Completed; "Dynamic workflow composition" remains In Progress as P3). See [ARCHITECTURE.md](ARCHITECTURE.md) for file maps, [API.md](API.md) for method details, [INSTRUCTIONS.md](INSTRUCTIONS.md) for AI editing rules.*
