<- Back to [Data Overview](../DATA.md)

# 📝 API Reference

## ⚡ Nodes

### `node_recall(state)` — Phase 1: Memory Recall

**Purpose:** Recall relevant past analyses from memory.

**Logic:**
```python
memory.recall(
    query=goal,
    limit=5,
    trace_id=state["trace_id"],
)
```

**Output:** Partial dict with `memory_context`.

**Error handling:** If memory recall fails, returns `{"memory_context": ""}` (empty string). The workflow proceeds without context.

---

### `node_execute(state)` — Phase 2: Code Generation + Execution

**Purpose:** Generate Python code from the goal and execute it.

**Logic:**
1. Build prompt with goal, memory context, and initial code (if provided)
2. Call `agent(role="code", task=...)` to generate code
3. Extract code from markdown fences using regex
4. Execute code via `python(code=...)`
5. Return output or error

**Output:** Partial dict with `output`, `exec_error`, `code`.

**Error handling:**
- Code generation fails → `node_error(state, "execute", ...)` → workflow ends
- Execution fails → `exec_error` set, output is empty string
- Code extraction fails → `node_error(state, "execute", ...)` → workflow ends

**Regex for code extraction:**
```python
match = re.search(r"```python\n(.*?)\`\`\`", text, re.DOTALL)
```

> **Note:** The regex uses `\`\`\`` which is a malformed escape sequence in raw strings. This emits a `SyntaxWarning` in modern Python. Should be `
\`\`\`` or use non-raw string.

---

### `route_after_execute(state)` — Conditional Router

**Purpose:** Route to critique or END based on execution result.

**Logic:**
```python
if state.get("exec_error"):
    return "failed"  # → END
return "critique"    # → node_critique
```

**Output:** String literal `"failed"` or `"critique"`.

---

### `node_critique(state)` — Phase 3: Review + Critique

**Purpose:** Review the execution output and provide feedback.

**Logic:**
1. Call `agent(role="critique", task=...)` with the output
2. Return the critique text

**Output:** Partial dict with `result` (critique text).

**Guard:** If `output` is empty, returns empty state (no critique). This is a silent skip — no trace step explains why.

---

### `node_store(state)` — Phase 4: Memory Storage

**Purpose:** Store the analysis result in memory.

**Logic:**
1. Store semantic memory: `memory.store_semantic(text=result, ...)`
2. Store procedural memory: `memory.store_procedural(text=code, ...)` (only if code was generated and execution succeeded)

**Output:** Empty dict (side effects only).

**Note:** Procedural memory is stored for ALL successful executions, including user-provided code. The doc says "only if code was generated" but the code doesn't distinguish.

---

### `node_notify(state)` — Phase 5: User Notification

**Purpose:** Notify the user of completion.

**Logic:**
1. Call `notify(action="notify", message=...)` with the result
2. Return `node_done(state, result=...)`

**Output:** `node_done` result dict.

---

## 📤 Output

The workflow returns a `dict`:

```json
{
  "status": "success",
  "result": "Analysis complete: Top 5 months are Jan, Mar, Dec, Jun, Sep",
  "error": "",
  "artifacts": []
}
```

**Failure:**
```json
{
  "status": "failed",
  "result": "",
  "error": "Code generation failed: timeout",
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
