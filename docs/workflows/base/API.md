<- Back to [Base Overview](../BASE.md)

# 📝 API Reference

## 🔧 Workflow State

```python
class WorkflowState(TypedDict, total=False):
    # Identity
    workflow: str      # "research" | "data" | "autocode" | "deep_research" | "understand"
    goal: str          # What we are trying to accomplish
    trace_id: str      # Tracer ID for this run

    # Inputs (workflow-specific)
    code: str          # Initial code for data workflow
    target_file: str   # File to edit (autocode)
    mode: str          # Autocode mode: fix_error | improve | add_feature
    error_msg: str     # Error traceback (autocode fix_error)
    feature_desc: str  # Feature description (autocode add_feature)

    # Accumulated context
    memory_context: str   # Recalled memories (formatted string)
    file_content: str       # Current file content (autocode)
    search_results: str     # Web search results
    analysis: str           # Agent(analyze) output
    patch: str               # Generated patch (autocode)
    review: dict             # Agent(review) structured output

    # Execution
    output: str              # Python execution output
    exec_error: str          # Execution error if any

    # Control
    retries: int             # Current retry count
    error: str               # Fatal workflow error
    status: str              # "running" | "success" | "failed"

    # Result
    result: str              # Final result summary
    artifacts: list          # Files created, commits made, etc.
```

| Field | Type | Description |
|-------|------|-------------|
| `workflow` | `str` | Workflow type identifier |
| `goal` | `str` | Primary task description |
| `trace_id` | `str` | Observability trace ID |
| `code` | `str` | Python code for data workflow |
| `target_file` | `str` | Target file path for autocode |
| `mode` | `str` | Autocode mode override |
| `error_msg` | `str` | Error traceback for autocode fix mode |
| `feature_desc` | `str` | Feature description for autocode feature mode |
| `memory_context` | `str` | Formatted memory recall results |
| `file_content` | `str` | Current file content (autocode) |
| `search_results` | `str` | Web search or scraped content |
| `analysis` | `str` | LLM analysis output |
| `patch` | `str` | Generated code patch |
| `review` | `dict` | Structured review output |
| `output` | `str` | Python execution stdout |
| `exec_error` | `str` | Python execution stderr |
| `retries` | `int` | Retry counter (autocode, deep_research) |
| `error` | `str` | Fatal error message |
| `status` | `str` | `"running"` → `"success"` / `"failed"` |
| `result` | `str` | Final human-readable result |
| `artifacts` | `list` | Created files, commits, reports, etc. |

> **Note:** This is a shared schema. Individual workflows (e.g., `autocode`) extend it with additional fields. The `total=False` flag makes all fields optional, allowing partial updates.

---

## ⚡ Utilities

### `trim_state(state)` — Phase 5 Memory Eviction

Evicts oversized fields from working memory to the async eviction queue:

```python
def trim_state(state: WorkflowState) -> WorkflowState:
    # Returns a NEW state dict (Copy-on-Write)
    # Evicts: search_results, output, analysis
    # Threshold: len(val) // 4 > 1000 tokens (~4000 chars)
    # Replaced with: "[Evicted: N tokens saved to episodic memory. Use memory tool to recall.]"
```

**Why:** Prevents LangGraph checkpoint bloat. Large search results or Python outputs can make checkpoints unwieldy.

**Thread safety:** Uses `eviction_queue.push()` which is async-safe.

---

### `node_step(state, node, message, checkpoint=False, **kwargs)` — Trace Logging

Logs a workflow step to the active trace:

```python
node_step(state, "execute", "running code", chars=len(code))
# → tracer.step(trace_id, "execute", "running code", chars=len(code))
```

**Checkpoint option:** If `checkpoint=True`, also saves a checkpoint via `save_checkpoint()`.

---

### `node_error(state, node, message, **kwargs)` — Error Handling

Marks state as failed and logs to trace:

```python
node_error(state, "execute", "Code generation failed: timeout")
# → Returns: {"status": "failed", "error": "Code generation failed: timeout"}
# → tracer.error(trace_id, "execute", "Code generation failed: timeout")
# → save_checkpoint(trace_id, "execute", {"status": "failed", "error": "..."})
```

**Guard:** Message is never empty. Falls back to `"Unspecified error in node 'execute'"`.

**Returns:** Partial dict with `status` and `error`.

**Note:** Saves a **partial** checkpoint (`{"status": "failed", "error": ...}`), not the full state. Resume from an error checkpoint will lose all workflow context. This is a known limitation.

---

### `node_done(state, result, artifacts=None)` — Completion

Marks state as succeeded:

```python
node_done(state, result="Analysis complete", artifacts=["report.html"])
# → Returns: {"status": "success", "result": "Analysis complete", "artifacts": ["report.html"]}
# → tracer.finish(trace_id, success=True, result="Analysis complete")
# → mark_complete(trace_id)
```

**Returns:** Partial dict with `status`, `result`, `artifacts`.

---

## 🔄 Workflow Dispatcher

### `run_workflow(workflow_type, goal, trace_id, resume, **kwargs)`

Routes to the correct workflow graph:

| Workflow Type | Graph Builder | Special Handling |
|---------------|--------------|------------------|
| `research` | `workflows.research.build_research_graph()` | Standard StateGraph |
| `data` | `workflows.data.build_data_graph()` | Standard StateGraph |
| `autocode` | `workflows.autocode.build_graph()` | Converts `goal` → `task` |
| `deep_research` | `workflows.deep_research_impl.build_deep_research_graph()` | Standard StateGraph |
| `understand` | `workflows.understand.run_understand_workflow_sync()` | Direct function call (not StateGraph) |

**Returns:** `dict` with at minimum `{status, result, error, artifacts}`.

**Error handling:**
- Unknown workflow type → `"failed"` with clear error message
- Workflow crash → `"failed"` with exception details, trace logged
- Checkpoint version mismatch → warning, starts fresh

---

## 📤 Output

The dispatcher returns a `dict`:

```json
{
  "status": "success",
  "result": "Analysis complete: Top 3 months are Jan, Mar, Dec",
  "error": "",
  "artifacts": ["report.html"]
}
```

**Failure:**
```json
{
  "status": "failed",
  "result": "",
  "error": "Workflow 'unknown' crashed: ValueError: Invalid workflow type",
  "artifacts": []
}
```

---

## 🔒 Security

*(Fill this section with relevant info from edits and refactors. Add security details as they are learned.)*

---

## 📝 Error Handling

*(Fill this section with relevant info from edits and refactors. Add error classification as it is learned.)*

---

*Last updated: 2026-07-04. See [ARCHITECTURE.md](ARCHITECTURE.md) for file maps and design decisions, [CHANGELOG.md](CHANGELOG.md) for version history, [INSTRUCTIONS.md](INSTRUCTIONS.md) for AI editing rules.*
