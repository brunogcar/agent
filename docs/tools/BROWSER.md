# 🌐 Browser Tool

The `browser()` tool provides **Playwright-based browser automation** for JavaScript-rendered pages, interactive forms, visual screenshots, and dynamic content workflows. It is the agent's fallback when `web(read)` fails on SPAs, and the primary tool for user interaction workflows.

**Key characteristics:**
- **JavaScript rendering** — Full Chromium engine, handles React/Angular/Vue SPAs
- **Stateful sessions** — Cookies and localStorage persist within a `trace_id`
- **Interactive** — Click, fill, type, select, keyboard presses, scroll
- **Wait primitives** — `wait_for_selector` and `wait_for_url` for reliable async page transitions
- **Screenshots** — Full page or element capture, saved to disk
- **NOT_PARALLEL_SAFE** — Serialized via `threading.Lock()`; heavy resource usage

---

## 🏗️ Architecture

The browser tool follows a **thin facade + core submodule** pattern. `tools/browser.py` is the only file scanned by `registry.py` for `@tool` discovery; all logic lives in `tools/browser_core/`.

```
tools/browser.py                    # @tool facade — sync action dispatch
tools/browser_core/
├── actions.py                      # Action handlers + DISPATCH dict + DISPATCH_METADATA
├── init.py                         # _launch_browser(), _get_or_create_context(), _get_page()
├── loop.py                         # _ensure_browser_loop(), _run_browser_async()
├── lifecycle.py                    # _start_reaper(), _cleanup_all(), screenshot pruning
└── state.py                        # Global state: _browser, _contexts, _pages, _browser_lock
```

### Lifecycle Flow

```mermaid
graph TD
    A[Process Start] --> B[_browser = None]
    B --> C[First Call]
    C --> D[_launch_browser<br/>Playwright + Chromium]
    D --> E[_get_or_create_context<br/>per trace_id]
    E --> F[_get_page<br/>per trace_id]
    F --> G[page.goto / click / fill / ...]
    G --> H{Same trace?}
    H -->|Yes| G
    H -->|No| E
    G --> I[action="close"]
    I --> J[Close Context + Page]
    J --> K[Process Exit]
    K --> L[atexit → _cleanup_all]
    L --> M[Stop Playwright]
```

**Key design decisions:**
- **Global singleton browser** — Launched once, reused across all traces. ~150MB RAM, 1–3s cold start.
- **Per-trace BrowserContext** — Each `trace_id` gets an isolated context (cookies, localStorage). Prevents cross-trace pollution.
- **Dedicated event loop thread** — Playwright runs in a daemon thread with its own `asyncio` loop. The main thread calls `_run_browser_async(coro, timeout)` which bridges sync → async via `asyncio.run_coroutine_threadsafe()`.
- **Module-level lock** — `_browser_lock` serializes all browser operations. Prevents race conditions on global state.

---

## 📋 Tool Signature

```python
@tool
def browser(
    action: str,                       # Required. See Actions table below.
    url: str = "",                    # Target URL (navigate, wait_for_url)
    selector: str = "",               # CSS selector (click, fill, scroll, etc.)
    value: str = "",                   # Input value (fill, type, select_option)
    path: str = "",                    # Screenshot save path
    wait_until: str = "domcontentloaded",  # "networkidle" | "domcontentloaded" | "load"
    timeout: int = 30,                # Action timeout in seconds
    delay: int = 50,                  # Keystroke delay in ms (type)
    key: str = "",                     # Key name (keyboard_press)
    expression: str = "",              # JS expression (evaluate)
    headless: bool = True,             # Headless mode (False for debug)
    return_base64: bool = False,       # Return base64 screenshot inline (Phase 5)
    trace_id: str = "",                # Trace identifier for context isolation
    direction: str = "",               # Scroll direction: "top" | "bottom" | "up" | "down"
    amount: int = 0,                   # Scroll amount in pixels (default: full height)
) -> dict:
    """..."""
```

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `action` | `str` | — | **Required.** See Actions table below |
| `url` | `str` | `""` | URL for `navigate`, glob pattern for `wait_for_url` |
| `selector` | `str` | `""` | CSS selector for element actions |
| `value` | `str` | `""` | Text/value for `fill`, `type`, `select_option` |
| `path` | `str` | `""` | Screenshot save path (auto-generated if empty) |
| `wait_until` | `str` | `"domcontentloaded"` | Page load state to wait for |
| `timeout` | `int` | `30` | Timeout per action (seconds) |
| `delay` | `int` | `50` | Delay between keystrokes (ms) |
| `key` | `str` | `""` | Key name for `keyboard_press` |
| `expression` | `str` | `""` | JavaScript expression for `evaluate` |
| `headless` | `bool` | `True` | Run headless (False for visual debug) |
| `return_base64` | `bool` | `False` | Return base64 image (Phase 5) |
| `trace_id` | `str` | `""` | Trace identifier for context isolation |
| `direction` | `str` | `""` | Scroll direction: `"top"` \| `"bottom"` \| `"up"` \| `"down"` |
| `amount` | `int` | `0` | Pixels to scroll (0 = full height for top/bottom) |

---

## 🎬 Actions

| Action | Required Params | Optional Params | Description |
|--------|-----------------|-----------------|-------------|
| `navigate` | `url` | `wait_until`, `timeout`, `headless` | Go to URL, wait for load state |
| `click` | `selector` | `timeout`, `headless` | Click element by CSS selector |
| `fill` | `selector`, `value` | `timeout`, `headless` | Clear + type into input |
| `type` | `selector`, `value` | `delay`, `timeout`, `headless` | Type with human-like delay |
| `screenshot` | — | `selector`, `path`, `timeout`, `headless`, `return_base64` | Capture full page or element |
| `text_content` | — | `selector`, `timeout`, `headless` | Extract text (default: `body`) |
| `evaluate` | `expression` | `timeout`, `headless` | Run JavaScript, return result |
| `select_option` | `selector`, `value` | `timeout`, `headless` | Select dropdown option |
| `keyboard_press` | `key` | `timeout`, `headless` | Press key (Enter, Tab, Escape, etc.) |
| `get_url` | — | `timeout`, `headless` | Return current URL |
| `close` | — | `trace_id` | Close browser context for this trace |
| `wait_for_selector` | `selector` | `timeout`, `headless` | Wait for element to appear in DOM |
| `scroll` | — | `selector`, `direction`, `amount`, `timeout`, `headless` | Scroll page or element |
| `wait_for_url` | `url` | `timeout`, `headless` | Wait for URL to match pattern |

### Action Details

#### `navigate` — Go to URL

```python
result = browser(action="navigate", url="https://example.com", trace_id="t1")
```

```json
{
  "status": "success",
  "data": {
    "url": "https://example.com",
    "title": "Example Domain"
  }
}
```

**SSRF Protection:** All URLs pass through `is_safe_network_address()`. Private IPs, localhost, and internal ranges are blocked unless explicitly allowlisted in `cfg.allowed_internal_hosts`.

---

#### `click` — Click Element

```python
result = browser(action="click", selector="button.submit", trace_id="t1")
```

```json
{
  "status": "success",
  "data": {
    "clicked": true,
    "selector": "button.submit"
  }
}
```

---

#### `fill` / `type` — Input Text

```python
# fill: clear field then type
browser(action="fill", selector="input#email", value="user@example.com", trace_id="t1")

# type: human-like delay between keystrokes
browser(action="type", selector="input#email", value="user@example.com", delay=100, trace_id="t1")
```

---

#### `screenshot` — Capture Page

```python
# Full page
browser(action="screenshot", trace_id="t1")

# Specific element
browser(action="screenshot", selector="div.chart", trace_id="t1")

# Custom path
browser(action="screenshot", path="D:/reports/chart.png", trace_id="t1")
```

**Default path:** `{cfg.workspace_root}/screenshots/{trace_id}_{timestamp}.png`

```json
{
  "status": "success",
  "data": {
    "path": "D:/mcp/agent/workspace/screenshots/t1_1234567890.png"
  }
}
```

**Screenshot cleanup:** Files older than 7 days are auto-deleted on startup and every 6 hours.

---

#### `evaluate` — Run JavaScript

```python
result = browser(action="evaluate", expression="document.title", trace_id="t1")
```

```json
{
  "status": "success",
  "data": {
    "expression": "document.title",
    "result": "Example Domain"
  }
}
```

---

#### `scroll` — Scroll Page or Element

```python
# Scroll to bottom of page
browser(action="scroll", direction="bottom", trace_id="t1")

# Scroll to top
browser(action="scroll", direction="top", trace_id="t1")

# Scroll down by amount
browser(action="scroll", direction="down", amount=500, trace_id="t1")

# Scroll element into view
browser(action="scroll", selector="#target", trace_id="t1")
```

| Direction | Behavior |
|-----------|----------|
| `"top"` | `window.scrollTo(0, 0)` |
| `"bottom"` | `window.scrollTo(0, document.body.scrollHeight)` |
| `"up"` | `window.scrollBy(0, -amount)` (default 1000px) |
| `"down"` | `window.scrollBy(0, amount)` (default 1000px) |
| `selector` provided | `element.scroll_into_view_if_needed()` |

```json
{
  "status": "success",
  "data": {
    "scrolled": true,
    "direction": "bottom",
    "amount": 0
  }
}
```

---

#### `wait_for_selector` — Wait for Element

Use after clicks that trigger dynamic content, or before interacting with lazily-loaded elements.

```python
browser(action="wait_for_selector", selector="div.content", timeout=10, trace_id="t1")
```

```json
{
  "status": "success",
  "data": {
    "waited": true,
    "selector": "div.content"
  }
}
```

---

#### `wait_for_url` — Wait for Navigation

Use after form submits or SPA route changes where the next action must run on the new page.

```python
browser(action="wait_for_url", url="**/dashboard", timeout=10, trace_id="t1")
```

Supports glob patterns (e.g., `"**/dashboard"`, `"https://example.com/**"`).

```json
{
  "status": "success",
  "data": {
    "waited": true,
    "url": "https://example.com/dashboard"
  }
}
```

---

#### `close` — Clean Up

```python
browser(action="close", trace_id="t1")
```

Closes the BrowserContext and Page for the given trace. The global Chromium browser remains running for other traces.

---

## 🔒 Security

### SSRF Guard

All `navigate` URLs pass through `is_safe_network_address()` before any network request:

```python
hostname = urlparse(url).hostname or ""
if not is_safe_network_address(hostname):
    return fail(f"SSRF blocked: {url}", trace_id=trace_id)
```

Blocked by default: private IPs, localhost, link-local, multicast, loopback. Allowlist via `ALLOWED_INTERNAL_HOSTS` in `.env`.

### Dialog Auto-Dismiss

Every new page auto-registers a dialog dismiss handler to prevent event loop hangs:

```python
page.on("dialog", lambda d: asyncio.create_task(d.dismiss()))
```

---

## 🗄️ State Management

### Per-Trace Isolation

```python
# Trace A: logged into GitHub
browser(action="navigate", url="https://github.com/login", trace_id="trace_a")
browser(action="fill", selector="input[name=login]", value="user", trace_id="trace_a")
browser(action="click", selector="input[type=submit]", trace_id="trace_a")

# Trace B: fresh context, not logged in
browser(action="navigate", url="https://github.com", trace_id="trace_b")
# → Sees GitHub homepage, not dashboard
```

### Cleanup Triggers

| Trigger | Behavior |
|---------|----------|
| `action="close"` | Close context + page for trace |
| Error during action | Context + page remain (retry possible) |
| Idle > 10 minutes | Reaper thread closes idle context |
| Process exit | `atexit` → `_cleanup_all()` closes all + stops Playwright |

---

## ⚙️ Configuration

No dedicated `.env` variables. Uses:
- `cfg.workspace_root` — screenshot and download paths
- Playwright's default Chromium binary (installed via `playwright install chromium`)

---

## 📊 Resource Management

| Resource | Cost | Mitigation |
|----------|------|------------|
| Chromium launch | ~150MB RAM, 1–3s | Global singleton, launched once |
| New context | ~5MB RAM | Reused within trace, reaped after idle |
| Screenshot (full page) | ~500KB–2MB PNG | Saved to disk, auto-pruned after 7 days |
| Concurrent calls | N/A | `threading.Lock()` serializes all calls |

---

## 🧪 Testing

```powershell
# Run all browser tests (fully mocked, no Playwright needed)
D:\mcpgentenv\Scripts\pytest.exe tests/tools/browser -v -W error
```

**Test architecture:**
- `conftest.py` provides `mock_browser` and `mock_cfg_for_browser` fixtures
- `mock_browser` builds a full mock chain: Browser → Context → Page (all `AsyncMock`)
- Tests are **fully isolated** — no real Chromium, no network, no shared state
- `reset_browser_state` fixture clears globals between tests

**Mock strategy:**
- `page.on()` is synchronous — use `MagicMock`, not `AsyncMock`
- All async Playwright actions (`goto`, `click`, `fill`, etc.) use `AsyncMock`
- `conftest.py` patches `cfg` at module level in `lifecycle`, `init`, and `actions`

**Test file layout (mirrors source):**

```
tests/tools/browser/
├── conftest.py                 # Shared fixtures
├── test_navigate.py            # Navigate action
├── test_click.py               # Click action
├── test_fill.py                # Fill action
├── test_type.py                # Type action
├── test_screenshot.py          # Screenshot action
├── test_text_content.py        # Text extraction
├── test_evaluate.py            # JS evaluation
├── test_select_option.py      # Dropdown selection
├── test_keyboard_press.py     # Key press
├── test_get_url.py            # URL retrieval
├── test_close.py               # Context cleanup
├── test_scroll.py             # Scroll action (Phase 3)
├── test_wait_for_selector.py  # Wait for element (Phase 3)
├── test_wait_for_url.py       # Wait for URL (Phase 3)
├── test_browser_error_handling.py  # Unknown action, empty action
├── test_browser_screenshot.py      # Size limits, truncation
└── test_browser_ssrf.py            # SSRF blocking
```

---

## 🔀 When to Use vs Alternatives

| Need | Tool | Why |
|------|------|-----|
| Static page text | `web(read)` | 10× faster, no overhead |
| JS-rendered page | `browser(navigate+text_content)` | Full Chromium rendering |
| Interactive forms | `browser(click, fill, select_option)` | User interaction simulation |
| Infinite scroll / lazy load | `browser(scroll)` | Loads dynamic content |
| SPA navigation | `browser(wait_for_url)` | Waits for route change |
| Screenshots | `browser(screenshot)` | Visual capture |
| Multi-step flows | `browser` + sequential actions | Session state preserved |
| Simple search | `web(search)` | Free, no API costs |
| AI-ranked search | `tavily(search)` | Better relevance, citations |

---

## 🛡️ AI Agent Instructions

If you are an AI assistant modifying the browser tool:

1. **Never mutate LangGraph state in-place** — return partial update dicts only.
2. **Never write to stdout** — all logging goes through `core.tracer` to stderr.
3. **Preserve the async bridge** — all Playwright calls go through `_run_browser_async()` in the dedicated loop thread. Never call Playwright directly from the main thread.
4. **Module-level cfg import** — if conftest.py patches `tools.browser_core.actions.cfg`, `cfg` must be imported at module level in `actions.py`. Inline imports break `unittest.mock.patch`.
5. **Add actions to all three places** — new actions require: (a) handler function, (b) entry in `DISPATCH`, (c) entry in `DISPATCH_METADATA`.
6. **Thread safety** — all handlers acquire `_browser_lock`. Never bypass the lock.
7. **SSRF first** — `navigate` must validate URLs before any network call.
8. **Test with mock_browser** — new tests must use the `mock_browser` fixture from `conftest.py`, not manual `patch()` of `_get_page`.
9. **Screenshot paths** — use `cfg.workspace_root / "screenshots"`, never hardcoded paths.
10. **Dialog handler** — new pages must register `page.on("dialog", ...)` to prevent hangs.

---

## 🔗 Source Code Reference

| File | Purpose |
|------|---------|
| `tools/browser.py` | `@tool` facade, action dispatch, tracer logging |
| `tools/browser_core/actions.py` | Action handlers, `DISPATCH`, `DISPATCH_METADATA` |
| `tools/browser_core/init.py` | Browser/context/page lazy initialization |
| `tools/browser_core/loop.py` | Dedicated async event loop thread |
| `tools/browser_core/lifecycle.py` | Reaper, cleanup, screenshot pruning |
| `tools/browser_core/state.py` | Global state variables and reset helpers |
| `tests/tools/browser/conftest.py` | Test fixtures (`mock_browser`, `mock_cfg_for_browser`) |

---

## 🔮 Future Roadmap

| Phase | Status | Description |
|-------|--------|-------------|
| **Phase 1** | ✅ Complete | Core actions: navigate, click, fill, type, screenshot, text_content, evaluate, select_option, keyboard_press, get_url, close |
| **Phase 2** | ✅ Complete | Browser split: `tools/browser.py` → `tools/browser_core/` (actions, init, loop, lifecycle, state) |
| **Phase 3** | ✅ Complete | New actions: `scroll`, `wait_for_selector`, `wait_for_url` |
| **Phase 4** | 🚧 Planned | File upload/download actions |
| **Phase 5** | 🚧 Planned | Vision integration: `return_base64`, `analyze_page`, `extract_links`, `extract_tables` |
| **Phase 6** | ✅ Complete | Tracer logging, `DISPATCH_METADATA`, atexit fix, rich error messages |
| **Phase 7** | 🚧 Planned | Integrate as fallback in `workflows/research.py` — when `web(read)` returns `< 300` chars, retry with `browser` |

---

*Last updated: Phase 6 complete. 43 browser tests passing, 2 skipped. Architecture: thin facade + browser_core submodules.*
