# 🔄 Workflows Architecture & Orchestration Guide

Workflows are long-running, multi-step orchestration pipelines built on **LangGraph**. They coordinate multiple tools, LLM calls, and memory operations to achieve complex goals that require sequential reasoning, error recovery, and state management.

*(Note: This document covers the high-level architecture and shared foundation. Deep-dive state machines and node-by-node breakdowns for specific workflows will be maintained in their own dedicated documentation files, e.g., `docs/AUTOCODE.md`).*

---

## 🏗️ The Foundation Layer (`workflows/base.py`)

All workflows inherit from a shared foundation that standardizes state management, LLM dispatch, and observability. This module is not directly triggerable by the LLM; it is the bedrock for the core workflows.

### Key Components

| Component | Purpose |
|-----------|---------|
| **`WorkflowState`** | A `TypedDict(total=False)` that defines the shape of the graph state. Because it uses `total=False`, nodes only need to return the specific fields they are updating (partial updates). |
| **`_call()` Helper** | Centralized LLM dispatch function. Automatically routes to the Planner, Executor, or Router based on the requested role. Integrates circuit breakers, timeout enforcement, and automatic trace logging. |
| **`_dispatch()` Router** | Uses the Router model (or heuristic fallback) to classify incoming goals and route them to the correct workflow type (`research`, `data`, `autocode`) if triggered via `type="auto"`. |
| **Trace Emission** | Automatically emits structured JSON traces for every node execution to `stderr` and `logs/agent_YYYYMMDD.jsonl`, ensuring full observability without manual logging. |

---

## 📚 Core Workflows (High-Level Overview)

The agent currently exposes three core workflows, triggerable via the `workflow()` meta-tool or the REST API.

### 1. Research (`workflows/research.py`)
**Purpose**: Gather information from the web, synthesize findings, and store knowledge in memory.
* **High-Level Flow**: Recall existing context → Generate search queries → Scrape top results → Synthesize findings via Planner → Store in episodic/semantic memory.
* **Key Safety Mechanisms**: 
  * SSRF protection via `core/path_guard.py` (blocks private IP ranges).
  * Strict citation tracking (`core/citations.py`) to prevent hallucinated sources.
  * Hard timeouts on web scraping to prevent hanging on unresponsive sites.

### 2. Data (`workflows/data.py`)
**Purpose**: Analyze datasets, perform calculations, generate charts, and produce reports.
* **High-Level Flow**: Recall data procedures → Generate pandas/numpy code → Execute in sandbox → Critique output → Store results and generated assets.
* **Key Safety Mechanisms**:
  * Uses the `python` tool in `run_data` mode (isolated subprocess with whitelisted imports).
  * Output validation to ensure generated files (charts, CSVs) exist and are non-empty.
  * Schema enforcement for structured data outputs.

### 3. Autocode (`workflows/autocode.py`)
**Purpose**: Fix bugs, add features, and refactor code with full TDD (Test-Driven Development) and safety rollback.
* **High-Level Flow**: Git Snapshot → Read target files → Recall past bugs → Analyze/Plan → Generate Code → AST Syntax Check → Apply Patch → Run Tests → Commit (or Rollback) → Store procedural memory.
* **Key Safety Mechanisms**:
  * **Protected Files**: Will NEVER edit core infrastructure (`server.py`, `core/*`, `registry.py`).
  * **Git Snapshot/Rollback**: Automatic stash-based backup before changes; automatic rollback if tests fail.
  * **AST Validation**: Blocks malformed or dangerous code before it touches the filesystem.
  * **Retry Limits**: Caps TDD iterations (`AUTOCODE_MAX_RETRIES`) to prevent infinite loops.

---

## 🛡️ Workflow Safety & Architectural Rules

When writing or modifying workflow nodes, all developers (and AI assistants) **must** adhere to these LangGraph and MCP constraints:

### 1. Immutability & Partial Updates (CRITICAL)
LangGraph does **not** deep-copy nested mutable objects. You must never mutate the shared state dictionary in-place.
* ❌ **WRONG**: `state["messages"].append(new_msg)` or `return {**state, "status": "done"}`
* ✅ **RIGHT**: `messages = list(state.get("messages", [])) + [new_msg]` followed by `return {"messages": messages}`

### 2. MCP Stdio Safety
Never use `print()` or write to `sys.stdout` inside any workflow node. The MCP protocol uses `stdout` for JSON-RPC communication. Writing to stdout will corrupt the payload and crash the server. Always use `tracer.step()` or `sys.stderr`.

### 3. Memory Integration
Every workflow should follow the "Bookend Pattern":
* **Start**: Always `recall` relevant memories to inject context into the first LLM prompt.
* **End**: Always `store` the outcome (episodic for events, procedural for lessons learned) so the agent learns from the execution.

### 4. Timeout Enforcement
Wrap all external tool calls, subprocess executions, and LLM calls in timeouts. A hanging tool should fail the node gracefully and trigger a rollback or retry, not freeze the entire agent loop.

---

## 🚀 Triggering & Integration

Workflows can be triggered from three different entry points:

**1. Via MCP Tool (LLM initiated)**
```python
workflow(type="autocode", goal="Fix the KeyError in skills/b3/b3_dividends.py")
```

**2. Via REST API (External client initiated)**
```bash
curl -X POST http://localhost:8000/task \
  -H "Authorization: Bearer $GATEWAY_SECRET" \
  -H "Content-Type: application/json" \
  -d '{"goal": "Research B3 dividend trends", "workflow": "research"}'
```

**3. Via Python (Internal orchestration)**
```python
from workflows.base import run_workflow

result = run_workflow(
    workflow_type="data",
    goal="Analyze sales.csv",
    trace_id="abc123"
)
```