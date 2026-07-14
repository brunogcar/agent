<- Back to [Router Overview](../ROUTER.md)

# 🛡️ AI Router Instructions

## ❌ NEVER DO

1. **Never remove the Confidence Guard** — the `low` confidence interception in `tools/workflow.py` prevents massive VRAM waste on misunderstood tasks.
2. **Never remove the heuristic fallback** — if LM Studio is offline, the agent must still route basic tasks via keywords.
3. **Do not simplify the JSON parser** — do not replace `_extract_first_json()` with `re.search(r'{.*}')`. The `raw_decode()` approach handles nested objects and escaped quotes safely.
4. **Never add heavy computations to the routing path** — do not add file I/O or secondary LLM calls. This must remain ultra-lightweight. **[v1.0 exception]** The swarm fallback (`_swarm_fallback_route()`) is the *only* sanctioned secondary LLM call in the routing path, gated by `ROUTER_SWARM_FALLBACK=1` (default OFF) + 15s timeout + non-fatal error handling. Do not add any others.
5. **Never hardcode model identifiers** — always use `role="router"` in `llm.complete()`. Never hardcode model identifiers.
6. **Never create `.bak` files** — forbidden by project rules.
7. **Never rewrite the entire file** — surgical edits only. Preserve existing code exactly.
8. **Never skip `compileall` before `pytest`** — catches syntax errors early.
9. **Never print to stdout** — MCP stdio corruption. Return dicts only.
10. **Never enable `ROUTER_SWARM_FALLBACK=1` without cloud providers configured. The swarm fallback calls `swarm(action="vote", ...)` which fan-outs to all configured cloud providers (`<NAME>_API_KEY` + `<NAME>_BASE_MODEL`). If no cloud providers are configured, the swarm returns `status="error"` (handled gracefully — the fallback returns `None` and the heuristic decision stands), but enabling the flag in that state just adds an import + lookup + `fail()` round-trip per low-confidence route for zero benefit. Use `swarm(action="list_providers")` to verify ≥1 cloud provider is configured before enabling. Local-only deployments (LM Studio only) should leave this flag OFF.
11. **Never change the swarm fallback's `temperature=0` to any other value. The vote's `agreement` classification must measure *genuine model disagreement*, not sampling noise. Two LLMs at `temperature=0` converge on the same answer more often than at `temperature=0.7` — so a `disagreement` verdict at `temperature=0` is unambiguous ("models genuinely disagree on classification"), whereas at `temperature=0.7` it would be ambiguous ("models sampled different tokens but might agree on classification"). The router's `_swarm_fallback_route()` hardcodes `temperature=0` — do not make it configurable per-call, do not "tune" it. See `docs/tools/swarm/INSTRUCTIONS.md` rule #45.
12. **Never let `_swarm_fallback_route()` raise out of `route()`. The router's contract is `route(goal) -> RoutingDecision` — it must never raise. The swarm fallback is wrapped in `try/except Exception` that logs via `tracer.warning(...)` and returns `None` (which makes the caller fall through to the heuristic decision). If you add new code paths inside `_swarm_fallback_route()`, they MUST be inside the try block. The flag is advisory — it must never turn a successful `route()` call into a failed one.

## ✅ ALWAYS DO

13. **Always update keyword lists carefully** — when adding to regex patterns, ensure there is no overlap that would cause a direct tool request to be misrouted to a heavy workflow.
14. **Always use `re.compile()` at class level** — all new keyword patterns must be pre-compiled, not compiled on every call.
15. **Always check priority order** — when adding new patterns, insert them in the correct priority position in `_heuristic_route()`. More specific patterns must come before more general ones.
16. **Always keep prompt in sync** — when adding a new tool or workflow, update BOTH the system prompt AND the heuristic fallback. Also update `ROUTER.md` and the drift test.
17. **Always use `tracer.step()` with `trace_id`** — all routing decisions must be logged. Use `tracer.warning(...)` (not `tracer.step`) for non-fatal swarm fallback failures — these are warnings, not normal routing decisions.
18. **Always patch pytest to `D:\mcp\agent\venv\Scripts\pytest.exe`** — per project workflow.
19. **Always include `-W error` and `--tb=short` in pytest commands** — clean output, catch warnings.
20. **Always update this doc** when adding tools, workflows, or changing routing logic.
21. **Always run `tests/core/test_router.py` after touching `_swarm_fallback_route()`. The 8-test suite covers: enabled/disabled flag behavior, high-confidence heuristic skip, low-agreement/invalid-winner/swarm-failure/exception-swallow paths, and the `temperature=0` invariant (test asserts the swarm call uses `temperature=0` + `action="vote"` + `max_tokens<=50`). Any change to the swarm fallback's call signature or guard conditions must keep these tests green.

## 🚫 Anti-Patterns & Lessons Learned

*(No entries yet. Add lessons here as they are learned from future refactors and bug fixes. When an AI assistant encounters a bug, fix, or architectural insight during editing, add it here with:*

> - **What happened:** The symptom or bug
> - **Why it matters:** The impact
> - **Fix:** The solution or pattern to follow

*Fill this section with relevant information during edits and refactors.)*

---

*Last updated: 2026-07-14 (v1.0 — added NEVER DO rules #10-#12 (no flag without cloud providers, never change temp=0, never let swarm fallback raise) + ALWAYS DO rule #21 (run test_router.py after touching _swarm_fallback_route); rule #4 + #17 updated for swarm-fallback exception + tracer.warning). See [ARCHITECTURE.md](ARCHITECTURE.md) for file maps, [API.md](API.md) for method details, [CHANGELOG.md](CHANGELOG.md) for version history.*
