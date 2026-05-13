```markdown
# MCP Agent Stack

**Fully autonomous local AI agent built on MCP, LM Studio (3 models + optional Vision), ChromaDB, SearXNG, and LangGraph.**

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/)
[![MCP](https://img.shields.io/badge/MCP-stdio-green)](https://modelcontextprotocol.io)
[![LM Studio](https://img.shields.io/badge/LM_Studio-0.3+-orange)](https://lmstudio.ai/)
[![LangGraph](https://img.shields.io/badge/LangGraph-0.3+-purple)](https://langchain-ai.github.io/langgraph/)

---

## Architecture Overview

```mermaid
graph TD
    A["User (LM Studio / CLI / Gateway)"] -->|MCP stdio or REST| B[server.py]
    B --> C[registry.py]
    C --> D[Tools Layer (11 meta-tools)]
    C --> E[Intelligence Layer]
    D --> F[core/llm.py]
    E --> F
    F -->|OpenAI-compatible API| G["LM Studio (localhost:1234)"]
    G --> H[(Planner: Qwen3.5-9B)]
    G --> I[(Executor: Hermes-3-8B)]
    G --> J[(Router: Nemotron-3-Nano-4B)]
    E --> K[memory/store.py<br/>3-collection ChromaDB]
    E --> L[routing/router.py<br/>Nemotron task classifier]
    E --> M[workflows/<br/>research, data, autocode]
    D --> N[External: SearXNG, local FS, Git, notifications]
    B --> O[core/tracer.py → structured JSONL logs]
    B --> P[gateway/app.py → REST API]
```

**3‑model configuration:**
- **Planner** (orchestration, memory summaries, vision) — `qwen/qwen3.5-9b`
- **Executor** (code generation, analysis, synthesis) — `hermes-3-llama-3.1-8b`
- **Router** (fast task classification) — `nvidia/nemotron-3-nano-4b`

All models served locally through LM Studio's OpenAI-compatible `/v1` endpoint at `http://localhost:1234/v1`.

---

## Hardware & Model

| Component | Minimum | Recommended (this build) |
|-----------|---------|--------------------------|
| CPU | Any modern x86-64 | AMD Ryzen 5 5900X |
| RAM | 64 GB DDR4 3600 MHz |
| GPU VRAM | 16 GB (RTX 5060 Ti) |
| Storage | 20+ GB free | NVMe SSD |
| OS | Windows 10 / Ubuntu 22.04 | Windows 11 or Linux |

### Models (via LM Studio)

| Role | Model | Quantization | Context Window | Timeout |
|------|-------|-------------|----------------|---------|
| Planner | `qwen/qwen3.5-9b` | Q4_0+ | 131k | 90s |
| Executor | `hermes-3-llama-3.1-8b` | Q4_0+ | 16k | 120s |
| Router | `nvidia/nemotron-3-nano-4b` | Q4_0+ | 4k | 15s |
| Vision *(optional)* | any LLaVA/Qwen-VL | Q4_0+ | — | 60s |

---

## Project Structure

```
agent/
├── server.py                   # Entry point: MCP stdio server, tool registration, warmup
├── registry.py                 # Auto‑discovers @tool functions in tools/ and skills/
├── mcp.json                    # MCP server configuration (agent + fs + git + time)
├── requirements.txt            # All Python dependencies
├── .env                        # Environment variables (paths, models, ports…)
├── core/
│   ├── config.py               # Singleton config (paths, models, env vars)
│   ├── llm.py                  # Unified LLM client with circuit breaker, role dispatch, structured output
│   ├── tracer.py               # Structured JSONL logging with trace IDs (stderr + logs/)
│   ├── patch.py                # str_replace patching with .bak backups
│   └── citations.py            # Per‑trace citation tracker ([1], [2]…)
├── tools/                      # 11 meta‑tools that the LLM sees
│   ├── web.py                  # SearXNG search, BS4 scraping, SSRF protection
│   ├── python_exec.py          # Sandboxed execution (run / run_data modes)
│   ├── file_ops.py             # Full file system CRUD, PDF, Office files, SQLite FTS
│   ├── git.py                  # Plugin dispatcher to git_ops/
│   ├── git_ops/                # Git plugin system (commit, log, diff, rollback, branch, etc.)
│   ├── notify.py               # Desktop notifications (send, schedule, cancel, list)
│   ├── visualize.py            # Charts, maps, reports, dashboards via Plotly + Folium
│   ├── vision.py               # Multimodal image analysis using cfg.vision_model
│   ├── memory_tool.py          # LLM‑facing wrapper for memory/store.py (store, recall, delete, stats)
│   ├── agent_tool.py           # 10 specialist LLM roles (code, review, classify, research, …)
│   ├── cli.py                  # Natural‑language → shell command dispatcher (4‑layer routing)
│   ├── workflow_tool.py        # Launch LangGraph workflows (research, data, autocode)
│   └── report_templates.py     # Premium HTML report templates (market, code)
├── memory/
│   └── store.py                # ChromaDB persistence: episodic, semantic, procedural collections + decay scoring
├── routing/
│   └── router.py               # Nemotron‑based task router with heuristic fallback
├── workflows/
│   ├── base.py                 # Shared state, node helpers, dispatcher
│   ├── research.py             # Recall → Search → Scrape → Synthesize → Store → Notify
│   ├── data.py                 # Recall → Execute → Critique → Store → Notify
│   └── autocode.py             # Snapshot → Read → Recall → Analyze → Code → Review → Syntax → Apply → Test → Commit/Rollback → Store → Notify
├── gateway/
│   └── app.py                  # FastAPI REST API (chat, task, result, health, tools, memory stats)
├── skills/
│   ├── dispatcher.py           # Auto‑discovers skill domains from skills/*/__init__.py
│   └── b3/
│       └── __init__.py         # B3 (Brazilian stock exchange) domain: sync, query, status
└── system_prompts/
    ├── qwen_planner.md         # Planner instructions, JSON output format, vision rules
    ├── hermes_executor.md      # Executor's 11 specialist roles with per‑role output schemas
    ├── nemotron_router.md      # Router classification and routing logic
    └── system_prompt.md        # Project‑level instructions, tool reference, workflow patterns
```

---

## Quick Start (for context loading)

1. **Clone & dependencies**  
   ```bash
   git clone https://github.com/brunogcar/agent && cd agent
   pip install -r requirements.txt
   ```

2. **Configure**  
   Copy `.env.example` to `.env` (or use the current `.env` below) and adjust paths/models/SearXNG URL.

3. **Required services**  
   - LM Studio with the three models loaded (see `.env`).  
   - SearXNG instance at `http://localhost:8080` (optional, for web search).  
   - ChromaDB auto‑creates at `MEMORY_ROOT`.

4. **Run**  
   ```bash
   python server.py           # MCP stdio mode
   # or
   uvicorn gateway.app:app --host 0.0.0.0 --port 8000  # REST API mode
   ```

---

## Configuration (`.env`)

All paths and model names are driven by environment variables, loaded by `core/config.py` as a singleton `cfg`.

```ini
# ── Paths (no trailing slash) ──────────────────────────────────────────────
AGENT_ROOT=D:/mcp/agent
WORKSPACE_ROOT=D:/mcp/agent/workspace
MEMORY_ROOT=D:/mcp/agent/memory_db

# ── LM Studio ──────────────────────────────────────────────────────────────
LM_STUDIO_BASE_URL=http://localhost:1234/v1
FASTMCP_LOG_LEVEL=error

# ── Model roles ────────────────────────────────────────────────────────────
PLANNER_MODEL=qwen/qwen3.5-9b
EXECUTOR_MODEL=hermes-3-llama-3.1-8b
ROUTER_MODEL=nvidia/nemotron-3-nano-4b
VISION_MODEL=qwen/qwen3.5-9b          # Usually same as planner

# ── External services ──────────────────────────────────────────────────────
SEARXNG_URL=http://localhost:8080     # or your NAS IP: http://192.168.1.10:30053

# ── Memory tuning ────────────────────────────────────────────────────────────
MEMORY_DELETE_THRESHOLD=0.4           # Importance below this may be pruned
MEMORY_DECAY_DAYS=30
MEMORY_TOP_K=5

# ── Execution ──────────────────────────────────────────────────────────────
EXECUTION_TIMEOUT=120                 # Seconds for code execution (sandbox)

# ── Autocode ────────────────────────────────────────────────────────────────
AUTOCODE_MAX_RETRIES=3
AUTOCODE_MAX_FILE_CHARS=6000
AUTOCODE_DEBUG=0                      # Set to 1 for verbose trace logging

# ── Gateway ─────────────────────────────────────────────────────────────────
GATEWAY_HOST=0.0.0.0
GATEWAY_PORT=8000
GATEWAY_SECRET=changeme               # Change before exposing to network!

# ── Environment ────────────────────────────────────────────────────────────
ENV=development                        # development or production
```

> **Note:** `SANDBOX_TIMEOUT` is planned but not yet wired in the codebase – currently only `EXECUTION_TIMEOUT` controls all execution timeouts.

---

## Tools Reference (what the LLM can invoke)

All tools are registered via `@tool` decorators and auto‑discovered by `registry.py`.

| Tool | File | Key Functionality |
|------|------|-------------------|
| **web** | `tools/web.py` | Web search (SearXNG) and scraping (BeautifulSoup), SSRF protection. |
| **python** | `tools/python_exec.py` | Run Python code in sandbox (`run` mode) or with data‑science libs (`run_data` mode). |
| **file** | `tools/file_ops.py` | File read/write/list/backup/search/read_pdf, Office files (docx/xlsx/pptx), SQLite FTS. |
| **git** | `tools/git.py` + `git_ops/` | Plugin‑based Git operations: init, status, commit, log, diff, branch, checkout, rollback, snapshot, restore. |
| **notify** | `tools/notify.py` | Cross‑platform desktop notifications (send, schedule, cancel, list). |
| **visualize** | `tools/visualize.py` | Create charts (Plotly), maps (Folium), HTML reports, dashboards. |
| **vision** | `tools/vision.py` | Analyze images using `cfg.vision_model` (file, URL, base64). |
| **memory** | `tools/memory_tool.py` | Manage persistent memory: store, recall, delete, prune, summarize, stats (3‑collection ChromaDB). |
| **agent** | `tools/agent_tool.py` | Invoke specialised LLM sub‑agents: classify, route, research, summarize, extract, critique, analyze, code, review, plan. |
| **cli** | `tools/cli.py` | Transform natural language into shell commands. 4‑layer dispatch: regex patterns → shell whitelist → Nemotron route → Executor escalation. |
| **workflow** | `tools/workflow_tool.py` | Execute long‑running LangGraph workflows: `research`, `data`, `autocode`. |
| *(internal)* | `tools/report_templates.py` | Premium tabbed HTML report templates (used by visualise and workflows). |

---

## Intelligence Layer

### Memory (`memory/store.py`)

- **3 ChromaDB collections**: episodic (events), semantic (facts), procedural (skills).  
- **Decay scoring**: `score = importance × max(0.3, 1 − age_days / decay_days)`. Items below `MEMORY_DELETE_THRESHOLD` are pruned.  
- **Query rewriting**: improves recall by expanding query context.

### Router (`routing/router.py`)

- Uses the **Nemotron‑3‑Nano‑4B** model for fast task classification.  
- Outputs a route label (`web`, `python`, `memory`, `agent`, …) and complexity score (1‑10).  
- Falls back to heuristic keyword matching if LLM call fails.

### Workflows (`workflows/`)

Built with LangGraph, all workflows use `base.py`'s `WorkflowState` and emit structured traces:

- **research.py**: Recall → Search → Scrape → Synthesize → Store → Notify  
  *(Use for: information gathering, summarisation, fact-finding)*
- **data.py**: Recall → Execute → Critique → Store → Notify  
  *(Use for: pandas/numpy analysis, calculations, dataset generation)*
- **autocode.py**: Snapshot → Read → Recall → Analyze → Code → Review → Syntax → Apply → Test → Commit (or Rollback) → Store → Notify  
  *(Use for: fixing bugs, adding features, refactoring code)*

**Protected files** — autocode will never touch these, nor any file outside `WORKSPACE_ROOT`:
- `server.py`, `registry.py`
- `core/config.py`, `core/tracer.py`
- `memory/store.py`

---

## Models & Roles

| Role | Model | Purpose | Context Window | Timeout |
|------|-------|---------|----------------|---------|
| `planner` | `qwen/qwen3.5-9b` | Orchestration, memory summaries, vision | 131k | 90s |
| `executor` | `hermes-3-llama-3.1-8b` | Code generation, analysis, synthesis | 16k | 120s |
| `router` | `nvidia/nemotron-3-nano-4b` | Task classification, tool selection | 4k | 15s |
| `vision` | (same as planner) | Multimodal image analysis | — | 60s |

All models are served by **LM Studio** at `http://localhost:1234/v1` (OpenAI‑compatible endpoint).  
`core/llm.py` implements a circuit breaker to prevent cascading failures.

---

## Gateway API (`gateway/app.py`)

**REST endpoints** (Phase 9):

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/chat` | POST | Send a message to the agent (async task) |
| `/task` | POST | Submit a structured task |
| `/result/{task_id}` | GET | Retrieve task result by task ID |
| `/health` | GET | Health check (checks LM Studio availability) |
| `/tools` | GET | List registered tools |
| `/memory/stats` | GET | Memory statistics |

Authentication via `GATEWAY_SECRET`.  
Rate limiting (planned via `slowapi`): 30 req/min on `/chat`, 60 req/min on `/task`.  
Messaging adapters (Discord, Telegram) are planned.

---

## Skills (`skills/`)

- **Dispatcher** (`skills/dispatcher.py`) auto‑discovers skill domains (folders with an `__init__.py`).  
- **B3** (`skills/b3/__init__.py`): Brazilian stock market domain – sync B3 data, query tickers, status checks.  
  *(Mode: `sync` to download daily CSVs; `query` to run SQL queries)*

---

## Observability & Tracing

- **Structured logging** via `structlog` in `core/tracer.py`.  
- All LLM calls, tool executions, and workflow steps emit trace‑ID‑tagged JSON lines to stderr and `logs/agent_YYYYMMDD.jsonl`.  
- **Citation tracking** in `core/citations.py` for web‑based answers.

---

## System Prompts

Four Markdown files in `system_prompts/` define the behaviour of each model:

- `qwen_planner.md` – Planner instructions, JSON output format, vision rules
- `hermes_executor.md` – Executor's 11 specialist roles with per‑role output schemas
- `nemotron_router.md` – Router classification and routing logic
- `system_prompt.md` – Master project prompt (tool reference, workflows, safety rules)

---

## Key Design Decisions

- **MCP stdio transport** for seamless integration with LM Studio, Claude Desktop and other MCP hosts.  
- **Tool auto‑discovery** via `registry.py` so new tools are picked up without manual wiring.  
- **Plugin architecture for Git** – `git_ops/` modules are discovered dynamically.  
- **Sandboxed Python execution** – `run` mode restricts builtins; `run_data` runs in‑process with heavy libs in a subprocess.  
- **Memory decay** – Prevents context pollution and keeps the knowledge base relevant.  
- **Circuit breakers** — Per-role resilience prevents cascading failures when models are unavailable.

---

## Installation (Detailed)

### 1. Prerequisites

```bash
# Python 3.11+
python --version

# Node.js 18+ (for npx MCP servers)
node --version

# Git
git --version
```

### 2. Clone and install

```bash
cd D:/mcp
git clone https://github.com/brunogcar/agent agent
cd agent

pip install -r requirements.txt
```

> **WeasyPrint on Windows**: requires GTK3 runtime.  
> Download: https://github.com/tschoonj/GTK-for-Windows-Runtime-Environment-Installer  
> If it fails, skip it — HTML reports work without it, only PDF export is unavailable.

### 3. Configure

```bash
# Copy the example env and edit with your paths/models
cp .env.example .env
# Edit .env with your actual paths, model names, and SearXNG URL
```

### 4. SearXNG (self-hosted search) — Optional

**Docker (recommended):**
```bash
docker run -d \
  --name searxng \
  -p 30053:8080 \
  -e SEARXNG_SECRET=changeme \
  searxng/searxng

# Verify
curl http://localhost:30053/search?q=test&format=json
```

Set `SEARXNG_URL=http://localhost:30053` in `.env` (or your NAS IP).

### 5. LM Studio

1. Download LM Studio: https://lmstudio.ai
2. Load the three models (Planner, Executor, Router) as specified in `.env`
3. Enable the local server on port 1234
4. Verify: `curl http://localhost:1234/v1/models`


## Memory System

### Storing memories

```python
# Episodic — things that happened
memory(action="store", memory_type="episodic",
       text="Fixed SyntaxError in tools/web.py",
       importance=8, goal="fix scraping", outcome="success",
       tools_used="autocode,git", trace_id="abc123")

# Semantic — things you know
memory(action="store", memory_type="semantic",
       text="ChromaDB supports persistent local storage",
       importance=7, tags="chromadb,architecture")

# Procedural — how to do things
memory(action="store", memory_type="procedural",
       text="To register a new tool: decorate with @tool",
       importance=9, tags="mcp,tools")
```

### Recalling memories

```python
# Search all collections
memory(action="recall", query="how to fix syntax errors", top_k=5)

# Search specific collection
memory(action="recall", query="ChromaDB", collections=["semantic"])

# Filter by tags
memory(action="recall", query="tool registration", tags_filter="mcp")
```

### Decay scoring

Memories are ranked by: `score = importance × max(0.3, 1 − age_days / decay_days)`

| Age | Importance 10 | Importance 5 | Importance 1 |
|-----|--------------|--------------|--------------|
| 0 days | 10.0 | 5.0 | 1.0 |
| 15 days | 6.5 | 3.25 | 0.65 |
| 30 days | 3.0 | 1.5 | 0.3 |
| 60 days | 3.0 | 1.5 | 0.3 (floor) |

---

## Workflows Overview

Three core workflow types built with LangGraph:

- **Research** — gather information from web, synthesize findings
- **Data** — analyze datasets with pandas/numpy, generate reports
- **Autocode** — fix bugs, add features, refactor code (with full TDD + safety)

Each workflow is triggered via `workflow(type="auto/research/data", goal=...)` or through the agent meta-tool.

---

## Troubleshooting

| Issue | Solution |
|-------|----------|
| **LM Studio reachable: False** | → LM Studio is not running or the server is not enabled.<br/>→ Check `http://localhost:1234/v1/models` in your browser. |
| **Cannot reach SearXNG** | → Check `SEARXNG_URL` in `.env` matches your NAS/Docker IP and port.<br/>→ Test: `curl http://YOUR_IP:30053/search?q=test&format=json` |
| **ChromaDB import error** | → Try: `pip install chromadb --no-binary chromadb` |
| **kaleido crashes on PNG export** | → Try: `pip install kaleido==0.2.1` |
| **Autocode produces syntax errors** | → Check `AUTOCODE_DEBUG=1` in `.env` and review the trace log.<br/>→ The code generation prompts assume Hermes’ strict JSON output; other executor models may produce malformed plans. |
| **Tool not appearing after adding it** | → Confirm the function has the `@tool` decorator.<br/>→ Confirm the file is inside the `tools/` directory.<br/>→ Restart the MCP server (`python server.py`). |
| **WeasyPrint PDF export fails on Windows** | → GTK3 runtime may be missing. Download: https://github.com/tschoonj/GTK-for-Windows-Runtime-Environment-Installer<br/>Or skip it — HTML reports work without PDF export. |


## Adding New Tools

1. Create `tools/your_tool.py`
2. Import and use the `@tool` decorator:

```python
from registry import tool

@tool
def your_tool(action: str, param: str = "") -> dict:
    """Docstring is what the LLM sees — make it clear."""
    if action == "do_thing":
        return {"status": "success", "result": "..."}
    return {"status": "error", "error": f"Unknown action '{action}'"}
```

3. That's it — `registry.py` auto-discovers it on next server start.  
   No changes to `server.py` or any other file needed.

---

## Adding New LLM Providers

The `core/llm.py` provider abstraction makes this a one-file change:

```python
from core.llm import llm, LMStudioProvider

# DeepSeek (OpenAI-compatible)
llm.register_provider(
    "deepseek",
    LMStudioProvider("https://api.deepseek.com/v1")
)

# Then use it in a role override:
cfg.model_registry["executor"]["provider"] = "deepseek"
cfg.model_registry["executor"]["model"] = "deepseek-coder-v2"
```

---

## Why This Architecture?

**Three-model design:**
- **Planner (Qwen 9B)** — handles complex reasoning, memory summaries, and vision tasks that need long-context understanding
- **Executor (Hermes 8B)** — specialized for code generation with strict JSON output, tight temperature control (0.1)
- **Router (Nemotron 4B)** — ultra-fast (15s timeout) classification to route simple tasks directly without loading heavy models

**Circuit breakers:**
- Each LLM role has a dedicated circuit breaker that fails fast after 3 consecutive failures
- After a failure window, the circuit enters "half-open" state and allows one test call
- This prevents cascading timeouts when LM Studio becomes unresponsive

**Memory decay:**
- Prevents context pollution by gradually reducing importance scores over time
- Items below `MEMORY_DELETE_THRESHOLD` (default 0.4) are automatically pruned
- Keeps the knowledge base focused on recent and important information

---

## Licence

Private project. Not for redistribution.

---

*This README is designed to serve as a complete AI‑readable project context. For a full file‑by‑file breakdown, refer to the initial context‑loading prompt.*
```