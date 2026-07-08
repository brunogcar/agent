<- Back to [Web Overview](../WEB.md)

# 🛡️ AI Instructions

## ❌ NEVER DO

1. **Never add `summarize` or `include_raw` params** — these never existed in the code. The LLM draft fabricated them.
2. **Never add per-action prompt engineering in the facade** — the web tool is a data-fetching tool, not an LLM orchestrator. Summarization belongs in workflows.
3. **Never remove the singleton client** — per-request `httpx.Client()` causes TCP/TLS handshake overhead and connection leaks. The singleton is the correct pattern.
4. **Never skip `_is_safe_url()` in `_fetch_html()`** — SSRF protection must be at the HTTP layer, not just the facade.
5. **Never expand `PARALLEL_SAFE` to include `web`** — `web` is already in `PARALLEL_SAFE`. The tool itself is safe for `parallel()` usage.
6. **Never create `.bak` files** — forbidden by project rules.
7. **Never rewrite the entire file** — surgical edits only. Preserve existing code exactly.
8. **Never add `**kwargs` to the `@tool` facade** — FastMCP schema breaks.
9. **Never print to stdout** — MCP stdio corruption. Return dicts only.
10. **Never skip `compileall` before `pytest`** — catches syntax errors early.
11. **Never call `future.cancel()` on running threads** — `ThreadPoolExecutor` futures that are `not_done` after `wait()` are already running. `.cancel()` is a no-op. Report them as timeout errors instead.
12. **Never import crawl4ai at module top level** — v1.3: It's a soft dependency. Import it lazily inside `_action_crawl()` only. Existing tests must pass without crawl4ai installed.
13. **Never add automatic fallback from `crawl` to `scrape`** — v1.3: The crawl action is a prototype for evaluation. Automatic fallback would hide crawl4ai failures and defeat the evaluation purpose. Caller retries explicitly.
14. **Never run crawl4ai's `AsyncWebCrawler` in the main event loop** — v1.3: The MCP server may have its own loop. Run via `asyncio.run()` in a dedicated thread to avoid "event loop already running" errors.

## ✅ ALWAYS DO

12. **Always use `_make_client()` context manager** — yields the singleton without closing it. Never use `httpx.Client()` directly in new code.
13. **Always call `prune_tool_dict()` for `read` and `search_and_read`** — these are the user-facing actions that may return large text. `scrape` is the raw internal helper.
14. **Always test SSRF blocking** — patch `core.net.security.is_safe_network_address` (not the wrapper) and assert blocked URLs return `fail`.
15. **Always test with explicit `cfg` values** — `MagicMock` causes comparison errors with `cfg.web_max_text_chars`. Use `patch.object(cfg, 'web_max_text_chars', 8000)`.
16. **Always test the unknown action path** — `web(action="nonsense")` must return `fail` with the usage hint.
17. **Always patch where the name is looked up** — `tools.web_ops.actions.search._make_client`, not `tools.web._make_client`.
18. **Always update this doc** when adding actions, changing return shapes, or modifying the singleton client.
19. **Always use `sorted()` in `__init__.py` glob** — `sorted(_actions_dir.glob("*.py"))` for deterministic import order across filesystems.
20. **Always lazy-import `prune_tool_dict`** — Import inside the handler function, not at module top, to avoid circular imports with `core.memory_backend.pruner`.
21. **Always use a single shared `cfg` mock** in `conftest.py` — patch all action modules to the same `MagicMock` object so mutations are visible to every handler.
22. **Always test the `max_chars=None` default path** — omit `max_chars` from facade calls and assert handlers resolve `cfg.web_max_text_chars`.
23. **Always test content-type guards** — set `response.headers = {"content-type": "application/pdf"}` and assert structured error.
24. **Always test retry behavior** — mock `time.sleep` to avoid real delays, assert call count equals retry attempts.

---

## 🚫 Anti-Patterns & Lessons Learned

*(No entries yet. Add lessons here as they are learned from future refactors and bug fixes. When an AI assistant encounters a bug, fix, or architectural insight during editing, add it here with:*

> - **What happened:** The symptom or bug
> - **Why it matters:** The impact
> - **Fix:** The solution or pattern to follow

*Fill this section with relevant information during edits and refactors.)*

---

*Last updated: 2026-07-08. See [ARCHITECTURE.md](ARCHITECTURE.md) for file maps, [API.md](API.md) for action details, [CHANGELOG.md](CHANGELOG.md) for version history.*
