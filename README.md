# MCP Agent Stack

A fully autonomous local AI agent built on the Model Context Protocol (MCP),
running entirely on consumer hardware with no cloud dependencies.

The agent can research, write and fix its own code, analyse data, create
documents and visualisations, manage files and git history, and schedule tasks
— all through a clean set of 6 meta-tools that hide 100+ internal operations
from the language model.

---

## Hardware & Model Requirements

| Component | Minimum | Recommended (this build) |
|-----------|---------|--------------------------|
| CPU | Any modern x86-64 | AMD Ryzen 5 5900X |
| RAM | 16 GB | 64 GB DDR4 3600 MHz |
| GPU VRAM | 8 GB | 16 GB (RTX 5060 Ti) |
| Storage | 20 GB free | NVMe SSD |
| OS | Windows 10 / Ubuntu 22.04 | Windows 11 or Linux |

### Models (via LM Studio)

| Role | Model | Quantization | Context |
|------|-------|-------------|---------|
| Planner | `qwen/qwen3.5-9b` | Q4_0+ | 131k |
| Executor | `hermes-3-llama-3.1-8b` | Q4_0+ | 16k |
| Router | `nvidia/nemotron-3-nano-4b` | Q4_0+ | 4k |
| Vision *(optional)* | any LLaVA/Qwen-VL | Q4_0+ | — |

All models served locally via **LM Studio** on `http://localhost:1234/v1`.

---

## Architecture

```
┌─────────────────────────────────────────────────┐
│                 Claude / User                   │
└────────────────────┬────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────┐
│           PLANNER  (Qwen 3.5 9B)                │
│  Produces structured JSON plan — never calls    │
│  tools directly                                 │
└────────────────────┬────────────────────────────┘
                     │ JSON plan
┌────────────────────▼────────────────────────────┐
│           ROUTER   (Nemotron 4B)                │
│  Classifies task type, selects workflow or      │
│  direct tool, assigns executor model            │
└──────────┬──────────────────┬───────────────────┘
           │                  │
┌──────────▼──────┐  ┌────────▼──────────────────┐
│   WORKFLOWS     │  │  EXECUTOR (Hermes 3 8B)   │
│   (LangGraph)   │  │  Strict JSON schema only  │
│  research       │  │  CODER / REVIEWER /        │
│  data           │  │  ANALYZER system prompts  │
│  autocode       │  │  all correctly wired       │
└──────────┬──────┘  └────────┬──────────────────┘
           └────────┬─────────┘
┌───────────────────▼──────────────────────────────┐
│              6 META-TOOLS                        │
│  web · python · file · git · notify · visualize  │
└───────────────────┬──────────────────────────────┘
                    │
┌───────────────────▼──────────────────────────────┐
│           IMPLEMENTATION LAYER                   │
│  SearXNG · ChromaDB · SQLite FTS                 │
│  LM Studio · openpyxl · plotly · folium          │
│  fpdf2 · python-docx · python-pptx               │
└──────────────────────────────────────────────────┘
```

### Model roles — enforced, not suggestions

| Role | Model | Used for | Timeout |
|------|-------|----------|---------|
| Planner | Qwen 3.5 9B | Workflow orchestration, memory summarisation | 90s |
| Executor | Hermes 3 8B | Code generation, analysis, synthesis | 120s |
| Router | Nemotron 4B | Task classification, tool selection | 15s |

### Memory — 3 ChromaDB collections

| Collection | Stores | Example |
|------------|--------|---------|
| `episodic` | What happened | "Fixed SyntaxError in memory.py — outcome: success" |
| `semantic` | What you know | "ChromaDB supports persistent local storage" |
| `procedural` | How to do things | "To register a new tool: decorate with @tool" |

Recall uses **decay scoring**: `score = importance × max(0.3, 1 − age/30days)`  
Old high-importance memories fade slowly but never disappear entirely.

---

## Project Structure

```
D:/mcp/
├── agent/                          ← agent source (this repo)
│   ├── .env                        ← all configuration (never committed)
│   ├── .gitignore
│   ├── server.py                   ← FastMCP entrypoint (minimal)
│   ├── registry.py                 ← auto-discovers @tool functions
│   ├── requirements.txt
│   │
│   ├── core/
│   │   ├── config.py               ← singleton cfg — all paths/models/settings
│   │   ├── llm.py                  ← unified LLM client, provider abstraction
│   │   └── tracer.py               ← structured logging, trace IDs
│   │
│   ├── tools/                      ← 6 meta-tools (what the LLM sees)
│   │   ├── web.py                  ← search | scrape | read | search_and_read
│   │   ├── python_exec.py          ← run (sandbox) | run_data (imports OK)
│   │   ├── file_ops.py             ← 14 actions: txt/pdf/docx/xlsx/pptx
│   │   ├── git_ops.py              ← snapshot | commit | rollback | log | status | diff
│   │   ├── notify.py               ← send | schedule | cancel | list
│   │   └── visualize.py            ← chart | map | report | dashboard
│   │
│   ├── memory/
│   │   └── store.py                ← 3-collection ChromaDB + decay scoring
│   │
│   ├── routing/                    ← Phase 8 — Nemotron router layer
│   ├── workflows/                  ← Phase 7 — research / data / autocode
│   ├── gateway/                    ← Phase 9 — REST API + messaging adapters
│   └── skills/                     ← Phase 10 — B3 and domain skill packs
│
├── workspace/                      ← agent working directory (git tracked)
│   ├── autocode/                   ← autocode outputs and backups
│   └── visualizations/             ← generated HTML charts, maps, dashboards
│
└── memory_db/                      ← persistent storage (not committed)
    ├── chroma/                     ← ChromaDB vector collections
    ├── agent.db                    ← SQLite general storage
    └── task.db                     ← SQLite task queue
```

---

## The 6 Meta-Tools

The LLM sees exactly 6 tools. All complexity is hidden inside.

### `web(action, ...)`
Search the web or read web pages. Internally uses SearXNG + httpx + BeautifulSoup4.

| Action | Required | Optional | Returns |
|--------|----------|----------|---------|
| `search` | `query` | `max_results=5` | `{results: [{url, title, snippet}]}` |
| `scrape` | `url` | `max_chars=8000` | `{title, text, word_count}` |
| `read` | `url` | `max_chars=8000` | alias for scrape |
| `search_and_read` | `query` | `max_results=3` | `{results: [{url, title, text}]}` |

```python
web(action="search", query="FastMCP python tutorial")
web(action="scrape", url="https://docs.python.org/3/library/pathlib.html")
web(action="search_and_read", query="ChromaDB persistent client")
```

### `python(mode, code)`
Execute Python code safely. Two modes with different isolation levels.

| Mode | Imports | Execution | Use for |
|------|---------|-----------|---------|
| `run` | None (sandbox) | In-process | Pure logic, math, string ops |
| `run_data` | stdlib + pandas/numpy/etc | In-process or subprocess | Data analysis, file processing |

```python
python(mode="run", code="print(sum(i**2 for i in range(10)))")
python(mode="run_data", code="import pandas as pd\ndf = pd.read_csv('data.csv')\nprint(df.describe())")
```

Always use `print()` to return output — variables are not captured.

### `file(action, ...)`
Read, write, search and manage files. 14 actions covering all common formats.

| Category | Actions |
|----------|---------|
| Basic | `read`, `write`, `list`, `backup` |
| Multi-file | `read_many` (concurrent), `search` (SQLite FTS) |
| PDF | `read_pdf`, `write_pdf` |
| Word | `read_docx`, `write_docx` |
| Excel | `read_xlsx`, `write_xlsx` |
| PowerPoint | `read_pptx`, `write_pptx` |

All paths resolve relative to `workspace/`. Path traversal outside allowed roots is blocked.  
`write` auto-creates a `.bak` backup of any existing file.

### `git(operation, ...)`
Version control for workspace and agent code.

| Operation | Use for |
|-----------|---------|
| `snapshot` | Create safe rollback point **before** any automated change |
| `commit` | Record successful changes **after** testing passes |
| `rollback` | Undo all uncommitted changes when something fails |
| `log` | View recent commit history |
| `status` | See what has changed |
| `diff` | View exact changes |

`root` parameter: `"workspace"` (default) or `"agent"` — the agent can version both.

```python
git(operation="snapshot", message="before editing memory.py")
git(operation="commit",   message="fix: correct decay scoring")
git(operation="rollback")                                        # undo on failure
git(operation="log", n=5, root="agent")
```

### `notify(action, ...)`

| Action | Use for |
|--------|---------|
| `send` | Immediate desktop notification |
| `schedule` | Reminder after N minutes |
| `cancel` | Cancel a scheduled reminder |
| `list` | Show all pending reminders |

Cross-platform: Windows uses plyer (toast), Linux uses notify-send, both fall back to console.

### `visualize(type, ...)`
Create self-contained interactive HTML files — open in any browser, no server needed.

| Type | Output | Libraries |
|------|--------|-----------|
| `chart` | Interactive Plotly chart | plotly |
| `map` | Interactive Leaflet map | folium |
| `report` | Professional HTML report with embedded charts | jinja2 + plotly |
| `dashboard` | Multi-panel responsive dashboard | plotly |

Chart types: `bar · line · scatter · area · pie · histogram · box · heatmap · treemap · funnel · bubble`  
Map types: `markers · heatmap · choropleth · route · circles`

All outputs saved to `workspace/visualizations/`.  
Optional PNG export (`export_png=True`) via kaleido.  
Optional PDF export for reports (`export_pdf=True`) via weasyprint.

---

## Configuration (`.env`)

```ini
# Paths — use forward slashes, no trailing slash
AGENT_ROOT=D:/mcp/agent
WORKSPACE_ROOT=D:/mcp/workspace
MEMORY_ROOT=D:/mcp/memory_db

# LM Studio
LM_STUDIO_BASE_URL=http://localhost:1234/v1

# Model roles
PLANNER_MODEL=qwen/qwen3.5-9b
EXECUTOR_MODEL=hermes-3-llama-3.1-8b
ROUTER_MODEL=nvidia/nemotron-3-nano-4b
# VISION_MODEL=               # uncomment when a vision model is loaded

# SearXNG (self-hosted)
SEARXNG_URL=http://192.168.1.10:30053

# Memory tuning
MEMORY_DELETE_THRESHOLD=0.4
MEMORY_DECAY_DAYS=30
MEMORY_TOP_K=5

# Execution
EXECUTION_TIMEOUT=120
SANDBOX_TIMEOUT=30

# Autocode
AUTOCODE_MAX_RETRIES=3
AUTOCODE_MAX_FILE_CHARS=6000
AUTOCODE_DEBUG=0            # set to 1 for verbose trace logging

# Gateway (Phase 9)
GATEWAY_HOST=0.0.0.0
GATEWAY_PORT=8000
GATEWAY_SECRET=changeme     # change before exposing to network

# Environment
ENV=development
```

---

## MCP Server Configuration (`mcp.json`)

4 servers instead of the original 9. SearXNG, SQLite, fetch, and sequential-thinking
are absorbed into the agent's meta-tools and no longer exposed separately.

```json
{
  "mcpServers": {
    "agent": {
      "command": "python",
      "args": ["D:/mcp/agent/server.py"],
      "cwd": "D:/mcp/agent",
      "env": { "ENV_FILE": "D:/mcp/agent/.env" }
    },
    "fs": {
      "command": "npx",
      "args": [
        "-y", "@modelcontextprotocol/server-filesystem",
        "D:/mcp/workspace",
        "D:/mcp/agent"
      ]
    },
    "git": {
      "command": "npx",
      "args": ["-y", "@cyanheads/git-mcp-server@latest"],
      "env": {
        "MCP_TRANSPORT_TYPE": "stdio",
        "GIT_BASE_DIR": "D:/mcp/workspace"
      }
    },
    "time": {
      "command": "npx",
      "args": ["-y", "@mcpcentral/mcp-time"]
    }
  }
}
```

---

## Installation

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
git clone <repo-url> agent
cd agent

pip install -r requirements.txt
```

> **weasyprint on Windows** requires the GTK3 runtime.  
> Download: https://github.com/tschoonj/GTK-for-Windows-Runtime-Environment-Installer  
> If it fails, skip it — HTML reports work without it, only PDF export is unavailable.

### 3. Configure

```bash
# Copy the example env and edit with your paths/models
cp .env.example .env
# Edit .env with your actual paths, model names, and SearXNG URL
```

### 4. SearXNG (self-hosted search)

```bash
# Docker (recommended)
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
2. Load all three models (Planner, Executor, Router)
3. Enable the local server on port 1234
4. Verify: `curl http://localhost:1234/v1/models`

### 6. Verify installation

```bash
# Phase 1 — config and tracing
python -c "from core.config import cfg; from core.tracer import tracer; cfg.ensure_dirs(); print(cfg)"

# Phase 2 — LLM client
python verify_phase2.py

# Phase 3 — memory
python verify_phase3.py

# Phase 4 — meta-tools
python verify_phase4.py
python verify_phase4b.py
python verify_phase4c.py
```

### 7. Start the agent

```bash
python server.py
```

---

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
       text="ChromaDB collections are isolated vector spaces",
       importance=7, tags="chromadb,architecture")

# Procedural — how to do things
memory(action="store", memory_type="procedural",
       text="To add a new tool: decorate with @tool, no changes to server.py needed",
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

## Workflows (Phase 7)

Three core workflow types built with LangGraph:

### Research workflow
```
recall → search → scrape → synthesize (Hermes) → store → notify
```
Use for: information gathering, summarisation, fact-finding.

### Data workflow
```
recall → execute code → critique → store → notify
```
Use for: pandas/numpy analysis, calculations, dataset generation.

### Autocode workflow
```
snapshot → read → recall → analyze (Hermes+ANALYZER_SYSTEM)
        → generate patch (Hermes+CODER_SYSTEM)
        → review (Hermes+REVIEWER_SYSTEM)
        → syntax check → ruff lint → test
        → apply → commit  OR  rollback on failure
        → store learning → notify
```
Use for: fixing bugs, adding features, refactoring code.

**Protected files** — autocode will never touch these:
- `server.py`
- `registry.py`
- `core/config.py`
- `core/tracer.py`

---

## Observability

Every workflow run gets a `trace_id` (8-char hex). All steps, errors, and
results attach to it.

```
[1e124f2e] autocode | goal='fix decay scoring' | status=success | steps=12 | elapsed=47.3s
```

Logs written to `logs/agent_YYYYMMDD.jsonl` (structured JSON, one entry per line).

```bash
# View today's log
cat logs/agent_$(date +%Y%m%d).jsonl | python -m json.tool | less

# Filter by trace
grep "1e124f2e" logs/agent_20260430.jsonl
```

---

## Cross-machine Setup (Phase 9)

The gateway layer exposes a REST API so two machines can collaborate:

```
Machine A (Windows, RTX 5060 Ti) ←→ Machine B (Linux, other GPU)
         POST /task                        POST /task
         GET  /result/{trace_id}           GET  /result/{trace_id}
```

Both machines run the same codebase with different `.env` files.  
Machine B can delegate heavy LLM tasks to Machine A, or run parallel workflows.

Configure in `.env`:
```ini
GATEWAY_HOST=0.0.0.0
GATEWAY_PORT=8000
GATEWAY_SECRET=your-shared-secret
```

---

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
# In your startup code or a config file:
from core.llm import llm, LMStudioProvider

# DeepSeek (OpenAI-compatible)
llm.register_provider(
    "deepseek",
    LMStudioProvider("https://api.deepseek.com/v1")
)

# Then use it in a role override:
cfg.model_registry["executor"]["provider"] = "deepseek"
cfg.model_registry["executor"]["model"]    = "deepseek-coder-v2"
```

---

## Troubleshooting

**`LM Studio reachable: False`**  
→ LM Studio is not running or the server is not enabled.  
→ Check `http://localhost:1234/v1/models` in your browser.

**`Cannot reach SearXNG`**  
→ Check `SEARXNG_URL` in `.env` matches your NAS/Docker IP and port.  
→ Test: `curl http://YOUR_IP:30053/search?q=test&format=json`

**ChromaDB import error**  
→ Try: `pip install chromadb --no-binary chromadb`

**`kaleido` crashes on PNG export**  
→ Try: `pip install kaleido==0.2.1`

**Autocode produces syntax errors**  
→ Check `AUTOCODE_DEBUG=1` in `.env` and review the trace log.  
→ The CODER_SYSTEM and REVIEWER_SYSTEM prompts require Hermes — confirm the executor model is loaded in LM Studio.

**Tool not appearing after adding it**  
→ Confirm the function has the `@tool` decorator.  
→ Confirm the file is inside the `tools/` directory.  
→ Restart the MCP server (`python server.py`).

---

## Roadmap

| Phase | Status | Description |
|-------|--------|-------------|
| 1 | ✅ Done | Foundation — config, tracer, registry |
| 2 | ✅ Done | LLM client — provider abstraction, role dispatch |
| 3 | ✅ Done | Memory — 3-collection ChromaDB, decay scoring |
| 4 | ✅ Done | Meta-tools — web, python, file, git, notify |
| 4b | ✅ Done | Visualise — chart, map, report, dashboard |
| 4c | ✅ Done | Office files — docx, xlsx, pptx read/write |
| 5 | 🔄 Next | Agent + memory meta-tools, Nemotron router wired |
| 6 | ⬜ | Server.py complete, mcp.json finalised, end-to-end test |
| 7 | ⬜ | Workflows — research, data, autocode rebuilt with traces |
| 8 | ⬜ | Router layer — Nemotron classifies all incoming tasks |
| 9 | ⬜ | Gateway — REST API + messaging adapters (Discord, Telegram) |
| 10 | ⬜ | B3 skills — Brazilian stock market domain pack |

---

## Licence

Private project. Not for redistribution.
