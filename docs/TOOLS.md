# 🛠️ Tools Architecture & Meta-Tool Inventory

Tools are the atomic actions the LLM can execute. They act as the "hands" of the agent, interacting with the file system, web, git, local sandbox, and external APIs. 

## 🏗️ Tool Creation Guidelines

### The `@tool` Auto-Discovery Pattern
Tools rely on zero-config auto-discovery via `registry.py`. You do not need to manually wire new tools into `server.py`.

1. Create a new Python file in the `tools/` directory (e.g., `tools/my_tool.py`).
2. Import the decorator: `from registry import tool`.
3. Decorate your function. 
   - **Type hints** automatically generate the MCP JSON schema.
   - **Docstrings** become the LLM-visible prompt/description.

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
1. **MCP Stdio Safety (CRITICAL)**: **NEVER** use `print()` or write to `sys.stdout` inside any tool. The MCP protocol uses `stdout` for JSON-RPC communication. Writing to stdout will corrupt the payload and crash the server. Use `core.tracer` or `sys.stderr` for all logging.
2. **Standardized Returns**: Always return a dictionary containing at least `{"status": "success"}` or `{"status": "error", "error": "descriptive message"}`.
3. **Input Validation**: Always validate file paths (prevent directory traversal outside `WORKSPACE_ROOT`) and sanitize inputs to prevent injection attacks.
4. **Timeouts**: Wrap external HTTP calls, subprocess executions, and heavy computations in timeouts to prevent blocking the LLM execution loops.

---

## 📦 Core Meta-Tool Inventory

The agent currently exposes 11 primary meta-tools to the LLM.

| Tool Name | Source File(s) | Purpose & Key Mechanics |
|---|---|---|
| **web** | `tools/web.py` | **Web Search & Scraping.** Integrates with a local SearXNG instance for search and uses BeautifulSoup for scraping. Includes strict SSRF protection to block requests to local/private IP ranges. |
| **python** | `tools/python_exec.py` | **Sandboxed Execution.** <br>• `run` mode: Executes standard Python with restricted builtins.<br>• `run_data` mode: Executes data-science code (pandas/numpy) in an isolated subprocess. |
| **file** | `tools/file_ops.py` | **File System Operations.** Full CRUD operations, directory listing, PDF text extraction, Office file parsing (docx/xlsx/pptx), and SQLite FTS (Full Text Search). **Strictly blocks access to protected core files.** |
| **git** | `tools/git.py` + `git_ops/` | **Version Control.** Plugin-based dispatcher. Routes commands to dynamically discovered modules in `git_ops/` (commit, log, diff, branch, rollback, snapshot, restore). Uses system `git` via `subprocess`, not GitPython. |
| **notify** | `tools/notify.py` | **Desktop Notifications.** Cross-platform alerts via `plyer`. Supports immediate sending, scheduling, canceling, and listing pending notifications. |
| **report** | `tools/report_tool.py` | **Data Visualization & Reporting.** Generates interactive charts (Plotly), geographical maps (Folium), and premium tabbed HTML dashboards. Can export to PDF via WeasyPrint or PNG via Kaleido. |
| **vision** | `tools/vision.py` | **Multimodal Analysis.** Routes base64 encoded images, local file paths, or URLs to the **Planner** (or dedicated Vision) model for image understanding and OCR. |
| **memory** | `tools/memory_tool.py` | **Persistent Knowledge Base.** LLM-facing wrapper for `memory/store.py`. Allows the agent to store, recall, delete, prune, and summarize memories across the 3 ChromaDB collections. Enforces MED-05 tag validation. |
| **agent** | `tools/agent_tool.py` | **Specialist Sub-Agents.** Invokes 10 specialized LLM roles (classify, route, research, summarize, extract, critique, analyze, code, review, plan). Routes to Planner, Executor, or Router based on the specific sub-task. |
| **cli** | `tools/cli.py` | **Natural Language to Shell.** Translates NL requests into shell commands using a 4-layer dispatch system: Regex patterns → Shell whitelist → Router classification → Executor escalation. |
| **workflow**| `tools/workflow_tool.py`| **State Machine Trigger.** Launches long-running LangGraph workflows (`research`, `data`, `autocode`). Handles async task tracking and routing via the Router model if set to `auto`. |

### Internal / Helper Modules
These are not exposed directly to the LLM as tools, but provide critical backing logic for the meta-tools:

- **`tools/report_templates.py`**: Contains premium, tabbed HTML/CSS templates used by the `report` tool and various workflows to generate beautiful market and code analysis dashboards.
- **`tools/git_ops/`**: A directory of discrete Python files acting as plugins for the `git` meta-tool. Adding a new `.py` file here with the correct interface automatically registers a new git action.