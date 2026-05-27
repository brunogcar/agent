# 🧠 MCP Agent Stack - Master Context & Session Memory

## 1. Core Architectural Directives (STRICT RULES)
- **MCP Stdio Safety**: NEVER use `print()` or write to `sys.stdout` in `server.py`, `tools/`, or `workflows/`. All logs go to `stderr` via `core/tracer.py`.
- **Role Abstraction**: NEVER hardcode model names (e.g., Qwen, Hermes, Nemotron) in Python logic. Use roles: **Planner**, **Executor**, **Router**. Models are strictly defined in `.env`.
- **Protected Files**: Autocode and file tools are FORBIDDEN from editing: `server.py`, `registry.py`, `core/config.py`, `core/tracer.py`, `core/llm.py`, `memory/store.py`, `gateway/app.py`.
- **No Guessing**: AI must NEVER guess file structures, function names, or class attributes. Always read the provided source code or fetch from the repo before writing integration code.
- **Tool Returns**: All tools must return a `dict` (e.g., `{"status": "success", "data": ...}` or `{"status": "error", "error": "...", "trace_id": "..."}`).

## 2. Domain Knowledge
### Skills (Hub-and-Spoke Pattern)
- **Discovery**: `skills/dispatcher.py` scans for Hubs (`<domain>.py`). Subdomains are pure Python modules, NOT exposed via `@tool`.
- **B3 Domain** (`skills/b3/b3.py`): Subdomains: `b3_api` (data ingestion/CSV sync), `b3_cvm` (cross-domain ticker mapping).
- **CVM Domain** (`skills/cvm/cvm.py`): Subdomains: `cvm_dfp_itr` (HTTP wrapper), `cvm_dividends` (DFP/ITR cross-referencing), `cvm_shareholders` (FRE/insider tracking).

### Tools (Auto-Discovery)
- **Pattern**: `@tool` decorator in `registry.py`. Docstrings become LLM prompts. Type hints become JSON schemas.
- **CLI Tool**: 4-layer routing (Regex -> Shell Allowlist -> Router -> Executor).
- **Vision Tool**: Multimodal analysis. Routes to Planner/Vision role.
- **Git Tool**: Plugin dispatcher to `tools/git_ops/`. Uses `subprocess`, NOT GitPython.

### Autocode Workflow (`workflows/autocode.py`)
- **Architecture**: 12-step LangGraph state machine (Snapshot -> Read -> Recall -> Analyze -> Code -> Review -> Syntax -> Apply -> Test -> Commit/Rollback -> Store -> Notify).
- **Task Classifier Modes**: `feature`, `audit`, `edit`, `fix`, `refactor`, `create_skill`, `unclear`.
- **Safety**: Takes git snapshots before patching. Uses `core/patch.py` (str_replace + `.bak`). Rolls back on test failure.

## 3. Completed Sprint Fixes (P0 & P2)
### P0-1: CLI Shell Hardening (`tools/cli.py`, `tools/cli_ops/helpers.py`)
- Replaced `shell=True` with `shlex.split()` and `shell=False`.
- Implemented strict `ALLOWED_COMMANDS` allowlist and `DENY_PATTERNS` denylist.
- Added `pathlib.Path.resolve()` workspace scoping to block directory traversal.

### P0-2: Vision Hardening (`tools/vision.py`)
- Added strict 1-source validation (file, base64, or url).
- Implemented SSRF protection (blocks localhost, 127.0.0.1, 192.168.x.x).
- Enforced 30s `httpx` timeout on URL downloads.

### P0-3: Workflow Standardization (`tools/workflow_tool.py`)
- Enforced `VALID_WORKFLOWS` allowlist (research, data, autocode, report, auto).
- Added fail-fast parameter guards for Autocode (requires `target_file`, `error_msg`, etc.).
- Guaranteed `trace_id` inclusion in all return dictionaries.
- Aligned auto-routing with `core/router.py` (`router.route()` returning `RoutingDecision` object with attributes, not dict keys).

### P2-4: Git Diff Truncation (`tools/git_ops/diff.py`)
- Replaced dangerous character-based truncation (`out[:10_000]`) with line-based truncation (`max_lines=500`).
- Added explicit LLM context warning when truncated.

### P2-5: Testing Structure
- Created `pytest.ini` (`pythonpath = .`, `testpaths = tests`) to fix nested import resolution.
- Established `tests/tools/<tool_name>/` structure.
- Wrote comprehensive mocked unit tests for Vision (SSRF, timeouts) and Workflow (validation, routing) using `unittest.mock.patch`.

## 4. Key File Locations & Signatures
- **Router**: `core/router.py` -> `router = TaskRouter()`, `router.route(goal, trace_id) -> RoutingDecision`
- **LLM Client**: `core/llm.py` -> `llm.call(role, messages, ...)`
- **Config**: `core/config.py` -> `cfg.workspace_root`, `cfg.agent_root`
- **Tracer**: `core/tracer.py` -> `tracer.step()`, `tracer.error()`, `tracer.new_trace()`