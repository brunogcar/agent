# 🔄 Workflows Architecture & Orchestration Guide

> **Status:** v3 — Verified July 2026 against real source via `workflows/` directory and per-tool docs..

Workflows are long-running, multi-step orchestration pipelines built on **LangGraph**. They coordinate multiple tools, LLM calls, and memory operations to achieve complex goals that require sequential reasoning, error recovery, and state management.

This document provides a **high-level overview** of all workflows and serves as an **index** to the detailed workflow docs. For deep-dive state machines, node-by-node breakdowns, and tool-specific details, see the dedicated docs in `docs/workflows/`.

| Document | Workflow | Key Topics |
|----------|----------|------------|
| [BASE.md](workflows/BASE.md) | Foundation | WorkflowState, node helpers, checkpoint resumption, exception isolation |
| [RESEARCH.md](workflows/RESEARCH.md) | Research | Single-query pipeline, browser fallback, citation tracking |
| [DEEP_RESEARCH.md](workflows/DEEP_RESEARCH.md) | Deep Research | ReAct loop, budget tracking, convergence detection, three-tier tools |
| [DATA.md](workflows/DATA.md) | Data | Python execution, critique layer, dual memory storage |
| [AUTOCODE.md](workflows/AUTOCODE.md) | Autocode | TDD, git scoping, surgical patching, 17-node state machine |
| [UNDERSTAND.md](workflows/UNDERSTAND.md) | Understand | AST parsing, incremental indexing, knowledge graph |
| [AUTORESEARCH.md](workflows/AUTORESEARCH.md) | Autoresearch | Evolutionary experiment loop, metric-driven keep/discard, results ledger |

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

**Known limitations:**
- `node_error()` saves only `{"status": "failed", "error": ...}` — loses all workflow context on resume. Should save full state.
- `run_workflow()` exception handler returns failure dict but never calls `save_checkpoint()`. State at crash time is lost.
- `understand` workflow ignores `trace_id`, `goal`, and checkpoint system. `resume=True` is meaningless.

See [workflows/BASE.md](workflows/BASE.md) for full details.

---

## 📁 Module Map

```
workflows/
├── base.py                 # Shared WorkflowState + node helpers + dispatcher
├── research.py             # Thin facade → research_impl/ (v1.0)
├── data.py                 # 5-node linear pipeline
├── autocode.py             # Thin facade → autocode_impl/
├── deep_research.py        # Thin facade → deep_research_impl/
├── understand.py           # Direct async function calls (not LangGraph)
├── autoresearch.py         # Thin facade → autoresearch_impl/ (7-node experiment loop)
├── helpers/
│   └── checkpoint.py       # Checkpoint journal: save, get_latest, mark_complete
├── autocode_impl/          # 17-node subpackage
│   ├── constants.py
│   ├── git_ops.py
│   ├── graph.py
│   ├── helpers.py
│   ├── mermaid.py
│   ├── patch.py
│   ├── routes.py
│   ├── state.py
│   ├── test_mapper.py
│   ├── test_runner.py
│   └── nodes/
│       ├── analyze_impact.py
│       ├── brainstorm.py
│       ├── branch.py
│       ├── classify.py
│       ├── commit.py
│       ├── create_skill.py
│       ├── debug.py
│       ├── execute.py
│       ├── memory.py
│       ├── plan.py
│       ├── report.py
│       ├── run_tests.py
│       ├── tests.py
│       ├── validate.py
│       ├── verify.py
│       └── write_files.py
└── deep_research_impl/     # ReAct loop subpackage
    ├── budget.py
    ├── constants.py
    ├── graph.py
    ├── routes.py
    ├── state.py
    └── nodes/
        ├── decompose.py
        ├── search.py
        └── synthesize.py

workflows/autoresearch_impl/  # 7-node experiment loop subpackage
├── __init__.py
├── graph.py
├── routes.py
├── state.py
└── nodes/
    ├── setup.py
    ├── propose.py
    ├── modify.py
    ├── run_experiment.py
    ├── evaluate.py
    ├── decide.py
    └── log.py
```

---

## 📚 Workflow Catalog

The agent currently exposes **6 workflows**, triggerable via `run_workflow()` or the `workflow()` meta-tool.

### 1. 🔍 Research — [workflows/RESEARCH.md](workflows/RESEARCH.md)

**Status:** v1.1 — Split into `workflows/research_impl/` subpackage (v1.0). Trim node wired in (v1.1).

**Purpose:** Quick information gathering and synthesis. Single search → parallel scrape → one-shot synthesis.

**Flow:** recall → search → parallel_scrape → synthesize → trim → report → store → distill → notify

**Key characteristics:**
- **Single-query** — One SearXNG search, top results scraped in parallel (uses `cfg.web_max_search_results`, default 10)
- **Browser fallback** — JS-heavy pages retried with `browser(navigate+text_content)`
- **TDD not used** — No test-driven development; pure information synthesis
- **Fast** — 1-2 minutes for simple queries
- **Trim node (v1.1)** — Evicts oversized `search_results` to episodic memory after synthesize
- **v1.0 fixes** — 8 bugs fixed (agent action, as_completed timeout, 800-char truncation, zombie futures, etc.)

**Safety:** SSRF protection, citation tracking, prune_tool_dict truncation.

**Output:**
```json
{
  "status": "success",
  "result": "ChromaDB best practices include...",
  "error": "",
  "artifacts": ["report.html"]
}
```

---

### 2. 🔬 Deep Research — [workflows/DEEP_RESEARCH.md](workflows/DEEP_RESEARCH.md)

**Status:** v1.1 — Split into `workflows/deep_research_impl/` subpackage. `WORKFLOW_METADATA` + citations wired in (v1.1). All P0 bugs fixed (v1.0.1-v1.1).

**Purpose:** Iterative, multi-faceted research for complex questions. ReAct-style loop with self-evaluation.

**Flow:** recall → decompose → search → synthesize → [route: loop or exit] → report → notify → store → distill

**Key characteristics:**
- **ReAct loop** — Cycles through decompose → search → synthesize until convergence or max iterations
- **Budget-aware** — Hard caps on API calls (Tavily) and browser actions (tracked separately)
- **Three-tier tools** — `tavily` → `web` → `browser` fallback chain
- **Convergence detection** — SequenceMatcher similarity exits when knowledge stops changing (threshold: 0.85)
- **Self-evaluation** — Completeness scoring (0-100) per iteration
- **v1.0.1-v1.1 fixes** — All P0 bugs fixed: `action="dispatch"` added, API budget on Tavily attempt only, `task`/`context` swap fixed, 800-char truncation removed, citations wired into report+notify

**Safety:** Nested-call guard, URL deduplication, knowledge capping at 6K chars.

**Output:**
```json
{
  "status": "success",
  "result": "Quantum computing error correction has seen...",
  "error": "",
  "artifacts": ["report.html"]
}
```

---

### 3. 📊 Data — [workflows/DATA.md](workflows/DATA.md)

**Status:** v1.0 — 5-node LangGraph pipeline, split into `workflows/data_impl/` subpackage (per-node modules + `WORKFLOW_METADATA`).

**Purpose:** Python-based data analysis, calculations, and dataset generation.

**Flow:** recall → execute → critique → store → notify (execute has a conditional edge: failure → END)

**Key characteristics:**
- **Code execution** — Real Python via `python(mode="run_data")`
- **Optional generation** — If no code provided, `agent(action="dispatch", role="code")` generates it from the goal
- **Critique layer** — `agent(action="dispatch", role="critique")` evaluates output quality (best-effort, logged on failure)
- **Dual memory** — Stores episodic (result) + procedural (working code). Procedural storage is gated on `code_generated` so user-provided code is not stored.
- **v1.0 fixes applied:** partial-dict node returns; code-gen & execution failures now set `exec_error` (route to END, not critique); `context=` for critique text; exception isolation on memory/notify/agent; observable code-extraction fallbacks; dead `route_after_critique` removed.

**Safety:** Sandboxed execution; best-effort critique and non-fatal memory/notify (never flip a successful analysis to failed).

**Output:**
```json
{
  "status": "success",
  "result": "Analysis complete: Top 5 months are Jan, Mar, Dec, Jun, Sep",
  "error": "",
  "artifacts": []
}
```

---

### 4. 🤖 Autocode — [workflows/AUTOCODE.md](workflows/AUTOCODE.md)

**Status:** v1.0 — Already split into `workflows/autocode_impl/` subpackage with 17 per-node modules.

**Purpose:** Autonomous code generation with TDD, git scoping, and architectural safety.

**Flow:** classify → validate → brainstorm → plan → branch → tests → execute → write_files → analyze_impact → run_tests → [debug → retry] → verify → report → commit → distill

**Key characteristics:**
- **TDD on disk** — Real pytest subprocess; exit codes are ground truth
- **Surgical patching** — `str_replace` patches preferred over full rewrites
- **Git scoping** — Workspace-scoped branches and commits
- **Protected files** — Blocks writes to `server.py`, `core/*`, `registry.py`
- **Self-correcting** — Debug → retry with temperature jitter
- **17 nodes** — Most complex workflow in the agent
- **Critical bug:** `.bak` files created (violates user rule)
- **Critical bug:** `git(action="snapshot")` doesn't exist (removed in un-multiplex refactor)
- **Critical bug:** `files_map` never populated — `analyze_impact` never runs
- **Critical bug:** `node_analyze_impact` is async in sync graph — may fail or hang
- **Critical bug:** `node_brainstorm` loses KG files (stores original instead of merged)

**Safety:** Protected files, git snapshot/rollback, AST validation, retry limits, hallucination guard.

**Output:**
```json
{
  "status": "success",
  "result": "Code changes applied successfully: Added retry logic to web search",
  "error": "",
  "artifacts": ["web.py", "test_web.py"],
  "commit_sha": "abc123",
  "test_passed": true,
  "lint_passed": true
}
```

---

### 5. 🧠 Understand — [workflows/UNDERSTAND.md](workflows/UNDERSTAND.md)

**Status:** v1.0 — 4-node LangGraph StateGraph with sync nodes, checkpoint/resume support, trace_id propagation.

**Purpose:** Build and maintain a deterministic Codebase Knowledge Graph for Python projects.

**Flow:** init_project → discover_files → parse_and_store → report

**Key characteristics:**
- **AST-based parsing** — Extracts imports via Python AST (not regex)
- **Incremental indexing** — Chunked MD5 + mtime comparison; only changed files re-parsed
- **Physical isolation** — Separate artifact directories for agent root vs workspace
- **Batch processing** — Files parsed in configurable batches (UNDERSTAND_BATCH_SIZE, default 10)
- **Sync nodes** — All nodes are `def` (sync), routed through base.py's standard `graph.invoke()`
- **GraphStore lifecycle** — Connections properly opened and closed in each node
- **Trace correlation** — trace_id propagated through state to all nodes
- **Checkpoint/resume** — Supported via base.py's standard graph.invoke() path

**Safety:** Size rejection, file size limits, skip directories.

**Output:**
```json
{
  "status": "success",
  "result": "Project analysis complete: 42 files, 156 dependencies",
  "error": "",
  "artifacts": ["report.html"]
}
```

---

### 6. 🔬 Autoresearch — [workflows/AUTORESEARCH.md](workflows/AUTORESEARCH.md)

**Status:** v1.0 — 7-node LangGraph StateGraph with an infinite experiment loop. Evolutionary (try many, keep best) — distinct from autocode (convergent: solve one task).

**Purpose:** Autonomous experiment-driven optimization. Repeatedly modify a target file (e.g. `train.py`), run it as a time-boxed subprocess, extract a metric, and either commit (if improved) or roll back (if worse). The loop runs indefinitely until a human interrupts it.

Inspired by [karpathy/autoresearch](https://github.com/karpathy/autoresearch).

**Flow:** setup → propose → modify → run_experiment → evaluate → log → decide → propose (loop)

**Key characteristics:**
- **Evolutionary, not convergent** — Many experiments, one branch, `results.tsv` ledger of outcomes. No "done" state.
- **Indefinite loop** — `decide → propose` is an unconditional back-edge. Exits only on human interrupt or LangGraph's `recursion_limit` (dispatcher sets 1000 — ~166 experiments per invocation).
- **Metric-driven** — Every iteration judged by a single numeric metric extracted from experiment output (`{metric_name}: <float>`, last occurrence).
- **Git-based keep/discard** — Improvements committed; failures `git reset --hard HEAD` + `git clean -fd`. Git is the safety net.
- **Results ledger** — Every experiment (keep OR discard) appended to `results.tsv` — operators `tail -f` while the loop runs.
- **Atomic writes** — `node_modify` uses `tempfile.mkstemp` + `os.fsync` + `os.replace`; target file never half-written.
- **Time-boxed experiments** — `subprocess.run(timeout=time_budget)` (default 300s).
- **Reuses autocode infrastructure** — `node_propose` calls `autocode_impl.helpers._call()` for retry + cancellation; uses `core.json_extract.extract_json()` for proposal parsing.

**Safety:** Atomic writes, git-based rollback, time-boxed subprocesses, output truncation (50KB), `re.escape(metric_name)`, list-arg `subprocess.run` (no `shell=True`).

**Output:**
```json
{
  "status": "success",
  "result": "",
  "error": "",
  "artifacts": ["results.tsv"],
  "trace_id": "autoresearch_001",
  "workflow": "autoresearch",
  "experiment_count": 142,
  "baseline_metric": 0.450,
  "current_best": 0.418,
  "experiment_history": [...]
}
```

---

## 🔄 Workflow Comparison

| Aspect | Research | Deep Research | Data | Autocode | Understand | Autoresearch |
|--------|----------|---------------|------|----------|------------|--------------|
| **Status** | v1.1 | v1.1 | v1.1 | v1.0 | v1.0 | v1.0 |
| **Structure** | 9-node pipeline (v1.1: +trim) | 8-node cyclic ReAct | 6-node pipeline (v1.1: +trim) | 17-node state machine | 4-node LangGraph pipeline | 7-node infinite loop |
| **Primary tools** | `web`, `browser` | `tavily`, `web`, `browser` | `python_exec`, `agent` | `agent`, `python_exec`, `git` | `python` (AST), `GraphStore` | `subprocess`, `git` |
| **LLM roles** | `research` | `planner`, `research`, `executor` | `code`, `critique` | `router`, `planner`, `executor`, `test` | N/A | `planner` |
| **Loop type** | Linear | Cyclic (decompose→search→synthesize) | Linear | Cyclic (debug→retry) | Linear | Infinite (propose→…→decide→propose) |
| **TDD** | ❌ No | ❌ No | ❌ No | ✅ Yes (real pytest) | ❌ No | ❌ No |
| **Git ops** | ❌ No | ❌ No | ❌ No | ✅ Yes (branch, commit) | ❌ No | ✅ Yes (branch, commit, reset) |
| **Memory** | Recall + store | Recall + store | Recall + store | Recall + store + distill | N/A | ❌ No (results.tsv is the ledger) |
| **Budget tracking** | ❌ No | ✅ Yes (API calls, browser actions) | ❌ No | ✅ Yes (retries) | ❌ No | ✅ Yes (time_budget per experiment) |
| **Convergence** | ❌ No | ✅ Yes (cosine similarity) | ❌ No | ❌ No | ❌ No | ❌ No (human stops the loop) |
| **Exit condition** | Done | Convergence / max iter | Done | Tests pass | Done | Human interrupt / recursion_limit |
| **Use case** | Quick facts | Complex research | Data analysis | Code generation | Codebase indexing | Metric optimization |
| **Typical duration** | 1-2 min | 3-10 min | 30s-2 min | 2-10 min | 1-5 min | Indefinite (overnight+) |
| **Critical bugs** | 0 (v1.0 fixed all P0s) | 0 (fixed v1.0.1-v1.1) | 0 (v1.0 fixed all P0s) | 11 P0 | 3 P0 | 0 (v1.0) |

---

## 📋 Unified Return Schema

All workflows return the same dict shape from `run_workflow()`. The `trace_id` is propagated through the state and present in the final result.

**Success:**
```json
{
  "status": "success",
  "result": "Final result summary...",
  "error": "",
  "artifacts": ["report.html", "fix.patch"],
  "trace_id": "abc123"
}
```

**Failure:**
```json
{
  "status": "failed",
  "result": "",
  "error": "Workflow 'research' crashed: KeyError: ...",
  "artifacts": [],
  "trace_id": "abc123"
}
```

**Guaranteed keys:** `status`, `result`, `error`, `artifacts`, `trace_id`.

**Workflow-specific extra keys** (when applicable):
- `commit_sha` — Autocode only
- `test_passed` / `lint_passed` — Autocode only
- `experiment_count` / `baseline_metric` / `current_best` / `experiment_history` — Autoresearch only

---

## 🚀 Triggering & Integration

### 1. Via Python (Primary Entry Point)
```python
from workflows.base import run_workflow

result = run_workflow(
    workflow_type="research",      # "research" | "data" | "autocode" | "deep_research" | "understand" | "autoresearch"
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

## 🧪 Testing Quick Reference

| Workflow | Test Command |
|----------|-------------|
| Base | `.\venv\Scripts\python tests/workflows/base/ -W error --tb=short -v` |
| Research | `.\venv\Scripts\python tests/workflows/research/ -W error --tb=short -v` |
| Deep Research | `.\venv\Scripts\python tests/workflows/deep_research/ -W error --tb=short -v` |
| Data | `.\venv\Scripts\python tests/workflows/data/ -W error --tb=short -v` |
| Autocode | `.\venv\Scripts\python tests/workflows/autocode/ -W error --tb=short -v` |
| Understand | `.\venv\Scripts\python tests/workflows/understand/ -W error --tb=short -v` |
| Autoresearch | `python -m pytest tests/workflows/autoresearch/ -W error --tb=short -v` |

---

## 🧩 Chunking in Workflows

Text chunking via [chonkie](https://github.com/chonkie-ai/chonkie) is integrated in **one workflow utility** (`trim_state()`) with **2 additional roadmap integration points**. See `docs/TOOLS.md` § "Chunking (chonkie)" for the tool-layer analysis.

### Current: `trim_state()` in `workflows/base.py` (v1.3)

`trim_state()` evicts oversized state fields (`search_results`, `output`, `analysis`) to episodic memory when they exceed ~1000 tokens. v1.3 makes this **chonkie-aware**:

| Path | When | Behavior |
|------|------|----------|
| **Chonkie** (v1.3) | chonkie installed + chunking produces >1 chunk | Split text into sentence-aware chunks → evict each individually (precise recall later) → keep first chunk as preview in state |
| **Fallback** (v1.0) | chonkie missing, chunking fails, or single chunk | Whole-string eviction → generic placeholder (no preview) |

**Why the preview matters:** The LLM sees `[Evicted: 2500 tokens across 6 chunks saved to episodic memory. Preview: "The search returned..." Use memory(recall, tags_filter="evicted") to retrieve specific chunks.]` instead of a blind placeholder. It has enough context to decide whether to recall.

**Chunk position encoding:** Each evicted chunk's `source` field encodes its position (`evicted:output:chunk_2_of_5`) so the LLM can identify which chunk to recall. The `source` field is used (not `source_doc_id` metadata) because the eviction flusher unpacks metadata as kwargs to `memory.store()`, which doesn't accept `source_doc_id`.

**⚠️ Current status:** `trim_state()` is a **utility** — no workflow calls it yet. It's ready for when workflows wire it into their graphs (see `base/CHANGELOG.md` #18). The chonkie improvement is "ready for use," not "in use."

### Roadmap: TencentDB symbol offloading for state (P2/P3 future)

**[Roadmap]** The `trim_state()` function currently uses chonkie-aware eviction (v1.3). A more sophisticated approach inspired by [TencentDB Agent Memory](https://github.com/TencentCloud/TencentDB-Agent-Memory) would offload verbose state fields to per-run files and replace them with compact Mermaid symbol graphs in state. Nodes that need full data drill down via file path. This would complement the existing chonkie approach — chonkie for within-field compression, Mermaid symbols for cross-field context management.

### Roadmap: understand workflow (P2)

When the understand workflow is extended to index `.md`/`.txt`/`.rst` docs (currently code-only), `core/kgraph/embeddings.py` should use chonkie `SentenceChunker` for prose files. Tree-sitter (currently used for code) can't parse prose. This is **conditional** on file-type support landing first — see `understand/CHANGELOG.md` #6.

### Roadmap: autocode #37 (P3 future)

If autocode is refactored to accumulate debug-loop history (current `debug.py` is stateless per iteration — each debug call sees only current test output), chonkie could compress the history to fit the LLM context. This is a **long-term future** item — depends on autocode first being refactored to accumulate history. See `autocode/CHANGELOG.md`.

---

*Architecture: shared WorkflowState + node helpers + dispatcher → 6 distinct workflows → memory bookend pattern (except autoresearch, which uses results.tsv) → checkpoint resumption → exception isolation → best-effort side effects.*

---

## 🆕 How to Add a New Workflow

When adding a **new workflow** to the MCP Agent Stack, update **all** of the following. Missing any one of them causes drift between the source code, the docs, and the LLM's tool schema. This checklist mirrors `docs/TOOLS.md` § "New Tool Checklist" but is adapted for the workflow pattern (facade + `_impl/` subpackage + dispatcher integration).

### Step-by-step checklist

| # | File | What to do |
|---|------|------------|
| 1 | `workflows/{name}.py` | Create the **thin facade**. Re-export `build_{name}_graph` + `WORKFLOW_METADATA` from `workflows/{name}_impl/graph.py`. No business logic. Match the pattern in `workflows/autoresearch.py` (10 lines). |
| 2 | `workflows/{name}_impl/__init__.py` | Empty package init. One-line docstring is fine. |
| 3 | `workflows/{name}_impl/state.py` | Define `{Name}State(WorkflowState, total=False)` TypedDict. Extend `WorkflowState` for shared dispatcher fields. Add workflow-specific fields. Include a `_default_state(...)` factory that pulls sane defaults from `cfg`. Match `autoresearch_impl/state.py`. |
| 4 | `workflows/{name}_impl/nodes/` | Create **one file per node**, one responsibility each. Each `node_xxx(state) -> dict` returns a PARTIAL state dict (LangGraph pattern — only changed keys). Lazy-import tools inside node functions (avoid circular imports). Match `autoresearch_impl/nodes/` (7 files for 7 nodes). |
| 5 | `workflows/{name}_impl/routes.py` | Create routing functions for conditional edges. Each `route_after_xxx(state) -> str` returns the next node name. Keep routing logic simple — complex decisions belong in a node, not a router. Match `autoresearch_impl/routes.py` (2 routers). |
| 6 | `workflows/{name}_impl/graph.py` | Create `build_{name}_graph()` — instantiate `StateGraph({Name}State)`, `add_node(...)` for each node, wire edges + conditional edges, `set_entry_point(...)`, return `g.compile()`. Also define `WORKFLOW_METADATA` dict (mirror autocode's schema: `name`, `version`, `description`, `entry_point`, `nodes`, `edges`, `loops`, `branches`, `safety_features`). Match `autoresearch_impl/graph.py`. |
| 7 | `tools/workflow.py` | Add `"{name}"` to `VALID_WORKFLOWS` frozenset + `WorkflowType` Literal. Add a one-line description to the `workflow()` docstring. Add any workflow-specific kwargs to the `workflow()` signature (forward them to `run_workflow()`). |
| 8 | `workflows/base.py` | Add `elif wf_type == "{name}":` dispatch case in `run_workflow()`. Initialize state via `_default_state()`, merge caller-supplied kwargs, invoke the graph. If the workflow has an infinite loop (like autoresearch), pass `config={"recursion_limit": N}` to `.invoke()`. Update the module docstring + `WorkflowState.workflow` comment to list the new workflow. Update the unknown-type error message to include `"{name}"`. |
| 9 | `core/config.py` | Add config knobs for any workflow-specific env vars (e.g. `autoresearch_time_budget`). Use `os.getenv("WORKFLOW_NAME_KNOB", "default")`. |
| 10 | `tests/workflows/{name}/` | Create `__init__.py` + `conftest.py` (fixtures) + `test_graph.py` (topology + metadata + facade re-exports) + per-concern test files (one concern per file). Mock LLM calls + subprocess + git; never make live network calls. Match `tests/workflows/autoresearch/` (22 tests). Also update `tests/workflows/base/test_dispatcher.py` to assert the unknown-type error message includes `"{name}"`. |
| 11 | `docs/workflows/{NAME}.md` | Landing page (5-file standard: landing page + 4 subfiles). Follow `AUTORESEARCH.md` format: Overview, Key characteristics, Quick Start, Configuration, When-to-Use table, Subfile Directory table. Keep concise — match the workflow's complexity (autoresearch is simpler than autocode → smaller doc). |
| 12 | `docs/workflows/{name}/` | 4 subfiles following the 5-file standard: `CHANGELOG.md` (Version History, Breaking Changes, Completed, In Progress / Next Up, Deferred / Out of Scope), `ARCHITECTURE.md` (Source Code Reference table, Module Tree, Mermaid diagram, Key Design Decisions, Testing section), `API.md` (Facade signature, State Fields table, Per-Node Reference, Routes, Security, Error Handling), `INSTRUCTIONS.md` (NEVER DO, ALWAYS DO, Anti-Patterns). Use `[v1.0]` markers throughout. |
| 13 | `docs/WORKFLOWS.md` | (a) Add row to the summary Document/Workflow/Key Topics table at the top; (b) add `{name}.py` + `{name}_impl/` block to the Module Map; (c) bump the "N workflows" count in the Workflow Catalog intro; (d) add `### N. {Name}` detailed entry to the Workflow Catalog; (e) add column to the Workflow Comparison table; (f) add workflow-specific extra keys to the Unified Return Schema section; (g) add row to the Testing Quick Reference table; (h) update the footer line ("N distinct workflows"). |
| 14 | `docs/system_prompts/system_prompt.md` | Add the new workflow to the `workflow` tool capabilities line + the `## HARD RULES` Workflow patterns rule. The LLM needs to know the workflow exists + when to use it. |
| 15 | `docs/TOOLS.md` | Bump the workflow count in `### 15. 🔄 Workflow` (e.g. "6 workflow types" → "7 workflow types") + the summary table row that mentions the count. |

### Order of operations (recommended)

1. Write `workflows/{name}_impl/` first (state → routes → nodes → graph). The subpackage must be importable on its own before the facade touches it.
2. Write `workflows/{name}.py` facade (depends on the subpackage).
3. Run `python -c "from workflows.{name} import build_{name}_graph, WORKFLOW_METADATA"` to verify imports + graph compilation.
4. Update `tools/workflow.py` + `workflows/base.py` + `core/config.py` (dispatcher integration).
5. Run `python -c "from workflows.base import run_workflow; run_workflow('{name}', goal='test', trace_id='smoke')"` to verify dispatch (use a tiny goal; expect early failure or short run).
6. Write tests in `tests/workflows/{name}/`. Run `python -m pytest tests/workflows/{name}/ -W error --tb=short -v`.
7. Update `tests/workflows/base/test_dispatcher.py` (unknown-type error assertion).
8. Write `docs/workflows/{NAME}.md` landing page + `docs/workflows/{name}/` 4 subfiles.
9. Update `docs/WORKFLOWS.md` (catalog + comparison + test reference + count).
10. Update `docs/system_prompts/system_prompt.md` (LLM tool list).
11. Update `docs/TOOLS.md` (workflow count).
12. Run `compileall` + `pytest` before committing.
13. Restart LM Studio (cached tool schemas require full restart to refresh).

### Common mistakes

- **Forgetting `__init__.py` in `nodes/`** — nodes silently not importable; `build_{name}_graph()` raises `ImportError`.
- **Mutating state in-place** — LangGraph does NOT deep-copy. `state["list"].append(x)` corrupts shared state. Always `list(state.get("list", [])) + [x]` then return `{"list": new_list}`.
- **Importing tools at module top** — circular imports. `tools.git` may transitively import `workflows.*` via the registry. Lazy-import inside the node function.
- **Forgetting to bump the workflow count** in `docs/WORKFLOWS.md` + `docs/TOOLS.md` — doc drift.
- **Writing the facade before the subpackage** — `ImportError` on first run.
- **Forgetting `WORKFLOW_METADATA`** — MCP clients can't introspect the workflow. Always define it, even for a simple workflow.
- **Setting `recursion_limit` too low for loop workflows** — LangGraph's default is 25. An infinite-loop workflow (like autoresearch) needs `recursion_limit >= 1000` or it raises `GraphRecursionError` after ~4 iterations.
- **Not restarting LM Studio after schema changes** — LLM sees stale workflow list.
- **Adding a workflow that doesn't extend `WorkflowState`** — the dispatcher's `run_workflow()` expects shared fields (`workflow`, `trace_id`, `status`, `error`, `result`, `artifacts`). Extend `WorkflowState` to inherit them.
- **Forgetting to update the unknown-type error message in `workflows/base.py`** — the dispatcher's `"Unknown workflow type '{wf_type}'. Use: research | data | autocode | ..."` string must list the new workflow or operators get misleading error messages.

---

## 🔗 Cross-References

- **Tools:** See `docs/TOOLS.md`
- **Core:** See `docs/CORE.md`
- **Skills:** See `docs/SKILLS.md`
- **Environment:** See `.env.example` in repo root
