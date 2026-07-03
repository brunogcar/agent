<- Back to [Router Overview](../ROUTER.md)

# 🛡️ AI Router Instructions

## ❌ NEVER DO

1. **Never remove the Confidence Guard** — the `low` confidence interception in `tools/workflow_tool.py` prevents massive VRAM waste on misunderstood tasks.
2. **Never remove the heuristic fallback** — if LM Studio is offline, the agent must still route basic tasks via keywords.
3. **Do not simplify the JSON parser** — do not replace `_extract_first_json()` with `re.search(r'{.*}')`. The `raw_decode()` approach handles nested objects and escaped quotes safely.
4. **Never add heavy computations to the routing path** — do not add file I/O or secondary LLM calls. This must remain ultra-lightweight.
5. **Never hardcode model identifiers** — always use `role="router"` in `llm.complete()`. Never hardcode model identifiers.
6. **Never create `.bak` files** — forbidden by project rules.
7. **Never rewrite the entire file** — surgical edits only. Preserve existing code exactly.
8. **Never skip `compileall` before `pytest`** — catches syntax errors early.
9. **Never print to stdout** — MCP stdio corruption. Return dicts only.

## ✅ ALWAYS DO

10. **Always update keyword lists carefully** — when adding to regex patterns, ensure there is no overlap that would cause a direct tool request to be misrouted to a heavy workflow.
11. **Always use `re.compile()` at class level** — all new keyword patterns must be pre-compiled, not compiled on every call.
12. **Always check priority order** — when adding new patterns, insert them in the correct priority position in `_heuristic_route()`. More specific patterns must come before more general ones.
13. **Always keep prompt in sync** — when adding a new tool or workflow, update BOTH the system prompt AND the heuristic fallback. Also update `ROUTER.md` and the drift test.
14. **Always use `tracer.step()` with `trace_id`** — all routing decisions must be logged.
15. **Always patch pytest to `D:\mcp\agent\venv\Scripts\pytest.exe`** — per project workflow.
16. **Always include `-W error` and `--tb=short` in pytest commands** — clean output, catch warnings.
17. **Always update this doc** when adding tools, workflows, or changing routing logic.

## 🚫 Anti-Patterns & Lessons Learned

*(No entries yet. Add lessons here as they are learned from future refactors and bug fixes. When an AI assistant encounters a bug, fix, or architectural insight during editing, add it here with:*

> - **What happened:** The symptom or bug
> - **Why it matters:** The impact
> - **Fix:** The solution or pattern to follow

*Fill this section with relevant information during edits and refactors.)*

---

*Last updated: 2026-07-04. See [ARCHITECTURE.md](ARCHITECTURE.md) for file maps, [API.md](API.md) for method details, [CHANGELOG.md](CHANGELOG.md) for version history.*
