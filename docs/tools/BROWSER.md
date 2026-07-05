# 🌐 Browser Tool

The `browser()` tool automates web browsers via Playwright — navigate, click, fill, type, screenshot, evaluate JavaScript, scroll, hover, manage cookies, upload files, and more. All browser operations run in a dedicated async event loop to avoid blocking the main MCP thread.

**Key characteristics:**
- **Atomic actions** — `navigate`, `click`, `fill`, `type`, `screenshot`, `text_content`, `evaluate`, `select_option`, `keyboard_press`, `get_url`, `close`, `wait_for_selector`, `scroll`, `wait_for_url`, `hover`, `cookies`, `set_viewport`, `extract_html`, `extract_links`, `extract_tables`, `upload`. One action = one behavior
- **Auto-generated schema** — `@meta_tool` decorator builds `Literal` enum and docstring from DISPATCH
- **Session isolation** — Each `trace_id` gets its own `BrowserContext` (isolated cookies, localStorage)
- **Global singleton** — One Chromium instance shared across all traces; contexts are per-trace
- **SSRF protection** — `is_safe_network_address` blocks private IPs and localhost; URL scheme validation blocks `file://`, `javascript:`, `data:`
- **Screenshot auto-cleanup** — Files older than 7 days deleted on startup and every 6 hours
- **Screenshot-on-failure** — Failed actions (except `screenshot` and `close`) automatically capture a debug screenshot
- **Tracer spans** — Every action logs `action={name}`, `action={name}:complete`, and `action={name}:failed`
- **Navigate retry** — Uses `get_retry_delay()` from `core/net/errors.py` with unified constants from `core/net/default.py` (`BROWSER_TIMEOUT=30`, `BROWSER_NAV_RETRIES=2`)

---

## 🚀 Quick Start

*(Fill this section with relevant info from edits and refactors. Add quick start examples as they are learned.)*

---

## 🔄 When to Use vs Alternatives

| Need | Tool | Why |
|------|------|-----|
| Static page text | `web(read)` | Faster, no browser overhead |
| JS-rendered page text | `browser(navigate+text_content)` | Renders JavaScript |
| Interactive forms | `browser(click, fill, select_option)` | Supports interaction |
| Screenshots | `browser(screenshot)` | Captures rendered page |
| Multi-page workflows | `browser` + sequential actions | Maintains session state |
| Infinite scroll / lazy load | `browser(scroll)` | Loads dynamic content |
| SPA navigation | `browser(wait_for_url)` | Waits for route change |
| Hover-dependent UI | `browser(hover)` | Triggers dropdowns/tooltips |
| Cookie management | `browser(cookies)` | Get/set session cookies |
| Viewport testing | `browser(set_viewport)` | Responsive testing |
| Raw HTML extraction | `browser(extract_html)` | DOM structure |
| Extract all links | `browser(extract_links)` | Structured link data |
| Extract tables | `browser(extract_tables)` | Structured table data |
| File upload | `browser(upload)` | Upload to file inputs |

---

## ⚙️ Configuration

*(Fill this section with relevant info from edits and refactors. Add .env variables, requirements, and setup notes as they are learned.)*

---

## 📂 Subfile Directory

| File | Description |
|------|-------------|
| [Architecture](browser/ARCHITECTURE.md) | File maps, design decisions, test trees, mermaid diagrams |
| [API Reference](browser/API.md) | Tool signature, all 20 actions, security, output |
| [Changelog](browser/CHANGELOG.md) | Version history, breaking changes, v1/v1.1/v1.2 fixes, v2 roadmap |
| [Instructions](browser/INSTRUCTIONS.md) | AI editing rules, NEVER DO, ALWAYS DO, anti-patterns |

---

*Architecture: thin facade + @meta_tool + atomic action modules + auto-discovery + dedicated async loop + thread-safe lock + trace isolation + SSRF protection + URL scheme validation + safe JS injection + screenshot-on-failure + navigate retry + core/net adoption.*
