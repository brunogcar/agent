<- Back to [Base Overview](../BASE.md)

# 📝 API Reference

## 🔧 Workflow State

```python
class WorkflowState(TypedDict, total=False):
    # Identity
    workflow: str      # "research" | "data" | "autocode" | "deep_research" | "understand"
    goal: str          # What we are trying to accomplish
    trace_id: str      # Tracer ID for this run
    task: str          # [v1.2] Autocode task (same as goal; autocode uses task internally)

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
    analysis: str           # agent(analyze) output
    patch: str               # Generated patch (autocode)
    review: dict             # agent(review) structured output

    # Execution
    output: str              # Python execution output
    exec_error: str          # Execution error if any

    # Control
    retries: int             # Retry counter (autocode, deep_research)
    error: str               # Fatal error message
    status: str              # "running" | "success" | "failed"

    # Result
    result: str              # Final result summary
    artifacts: list          # Files created, commits made, etc.
```

> **Note:** This is a shared schema. Individual workflows (e.g., `autocode`) extend it with additional fields. The `total=False` flag makes all fields optional, allowing partial updates.

---

## ⚡ Utilities

### `trim_state(state)` — Phase 5 Memory Eviction

Evicts oversized fields from working memory to the async eviction queue:

```python
def trim_state(state: WorkflowState) -> WorkflowState:
    # Returns a NEW state dict (Copy-on-Write)
    # Evicts: search_results, output, analysis
    # Threshold: len(val) // 4 > 1000 tokens (~4005 chars)
    # Replaced with: "[Evicted: N tokens saved to episodic memory. Use memory tool to recall.]"
```

**Why:** Prevents LangGraph checkpoint bloat.

---

### `node_step(state, node, message, checkpoint=False, **kwargs)` — Trace Logging

**HELPER** (not a LangGraph node). Logs a workflow step to the active trace. Returns `None`.

```python
node_step(state, "execute", "running code", chars=len(code))
# → tracer.step(trace_id, "execute", "running code", chars=len(code))
```

**Checkpoint option:** If `checkpoint=True`, saves the full state via `save_checkpoint()`.

---

### `node_error(state, node, message, **kwargs)` — Error Handling

**HELPER** (not a LangGraph node). Marks state as failed and logs to trace.

```python
node_error(state, "execute", "Code generation failed: timeout")
# → Returns: {"status": "failed", "error": "Code generation failed: timeout"}
# → tracer.error(trace_id, "execute", "Code generation failed: timeout")
# → save_checkpoint(trace_id, "execute", {**state, "status": "failed", "error": "..."})
```

**Guard:** Message is never empty. Falls back to `"Unspecified error in node 'execute'"`.

**[v1.2] Full state checkpoint:** Saves the complete workflow state (not just `{status, error}`), so resume from an error checkpoint has full context.

**Returns:** Partial dict with `status` and `error`.

---

### `node_done(state, result, artifacts=None)` — Completion

**HELPER** (not a LangGraph node). Marks state as succeeded.

```python
node_done(state, result="Analysis complete", artifacts=["report.html"])
# → save_checkpoint(trace_id, "done", {**state, "status": "success", "result": "..."})
# → tracer.finish(trace_id, success=True, result="Analysis complete")
# → mark_complete(trace_id)
```

**[v1.2] Success checkpoint:** Saves a checkpoint before `mark_complete()` so the final state is preserved if the process dies between them.

**Returns:** Partial dict with `status`, `result`, `artifacts`.

---

## 🔄 Workflow Dispatcher

### `run_workflow(workflow_type, goal, trace_id, resume, **kwargs)`

Routes to the correct workflow graph:

| Workflow Type | Graph Builder | Special Handling |
|---------------|--------------|------------------|
| `research` | `workflows.research.build_research_graph()` | Standard StateGraph |
| `data` | `workflows.data.build_data_graph()` | Standard StateGraph |
| `autocode` | `workflows.autocode_impl.graph.invoke_with_timeout()` | Converts `goal` → `task`; timeout wrapper |
| `deep_research` | `workflows.deep_research_impl.build_deep_research_graph()` | Standard StateGraph |
| `understand` | `workflows.understand.build_understand_graph()` | Uses `_default_state()` + standard `graph.invoke()` |

**Returns:** `dict` with at minimum `{status, result, error, artifacts}`.

**Error handling:**
- Unknown workflow type → `"failed"` with clear error message listing all 5 valid types
- Workflow crash → checkpoint saved, then `"failed"` with exception details
- Checkpoint version mismatch → warning, starts fresh
- Resume → preserves checkpoint's original goal (v1.2)

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
  "error": "Workflow 'research' crashed: RuntimeError: Connection refused",
  "artifacts": []
}
```

---

*Last updated: 2026-07-06 (v1.2). See [ARCHITECTURE.md](ARCHITECTURE.md) for file maps and design decisions, [CHANGELOG.md](CHANGELOG.md) for version history, [INSTRUCTIONS.md](INSTRUCTIONS.md) for AI editing rules.*
