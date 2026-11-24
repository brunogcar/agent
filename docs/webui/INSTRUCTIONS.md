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

14. **Never add a per-subtab API route for a new tab (v1.7+).** New subtabs are registered in `webui/adapters/registry.py` and served by the ONE generic endpoint `GET /api/webui/company/{ticker}/sections/{key}`. Adding a route per subtab is the pattern v1.7 replaced.

15. **Never invent a new payload shape for the generic renderer.** Payloads rendered by the generic section renderer MUST satisfy `webui/adapters/contract.py` (flat `{kpis, sections}` / grouped `{groups}` / error `{_error}`; section types: chart, table, two_column, ratio_grid, heatmap). The dispatcher validates and logs violations — build sections with the `contract.py` helpers instead of hand-rolling dicts.

---

### ALWAYS DO

1. **Always use `TemplateResponse(request, "template.html", context)`.** The Starlette 0.29+ signature requires `request` as the first positional arg. The old `TemplateResponse("template.html", context)` signature raises `unhashable type: 'dict'`.

2. **Always wrap engine calls in `engine_cache_scope()`.** The calculations engines use `@engine_cached` which checks a ContextVar cache. Without `engine_cache_scope()`, shared engines (earnings, pl, debt) get re-queried N times.

3. **Always set `data-theme` before CSS loads.** FOUC (Flash-Of-Unstyled-Content) prevention: the `<html data-theme>` is SERVER-rendered from the `webui_theme` COOKIE — the cookie is the single source of truth (v1.5: the FOUC script's old `localStorage.theme` read was never written anywhere, so a stale value could override the selected theme). The only localStorage uses are the sidebar-collapse flag and one-shot navigation keys — never theme/locale.

4. **Always init charts after HTMX swaps.** Inline `<script>` tags in HTMX-swapped content don't execute. `app.js` listens for `htmx:afterSwap` and calls `initChartsInElement()`. Any new chart must use the `data-chart-type` attribute pattern.

5. **Always check `request.is_disconnected()` in SSE generators.** Otherwise the generator leaks after the client closes the tab. Use `asyncio.wait_for(queue.get(), timeout=15)` with keepalive comments.

6. **Always use `X-Accel-Buffering: no` on SSE responses.** Nginx and other proxies buffer SSE streams by default, causing progress events to arrive in batches instead of real-time.

7. **Always add new themes as JSON files.** Drop a file in `webui/themes/`, done. `theme.py` auto-discovers. No code change needed.

8. **Always add new locales as JSON files.** Drop a file in `webui/locales/`, add the code to `SUPPORTED_LOCALES` in `i18n.py`. No other code change.

9. **Always use `PRAGMA journal_mode=WAL` on SQLite connections.** The startup `db_wal.py` sets this persistently, but if you open a new connection manually, set WAL + `busy_timeout=5000`.

10. **Always run `python webui.py` to test.** Not `uvicorn webui.app:create_app`. The entry point sets up sys.path, runs WAL setup, and configures uvicorn correctly.

11. **Always add a new tab through the adapter registry (v1.7+).** The recipe: (1) a service method returning a contract payload — use the `contract.py` builders (`chart_section`, `table_section`, `kpi`, …); (2) ONE `register("options:overview", _bind(OptionsService, "overview"), family="options", label="…")` call in `webui/adapters/registry.py`; (3) a tab shell partial + a client loader fetching `/api/webui/company/{ticker}/sections/options:overview`. Register with `generic=False` only when the subtab has its own client renderer (like Preço/Financeiro do).

12. **Always get service instances from `webui.adapters.registry.service(cls)`.** It's the memoized singleton factory — routes and adapters share ONE instance (PriceService carries the shared OHLCV cache). Constructing `PriceService()` directly duplicates the cache.

13. **Always check the pre-flight panel when data seems missing.** `/webui/sync` shows the Diagnóstico do Sistema card (DB existence, schema, WAL, row counts, adapter registry). `GET /api/webui/preflight/` returns the same report as JSON for scripting. A "re-key pendente" warn on itr.db means the DB predates v1.7.1 — sync the `itr` source (the per-source button force re-downloads current+previous year and the engine re-keys as it re-parses); for the full history run the engine once: `python -c "from data_sources.cvm.itr.sync_engine import sync; sync(full_history=True, force=True)"` (idempotent — only rows still at meses=12 are touched; close the WebUI first, the pass wipes the engine cache).

14. **Always re-key snapshot semantics from the filing's flow rows, never the calendar month.** A BPA/BPP row has no period of its own — its bucket comes from the DRE/DFC rows of the same filing (see `data_sources/cvm/_meses.py`'s snapshot corollary and Design Decision 12). Calendar-month mappings silently mis-bucket fiscal-year filers (May/Aug/Nov quarter ends).
