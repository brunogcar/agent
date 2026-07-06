<- Back to [Data Overview](../DATA.md)

# 📝 API Reference

> v1.0: All nodes live in `workflows/data_impl/nodes/` and return **partial update dicts** (only changed keys). Import nodes from `workflows.data_impl.nodes.<node>`; import `build_data_graph` / `WORKFLOW_METADATA` from the thin facade `workflows.data`.

## ⚡ Nodes

### `node_recall(state) -> dict` — Phase 1: Memory Recall

**Purpose:** Recall relevant past analyses from memory.

**Logic:**
```python
results = memory.recall(query=goal, top_k=3, trace_id=tid)
```

**Output:** `{"memory_context": ctx}` (partial dict).

**Error handling:** [Fix #8] `memory.recall` is wrapped in `try/except`. On failure, logs to the trace and returns `{"memory_context": ""}` — the workflow proceeds without context. Non-fatal.

---

### `node_execute(state) -> dict` — Phase 2: Code Generation + Execution

**Purpose:** Generate Python code from the goal (if none provided) and execute it.

**Logic:**
1. If `state["code"]` is empty → call `agent(action="dispatch", role="code", task=..., context=memory_context)` to generate code.
2. Extract code via `_extract_code_from_response(parsed, text, trace_id)` — `parsed["patch"]` → ```python``` fence → raw text (each fallback logged).
3. Execute via `python(mode="run_data", code=code)`.
4. Return output, or set `exec_error` on failure.

**Output (success):** `{"output": ..., "exec_error": "", "code": ..., "code_generated": bool}` (partial dict).

**Output (failure):** `{**node_error(state, "execute", msg), "exec_error": msg, "output": ""}` — [Fix #2] sets `exec_error` so `route_after_execute` routes to END (both code-gen and execution failures).

**`code_generated` flag:** [Fix #5] `True` when the code was LLM-generated, `False` when user-provided. Read by `node_store` to gate procedural-memory storage.

**Error handling:**
- Code-gen failure (agent returns non-success) → `exec_error` set, routes to END.
- Execution failure (python returns non-success) → `node_error()` (trace + checkpoint) + `exec_error` set. [Fix #3]
- Unexpected exception from `agent()`/`python()` → caught, converted to `exec_error`. [Fix #8]

---

### `route_after_execute(state) -> str` — Conditional Router

**Purpose:** Route to critique on success, END on failure.

**Logic:**
```python
if state.get("exec_error"):
    return "failed"   # → END
return "critique"      # → node_critique
```

> [Fix #10] `route_after_critique` was removed — it always returned `"store"` (dead code). `critique` → `store` is now a direct edge.

---

### `node_critique(state) -> dict` — Phase 3: Review + Critique

**Purpose:** Evaluate whether the execution output adequately answers the goal.

**Logic:**
```python
agent(action="dispatch", role="critique", task=..., context=f"Code output:\n{output[:1000]}", trace_id=tid)
```

> [Fix #4] Uses `context=` (text channel), not `content=` (base64 image channel).

**Output (success):** `{"result": f"OUTPUT:\n{output}\n\nANALYSIS:\n{r['text']}"}` (partial dict).
**Output (empty output):** `{}` — [Fix #6] logged via `node_step` (was silent).
**Output (critique failure):** `{"result": output}` — [Fix #7] logged via `tracer.error` (was silent fallback).

---

### `node_store(state) -> dict` — Phase 4: Memory Storage

**Purpose:** Store the analysis result in memory.

**Logic:**
1. `memory.store_episodic(text=..., importance=6, goal=..., outcome="success", tools_used="python,agent,memory", trace_id=...)`
2. `memory.store_procedural(text=..., importance=6, tags="data,python,working-code", trace_id=...)` — **only if `state["code_generated"]` is truthy.** [Fix #5]

**Output:** `{}` (side effects only).

**Error handling:** [Fix #8] Both `store_*` calls are wrapped in `try/except` + `tracer.error`. Storage is best-effort — a memory failure does not crash the workflow.

---

### `node_notify(state) -> dict` — Phase 5: User Notification

**Purpose:** Notify the user and mark the workflow done.

**Logic:**
```python
notify(action="send", title="Data analysis complete", message=f"{goal[:50]}: {result[:80]}")
return node_done(state, result=result or "Data analysis complete")
```

**Output:** `node_done(...)` → `{"status": "success", "result": ..., "artifacts": []}`.

**Error handling:** [Fix #10] `notify()` is wrapped in `try/except` + `tracer.error`. A notification failure does not prevent `node_done` from marking the workflow successful — the analysis itself already succeeded.

---

## 📤 Output

The workflow returns a `dict`:

```json
{
  "status": "success",
  "result": "OUTPUT:\n6\n\nANALYSIS:\nThe output correctly answers the goal.",
  "error": "",
  "artifacts": []
}
```

**Failure (routes to END from `execute`):**
```json
{
  "status": "failed",
  "error": "Execution failed: SyntaxError: invalid syntax",
  "exec_error": "SyntaxError: invalid syntax",
  "output": ""
}
```

---

## 🔒 Security

- Code execution is sandboxed via `python(mode="run_data")` — see `tools/python.py` for the import/escape allow-lists.
- No network I/O in this workflow (unlike `research`); `core/net` retry/SSRF helpers are not applicable here.

---

## 📝 Error Handling

| Failure | Node | Behavior |
|---------|------|----------|
| Memory recall fails | `node_recall` | Logged; proceeds with empty context (non-fatal) |
| Code generation fails | `node_execute` | `exec_error` set → routes to END |
| Code generation raises | `node_execute` | Caught → `exec_error` → END |
| Execution fails | `node_execute` | `node_error()` + `exec_error` → END |
| Execution raises | `node_execute` | Caught → `exec_error` → END |
| Critique fails | `node_critique` | `tracer.error`; falls back to raw output |
| Critique raises | `node_critique` | `tracer.error`; falls back to raw output |
| Memory store fails | `node_store` | `tracer.error`; returns `{}` (non-fatal) |
| Notify fails | `node_notify` | `tracer.error`; still returns `node_done` (non-fatal) |

---

*Last updated: 2026-07-06 (v1.0 split). See [ARCHITECTURE.md](ARCHITECTURE.md) for file maps and design decisions, [CHANGELOG.md](CHANGELOG.md) for version history.*
