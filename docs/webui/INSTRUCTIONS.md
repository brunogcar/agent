<- Back to [WebUI Overview](../WEBUI.md)

# 🛡️ WebUI AI Instructions

> Rules for AI assistants editing the WebUI code. No API details, no architecture — just rules.

---

### NEVER DO

1. **Never build a SPA (React/Vue/Svelte).** The WebUI is server-rendered Jinja2 + HTMX. A SPA would require Node.js, a build step, a bundler, CORS config, and duplicate the formatting logic in JS. The data is server-owned — rendering stays server-side.

2. **Never call the MCP `skill()` dispatcher from WebUI routes.** The MCP dispatcher is LLM-shaped (stringified JSON params, trace_ids, LLM error envelopes). Import calculation engines directly via `webui/services/`.

3. **Never import skill engines directly from route handlers.** All data access goes through `webui/services/`. Routes are thin HTTP handlers, not data access layers.

4. **Never use WebSocket for sync progress.** SSE (Server-Sent Events) is the right tool — one-way, auto-reconnects, no protocol library. WebSocket is for bidirectional communication only.

5. **Never use gettext/Babel for i18n.** JSON translation files + the `t()` function. gettext's `.po`/`.mo` compile step is overkill for ~200-300 strings.

6. **Never translate domain terms.** DRE, DFC, DVA, P/L, P/VPA, ROE, EBITDA, CNPJ, CD CVM — these are proper nouns in finance. An English-language Brazilian finance UI still says "DRE".

7. **Never hardcode colors in CSS.** Use CSS variables (`var(--color-brand)`, etc.). Themes are JSON files that define the variables.

8. **Never hardcode user-visible strings in templates.** Every string goes through `{{ t("key") }}` from day one. Retrofitting i18n is 10x harder than building it in.

9. **Never block the event loop on sync.** Sync takes minutes. Run it in a background thread, stream progress via SSE. The HTTP endpoint must return immediately.

10. **Never skip SQLite WAL mode.** Without WAL, concurrent reads (WebUI) + sync writes = `database is locked`. The startup WAL setup in `core/db_wal.py` is critical.

11. **Never use CDN for vendor JS.** HTMX, Alpine.js, Chart.js are vendored in `webui/static/vendor/`. Local-first project, works offline, no version drift.

12. **Never create a `.bak` file.** Forbidden by project rules.

13. **Never rewrite the report design system.** The WebUI reuses CSS variables, macros, and Chart.js patterns from `tools/report_ops/templates/`. Share the design system, don't duplicate it.

---

### ALWAYS DO

1. **Always use `TemplateResponse(request, "template.html", context)`.** The Starlette 0.29+ signature requires `request` as the first positional arg. The old `TemplateResponse("template.html", context)` signature raises `unhashable type: 'dict'`.

2. **Always wrap engine calls in `engine_cache_scope()`.** The calculations engines use `@engine_cached` which checks a ContextVar cache. Without `engine_cache_scope()`, shared engines (earnings, pl, debt) get re-queried N times.

3. **Always set `data-theme` before CSS loads.** FOUC (Flash-Of-Unstyled-Content) prevention: inline script in `<head>` reads `localStorage.theme` and sets `data-theme` on `<html>` before any CSS loads.

4. **Always init charts after HTMX swaps.** Inline `<script>` tags in HTMX-swapped content don't execute. `app.js` listens for `htmx:afterSwap` and calls `initChartsInElement()`. Any new chart must use the `data-chart-type` attribute pattern.

5. **Always check `request.is_disconnected()` in SSE generators.** Otherwise the generator leaks after the client closes the tab. Use `asyncio.wait_for(queue.get(), timeout=15)` with keepalive comments.

6. **Always use `X-Accel-Buffering: no` on SSE responses.** Nginx and other proxies buffer SSE streams by default, causing progress events to arrive in batches instead of real-time.

7. **Always add new themes as JSON files.** Drop a file in `webui/themes/`, done. `theme.py` auto-discovers. No code change needed.

8. **Always add new locales as JSON files.** Drop a file in `webui/locales/`, add the code to `SUPPORTED_LOCALES` in `i18n.py`. No other code change.

9. **Always use `PRAGMA journal_mode=WAL` on SQLite connections.** The startup `db_wal.py` sets this persistently, but if you open a new connection manually, set WAL + `busy_timeout=5000`.

10. **Always run `python webui.py` to test.** Not `uvicorn webui.app:create_app`. The entry point sets up sys.path, runs WAL setup, and configures uvicorn correctly.
