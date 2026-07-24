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

---

### Anti-patterns & Lessons Learned

*(Fill this section with relevant info from edits and refactors. Add lessons learned as they are discovered.)*
