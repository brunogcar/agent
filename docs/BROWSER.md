# BROWSER

## Overview

The `browser()` tool provides **Playwright-based browser automation** for JavaScript-rendered pages, interactive forms, and visual screenshots. It is the agent's fallback when `web(read)` fails on SPAs, and the primary tool for user interaction workflows.

**Key characteristics:**
- **JavaScript rendering** — Full Chromium engine, handles React/Angular/Vue
- **Stateful sessions** — Cookies and localStorage persist within a `trace_id`
- **Interactive** — Click, fill, type, select, keyboard presses
- **Screenshots** — Full page or element capture, saved to disk
- **NOT_PARALLEL_SAFE** — Serialized via `threading.Lock()`; heavy resource usage

---

## Architecture

```
tools/browser.py
├── browser(action, ...)           # @tool facade — sync, action-dispatch
├── _run_async(coro)              # Async-to-sync bridge
├── _launch_browser(...)          # Lazy Playwright launch (global singleton)
├── _get_or_create_context(...)   # Per-trace BrowserContext
├── _get_page(...)                # Per-trace Page
├── _start_reaper()               # Daemon thread: close idle contexts (>10min)
├── _cleanup_all()                # atexit hook: close all resources
└── _browser_lock                 # threading.Lock() — serializes all calls
```

**Lifecycle:**
```
Process start
    └─ _browser = None

First call (navigate)
    └─ _launch_browser() → Playwright + Chromium (global, headless)
        └─ _get_or_create_context(trace_id) → BrowserContext (isolated)
            └─ _get_page(trace_id) → Page
                └─ page.goto(url)

Subsequent calls (same trace)
    └─ Reuse existing Context + Page

action="close" or error
    └─ Close Context + Page for trace_id

Process exit
    └─ atexit → _cleanup_all() → Close browser + stop Playwright
```

---

## Tool Signature

```python
@tool
def browser(
    action: str,                       # "navigate" | "click" | "fill" | "type" | ...
    url: str = "",                    # target URL (navigate)
    selector: str = "",               # CSS selector (click, fill, etc.)
    value: str = "",                  # input value (fill, type, select_option)
    path: str = "",                   # screenshot save path
    wait_until: str = "domcontentloaded",  # "networkidle" | "domcontentloaded" | "load"
    timeout: int = 30,                # action timeout in seconds
    delay: int = 50,                  # keystroke delay in ms (type)
    key: str = "",                    # key to press (keyboard_press)
    expression: str = "",             # JS expression (evaluate)
    headless: bool = True,            # headless mode (False for debug)
    return_base64: bool = False,      # return base64 screenshot inline
    trace_id: str = "",               # trace identifier
) -> dict:
    """..."""
```

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `action` | `str` | — | **Required.** See Actions table below |
| `url` | `str` | `""` | URL for `navigate` |
| `selector` | `str` | `""` | CSS selector for element actions |
| `value` | `str` | `""` | Text/value for `fill`, `type`, `select_option` |
| `path` | `str` | `""` | Screenshot save path (auto-generated if empty) |
| `wait_until` | `str` | `"domcontentloaded"` | Page load state to wait for |
| `timeout` | `int` | `30` | Timeout per action (seconds) |
| `delay` | `int` | `50` | Delay between keystrokes (ms) |
| `key` | `str` | `""` | Key name for `keyboard_press` |
| `expression` | `str` | `""` | JavaScript expression for `evaluate` |
| `headless` | `bool` | `True` | Run headless (False for visual debug) |
| `return_base64` | `bool` | `False` | Return base64 image (max 100KB) |
| `trace_id` | `str` | `""` | Trace identifier for context isolation |

---

## Actions

| Action | Required Params | Description |
|--------|-----------------|-------------|
| `navigate` | `url` | Go to URL, wait for load state |
| `click` | `selector` | Click element by CSS selector |
| `fill` | `selector`, `value` | Clear + type into input |
| `type` | `selector`, `value` | Type with human-like delay |
| `screenshot` | — | Capture full page or element |
| `text_content` | `selector` (opt) | Extract text from element (default: `body`) |
| `evaluate` | `expression` | Run JavaScript, return result |
| `select_option` | `selector`, `value` | Select dropdown option |
| `keyboard_press` | `key` | Press key (Enter, Tab, Escape, etc.) |
| `get_url` | — | Return current URL |
| `close` | — | Close browser context for this trace |

### `navigate` — Go to URL

```json
{
  "status": "success",
  "data": {
    "url": "https://example.com",
    "title": "Example Domain"
  }
}
```

### `screenshot` — Capture page

**Default behavior:** Saves to `workspace/screenshots/{trace_id}_{timestamp}.png`, returns path.

```json
{
  "status": "success",
  "data": {
    "path": "D:/mcp/agent/workspace/screenshots/t1_1234567890.png"
  }
}
```

**With `return_base64=True`:**
- Returns base64 string inline (capped at 100KB)
- Larger images truncated with `[truncated: full image at path]`

### `evaluate` — Run JavaScript

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

## Security

### SSRF Guard

All `navigate` URLs pass through `is_safe_network_address()`:

```python
if not is_safe_network_address(urlparse(url).hostname or ""):
    return fail(f"SSRF blocked: {url}", trace_id=trace_id)
```

### Dialog Auto-Dismiss

Every new page auto-registers a dialog dismiss handler to prevent hangs:

```python
page.on("dialog", lambda d: asyncio.ensure_future(d.dismiss()))
```

---

## State Management

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

### Cleanup

| Trigger | Behavior |
|---------|----------|
| `action="close"` | Close context + page for trace |
| Error during action | Auto-close context + page for trace |
| Idle > 10 minutes | Reaper thread closes context |
| Process exit | `atexit` closes all contexts + browser |

---

## Configuration

No dedicated `.env` variables. Uses:
- `cfg.workspace_root` — for screenshot and download paths
- Playwright's default Chromium binary (installed via `playwright install chromium`)

---

## Resource Management

| Resource | Cost | Mitigation |
|----------|------|------------|
| Chromium launch | ~150MB RAM, 1-3s | Global singleton, launched once |
| New context | ~5MB RAM | Reused within trace, reaped after idle |
| Screenshot (full page) | ~500KB-2MB PNG | Saved to disk, not returned inline |
| Concurrent calls | N/A | `threading.Lock()` serializes all calls |

---

## Testing

```powershell
# Run browser tests (fully mocked, no Playwright needed)
python -m pytest tests/tools/browser/ -v
```

**Mock strategy:**
- Patch `tools.browser._launch_browser` to return `AsyncMock`
- Build mock chain: Browser → Context → Page
- `page.on()` is synchronous — use `MagicMock`, not `AsyncMock`
- All async actions (`goto`, `click`, `fill`, etc.) use `AsyncMock`

---

## When to Use vs Alternatives

| Need | Tool | Why |
|------|------|-----|
| Static page text | `web(read)` | 10x faster, no overhead |
| JS-rendered page | `browser(navigate+text_content)` | Full Chromium rendering |
| Interactive forms | `browser(click, fill, select_option)` | User interaction simulation |
| Screenshots | `browser(screenshot)` | Visual capture |
| Multi-step flows | `browser` + sequential actions | Session state preserved |
| Simple search | `web(search)` | Free, no API costs |
| AI-ranked search | `tavily(search)` | Better relevance, citations |

---

## Future Roadmap

- **Phase 1 (Current):** Core actions: navigate, click, fill, type, screenshot, text_content, evaluate, select_option, keyboard_press, get_url, close
- **Phase 2 (Next):** Integrate as fallback in `workflows/research.py` — when `web(read)` returns `< 300` chars, retry with `browser`
- **Phase 3 (Future):** Add `browser(scroll)` action for infinite-scroll pages
- **Phase 4 (Future):** Add `browser(upload)` action for file upload workflows
- **Phase 5 (Future):** Vision tool integration — LLM can "see" screenshots via vision model
