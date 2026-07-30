<- Back to [INVESTSITE Overview](../INVESTSITE.md)

# 🛡️ AI Instructions

### NEVER DO

1. **Never add sync logic or a local database** — This skill is pure live fetching. User explicitly prefers live data every call. No SQLite, no cache DB.
2. **Never remove the rate limiting** — 0.5s between requests. investsite is a free site; hammering it risks IP bans.
3. **Never remove browser-like headers** — investsite blocks bare User-Agents (403). The `_HEADERS` dict with Referer + Origin is required.
4. **Never parse HTML with BeautifulSoup** — The regex-based parser works and has no extra dependency. Don't add bs4 just for this.
5. **Never fetch the chart pages without browser tool** — amCharts data loads dynamically via JS. Simple HTTP GET returns empty data. Defer to roadmap.
6. **Never create `.bak` files** — Forbidden by project rules.
7. **Never rewrite entire files** — Surgical edits only. Preserve existing code exactly.
8. **Never print to stdout** — MCP stdio corruption. Use `core.tracer` or stderr.

### ALWAYS DO

1. **Always uppercase the ticker** — investsite URLs are case-sensitive; tickers are uppercase.
2. **Always handle ConnectionError gracefully** — Network failures should return `{status: "error", error: ...}`, not crash.
3. **Always make summary best-effort** — If indicators or events fail, return what's available.
4. **Always extract CVM PDF links in events mode** — The `link_cvm` field is the primary value-add (direct rad.cvm.gov.br links).
5. **Always run `compileall` before `pytest`** — Catches syntax errors early.
6. **[v1.1] Always use `@register_mode(...)` for new modes** — Drop a file in `modes/` + decorate. No edits to `__init__.py` or `_registry.py` needed. The auto-discovery in `__init__.py` picks it up via `importlib.import_module` over `modes/*.py`.
7. **[v1.1] Always wrap dashboard sub-calls in try/except** — `indicators()` + `events()` inside `dashboard()` must each be wrapped so a network/parse failure degrades the corresponding tab to an empty payload (table has 0 rows, KPIs render as "—") instead of crashing the whole dashboard.
8. **[v1.1] Always preserve the flat-domain MANIFEST shape** — investsite is a TOP-LEVEL flat domain (not under cvm/). The MANIFEST uses `"domain": "investsite"` (NOT `sub_domain`) + `"has_sub_domains": False`. The `route()` signature stays `route(sub_domain="", mode="", **kwargs)` — the `sub_domain` param is accepted but ignored. This is the ONLY structural difference from the CVM skill pattern.
9. **[v1.1] Always patch per-mode fetch_page in tests** — Each mode file imports `fetch_page` from `skills.investsite.fetcher` at the top level (NOT lazy). Tests must patch `skills.investsite.modes.<mode>.fetch_page` (the symbol imported into the mode module's namespace), not `skills.investsite.fetcher.fetch_page` (the original definition — patching that wouldn't affect already-imported references).

---

### Anti-patterns & Lessons Learned

#### v1.1 — Modular split + dashboard composition

- **Split the monolith, KEEP the fetchers/parsers.** Unlike CVM skills where the monolith bundled helpers + fetchers + parsers, `investsite.py` was already split into 3 files (`investsite.py` for mode logic + `fetcher.py` for HTTP + `parsers.py` for HTML parsing). The v1.1 split only touches the mode logic — `fetcher.py` (158 lines) + `parsers.py` (319 lines) are UNCHANGED. Each mode file imports `fetch_page` + URL builders + parsers directly. This keeps the split surgical: only the per-mode files are new, the data plumbing is reused as-is.
- **Aliased sibling-mode imports for summary().** `summary()` calls `indicators()` + `events()` internally — these now live in sibling mode files. Use aliased imports (`from skills.investsite.modes.indicators import indicators as _indicators` + `from skills.investsite.modes.events import events as _events`) to avoid name clash with the `summary` mode name + keep call sites short (`_indicators(ticker=ticker)` instead of `indicators.indicators(ticker=ticker)`).
- **Top-level domain ≠ CVM sub_domain.** investsite is a flat top-level domain (no `cvd` parent). The MANIFEST keeps `"domain": "investsite"` + `route(sub_domain="", mode="", **kwargs)`. The `sub_domain` param is accepted (for dispatcher compatibility) but ignored. Don't try to "normalize" investsite to match the CVM pattern — the difference is intentional.
- **KPI spec per metric.** Dashboard KPIs use mixed specs: P/L, P/VPA, EV/EBITDA use `num` (raw multiples); ROE + Dividend Yield use `pct` (fractions 0.15 = 15%). The adapter's unit -> spec map (`pct -> pct`, `num -> num`) keeps the formatting consistent.
- **Defensive `_first_value` for multi-column sections.** The `parse_indicators` parser stores a scalar when a row has one value column and a list when it has multiple (e.g. "Consolidado" + "Atual"). The KPI builders use `_first_value(v)` to extract the first non-None element when the value is a list — otherwise pass through.
- **Cross-skill consumer updates needed.** Grep found non-test consumers of `skills.investsite.investsite`: `skills/cvm/calculations/engines/shares.py` + `skills/cvm/valuation/fetchers.py` + `tests/skills/cvm/test_integration.py` all used `from skills.investsite.investsite import indicators`. All three were updated to `from skills.investsite.modes.indicators import indicators` — no backward-compat re-export shim needed (cleaner than keeping a dead `investsite.py` file).
