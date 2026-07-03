<- Back to [Vision Overview](../VISION.md)

# 🛡️ AI Instructions

## ❌ NEVER DO

1. **Never add an `action` param** — the tool is not multiplexed. Wait for the `@meta_tool` refactor.
2. **Never hardcode model names** — always use `cfg.vision_model`.
3. **Never remove the kill-switch check** — the first `if not cfg.vision_model` guard must remain. The tool must degrade gracefully.
4. **Never bypass `is_safe_network_address()`** — always validate URLs before any HTTP request.
5. **Never increase `MAX_IMAGE_BYTES` or `MAX_BASE64_LEN` without explicit user approval** — these are deliberate safety rails.
6. **Never accept multiple image sources** — exactly one of `file_path`, `base64`, or `url` must be enforced.
7. **Never print to stdout** — MCP stdio corruption. Return dicts only. Use `sys.stderr` for debug logs only.
8. **Never create `.bak` files** — forbidden by project rules.
9. **Never rewrite the entire file** — surgical edits only. Preserve existing code exactly.
10. **Never add `**kwargs` to the `@tool` facade** — FastMCP schema breaks.
11. **Never duplicate JSON parsing logic** — use `llm.call()` built-in `json_mode` parsing, not manual fence stripping.
12. **Never accept non-http URL schemes** — `file://`, `ftp://`, etc. must be rejected.

## ✅ ALWAYS DO

13. **Always include `trace_id` in responses** — observability requires trace correlation.
14. **Always include `model` and `elapsed` in success responses** — consumers need to know which model and how long.
15. **Always include `parse_warning` when JSON parsing fails** — consumers need to know their structured output is missing.
16. **Always test the kill-switch path** — patch `cfg.vision_model = ""` and assert `status == "error"`.
17. **Always test SSRF blocking** — patch `is_safe_network_address` to return `False` and assert blocked.
18. **Always test URL download failures** — mock `httpx.Client.get` with timeout and HTTP error side effects.
19. **Always use `compileall` before `pytest`** — catches syntax errors early.
20. **Always update this doc** when adding params, changing return shapes, or modifying behavior.

---

## 🚫 Anti-Patterns & Lessons Learned

*(Fill this section with relevant information from edits and refactors. Add lessons here as they are learned from future refactors and bug fixes. When an AI assistant encounters a bug, fix, or architectural insight during editing, add it here with:*

> - **What happened:** The symptom or bug
> - **Why it matters:** The impact
> - **Fix:** The solution or pattern to follow

*Fill this section with relevant information during edits and refactors.)*

---

*Last updated: 2026-07-03. See [ARCHITECTURE.md](ARCHITECTURE.md) for file maps, [API.md](API.md) for action details, [CHANGELOG.md](CHANGELOG.md) for version history.*
