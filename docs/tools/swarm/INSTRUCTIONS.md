<- Back to [Swarm Overview](../SWARM.md)

# 🛡️ AI Instructions

These rules apply to any AI assistant (or human editor) modifying the swarm tool, its handlers, its helpers, or its documentation. Follow them strictly — deviations have caused real bugs in similar meta-tools (`git`, `file`, `web`).

## ❌ NEVER DO

1. **Never add `lmstudio` to swarm.** Swarm is for cloud providers only. `_get_available_providers()` explicitly skips `name == "lmstudio"` — do not remove this check. Local models belong to `agent()` / `llm.complete()`, not swarm. Adding `lmstudio` would defeat the "different models, different vendors" premise and make `race` / `vote` meaningless (single local model racing itself).

2. **Never use `llm.complete()` for the per-provider fan-out calls.** `llm.complete()` dispatches by *role* and routes to *one* provider per role — it cannot express "call all providers in parallel". Swarm calls `provider.chat_completion()` directly via `_call_provider()`. The ONLY exception is the `consensus` synthesis step, which legitimately uses `llm.complete(role="planner", ...)` because synthesis is a single-model role-routed task.

3. **Never add `swarm` to `PARALLEL_SAFE` in `core/parallel_executor.py`.** Swarm uses its own `ThreadPoolExecutor` internally — nesting it inside `parallel(tools=[...])` would create nested thread pools and risk thread exhaustion. Swarm must remain excluded from the parallel allowlist.

4. **Never add `swarm` to `tools/parallel.py` `_TOOL_MAP`.** Same reason as #3 — `_TOOL_MAP` is the allowlist for parallel-safe tools. Swarm is NOT parallel-safe.

5. **Never call `swarm()` from inside another `swarm()` call.** "Swarm-of-swarms" compounds ThreadPoolExecutor nesting. If you need a union of providers, configure them all in `.env` and call swarm once with `providers=""`.

6. **Never bypass `_get_available_providers()` to read `llm._registry._providers` directly in an action handler.** The helper centralizes the `lmstudio` skip, the `*_BASE_MODEL` env check, and the comma-separated filter parsing. Bypassing it = three places to fix when the rules change.

7. **Never let a provider exception propagate out of `_call_provider()`.** The whole point of per-provider error isolation is that one failed provider (network error, auth error, timeout) doesn't kill the action. `_call_provider()` must catch all exceptions and return a result dict with `text=""` and `error=str(e)`.

8. **Never sort `_call_providers_race()` results by provider name.** Race semantics require preserving "who won" ordering — the winner must be first. Only `_call_all_providers()` sorts by provider name (for deterministic consensus/vote/compare output).

9. **Never remove the `max_workers=min(len(providers), 5)` cap.** Without it, configuring 10 providers would spawn 10 threads per swarm call — thread explosion risk. The cap is a deliberate safety valve.

10. **Never add a `Literal[...]` enum to the swarm facade's `action` parameter.** Swarm uses `action: str` with manual dispatch — this is intentional. `@meta_tool` is still applied (for `doc_sections` and metadata), but the `Literal` patch is skipped. Changing this would break the manual dispatch in the facade.

11. **Never forget to forward ALL kwargs to the handler.** The facade builds `kwargs = {question, context, providers, max_tokens, timeout, trace_id}` and passes them to `handler(**kwargs)`. Handlers absorb unused params via `**kwargs`. Removing a kwarg from the facade breaks handlers that read it; adding a kwarg to the facade without updating handlers silently no-ops (handler just ignores it via `**kwargs`).

12. **Never remove `del fn.__signature__` logic in `@meta_tool` if the decorator is modified.** Even though swarm doesn't use the `Literal` patch, `@meta_tool` is a shared decorator used by git/file/web/etc. that DOES need signature cache busting. See `docs/tools/git/INSTRUCTIONS.md` rule #5/#25.

13. **Never add a new action without registering it via `@register_action("swarm", "<name>", ...)`.** The `__init__.py` auto-imports `actions/*.py` to trigger registration; an unregistered handler is invisible to the dispatcher and returns "Unknown action".

14. **Never use `print()` or write to `sys.stdout` inside any swarm code.** MCP protocol uses stdout for JSON-RPC — writing to it corrupts the payload and crashes the server. Use `core.tracer` or `sys.stderr` for logging.

15. **Never assume `provider.chat_completion()` returns a string.** It returns an OpenAI-shape dict: `{"choices": [{"message": {"content": "..."}}], "usage": {...}}`. `_call_provider()` extracts `choices[0].message.content` — if you change this, update the extraction logic.

16. **Never hardcode provider names in action handlers.** Use the `providers` filter param and let `_get_available_providers()` do the work. Hardcoding "openai" / "claude" makes the handler brittle to env config changes.

17. **Never read `<NAME>_API_KEY` from env inside swarm.** API keys are owned by the provider instances (read at registration time in `core/llm/`). Swarm only checks whether `<NAME>_BASE_MODEL` is set — never the API key. Reading API keys inside swarm = security risk + scope creep.

18. **Never skip the `duration_ms` injection in the facade.** Wall-clock timing is measured at the facade level (single source of truth). Handlers must NOT time themselves — that would double-count or miss post-processing time.

19. **Never modify the swarm result schema without updating `API.md`.** The return shapes (`responses`, `synthesis`, `winner`, `agreement`, `groups`, `provider_count`, `successful_count`, `duration_ms`) are part of the public contract. Schema changes are breaking changes — bump the version in CHANGELOG.md.

20. **Never add swarm to `core/router.py` `ROUTER_TOOLS` without considering parallel-safety.** Router may fan out to multiple tools — if it dispatches swarm alongside other tools, the nested-parallelism risk applies. Router-level swarm calls should be sequential, not parallel.

---

## ✅ ALWAYS DO

21. **Use `provider.chat_completion()` directly for per-provider calls.** This is the canonical way to call a specific provider bypassing role routing. Returns OpenAI-shape dict. See `_call_provider()` in `helpers.py`.

22. **Handle errors per-provider inside `_call_provider()`.** Wrap the `provider.chat_completion()` call in try/except, capture the exception message, return a result dict with `text=""` and `error=str(e)`. Never let one provider's failure kill the whole action.

23. **Sort results by provider name in `_call_all_providers()`.** Deterministic output for consensus/vote/compare. Use `results.sort(key=lambda r: r["provider"])`. Do NOT sort in `_call_providers_race()` (race needs winner-first ordering).

24. **Use `_SWARM_SYSTEM_PROMPT` for all per-provider calls.** Defined in `helpers.py`. Action handlers should NOT redefine their own system prompt — the shared prompt ensures consistent behavior across actions.

25. **Use `_build_messages()` to construct the messages list.** Handles the optional `context` param (prepended as a user/assistant turn). Don't build messages inline in the handler.

26. **Cap ThreadPoolExecutor at `min(len(providers), 5)` workers.** Hard safety valve against thread explosion. Both `_call_all_providers()` and `_call_providers_race()` must use this cap.

27. **Use `as_completed(futures, timeout=timeout+10)` for the outer wait.** The +10s buffer gives in-flight providers a chance to finish after their per-call `timeout` fires. Don't use `executor.map()` or `future.result()` without a timeout.

28. **Return `fail("All providers failed to respond.", responses=results)` when every provider fails.** Attach the `responses` array so callers can inspect per-provider errors. The action only fails at the all-failed threshold — partial failures are not fatal.

29. **Use `ok({...})` / `fail(...)` from `core.contracts` for return shapes.** Standardized `{"status": "success"|"error", ...}` dict. Don't hand-roll the status field.

30. **Inject `trace_id` into the result if missing.** The facade does this — handlers should NOT redundantly inject it. If you add a new code path that returns before the facade's injection, make sure trace_id is included.

31. **Forward `**kwargs` in handler signatures.** The facade passes all kwargs to every handler; `list_providers` ignores them via `def _action_list_providers(**kwargs)`. Don't add explicit params that aren't used — `**kwargs` absorbs the rest.

32. **Register new actions via `@register_action("swarm", "<name>", help_text=..., examples=[...])`.** The `help_text` and `examples` are surfaced through DISPATCH for documentation. Keep them accurate.

33. **Update `API.md` and `CHANGELOG.md` when adding or changing an action.** New action = new row in the Summary Table + new section in API.md + new Completed row in CHANGELOG.md with version bump.

34. **Document WHY in code comments, not just WHAT.** The "direct provider calls" decision (vs `llm.complete()`) and the "skip lmstudio" decision are non-obvious. Future AI auditors need the rationale to avoid "fixing" them.

35. **Use `llm.complete(role="planner", ...)` for the consensus synthesis step.** This is the one place swarm routes through `llm.complete()` — synthesis is single-model role-routed, not multi-provider fan-out. Don't be tempted to "swarm the synthesis too" — that's a recursive rabbit hole.

36. **Normalize vote responses with `text.strip().lower()[:200]`.** Coarse comparison suited to short answers (YES/NO, class labels). Don't change the truncation length without considering the impact on agreement classification thresholds.

37. **Test with `mock_llm_registry` fixtures (once tests exist).** Patch `core.llm.llm._registry._providers` with `FakeProvider` instances — never make real API calls in tests. See ARCHITECTURE.md → Testing section for the proposed plan.

---

## 🚫 Anti-Patterns & Lessons Learned

*(Fill this section with relevant information from edits and refactors. Add lessons here as they are learned from future refactors and bug fixes. When an AI assistant encounters a bug, fix, or architectural insight during editing, add it here with:*

> - **What happened:** The symptom or bug
> - **Why it matters:** The impact
> - **Fix:** The solution or pattern to follow

*Fill this section with relevant information during edits and refactors. As of v1.0, no anti-patterns have been encountered yet — this is a new tool. The most likely future entries will be around: provider API quirks (e.g. Claude/Gemini `json_schema` incompatibility — see `docs/core/llm/INSTRUCTIONS.md` rule #12), ThreadPoolExecutor deadlock under load, or `*_BASE_MODEL` env var naming mismatches.)*

---

*Last updated: 2026-07-09. See [ARCHITECTURE.md](ARCHITECTURE.md) for file maps, [API.md](API.md) for action details, [CHANGELOG.md](CHANGELOG.md) for version history.*
