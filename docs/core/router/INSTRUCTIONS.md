<- Back to [Router Overview](../ROUTER.md)

# 🛡️ AI Router Instructions

## ❌ NEVER DO

1. **Never remove the Confidence Guard** — the `low` confidence interception in `tools/workflow.py` prevents massive VRAM waste on misunderstood tasks.
2. **Never remove the heuristic fallback** — if LM Studio is offline, the agent must still route basic tasks via keywords.
3. **Do not simplify the JSON parser** — do not replace `_extract_first_json()` with `re.search(r'{.*}')`. The `raw_decode()` approach handles nested objects and escaped quotes safely. **[v1.0]** `_extract_first_json()` is now a standalone function in `core/router_backend/model_route.py` (was a method on `TaskRouter`); it delegates to `core/json_extract.extract_first_json()`.
4. **Never add heavy computations to the routing path** — do not add file I/O or secondary LLM calls. This must remain ultra-lightweight. **[v1.0 exception]** The swarm fallback (`swarm_fallback_route()` in `core/router_backend/swarm_fallback.py`) is the *only* sanctioned secondary LLM call in the routing path, gated by `ROUTER_SWARM_FALLBACK=1` (default OFF) + 15s timeout + non-fatal error handling. The `heuristic_route()` call that `route()` makes up-front for telemetry is NOT a secondary LLM call (it's pure regex, microseconds) — it does not violate this rule. Do not add any others.
5. **Never hardcode model identifiers** — always use `role="router"` in `llm.complete()`. Never hardcode model identifiers.
6. **Never create `.bak` files** — forbidden by project rules.
7. **Never rewrite the entire file** — surgical edits only. Preserve existing code exactly.
8. **Never skip `compileall` before `pytest`** — catches syntax errors early.
9. **Never print to stdout** — MCP stdio corruption. Return dicts only.
10. **Never enable `ROUTER_SWARM_FALLBACK=1` without cloud providers configured. The swarm fallback calls `swarm(action="vote", ...)` which fan-outs to all configured cloud providers (`<NAME>_API_KEY` + `<NAME>_BASE_MODEL`). If no cloud providers are configured, the swarm returns `status="error"` (handled gracefully — the fallback returns `None` and the heuristic decision stands), but enabling the flag in that state just adds an import + lookup + `fail()` round-trip per low-confidence route for zero benefit. Use `swarm(action="list_providers")` to verify ≥1 cloud provider is configured before enabling. Local-only deployments (LM Studio only) should leave this flag OFF.
11. **Never change the swarm fallback's `temperature=0` to any other value. The vote's `agreement` classification must measure *genuine model disagreement*, not sampling noise. Two LLMs at `temperature=0` converge on the same answer more often than at `temperature=0.7` — so a `disagreement` verdict at `temperature=0` is unambiguous ("models genuinely disagree on classification"), whereas at `temperature=0.7` it would be ambiguous ("models sampled different tokens but might agree on classification"). The router's `_swarm_fallback_route()` hardcodes `temperature=0` — do not make it configurable per-call, do not "tune" it. See `docs/tools/swarm/INSTRUCTIONS.md` rule #45.
12. **Never let `swarm_fallback_route()` raise out of `route()`. The router's contract is `route(goal) -> RoutingDecision` — it must never raise. The swarm fallback is wrapped in `try/except Exception` that logs via `tracer.warning(...)` and returns `None` (which makes the caller fall through to the heuristic decision). If you add new code paths inside `swarm_fallback_route()` (in `core/router_backend/swarm_fallback.py`), they MUST be inside the try block. The flag is advisory — it must never turn a successful `route()` call into a failed one.
13. **Never add business logic to `core/router.py`** — it's a 36-line thin facade (v1.0 split). All implementation lives in `core/router_backend/`. The facade only re-exports the 7 public symbols (`router`, `TaskRouter`, `RoutingDecision`, `ROUTER_SYSTEM_PROMPT`, `ROUTER_FEW_SHOT_EXAMPLES`, `ROUTER_TOOLS`, `ROUTER_WORKFLOWS`) and instantiates the singleton. If you find yourself adding a method, a constant, or any branching logic to the facade, you're in the wrong file — add it to the appropriate backend module (`router.py` for orchestrator logic, `heuristics.py` for regex, `model_route.py` for the LLM call, `adaptive.py` for thresholds, `telemetry.py` for telemetry, etc.) and re-export from the facade if it's part of the public surface.
14. **Never add regex patterns to `TaskRouter`** — put them in `heuristics.py`. **[v1.0]** All 16 routing regex patterns (`_RE_*`) are module-level constants in `core/router_backend/heuristics.py`, NOT class attributes on `TaskRouter` (as they were pre-v1.0). New patterns go in `heuristics.py` as `_RE_NEW_PATTERN = re.compile(...)` and are inserted at the correct priority position in the `heuristic_route()` function's 18-step chain. Do NOT add `re.compile()` calls to `router_backend/router_engine.py` (the orchestrator) or to the facade.

## ✅ ALWAYS DO

15. **Always update keyword lists carefully** — when adding to regex patterns, ensure there is no overlap that would cause a direct tool request to be misrouted to a heavy workflow.
16. **Always use `re.compile()` at module level in `heuristics.py`** — **[v1.0]** all new keyword patterns must be pre-compiled as module-level constants (`_RE_NEW_PATTERN = re.compile(...)`), not compiled on every call. Was class-level on `TaskRouter` pre-v1.0 — the v1.0 split moved all 16 patterns to module-level in `core/router_backend/heuristics.py`.
17. **Always check priority order** — when adding new patterns, insert them in the correct priority position in `heuristic_route()` (in `core/router_backend/heuristics.py`; was `TaskRouter._heuristic_route()` pre-v1.0). More specific patterns must come before more general ones.
18. **Always keep prompt in sync** — when adding a new tool or workflow, update BOTH the system prompt AND the heuristic fallback. Also update `ROUTER.md` and the drift test.
19. **Always use `tracer.step()` with `trace_id`** — all routing decisions must be logged. Use `tracer.warning(...)` (not `tracer.step`) for non-fatal swarm fallback failures — these are warnings, not normal routing decisions.
20. **Always patch pytest to `D:\mcp\agent\venv\Scripts\pytest.exe`** — per project workflow.
21. **Always include `-W error` and `--tb=short` in pytest commands** — clean output, catch warnings.
22. **Always update this doc** when adding tools, workflows, or changing routing logic.
23. **Always run `tests/core/test_router.py` after touching `swarm_fallback_route()`. The 8-test suite covers: enabled/disabled flag behavior, high-confidence heuristic skip, low-agreement/invalid-winner/swarm-failure/exception-swallow paths, and the `temperature=0` invariant (test asserts the swarm call uses `temperature=0` + `action="vote"` + `max_tokens<=50`). Any change to the swarm fallback's call signature or guard conditions must keep these tests green. **[v1.0]** Tests now patch `core.router_backend.router_engine.model_route` (was `mocker.patch.object(TaskRouter, "_model_route", ...)` pre-v1.0) — `_model_route` is no longer a method on `TaskRouter`; `route()` calls the imported `model_route` function which lives in `core.router_backend.router_engine`'s namespace.
24. **Always run `heuristic_route()` inside `route()` for telemetry, even when the model succeeds.** **[v1.0]** The pre-model heuristic call is what powers the routing telemetry (`log_routing_telemetry()` compares `model_workflow` vs `heuristic_workflow` to flag disagreements). It's cheap (single regex pass, microseconds — does NOT call the LLM). Do NOT "optimize" by skipping the heuristic when `model_route()` succeeds — you'd silently break the disagreement-tracking contract. The only exception is the empty-goal short-circuit, which returns before the heuristic call (and also skips telemetry).

## 🚫 Anti-Patterns & Lessons Learned

*(No entries yet. Add lessons here as they are learned from future refactors and bug fixes. When an AI assistant encounters a bug, fix, or architectural insight during editing, add it here with:*

> - **What happened:** The symptom or bug
> - **Why it matters:** The impact
> - **Fix:** The solution or pattern to follow

*Fill this section with relevant information during edits and refactors.)*

---

*Last updated: 2026-07-14 (v1.0 — first versioned release: added NEVER DO rules #13 (no business logic in `core/router.py` — thin facade) + #14 (no regex patterns in `TaskRouter` — put them in `heuristics.py`)) + ALWAYS DO rule #24 (always run `heuristic_route()` in `route()` for telemetry); renumbered ALWAYS DO section +2 (#13–#22 → #15–#24) to continue from NEVER DO #14 — no cross-doc references broke; updated rules #3 / #4 / #12 / #16 / #17 / #23 to reference the v1.0 backend module paths and standalone function names (`_model_route` → `model_route`, `_heuristic_route` → `heuristic_route`, `_swarm_fallback_route` → `swarm_fallback_route`)). See [ARCHITECTURE.md](ARCHITECTURE.md) for file maps, [API.md](API.md) for method details, [CHANGELOG.md](CHANGELOG.md) for version history.*
