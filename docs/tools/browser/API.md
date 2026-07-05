<- Back to [Browser Overview](../BROWSER.md)

# 📝 API Reference

## 🔧 Tool Signature

```python
@tool
@meta_tool(
    DISPATCH.get("browser", {}),
    doc_sections=[...]
)
def browser(
    action: str,
    url: str = "",
    selector: str = "",
    value: str = "",
    path: str = "",
    wait_until: str = "domcontentloaded",
    timeout: int = BROWSER_TIMEOUT,  # [core/net] from core/net/default.py (30)
    delay: int = 50,
    key: str = "",
    expression: str = "",
    headless: bool = True,
    return_base64: bool = False,
    trace_id: str = "",
    direction: str = "",
    amount: int = 0,
    state: str = "visible",
    width: int = 1280,
    height: int = 720,
    cookies_json: str = "",
    action_detail: str = "get",
    retries: int = BROWSER_NAV_RETRIES,  # [core/net] from core/net/default.py (2)
) -> dict:
    \"\"\"...\"\"\"
```

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `action` | `str` | **Yes** | Browser action: `navigate`, `click`, `fill`, `type`, `screenshot`, `text_content`, `evaluate`, `select_option`, `keyboard_press`, `get_url`, `close`, `wait_for_selector`, `scroll`, `wait_for_url`, `hover`, `cookies`, `set_viewport`, `extract_html`, `extract_links`, `extract_tables`, `upload` |
| `url` | `str` | No | URL for `navigate` or `wait_for_url`. Supports glob patterns for `wait_for_url` (e.g., `**/dashboard`). |
| `selector` | `str` | No | CSS selector for element-targeting actions. |
| `value` | `str` | No | Text value for `fill`, `type`, `select_option`. |
| `path` | `str` | No | Save path for `screenshot` or upload path for `upload`. Default: `workspace/screenshots/{trace_id}_{timestamp}.png`. |
| `wait_until` | `str` | No | Navigation wait condition: `domcontentloaded` (default), `networkidle`, `load`. |
| `timeout` | `int` | No | Timeout in seconds. Default: `BROWSER_TIMEOUT` from `core/net/default.py` (30). |
| `delay` | `int` | No | Keystroke delay in ms for `type`. Default: 50. |
| `key` | `str` | No | Key name for `keyboard_press`: `Enter`, `Tab`, `Escape`, etc. |
| `expression` | `str` | No | JavaScript code for `evaluate`. |
| `headless` | `bool` | No | Run browser headless. Default: `True`. |
| `return_base64` | `bool` | No | Return base64-encoded image for `screenshot`. Default: `False`. |
| `trace_id` | `str` | No | Trace ID for session isolation. **Required for `close`**. |
| `direction` | `str` | No | Scroll direction: `top`, `bottom`, `up`, `down`. Default: `bottom`. |
| `amount` | `int` | No | Scroll amount in pixels for `up`/`down`. Default: 0 (full height). |
| `state` | `str` | No | Element state for `wait_for_selector`: `visible` (default), `attached`, `detached`, `hidden`. |
| `width` | `int` | No | Viewport width for `set_viewport`. Default: 1280. |
| `height` | `int` | No | Viewport height for `set_viewport`. Default: 720. |
| `cookies_json` | `str` | No | JSON string of cookies for `cookies` action (set mode). Must be a JSON array of objects with `name`, `value`, and either `url` or `domain`+`path`. |
| `action_detail` | `str` | No | Sub-action for `cookies`: `get` (default), `set`, `clear`. |
| `retries` | `int` | No | Retry count for `navigate` on transient failure. Uses `get_retry_delay()` from `core/net/errors.py` with jitter. Default: `BROWSER_NAV_RETRIES` from `core/net/default.py` (2). |

---

## ⚡ Actions

### `navigate` — Go to URL and wait for load
```python
browser(action="navigate", url="https://example.com")
browser(action="navigate", url="https://example.com", wait_until="networkidle")
browser(action="navigate", url="https://example.com", retries=2)  # retry on failure
```
**URL scheme validation:** Only `http://` and `https://` are allowed. `file://`, `javascript:`, `data:` are rejected before any network call.

### `click` — Click an element
```python
browser(action="click", selector="button.submit")
```

### `fill` — Clear and type into an input
```python
browser(action="fill", selector="input.name", value="John")
```

### `type` — Type with human-like delay
```python
browser(action="type", selector="input.search", value="hello", delay=100)
```

### `screenshot` — Capture page or element
```python
browser(action="screenshot")  # full page
browser(action="screenshot", selector="div.chart")  # element
browser(action="screenshot", return_base64=True)  # inline base64
browser(action="screenshot", path="workspace/important.png")  # explicit path
```

### `text_content` — Extract text from element
```python
browser(action="text_content")  # default: body
browser(action="text_content", selector="h1")
```

### `evaluate` — Run JavaScript
```python
browser(action="evaluate", expression="document.title")
browser(action="evaluate", expression="window.scrollY")
```

### `select_option` — Select option from a `<select>` dropdown
```python
browser(action="select_option", selector="select.country", value="US")
```

### `keyboard_press` — Press a key
```python
browser(action="keyboard_press", key="Enter")
browser(action="keyboard_press", key="Tab")
```

### `get_url` — Return current page URL
```python
browser(action="get_url")
```

### `close` — Close browser context for this trace
```python
browser(action="close", trace_id="t1")
```
**⚠️ `trace_id` is REQUIRED.** Calling `close` without `trace_id` returns an error because the anonymous context key cannot be deterministically reconstructed.

### `wait_for_selector` — Wait for element to appear
```python
browser(action="wait_for_selector", selector="div.content")
browser(action="wait_for_selector", selector="div.content", state="visible")
browser(action="wait_for_selector", selector="div.spinner", state="detached")
```

### `scroll` — Scroll page or element
```python
browser(action="scroll", direction="bottom")  # scroll to bottom
browser(action="scroll", direction="top")  # scroll to top
browser(action="scroll", direction="down", amount=500)
browser(action="scroll", selector="#target")  # scroll element into view
```

### `wait_for_url` — Wait for URL to match pattern
```python
browser(action="wait_for_url", url="**/dashboard")
browser(action="wait_for_url", url="https://example.com/login")
```

### `hover` — Hover over element (NEW v1)
```python
browser(action="hover", selector=".menu-item")
```
Triggers CSS `:hover` states, dropdown menus, tooltips.

### `cookies` — Get, set, or clear cookies (NEW v1)
```python
browser(action="cookies")  # get all cookies
browser(action="cookies", action_detail="get", url="https://example.com")  # filtered by URL
browser(action="cookies", action_detail="set", cookies_json='[{"name":"session","value":"abc","url":"https://example.com"}]')
browser(action="cookies", action_detail="clear")
```
**Cookie JSON format:** Must be a JSON array of objects. Each object requires `name`, `value`, and either `url` or `domain`+`path`.

### `set_viewport` — Change viewport size (NEW v1)
```python
browser(action="set_viewport", width=1920, height=1080)
browser(action="set_viewport", width=375, height=812)  # mobile
```
**Note:** Viewport is per-page. New traces get the default viewport (1280x720).

### `extract_html` — Extract raw HTML (NEW v1)
```python
browser(action="extract_html")  # full page HTML (labeled "full_page")
browser(action="extract_html", selector="table.data")  # element HTML
```

### `extract_links` — Extract all links from the page (NEW v1)
```python
browser(action="extract_links")  # all <a> tags
browser(action="extract_links", selector="nav a")  # filtered
```
Uses safe JS injection via `json.dumps()` to prevent selector-based code injection.

### `extract_tables` — Extract tables as structured data (NEW v1)
```python
browser(action="extract_tables")  # all <table> elements
browser(action="extract_tables", selector=".data-table")  # filtered
```
Uses safe JS injection via `json.dumps()` to prevent selector-based code injection.

### `upload` — Upload file to `<input type="file">` (NEW v1.1)
```python
browser(action="upload", selector="input[type=file]", path="data/report.pdf")
browser(action="upload", selector="#avatar", path="photo.png")
```
**Requirements:** `selector` must target a `<input type="file">` element. `path` must be an existing file on the local filesystem.

---

## 🔒 Security

| Feature | Implementation |
|---------|---------------|
| **SSRF guard** | `is_safe_network_address` blocks private IPs (`192.168.x.x`, `10.x.x.x`, `127.x.x.x`, `0.0.0.0`, `::1`) and localhost |
| **URL scheme validation** | `navigate` requires `http://` or `https://`. `file://`, `javascript:`, `data:` are rejected before any network call |
| **Path guard** | Screenshot and upload paths resolved via `cfg.workspace_root` — no path traversal outside workspace |
| **Trace isolation** | Each `trace_id` gets its own `BrowserContext` — cookies and localStorage are never shared |
| **Auto-cleanup** | Screenshots older than 7 days deleted automatically |
| **Evaluate sandbox** | JavaScript runs in page context — no Node.js `require()` access (Chromium isolates page JS from Node) |
| **Safe JS injection** | `extract_links` and `extract_tables` use `json.dumps()` (not `repr()` or f-strings) to embed selectors into JavaScript |
| **Path guard** | `upload` validates path via `resolve_path` — rejects paths outside `workspace_root` |

---

## 📤 Output

All actions return:
```python
{
    "status": "success",  # or "error"
    "trace_id": "abc123",
    "data": {...},  # action-specific data
}
```

Error responses include debug screenshot path when available:
```python
{
    "status": "error",
    "trace_id": "abc123",
    "error": "Click failed: Timeout (failure screenshot: workspace/screenshots/error_abc123_1234567890.png)",
}
```

---

## 🧠 Memory Integration

The browser tool does not store episodic memories directly. However, the research workflow (which uses the browser tool) stores research findings via `memory.store_episodic()`.

---

*Last updated: 2026-07-03. See [ARCHITECTURE.md](ARCHITECTURE.md) for file maps and design decisions, [CHANGELOG.md](CHANGELOG.md) for version history, [INSTRUCTIONS.md](INSTRUCTIONS.md) for AI editing rules.*
