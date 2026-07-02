# 🛠️ Tools Architecture & Meta-Tool Inventory

Tools are the atomic actions the LLM can execute. They act as the "hands" of the agent, interacting with the file system, web, git, local sandbox, and external APIs.

## 🏗️ Tool Creation Guidelines

### The `@tool` Auto-Discovery Pattern

Tools rely on **zero-config auto-discovery** via `registry.py`. You do not need to manually wire new tools into `server.py`.

1. Create a new Python file in the `tools/` directory (e.g., `tools/my_tool.py`).
2. Import the decorator: `from registry import tool`.
3. Decorate your function.
4. Type hints automatically generate the MCP JSON schema.
5. Docstrings become the LLM-visible prompt/description.

```python
# tools/my_tool.py
from registry import tool

@tool
def my_custom_tool(action: str, param: str = "", dry_run: bool = False) -> dict:
    """
    Performs a custom action for task automation.
    Use dry_run=True to preview changes without applying them.
    """
    if not param:
        return {"status": "error", "error": "Parameter 'param' is required."}
        
    if action == "do_something":
        if dry_run:
            return {"status": "success", "preview": f"Would do something with {param}"}
        return {"status": "success", "result": f"Done something with {param}"}
        
    return {"status": "error", "error": f"Unknown action '{action}'"}
```

### 🚨 Critical Safety & Architecture Rules

1. **MCP Stdio Safety (CRITICAL)**: NEVER use `print()` or write to `sys.stdout` inside any tool. The MCP protocol uses `stdout` for JSON-RPC communication. Writing to stdout will corrupt the payload and crash the server. Use `core.tracer` or `sys.stderr` for all logging.

2. **Standardized Returns**: Always return a dictionary containing at least `{"status": "success"}` or `{"status": "error", "error": "descriptive message"}`.

3. **Input Validation**: Always validate file paths (prevent directory traversal outside `WORKSPACE_ROOT`) and sanitize inputs to prevent injection attacks.

4. **Timeouts**: Wrap external HTTP calls, subprocess executions, and heavy computations in timeouts to prevent blocking the LLM execution loops.

---

## 📦 Core Meta-Tool Inventory

The agent currently exposes **11 primary meta-tools** to the LLM.

| Tool Name | Source File(s) | Purpose & Key Mechanics |
|-----------|----------------|-------------------------|
| **web** | `tools/web.py` | **Web Search & Scraping.** Integrates with a local SearXNG instance for privacy-focused search and uses BeautifulSoup for HTML parsing. Includes strict SSRF protection via `core/path_guard.py` to block requests to local/private IP ranges (127.0.0.0/8, 10.0.0.0/8, 192.168.0.0/16, etc.). Supports both `search` (query-based) and `scrape` (URL-based) actions. |
| **python** | `tools/python_exec.py` | **Sandboxed Code Execution.** Two modes: <br>• **`run` mode**: Executes Python with AST-validated sandbox (blocks imports, `eval`/`exec`, file I/O, `getattr`/`setattr`, metaclasses, context managers). Fast-path string check + deep AST tree walking. <br>• **`run_data` mode**: Executes data-science code (pandas/numpy/matplotlib) in an isolated subprocess with whitelisted imports. Returns stdout, stderr, and local variables. |
| **file** | `tools/file.py` & `tools/file_ops/` | **File System Operations.** Plugin-based dispatcher routing to action handlers in `file_ops/`. Full CRUD operations (read, write, list, delete, backup), directory traversal, PDF text extraction via `pypdf`, Office file parsing (docx/xlsx/pptx), and SQLite FTS (Full Text Search). **Strictly blocks access to protected core files** via `core/path_guard.py`. Null-byte injection protection on all path operations. |
| **git** | `tools/git.py` & `tools/git_ops/` | **Version Control.** Plugin-based dispatcher with dynamically discovered action handlers in `git_ops/actions/`. Supports: `status`, `log`, `diff`, `commit`, `init`, `restore`, `rollback` (with automatic stash-based safety net), `snapshot`, `show`, `tag`, `branch`, `checkout`. Uses system `git` via `subprocess` (NOT GitPython) for reliability. Rollback defaults to safe stash-based recovery; `force=True` for permanent discard. |
| **notify** | `tools/notify.py` | **Desktop Notifications.** Cross-platform alerts via `plyer`. Supports immediate sending, scheduling (with delay), canceling pending notifications, and listing queued alerts. Useful for long-running workflow completion signals. |
| **report** | `tools/report_tool.py` | **Data Visualization & Reporting.** Generates interactive charts (Plotly), geographical maps (Folium), and premium tabbed HTML dashboards using templates from `tools/report_templates.py`. Can export to PDF via WeasyPrint (requires GTK3 on Windows) or PNG via Kaleido (pinned to 0.2.1 for stability). |
| **vision** | `tools/vision.py` | **Multimodal Image Analysis.** Routes base64-encoded images, local file paths, or URLs to the **Planner** model (or dedicated Vision model if configured) for image understanding, OCR, and visual reasoning. Respects `VISION_MAX_FILE_BYTES` limit (default 20MB). |
| **memory** | `tools/memory.py` | **Persistent Knowledge Base.** LLM-facing wrapper for `core/memory.py`. Allows the agent to `store`, `recall`, `delete`, `prune`, `summarize`, and get `stats` across 3 ChromaDB collections (episodic, semantic, procedural). Enforces MED-05 tag validation (rejects `< > " ' \` |`, max 6 tags, alphanumeric/hyphens only). Uses Write-Only Lock pattern (MED-01) for 30-50% throughput boost. |
| **agent** | `tools/agent_tool.py` | **Specialist Sub-Agents.** Invokes 10 specialized LLM roles: `classify`, `route`, `research`, `summarize`, `extract`, `critique`, `analyze`, `code`, `review`, `plan`. Each role has tailored system prompts and output schemas. Routes to Planner, Executor, or Router based on the specific sub-task complexity. |
| **cli** | `tools/cli.py` & `tools/cli_ops/` | **Natural Language to Shell.** Translates NL requests into shell commands using a 4-layer dispatch system: <br>1. Regex pattern matching (fast path for common commands) <br>2. Shell command whitelist (safe operations only) <br>3. Router model classification (Nemotron for intent detection) <br>4. Executor model escalation (Hermes for complex command generation). <br>Includes safety checks to prevent destructive operations without explicit confirmation. |
| **workflow** | `tools/workflow_tool.py` | **State Machine Trigger.** Launches long-running LangGraph workflows (`research`, `data`, `autocode`). Handles async task tracking via SQLite and routing via the Router model if `type="auto"`. Returns `trace_id` immediately for polling. Each workflow emits structured traces to `logs/agent_*.jsonl`. |

---

## 🔐 Recent Security Hardening (May 2026)

### AST Sandbox Validation (`tools/python_exec.py`)

The Python execution sandbox was hardened against advanced bypass techniques:

**Blocked Attack Vectors:**
- Direct imports (`import os`, `from sys import path`)
- Dangerous builtins (`eval`, `exec`, `compile`, `open`, `__import__`, `input`, `breakpoint`)
- Dynamic resolution (`getattr`, `setattr`, `delattr`) to prevent `getattr(__builtins__, "eval")`
- Subscript access (`__builtins__["eval"]`) via string-constant AST inspection
- Module attribute calls (`os.system()`, `subprocess.run()`)
- **Definition-time execution**: `ast.ClassDef` (metaclass attacks), `ast.With`/`ast.AsyncWith` (context managers), `ast.AsyncFunctionDef`

**Two-Layer Defense:**
1. **Fast-path string check**: Catches obvious patterns like `eval(`, `exec(`, `import os`
2. **AST tree walking**: Deep inspection of all `ast.Call`, `ast.Import`, `ast.Attribute`, `ast.Subscript` nodes

**Test Coverage:** 16 pytest cases in `tests/tools/python_exec/test_sandbox_security.py` verify blocking of obfuscated attacks.

### Git Rollback Safety (`tools/git_ops/actions/rollback.py`)

Default `rollback` action now uses **stash-based recovery**:
- Automatically stashes uncommitted changes before `git reset --hard HEAD`
- Returns `stash_ref` for manual recovery via `git stash pop`
- Only `force=True` performs permanent discard + `git clean -fd`

### Gateway ForwardRef Resolution (`core/gateway.py`)

Fixed FastAPI 422 errors by moving Pydantic models (`TaskRequest`, `ChatRequest`) to module level, resolving `from __future__ import annotations` ForwardRef issues in the factory pattern.

---

## 🧩 Internal / Helper Modules

These are not exposed directly to the LLM as tools, but provide critical backing logic:

- **`tools/report_templates.py`**: Premium, tabbed HTML/CSS templates for market analysis and code review dashboards.
- **`tools/git_ops/`**: Directory of discrete Python files acting as plugins for the `git` meta-tool. Each file in `actions/` registers via `@register_action` decorator.
- **`tools/file_ops/`**: Similar plugin structure for file operations (read, write, list, pdf, office, sqlite).
- **`tools/cli_ops/`**: Command handlers and routing logic for the CLI meta-tool.
- **`core/path_guard.py`**: Centralized path validation, SSRF protection, and null-byte injection prevention used by `web`, `file`, and `git` tools.

---

## 📝 Tool Return Schema

All tools MUST return a dictionary with at least:

**Success:**
```python
{
    "status": "success",
    "result": "...",  # or "output", "data", etc.
    "trace_id": "abc123"  # optional but recommended
}
```

**Error:**
```python
{
    "status": "error",
    "error": "Descriptive error message",
    "trace_id": "abc123"
}
```

This standardization allows workflows and the LLM to reliably parse tool outcomes and make routing decisions.
