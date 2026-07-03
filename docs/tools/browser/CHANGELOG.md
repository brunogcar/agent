<- Back to [Browser Overview](../BROWSER.md)

# 🗺️ Changelog

## 📝 Version History

| Version | Date | Changes |
|---------|------|---------|

*(Fill this section with relevant info from edits and refactors. Add version history as it is learned.)*

---

## ⚠️ Breaking Changes

### v1 (meta_tool refactor + new actions)

| Old | New | Migration |
|-----|-----|-----------|
| Monolithic `browser_ops/actions.py` (17.5KB) | Atomic `browser_ops/actions/*.py` (20 files) | No migration needed — same API |
| Manual `DISPATCH` dict + `DISPATCH_METADATA` | `@register_action` auto-discovery + `@meta_tool` | No migration needed — same API |
| Manual docstring in `browser()` | `@meta_tool` auto-generated from `help_text` + `examples` | No migration needed — same API |
| `screenshot` base64 TODO | `return_base64=True` fully implemented | Use `return_base64=True` |
| `wait_for_selector` no state param | `state="visible"` default | Default is backward-compatible |
| `**kwargs` in all handlers | `**kwargs` kept (absorbs unused facade params) | No migration needed |
| `close()` without `trace_id` | `close()` requires `trace_id` (previously leaked contexts) | Always pass `trace_id` to `close` |
| `extract_links`/`extract_tables` string interpolation | `json.dumps()` for safe JS injection | No migration — internal fix |

- Split monolithic `actions.py` into 20 atomic action files under `browser_ops/actions/`
- Added `@register_action` auto-discovery via `pathlib` + `importlib`
- Added `@meta_tool` auto-generated `Literal` enum and docstring
- Added `hover` action — hover over elements, triggers CSS `:hover` states
- Added `cookies` action — get/set/clear browser cookies per context (with URL filter)
- Added `set_viewport` action — change viewport size for responsive testing
- Added `extract_html` action — extract raw HTML from element or full page
- Added `extract_links` action — structured link extraction with safe JS injection
- Added `extract_tables` action — structured table extraction with safe JS injection
- Implemented `screenshot` base64 encoding (`return_base64=True`)
- Added screenshot-on-failure — debug screenshot attached to error messages
- Added tracer spans per action (`:complete` / `:failed`)
- Added `state` param to `wait_for_selector` (`"attached"`, `"detached"`, `"visible"`, `"hidden"`)
- Added duplicate action guard in `@register_action`: raises `ValueError` on collision
- Preserved "WHEN TO USE THIS TOOL" decision table via `doc_sections`

### v1.1 (bug fixes + upload + retry)

- **Fixed** `close()` without `trace_id` — now returns error instead of silently leaking context
- **Fixed** `extract_links`/`extract_tables` — use `json.dumps()` for safe JS selector injection; empty selector defaults to `"a"`/`"table"`
- **Fixed** `navigate` — URL scheme validation blocks `file://`, `javascript:`, `data:` before any network call
- **Fixed** `set_viewport` and `cookies` — `headless` param now forwarded to `_get_page`
- **Fixed** `select_option` help_text — restored `<select>` description
- **Fixed** `extract_html` — full page HTML labeled `"full_page"` instead of `"body"`
- **Fixed** `browser.py` — lazy-import `cfg` in `_try_failure_screenshot` to avoid unpatched binding in tests
- **Fixed** `browser.py` — screenshot-on-failure now also skipped on exception path for `screenshot` and `close` actions
- **Added** `upload` action — upload files to `<input type="file">` elements
- **Added** `navigate` retry with exponential backoff — `retries=N` param
- **Added** `cookies` URL filter — `url` param for targeted cookie retrieval
- **Added** `cookies` JSON validation — explicit error messages for malformed input

### v1.2 (Claude audit follow-up)

- **Fixed** `upload.py` — added `resolve_path` guard to prevent arbitrary filesystem access via path parameter
- **Fixed** `close.py` — returns `closed: False` with reason when context not found (was returning `closed: True` misleadingly)
- **Documented** `navigate.py` retry — added note that retry reuses same page/context; may fail if page crashed

---

## ✅ Completed

| Action | Status | Notes |
|--------|--------|-------|
| `@meta_tool` refactor | ✅ v1 | Auto-generated schema + docstring |
| `@register_action` pattern | ✅ v1 | Auto-discovery via `actions/` directory |
| `hover` | ✅ v1 | Hover over elements |
| `cookies` | ✅ v1 | Get/set/clear cookies with URL filter |
| `set_viewport` | ✅ v1 | Viewport resizing |
| `extract_html` | ✅ v1 | Raw HTML extraction |
| `screenshot` base64 | ✅ v1 | `return_base64=True` |
| `wait_for_selector` state param | ✅ v1 | `attached`, `detached`, `visible`, `hidden` |
| Screenshot-on-failure | ✅ v1 | Auto-capture on error |
| Tracer spans | ✅ v1 | Per-action `:complete` / `:failed` |
| Duplicate action guard | ✅ v1 | `ValueError` on collision |
| `extract_links` | ✅ v1 | Safe JS injection via `json.dumps()` |
| `extract_tables` | ✅ v1 | Safe JS injection via `json.dumps()` |
| `upload` | ✅ v1.1 | File upload to `<input type="file">` |
| `navigate` retry | ✅ v1.1 | Exponential backoff on transient failure |
| `close()` without `trace_id` fix | ✅ v1.1 | Returns error instead of leaking context |
| `extract_links`/`extract_tables` safe JS | ✅ v1.1 | `json.dumps()` for selector injection; empty selector defaults |
| `navigate` URL scheme validation | ✅ v1.1 | Blocks `file://`, `javascript:`, `data:` before network call |
| `set_viewport`/`cookies` headless | ✅ v1.1 | `headless` param forwarded to `_get_page` |
| `select_option` help_text | ✅ v1.1 | Restored `<select>` description |
| `extract_html` full_page label | ✅ v1.1 | Full page HTML labeled `"full_page"` instead of `"body"` |
| `browser.py` lazy cfg import | ✅ v1.1 | Avoids unpatched binding in tests |
| Screenshot-on-failure exclusion | ✅ v1.1 | Skipped on exception path for `screenshot` and `close` |
| `cookies` URL filter | ✅ v1.1 | `url` param for targeted cookie retrieval |
| `cookies` JSON validation | ✅ v1.1 | Explicit error messages for malformed input |
| `upload.py` resolve_path guard | ✅ v1.2 | Prevents arbitrary filesystem access |
| `close.py` context not found | ✅ v1.2 | Returns `closed: False` with reason |
| `navigate` retry documentation | ✅ v1.2 | Note that retry reuses same page/context |

---

## 🔄 In Progress / Next Up

| Feature | Notes | Priority |
|---------|-------|----------|
| `download` | Download file from link | v2 |
| `pdf` | Save page as PDF (Chromium-only) | v2 |
| `intercept` | Network request interception | v2 |
| `mobile_emulate` | Device emulation (requires context-level changes) | v2 |
| `scroll` smooth | `behavior: "smooth"` option | v2 |
| `evaluate` sandbox hardening | Block `require("fs")`, `require("child_process")` | v2 |
| `analyze_page` | Vision model integration — send screenshot to vision-capable LLM | v2 |

---

## 🚫 Deferred / Out of Scope

| # | Feature | Why Deferred | Priority |
|---|---------|------------|----------|
| 1 | `download` not yet implemented | Playwright download API is async-event-driven | Skip |
| 2 | `pdf` not yet implemented | Chromium-only, requires `page.pdf()` | Skip |
| 3 | `mobile_emulate` not yet implemented | Requires context-level device descriptor | Skip |
| 4 | `intercept` not yet implemented | Requires route handler setup before navigation | Skip |
| 5 | `scroll` does not support smooth scrolling | Use `evaluate` with `window.scrollTo({behavior: "smooth"})` | Skip |
| 6 | Very large screenshots may exceed memory | No size limit enforced yet | Skip |
| 7 | `compress_result()` not yet implemented | Large `extract_html`/`extract_links`/`extract_tables` outputs may blow out LLM context window | Skip |
| 8 | `navigate` retry reuses same page/context | If page crashed during failed attempt, subsequent retries will also fail. A future v2 improvement may close and recreate the context between retries. | Skip |

---

*Last updated: 2026-07-03. See [ARCHITECTURE.md](ARCHITECTURE.md) for file maps, [API.md](API.md) for action details, [INSTRUCTIONS.md](INSTRUCTIONS.md) for AI editing rules.*
