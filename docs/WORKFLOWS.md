# 🔄 Workflows Architecture & Orchestration Guide

Workflows are long-running, multi-step orchestration pipelines built on **LangGraph**. They coordinate multiple tools, LLM calls, and memory operations to achieve complex goals that require sequential reasoning, error recovery, and state management.

This document provides a **high-level overview** of all workflows. For deep-dive state machines, node-by-node breakdowns, and tool-specific details, see the dedicated docs in `docs/workflows/`.

---

## 🏗️ The Foundation Layer

All workflows inherit from a shared foundation defined in `workflows/base.py`.

| Component | File | Purpose |
|-----------|------|---------|
| **`WorkflowState`** | `workflows/base.py` | `TypedDict(total=False)` — shared state schema. Nodes return partial updates (only changed keys). |
| **`node_step()`** | `workflows/base.py` | Trace logging: `tracer.step(tid, node, message, **kwargs)` |
| **`node_error()`** | `workflows/base.py` | Mark state failed, log error, save checkpoint. Returns partial dict. |
| **`node_done()`** | `workflows/base.py` | Mark state succeeded, finish trace, mark complete. Returns partial dict. |
| **`trim_state()`** | `workflows/base.py` | Phase 5 memory eviction: evicts oversized fields to async queue to prevent checkpoint bloat. |
| **`run_workflow()`** | `workflows/base.py` | Dispatcher: trace creation → checkpoint resume → route to correct graph → exception isolation. |

**Key design decisions:**
- **Partial updates** — Nodes return `dict` with only changed keys. Never mutate state in-place. Never spread `**state`.
- **Trace auto-creation** — If `trace_id` is empty, `tracer.new_trace()` creates one automatically.
- **Checkpoint resumption** — `resume=True` restores from the checkpoint journal with version validation (`_checkpoint_version == 1`).
- **Exception isolation** — The entire dispatch is wrapped in try/except. Workflow crashes return clean failure dicts, never leak exceptions.

See `docs/workflows/BASE.md` for full details.

---

## 📚 Workflow Catalog

The agent currently exposes **6 workflows**, triggerable via `run_workflow()` or the `workflow()` meta-tool.

### 1. 🔬 Research (`workflows/research.py`)
**Purpose:** Quick information gathering and synthesis. Single search → parallel scrape → one-shot synthesis.

**Flow:** recall → search → parallel_scrape → synthesize → report → store → distill → notify

**Key characteristics:**
- **Single-query** — One SearXNG search, top results scraped in parallel
- **Browser fallback** — JS-heavy pages retried with `browser(navigate+text_content)`
- **TDD not used** — No test-driven development; pure information synthesis
- **Fast** — 1-2 minutes for simple queries

**Safety:** SSRF protection, citation tracking, prune_tool_dict truncation.

See `docs/workflows/RESEARCH.md` for full details.

---

### 2. 🔬 Deep Research (`workflows/deep_research.py` + `workflows/deep_research_core/`)
**Purpose:** Iterative, multi-faceted research for complex questions. ReAct-style loop with self-evaluation.

**Flow:** recall → decompose → search → synthesize → [route: loop or exit] → report → notify → store → distill

**Key characteristics:**
- **ReAct loop** — Cycles through decompose → search → synthesize until convergence or max iterations
- **Budget-aware** — Hard caps on iterations, API calls, and browser actions
- **Three-tier tools** — `tavily` → `web` → `browser` fallback chain
- **Convergence detection** — `SequenceMatcher` exits when knowledge stops changing
- **Self-evaluation** — Completeness scoring (0-100) per iteration

**Safety:** Nested-call guard, URL deduplication, knowledge capping at 6K chars.

See `docs/workflows/DEEP_RESEARCH.md` for full details.

---

### 3. 📊 Data (`workflows/data.py`)
**Purpose:** Python-based data analysis, calculations, and dataset generation.

**Flow:** recall → execute → critique → store → notify

**Key characteristics:**
- **Code execution** — Real Python via `python(mode="run_data")`
- **Optional generation** — If no code provided, `agent(role="code")` generates it from the goal
- **Critique layer** — `agent(role="critique")` evaluates output quality (best-effort)
- **Dual memory** — Stores both episodic (result) and procedural (working code) memories

**Safety:** Sandboxed execution, best-effort critique (never fails workflow).

See `docs/workflows/DATA.md` for full details.

---

### 4. 🤖 Autocode (`workflows/autocode.py` + `workflows/autocode_helpers/`)
**Purpose:** Autonomous code generation with TDD, git scoping, and architectural safety.

**Flow:** classify → validate → brainstorm → plan → branch → tests → execute → write_files → analyze_impact → run_tests → [debug → retry] → verify → report → commit → distill

**Key characteristics:**
- **TDD on disk** — Real pytest subprocess; exit codes are ground truth
- **Surgical patching** — `str_replace` patches preferred over full rewrites
- **Git scoping** — Workspace-scoped branches and commits
- **Protected files** — Blocks writes to `server.py`, `core/*`, `registry.py`
- **Self-correcting** — Debug → retry with temperature jitter
- **16 nodes** — Most complex workflow in the agent

**Safety:** Protected files, git snapshot/rollback, AST validation, retry limits, hallucination guard.

See `docs/workflows/AUTOCODE.md` for full details.

---

### 5. 🧠 Understand (`workflows/understand.py`)
**Purpose:** Build and maintain a deterministic Codebase Knowledge Graph for Python projects.

**Flow:** init_project → discover_files → parse_and_store → report

**Key characteristics:**
- **AST-based parsing** — Extracts imports via Python AST (not regex)
- **Incremental indexing** — MD5 + mtime comparison; only changed files re-parsed
- **Physical isolation** — Separate artifact directories for agent root vs workspace
- **Batch processing** — Files parsed in batches of 10

**Safety:** Size rejection, file size limits, skip directories.

See `docs/workflows/UNDERSTAND.md` for full details.

---

### 6. 🔄 Base (`workflows/base.py`)
**Purpose:** Shared infrastructure — not a user-facing workflow, but the foundation all others build on.

**Components:** `WorkflowState`, `node_step()`, `node_error()`, `node_done()`, `trim_state()`, `run_workflow()`

See `docs/workflows/BASE.md` for full details.

---

## 🔄 Workflow Comparison

| Aspect | Research | Deep Research | Data | Autocode | Understand |
|--------|----------|---------------|------|----------|------------|
| **Structure** | 8-node pipeline | Cyclic ReAct loop | 5-node pipeline | 16-node state machine | 4-node pipeline |
| **Primary tools** | `web`, `browser` | `tavily`, `web`, `browser` | `python_exec`, `agent` | `agent`, `python_exec`, `git` | `python` (AST) |
| **LLM roles** | `research` | `planner`, `research`, `executor` | `code`, `critique` | `router`, `planner`, `executor` | N/A |
| **Loop type** | Linear | Cyclic (decompose→search→synthesize) | Linear | Cyclic (debug→retry) | Linear |
| **TDD** | ❌ No | ❌ No | ❌ No | ✅ Yes (real pytest) | ❌ No |
| **Git ops** | ❌ No | ❌ No | ❌ No | ✅ Yes (branch, commit) | ❌ No |
| **Memory** | Recall + store | Recall + store | Recall + store | Recall + store + distill | N/A |
| **Budget tracking** | ❌ No | ✅ Yes (iterations, API, browser) | ❌ No | ✅ Yes (retries) | ❌ No |
| **Convergence** | ❌ No | ✅ Yes (SequenceMatcher) | ❌ No | ❌ No | ❌ No |
| **Use case** | Quick facts | Complex research | Data analysis | Code generation | Codebase indexing |
| **Typical duration** | 1-2 min | 3-10 min | 30s-2 min | 2-10 min | 1-5 min |

---

## 🚀 Triggering & Integration

### 1. Via Python (Primary Entry Point)
```python
from workflows.base import run_workflow

result = run_workflow(
    workflow_type="research",      # "research" | "data" | "autocode" | "deep_research" | "understand"
    goal="What are the best practices for ChromaDB in production?",
    trace_id="abc123",
    resume=False,                   # Resume from checkpoint if True
)

print(result["status"])   # "success" | "failed"
print(result["result"])   # Final result summary
```

### 2. Via MCP Tool (LLM initiated)
```python
workflow(type="autocode", goal="Fix the KeyError in skills/b3/b3_dividends.py")
```

### 3. Via REST API (External client initiated)
```bash
curl -X POST http://localhost:8000/task   -H "Authorization: Bearer $GATEWAY_SECRET"   -H "Content-Type: application/json"   -d '{"goal": "Research B3 dividend trends", "workflow": "research"}'
```

### 4. Direct Graph Access (Testing / Custom invocation)
```python
from workflows.research import build_research_graph

graph = build_research_graph()
result = graph.invoke({"goal": "...", "trace_id": "..."})
```

---

## 🛡️ Workflow Safety & Architectural Rules

### 1. Immutability & Partial Updates (CRITICAL)
LangGraph does **not** deep-copy nested mutable objects. You must never mutate the shared state dictionary in-place.

- ❌ **WRONG**: `state["messages"].append(new_msg)` or `return {**state, "status": "done"}`
- ✅ **RIGHT**: `messages = list(state.get("messages", [])) + [new_msg]` followed by `return {"messages": messages}`

### 2. MCP Stdio Safety
Never use `print()` or write to `sys.stdout` inside any workflow node. The MCP protocol uses `stdout` for JSON-RPC communication. Writing to stdout will corrupt the payload and crash the server. Always use `node_step()`, `tracer.step()`, or `sys.stderr`.

### 3. Memory Integration (Bookend Pattern)
Every workflow should follow:
- **Start**: Always `recall` relevant memories to inject context into the first LLM prompt.
- **End**: Always `store` the outcome (episodic for events, procedural for lessons learned).

### 4. Timeout Enforcement
Wrap all external tool calls, subprocess executions, and LLM calls in timeouts. A hanging tool should fail the node gracefully and trigger a rollback or retry, not freeze the entire agent loop.

### 5. Best-Effort Side Effects
Report generation, memory storage, and notifications should never fail the workflow. Catch exceptions and continue.

### 6. Checkpoint Safety
`node_error()` always saves a checkpoint. `node_done()` marks the checkpoint complete. This enables resumability after crashes.

---

## 📁 Documentation Map

| Workflow | Doc File | Nodes | Key Tools |
|----------|----------|-------|-----------|
| Base (shared) | `docs/workflows/BASE.md` | 3 helpers + dispatcher | `tracer`, `checkpoint` |
| Research | `docs/workflows/RESEARCH.md` | 8 | `web`, `browser`, `agent` |
| Deep Research | `docs/workflows/DEEP_RESEARCH.md` | 8 + cyclic | `tavily`, `web`, `browser`, `agent` |
| Data | `docs/workflows/DATA.md` | 5 | `python_exec`, `agent` |
| Autocode | `docs/workflows/AUTOCODE.md` | 16 | `agent`, `python_exec`, `git`, `report` |
| Understand | `docs/workflows/UNDERSTAND.md` | 4 | `python` (AST), `GraphStore` |

---

## 🗺️ Cross-Workflow Roadmap

### ✅ Completed

| Feature | Status | Notes |
|---------|--------|-------|
| Shared `WorkflowState` + helpers | ✅ v1.0 | `workflows/base.py` — all workflows use common foundation |
| Checkpoint resumption | ✅ v1.0 | `run_workflow(resume=True)` with version validation |
| Trace lifecycle management | ✅ v1.0 | Auto-creation, step logging, error tracking, completion |
| 5 user-facing workflows | ✅ v1.0 | research, deep_research, data, autocode, understand |
| LangGraph immutability | ✅ v1.0 | Partial updates, no in-place mutation, no `**state` |
| Memory bookend pattern | ✅ v1.0 | Recall before, store after — all workflows |
| Exception isolation | ✅ v1.0 | Try/except in dispatcher, clean failure dicts |

### 🔄 In Progress / Next Up

| Feature | Notes | Priority |
|---------|-------|----------|
| Workflow registry | Replace hardcoded if/elif in `run_workflow()` with dynamic `WORKFLOW_REGISTRY` dict | P1 |
| Unified test structure | All workflow tests should follow `conftest.py` + per-node file pattern (like `tests/tools/git/`) | P1 |
| Workflow composition | Enable workflows to call other workflows (e.g., `deep_research` → `autocode` for implementation) | P2 |
| Streaming partial results | Yield intermediate results per node instead of batch return at end | P2 |
| Configurable timeouts per workflow | Currently shared timeouts. Add workflow-specific timeout overrides | P2 |
| Workflow telemetry | Aggregate metrics: avg duration, success rate, node failure distribution | P3 |
| Workflow scheduling | Cron-like scheduling for periodic workflows (e.g., daily research reports) | P3 |

### 🚫 Deferred / Out of Scope

| # | Feature | Why Deferred | Priority |
|---|---------|------------|----------|
| 1 | **Remove LangGraph dependency** | LangGraph provides checkpointing, streaming, and visual debugging. Replacing it would require reimplementing all of that. | Skip |
| 2 | **Merge all workflows into one mega-workflow** | Each workflow has distinct goals, safety requirements, and tool sets. Merging would create unmaintainable complexity. | Skip |
| 3 | **Remove checkpoint system** | Checkpoints are essential for resumability and debugging across all workflows. | Skip |
| 4 | **Remove trace auto-creation** | Trace IDs are required for observability. Manual management would burden every caller. | Skip |

---

*Architecture: shared WorkflowState + node helpers + dispatcher → 5 distinct LangGraph workflows → memory bookend pattern → checkpoint resumption → exception isolation → best-effort side effects.*
