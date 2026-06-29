# 🔄 Workflows Architecture & Orchestration Guide

Workflows are long-running, multi-step orchestration pipelines built on **LangGraph**. They coordinate multiple tools, LLM calls, and memory operations to achieve complex goals that require sequential reasoning, error recovery, and state management.

This document provides a **high-level overview** of all workflows and serves as an **index** to the detailed workflow docs. For deep-dive state machines, node-by-node breakdowns, and tool-specific details, see the dedicated docs in `docs/workflows/`.

---

## 🏗️ The Foundation Layer

All workflows inherit from a shared foundation defined in `workflows/base.py`.

| Component | File | Purpose |
|-----------|------|---------|
| **`WorkflowState`** | `workflows/base.py` | `TypedDict(total=False)` — shared state schema (22 fields). Nodes return partial updates (only changed keys). |
| **`node_step()`** | `workflows/base.py` | Trace logging: `tracer.step(tid, node, message, **kwargs)` |
| **`node_error()`** | `workflows/base.py` | Mark state failed, log error, save checkpoint. Returns partial dict. **Note:** Saves partial checkpoint (loses workflow context on resume). |
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

### 1. 🔍 Research (`workflows/research.py`)
**Purpose:** Quick information gathering and synthesis. Single search → parallel scrape → one-shot synthesis.

**Flow:** recall → search → parallel_scrape → synthesize → report → store → distill → notify

**Key characteristics:**
- **Single-query** — One SearXNG search, top results scraped in parallel (max 3, hardcoded)
- **Browser fallback** — JS-heavy pages retried with `browser(navigate+text_content)`
- **TDD not used** — No test-driven development; pure information synthesis
- **Fast** — 1-2 minutes for simple queries
- **Critical bug:** `agent()` missing `action="dispatch"` in `node_synthesize` — always returns error
- **Critical bug:** `not r.get("status") == "success"` always false — error path never fires

**Safety:** SSRF protection, citation tracking, prune_tool_dict truncation.

**Doc:** `docs/workflows/RESEARCH.md`

---

### 2. 🔬 Deep Research (`workflows/deep_research.py` + `workflows/deep_research_core/`)
**Purpose:** Iterative, multi-faceted research for complex questions. ReAct-style loop with self-evaluation.

**Flow:** recall → decompose → search → synthesize → [route: loop or exit] → report → notify → store → distill

**Key characteristics:**
- **ReAct loop** — Cycles through decompose → search → synthesize until convergence or max iterations
- **Budget-aware** — Hard caps on API calls (Tavily) and browser actions (tracked separately)
- **Three-tier tools** — `tavily` → `web` → `browser` fallback chain
- **Convergence detection** — Cosine similarity exits when knowledge stops changing (threshold: 0.85)
- **Self-evaluation** — Completeness scoring (0-100) per iteration
- **Critical bug:** `agent()` missing `action="dispatch"` in `node_synthesize` and `node_evaluate`
- **Critical bug:** API budget decremented for web searches (should only decrement for Tavily)
- **Critical bug:** `completeness_threshold` scale mismatch — node defaults to 0.85 (0-1), route uses 85.0 (0-100)

**Safety:** Nested-call guard, URL deduplication, knowledge capping at 6K chars.

**Doc:** `docs/workflows/DEEP_RESEARCH.md`

---

### 3. 📊 Data (`workflows/data.py`)
**Purpose:** Python-based data analysis, calculations, and dataset generation.

**Flow:** recall → execute → critique → store → notify

**Key characteristics:**
- **Code execution** — Real Python via `python(mode="run_data")`
- **Optional generation** — If no code provided, `agent(role="code")` generates it from the goal
- **Critique layer** — `agent(role="critique")` evaluates output quality (best-effort)
- **Dual memory** — Stores both episodic (result) and procedural (working code) memories
- **Critical bug:** `agent()` missing `action="dispatch"` in `node_execute` and `node_critique`
- **Critical bug:** Code-gen failure routes to critique instead of END (route checks wrong field)
- **Critical bug:** `**state` spreading in all nodes violates LangGraph best practice

**Safety:** Sandboxed execution, best-effort critique (never fails workflow).

**Doc:** `docs/workflows/DATA.md`

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
- **17 nodes** — Most complex workflow in the agent (doc says 16, but graph has 17)
- **Critical bug:** `.bak` files created (violates user rule #54)
- **Critical bug:** `git(action="snapshot")` doesn't exist (removed in un-multiplex refactor)
- **Critical bug:** `files_map` never populated — `analyze_impact` never runs
- **Critical bug:** `node_analyze_impact` is async in sync graph — may fail or hang
- **Critical bug:** `node_brainstorm` loses KG files (stores original instead of merged)

**Safety:** Protected files, git snapshot/rollback, AST validation, retry limits, hallucination guard.

**Doc:** `docs/workflows/AUTOCODE.md`

---

### 5. 🧠 Understand (`workflows/understand.py`)
**Purpose:** Build and maintain a deterministic Codebase Knowledge Graph for Python projects.

**Flow:** init_project → discover_files → parse_and_store → report

**Key characteristics:**
- **AST-based parsing** — Extracts imports via Python AST (not regex)
- **Incremental indexing** — MD5 + mtime comparison; only changed files re-parsed
- **Physical isolation** — Separate artifact directories for agent root vs workspace
- **Batch processing** — Files parsed in batches of 10
- **Not a LangGraph StateGraph** — Direct async function calls, not graph-based
- **Critical bug:** Hardcoded `tid` strings in all nodes — no trace correlation
- **Critical bug:** `trace_id` never injected into initial state
- **Critical bug:** `GraphStore` created but discarded in `node_init`

**Safety:** Size rejection, file size limits, skip directories.

**Doc:** `docs/workflows/UNDERSTAND.md`

---

### 6. 🏗️ Base (`workflows/base.py`)
**Purpose:** Shared infrastructure — not a user-facing workflow, but the foundation all others build on.

**Components:** `WorkflowState`, `node_step()`, `node_error()`, `node_done()`, `trim_state()`, `run_workflow()`

**Critical bug:** `node_error` saves partial checkpoint (loses all workflow context on resume)
**Critical bug:** Exception handler in `run_workflow()` doesn't save checkpoint on crash
**Critical bug:** `understand` workflow disconnects from trace/checkpoint system
**Critical bug:** `report` workflow missing from dispatcher

**Doc:** `docs/workflows/BASE.md`

---

## 🔄 Workflow Comparison

| Aspect | Research | Deep Research | Data | Autocode | Understand |
|--------|----------|---------------|------|----------|------------|
| **Structure** | 8-node pipeline | Cyclic ReAct loop | 5-node pipeline | 17-node state machine | 4-node pipeline (not LangGraph) |
| **Primary tools** | `web`, `browser` | `tavily`, `web`, `browser` | `python_exec`, `agent` | `agent`, `python_exec`, `git` | `python` (AST), `GraphStore` |
| **LLM roles** | `research` | `planner`, `research`, `executor` | `code`, `critique` | `router`, `planner`, `executor`, `test` | N/A |
| **Loop type** | Linear | Cyclic (decompose→search→synthesize) | Linear | Cyclic (debug→retry) | Linear |
| **TDD** | ❌ No | ❌ No | ❌ No | ✅ Yes (real pytest) | ❌ No |
| **Git ops** | ❌ No | ❌ No | ❌ No | ✅ Yes (branch, commit) | ❌ No |
| **Memory** | Recall + store | Recall + store | Recall + store | Recall + store + distill | N/A |
| **Budget tracking** | ❌ No | ✅ Yes (API calls, browser actions) | ❌ No | ✅ Yes (retries) | ❌ No |
| **Convergence** | ❌ No | ✅ Yes (cosine similarity) | ❌ No | ❌ No | ❌ No |
| **Use case** | Quick facts | Complex research | Data analysis | Code generation | Codebase indexing |
| **Typical duration** | 1-2 min | 3-10 min | 30s-2 min | 2-10 min | 1-5 min |
| **Critical bugs** | 2 P0 | 5 P0 | 4 P0 | 11 P0 | 3 P0 |

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
curl -X POST http://localhost:8000/task \
  -H "Authorization: Bearer $GATEWAY_SECRET" \
  -H "Content-Type: application/json" \
  -d '{"goal": "Research B3 dividend trends", "workflow": "research"}'
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

### 7. Agent Tool Contract
The `agent()` facade requires `action` parameter. Always pass `action="dispatch"` for LLM calls. Never call `agent(role="...")` without `action`.

### 8. No `.bak` Files
Creating `.bak` backup files is forbidden by project rules. Use atomic writes (`tempfile.NamedTemporaryFile` + `os.replace`) instead.

---

## 📁 Documentation Map

| Workflow | Doc File | Nodes | Key Tools | Critical Bugs |
|----------|----------|-------|-----------|---------------|
| Base (shared) | `docs/workflows/BASE.md` | 3 helpers + dispatcher | `tracer`, `checkpoint` | 4 P0 |
| Research | `docs/workflows/RESEARCH.md` | 8 | `web`, `browser`, `agent` | 2 P0 |
| Deep Research | `docs/workflows/DEEP_RESEARCH.md` | 8 + cyclic | `tavily`, `web`, `browser`, `agent` | 5 P0 |
| Data | `docs/workflows/DATA.md` | 5 | `python_exec`, `agent` | 4 P0 |
| Autocode | `docs/workflows/AUTOCODE.md` | 17 | `agent`, `python_exec`, `git`, `report` | 11 P0 |
| Understand | `docs/workflows/UNDERSTAND.md` | 4 | `python` (AST), `GraphStore` | 3 P0 |

---

## 🗺️ Cross-Workflow Roadmap

### ✅ Completed

| Feature | Status | Notes |
|---------|--------|-------|
| Shared `WorkflowState` + helpers | ✅ v1.0 | `workflows/base.py` — all workflows use common foundation (22 fields) |
| Checkpoint resumption | ✅ v1.0 | `run_workflow(resume=True)` with version validation |
| Trace lifecycle management | ✅ v1.0 | Auto-creation, step logging, error tracking, completion |
| 5 user-facing workflows | ✅ v1.0 | research, deep_research, data, autocode, understand |
| LangGraph immutability | ✅ v1.0 | Partial updates, no in-place mutation, no `**state` |
| Memory bookend pattern | ✅ v1.0 | Recall before, store after — all workflows |
| Exception isolation | ✅ v1.0 | Try/except in dispatcher, clean failure dicts |

### 🔄 In Progress / Next Up

| # | Feature | Notes | Priority |
|---|---------|-------|----------|
| 1 | **Fix `agent()` missing `action="dispatch"`** | Found in `data.py`, `research.py`, `deep_research/synthesize.py`. `agent()` facade requires `action`. | P0 |
| 2 | **Fix `not r.get("status") == "success"` always false** | `research.py` line 67: `(not "success") == "success"` → `False`. Error path never fires. | P0 |
| 3 | **Remove `.bak` file creation** | Violates user rule #54. Found in `patch.py`, `write_files.py`, `helpers.py`. | P0 |
| 4 | **Fix `git(action="snapshot")` doesn't exist** | Removed in un-multiplex refactor. `git_ops.py` still calls it. | P0 |
| 5 | **Fix `node_error` partial checkpoint** | Saves only `{"status": "failed", "error": ...}` — loses all workflow context on resume. | P0 |
| 6 | **Fix exception handler missing checkpoint** | `run_workflow()` `except Exception` returns failure dict but never calls `save_checkpoint()`. | P0 |
| 7 | **Fix `understand` disconnect from trace/checkpoint** | Ignores `trace_id`, `goal`, and checkpoint system. `resume=True` is meaningless. | P0 |
| 8 | **Fix `report` workflow missing from dispatcher** | `workflow_tool.py` accepts `"report"` but `run_workflow()` has no `elif wf_type == "report"`. | P0 |
| 9 | **Fix `files_map` never populated** | No node sets `files_map`. `analyze_impact` always returns early with empty warnings. | P0 |
| 10 | **Fix `node_analyze_impact` async in sync graph** | LangGraph `StateGraph.add_node` expects sync. Async function may fail or hang. | P0 |
| 11 | **Fix `node_write_files` `run_dir` NameError** | If `test_code` missing but `tdd_source_code` exists, `run_dir` undefined. | P0 |
| 12 | **Fix `node_execute_step` uses non-existent `files_context`** | `state.get("files_context", "")` — field doesn't exist in `AutocodeState`. | P0 |
| 13 | **Fix `node_brainstorm` loses KG files** | Merges `kg_files` but stores original `state["files"]` instead of merged. | P0 |
| 14 | **Fix `impact_warnings` type mismatch** | `state.py` says `list[str]`, `analyze_impact.py` returns `list[dict]`. | P0 |
| 15 | **Fix `AGENT_ROOT = None` never set** | `state.py` line 10: `AGENT_ROOT = None # Set via cfg`. Never actually set. | P0 |
| 16 | **Fix `node_commit` uses `defense_note` not `defense_notes`** | State field is `defense_notes` (plural). Always empty. | P0 |
| 17 | **Fix `node_distill_memory` uses `hypothesis`/`defense_note` never set** | Debug node sets `root_cause` and `defense_notes`, not `hypothesis` or `defense_note`. | P0 |
| 18 | **Fix hardcoded `tid` strings in `understand`** | All nodes use hardcoded `tid` instead of `state.get("trace_id", "")`. | P0 |
| 19 | **Fix `trace_id` never injected into `understand` initial state** | `trace_id` created in `run_understand_workflow()` but never passed to nodes. | P0 |
| 20 | **Fix `GraphStore` created but discarded in `understand`** | `GraphStore` instance created in `node_init` but not stored in state. | P0 |
| 21 | **Fix API budget decremented for web searches in deep_research** | `node_search` decrements `budget_api_calls` for ALL successful searches. Only Tavily should decrement. | P0 |
| 22 | **Fix API budget NOT decremented for failed Tavily in deep_research** | Failed Tavily calls still consume API budget. Not reflected in tracking. | P0 |
| 23 | **Fix `completeness_threshold` scale mismatch in deep_research** | Node defaults to 0.85 (0-1), route uses 85.0 (0-100). Route check always true for score >= 1. | P0 |
| 24 | **Fix code-gen failure routing to critique in data** | `node_execute` returns `node_error()` on failure, but `route_after_execute` checks `exec_error` (not set by `node_error`), so workflow routes to `node_critique` instead of END. | P0 |
| 25 | **Fix `**state` spreading in all nodes** | All nodes return `{**state, ...}` which violates LangGraph best practice. Should return partial dicts. | P0 |
| 26 | **Workflow registry** | Replace hardcoded if/elif in `run_workflow()` with dynamic `WORKFLOW_REGISTRY` dict | P1 |
| 27 | **Unified test structure** | All workflow tests should follow `conftest.py` + per-node file pattern (like `tests/tools/git/`) | P1 |
| 28 | **Workflow composition** | Enable workflows to call other workflows (e.g., `deep_research` → `autocode` for implementation) | P2 |
| 29 | **Streaming partial results** | Yield intermediate results per node instead of batch return at end | P2 |
| 30 | **Configurable timeouts per workflow** | Currently shared timeouts. Add workflow-specific timeout overrides | P2 |
| 31 | **Workflow telemetry** | Aggregate metrics: avg duration, success rate, node failure distribution | P3 |
| 32 | **Workflow scheduling** | Cron-like scheduling for periodic workflows (e.g., daily research reports) | P3 |

### 🚫 Deferred / Out of Scope

| # | Feature | Why Deferred | Priority |
|---|---------|------------|----------|
| 1 | **Remove LangGraph dependency** | LangGraph provides checkpointing, streaming, and visual debugging. Replacing it would require reimplementing all of that. | Skip |
| 2 | **Merge all workflows into one mega-workflow** | Each workflow has distinct goals, safety requirements, and tool sets. Merging would create unmaintainable complexity. | Skip |
| 3 | **Remove checkpoint system** | Checkpoints are essential for resumability and debugging across all workflows. | Skip |
| 4 | **Remove trace auto-creation** | Trace IDs are required for observability. Manual management would burden every caller. | Skip |
| 5 | **Remove TDD from autocode** | TDD ensures test coverage and code quality. Removing it would degrade results. | Skip |
| 6 | **Remove debug loop from autocode** | Iteration catches edge cases and fixes errors. Single-pass would miss many issues. | Skip |
| 7 | **Remove impact analysis from autocode** | Blast radius analysis prevents unintended side effects. Essential for safety. | Skip |
| 8 | **Remove git integration from autocode** | Git branches and commits are essential for version control and rollback. | Skip |
| 9 | **Remove memory integration** | Memory recall improves context and quality. Removing it would degrade all workflows. | Skip |
| 10 | **Remove budget tracking from deep_research** | Budget tracking prevents runaway API costs. Essential for safety. | Skip |
| 11 | **Remove convergence detection from deep_research** | Without it, the workflow would run indefinitely or stop prematurely. | Skip |
| 12 | **Remove multi-tool search from deep_research** | Single-tool search would have limited coverage. Multi-tool is essential. | Skip |
| 13 | **Remove incremental indexing from understand** | Full re-parse on every run would be too slow for large projects. | Skip |
| 14 | **Remove batch processing from understand** | Processing all files at once would cause memory spikes. | Skip |
| 15 | **Real-time collaboration** | Multi-user research would require complex state synchronization. Out of scope. | Skip |
| 16 | **IDE integration** | LSP or VS Code extension development. Out of scope. | Skip |
| 17 | **Real-time streaming** | Streaming would require WebSocket or SSE infrastructure. Out of scope. | Skip |
| 18 | **Support non-Python languages** | The workflows are designed for Python. Other languages would require significant changes. | Skip |
| 19 | **Automatic fact-checking** | Fact-checking would require additional LLM calls and complex logic. Out of scope. | Skip |
| 20 | **File watching** | File watching would require additional infrastructure (e.g., watchdog). Out of scope. | Skip |

---

*Architecture: shared WorkflowState + node helpers + dispatcher → 5 distinct LangGraph workflows + 1 async orchestrator → memory bookend pattern → checkpoint resumption → exception isolation → best-effort side effects.*
