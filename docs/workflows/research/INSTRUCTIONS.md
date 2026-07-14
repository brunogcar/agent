<- Back to [Research Overview](../RESEARCH.md)

# 🛡️ AI Instructions

## ❌ NEVER DO

1. **Never mutate state in-place** — LangGraph does not deep-copy. Always return partial update `dict`s.
2. **Never spread `**state`** — Never return `{**state, "key": "value"}`. Return only the changed keys.
3. **Never remove parallel scraping** — Sequential scraping would be too slow.
4. **Never skip citation tracking** — Attribution is important for trust.
5. **Never use `print()` to stdout** — MCP stdio corruption. Use `tracer.step()` for logging.
6. **Never create `.bak` files** — forbidden by project rules.
7. **Never rewrite the entire file** — surgical edits only. Preserve existing code exactly.
8. **Never skip `compileall` before `pytest`** — catches syntax errors early.
9. **Never call `agent()` without `action="dispatch"`** — The `agent()` facade requires `action`. Always pass `action="dispatch"` for LLM calls.
10. **Never return `None` from LangGraph nodes** — Always return a `dict` (even empty `{}`).
11. **Never read `search_results` in nodes after `synthesize`** — v1.1: The trim node evicts `search_results` between synthesize and report. Nodes after synthesize (report, store, distill, notify) must use `result`, not `search_results`. If you add a new node after synthesize, use `state.get("result", "")`.
12. **Never use `as_completed(timeout=)` for parallel scraping** — v1.0 fix #4: `as_completed` timeout is per-first-future, not global. Use `concurrent.futures.wait(timeout=)` for global timeout.
13. **Never leave pending futures running on timeout** — v1.0 fix #5: Call `.cancel()` on timed-out futures to prevent zombie threads.
14. **Never let memory/notify failures crash the workflow** — v1.1.1: Wrap `memory.recall`, `memory.store_*`, and `notify()` in `try/except` + `tracer.error` (same pattern as data workflow Fix #8/#10).
15. **Never return a routing key that doesn't match the conditional edges dict** — v1.1.1 P0: `route_after_synthesize` returned `"report"` but the dict mapped `"trim"`. The trim node was unreachable. Always verify routing return values match `add_conditional_edges` dict keys.

## ✅ ALWAYS DO

16. **Always return `dict` from nodes** — Not `WorkflowState`. Partial updates only.
17. **Always pass `trace_id` to tracer calls** — Observability requires trace correlation.
18. **Always handle search failure gracefully** — Empty results should route to END, not crash.
17. **Always test `route_after_search` with both paths** — Assert `"failed"` and `"synthesize"`.
18. **Always test `route_after_synthesize` with both paths** — Assert `"failed"` and `"trim"` (v1.1: was `"report"`).
21. **Always test memory storage** — Assert semantic + procedural memory stored correctly.
22. **Always test notification** — Assert `notify()` called with correct message.
23. **Always update this doc** when adding nodes, changing routing logic, or modifying error handling.
22. **Always use `!= "success"` not `not ... == "success"`** — The latter is confusing due to operator precedence (functionally correct but hard to read).
23. **Always use `cfg.web_max_search_results`** — Never hardcode `max_results`. The config var exists for a reason.
26. **Always store full `result` in semantic memory** — v1.0 fix #7: Semantic memory is for content retrieval. Truncating to 800 chars made it nearly useless.
27. **Always deduplicate URLs in `node_search`** — v1.0 fix #12: Use a `seen_urls` set to prevent duplicate scraping.

---

## 🚫 Anti-Patterns & Lessons Learned

> - **What happened:** `node_search` hardcoded `max_results=3` for web searches, ignoring `cfg.web_max_search_results` (default 10). Users got only 3 results per query regardless of config.
> - **Why it matters:** Research quality suffered — 3 results is too few for complex topics. The config existed but was never used.
> - **Fix (Pre-v1.0):** Pass `cfg.web_max_search_results` to `web(action="search", ...)`. Never hardcode limits that already have config vars.

> - **What happened:** `node_synthesize` used `not r.get("status") == "success"` — confusing operator precedence. While functionally correct (`not (x == "success")`), it looked like `(not x) == "success"` which would always be False.
> - **Why it matters:** Confusing code leads to misdiagnosis. A developer reading this might think the error path never fires (it does), or "fix" it incorrectly.
> - **Fix (Pre-v1.0):** Use explicit `r.get("status") != "success"` — same behavior, unambiguous.

> - **What happened:** `node_synthesize` called `agent(role="research", ...)` without `action="dispatch"`. The `agent()` facade requires `action`. Without it, every synthesis call returned `Unknown action ''` error — the workflow never produced real results.
> - **Why it matters:** The workflow was completely broken for its primary purpose. Users saw `node_error()` failures instead of research results.
> - **Fix (Pre-v1.0):** Always pass `action="dispatch"` to `agent()`. This is now INSTRUCTIONS rule #9.

> - **What happened:** `node_parallel_scrape` used `as_completed(timeout=90)`. The timeout is for the first future to complete, not the total time. If the first future completed quickly, subsequent futures could hang indefinitely.
> - **Why it matters:** A single slow page could freeze the entire workflow with no way to cancel.
> - **Fix (v1.0 #4/#5):** Changed to `concurrent.futures.wait(timeout=)` for global timeout. Pending futures are `.cancel()`ed on timeout to prevent zombie threads.

> - **What happened:** `node_store` stored only `result[:800]` in semantic memory. For long research results (5KB+), this was a tiny fraction — semantic memory was nearly useless for recall.
> - **Why it matters:** Semantic memory is for content retrieval. Truncating to 800 chars defeated the purpose — recall returned fragments instead of the full research.
> - **Fix (v1.0 #7):** Store the full `result` in semantic memory. Episodic memory still stores a short summary (it's for event tracking, not content retrieval).

> - **What happened:** v1.1 trim node wired between synthesize and report. Initial concern: does `node_report` or any downstream node read `search_results`?
> - **Why it matters:** If a downstream node reads `search_results` after trim evicts it, it would get a placeholder string instead of real data → crash or garbage output.
> - **Fix (v1.1):** Verified all 4 downstream nodes (report, store, distill, notify) read `result` (set by synthesize), not `search_results`. The trim insertion point is safe. Added `test_trim_integration.py` with field-safety tests that assert this contract via source inspection.

---

*Last updated: 2026-07-14 (v1.1.1). See [ARCHITECTURE.md](ARCHITECTURE.md) for file maps, [API.md](API.md) for node details, [CHANGELOG.md](CHANGELOG.md) for version history.*
