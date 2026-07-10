<- Back to [Observability Overview](OBSERVABILITY.md)

# 🧭 AI Editing Rules

This document defines the rules an AI agent (or human editor) MUST follow when modifying the `core/observability/` subsystem. The goal is to preserve the v1.3 facade pattern, prevent regression of MCP stdio safety, and keep the checkpoint journal crash-safe.

---

## 🚫 NEVER DO

1. **NEVER import `tracer` from `core.observability.tracer_engine` in consumer code.** Always use the facade: `from core.tracer import tracer`. The facade exists so 71+ callsites don't need to change. The only consumers of `core.observability.tracer_engine` are: (a) `core/tracer.py` (the facade itself), (b) `core/observability/reader.py` (which needs the same singleton), and (c) `tests/core/tracer/test_tracer.py` for low-level `_TraceStore` / `generate_trace_id` access.

2. **NEVER write to `sys.stdout` from any observability module.** MCP stdio transport uses stdout as the protocol channel — any non-JSON-RPC bytes corrupt the connection. All console output goes to `sys.stderr`. Use `print(..., file=sys.stderr)` or structlog (which is configured for stderr).

3. **NEVER remove the `atexit.register(_writer.close)` call in `tracer_engine.py`.** Without it, the last batch of JSONL log entries may be lost on process exit (file not flushed/closed).

4. **NEVER swallow `KeyboardInterrupt` or `SystemExit` in `_FileWriter.write()`.** The current code re-raises these after catching `Exception`. If you "simplify" the except clause to just `except Exception`, you'll silently break Ctrl+C and shutdown.

5. **NEVER remove `f.flush()` + `os.fsync(f.fileno())` from `save_checkpoint()`.** Without fsync, the OS may buffer the write indefinitely; a crash leaves a truncated/partial JSONL line that breaks `json.loads()` on resume.

6. **NEVER change the kwargs-spread ordering in `Tracer.new_trace()` / `step()` / `error()` / `warning()` / `finish()`.** The `**kwargs` is spread FIRST so hardcoded keys (`trace_id`, `event`, `node`, `message`, `ts`, etc.) cannot be overwritten by caller-supplied kwargs. Reversing the order reintroduces the "event=task_not_found corrupts the event field" bug.

7. **NEVER remove `additionalProperties: False` from any JSON schema.** (This applies to schemas defined elsewhere but enforced via observability-tracked LLM calls — see `docs/core/llm/SCHEMAS.md`.)

8. **NEVER change `_TraceStore.MAX_TRACES` to a very large number.** The 200-trace bound is a memory-safety cap for long-running agents. If you need to retain more traces, add disk-based archival, not unbounded memory.

9. **NEVER remove the 14-day scan limit in `reader._scan_disk()`.** Without it, a busy agent with months of JSONL logs would cause `read_trace()` to do massive I/O on every call.

10. **NEVER remove the zombie detection in `get_latest()`.** Without it, a stuck workflow would be resumed forever, never making progress. The two heuristics (`resume_count >= MAX_RESUMES` and consecutive same-node failures) catch both "resumed too many times" and "stuck retrying the same node".

11. **NEVER delete a checkpoint journal from `save_checkpoint()` or `get_latest()`.** Only `mark_complete()` deletes journals. Deleting elsewhere breaks the audit trail and prevents post-mortem debugging.

12. **NEVER change `sanitize_state()` to raise on unserializable objects.** It MUST return `None` for unknown types — that's the whole point. Raising would crash the checkpoint write and lose the workflow state.

13. **NEVER add a `print()` without `file=sys.stderr`** anywhere in `core/observability/`. Same rule as #2 — applies to debug prints too.

14. **NEVER remove the facade re-exports.** `core/tracer.py` must continue to re-export `tracer`, `Tracer`, `_TraceStore`, `generate_trace_id`, `_writer` (and the other module-level names) so existing tests and callers don't break.

---

## ✅ ALWAYS DO

1. **ALWAYS import `tracer` via the facade** — `from core.tracer import tracer`. This is the canonical import path used by 71+ files.

2. **ALWAYS import reader, metrics, and checkpoint directly from `core.observability.*`** — these modules do NOT have facades. Use `from core.observability.reader import read_trace`, `from core.observability.metrics import track_node`, `from core.observability.checkpoint import save_checkpoint`, etc.

3. **ALWAYS use `tracer.step(trace_id, node, message, **kwargs)`** for trace-scoped operations. The first arg is the trace ID, second is the node name, third is the human message. Extra context goes in kwargs.

4. **ALWAYS call `tracer.finish(trace_id, success=...)` at the end of every workflow.** Unfinished traces clutter the in-memory store and produce misleading "running" status in `GET /traces`.

5. **ALWAYS use `node_step()` / `node_error()` / `node_done()` from `workflows/base.py`** rather than calling `tracer.step()` + `save_checkpoint()` manually. The helpers handle the trace logging AND checkpoint saving atomically.

6. **ALWAYS pass `trace_id` to `save_checkpoint()`** — it's the journal filename. Empty trace_id is a silent no-op (intentional — defensive against bad callers).

7. **ALWAYS call `mark_complete(trace_id)` on workflow success.** Without it, the journal accumulates indefinitely and `scan_incomplete()` reports false positives at the next server boot.

8. **ALWAYS validate `_checkpoint_version` after `get_latest()`** — `workflows/base.py` shows the pattern: if `restored.get("_checkpoint_version", 0) != 1`, start fresh rather than loading incompatible state.

9. **ALWAYS guard Prometheus `track_*` calls behind the import** — they're already no-ops if `prometheus_client` is missing, so no try/except needed. But don't introduce new module-level Prometheus instruments without checking `_PROM_AVAILABLE` first.

10. **ALWAYS use `logger.warning(...)` for non-fatal checkpoint I/O errors** — `save_checkpoint()` and `get_latest()` already do this. Don't upgrade to `logger.error()` — a checkpoint failure shouldn't be treated as a workflow failure.

11. **ALWAYS update this INSTRUCTIONS.md when adding a new module to `core/observability/`** — add a row to the Source Code Reference table in [ARCHITECTURE.md](ARCHITECTURE.md), add API entries to [API.md](API.md), and add a v1.x entry to [CHANGELOG.md](CHANGELOG.md).

12. **ALWAYS test patch paths after modifying the facade** — if you change what `core/tracer.py` re-exports, verify that `tests/core/tracer/test_tracer.py` still passes (or update its patch paths per the v1.0 breaking change note in CHANGELOG.md).

---

## ⚠️ Anti-Patterns

### Anti-Pattern 1: Direct engine import in consumer code
```python
# ❌ BAD — breaks the facade pattern
from core.observability.tracer_engine import tracer

# ✅ GOOD — use the facade
from core.tracer import tracer
```
**Why:** The facade exists for import stability. If you import from `tracer_engine` directly, you couple your code to the internal module path, defeating the purpose of the v1.3 extraction.

### Anti-Pattern 2: Manual tracer + checkpoint calls
```python
# ❌ BAD — bypasses the helpers, easy to forget checkpoint
tracer.step(tid, "execute", "running code")
from core.observability.checkpoint import save_checkpoint
save_checkpoint(tid, "execute", state)

# ✅ GOOD — use the workflow helper
from workflows.base import node_step
node_step(state, "execute", "running code", checkpoint=True)
```
**Why:** `node_step` handles both trace logging AND checkpoint saving atomically. It also respects the `checkpoint=False` default for steps that don't need persistence.

### Anti-Pattern 3: Silent failure in _FileWriter
```python
# ❌ BAD — swallows shutdown signals
def write(self, record):
    try:
        ...
    except Exception:
        pass  # also catches KeyboardInterrupt!

# ✅ GOOD — re-raises shutdown signals
def write(self, record):
    try:
        ...
    except (KeyboardInterrupt, SystemExit):
        raise
    except Exception:
        pass
```
**Why:** Ctrl+C and shutdown hooks need to propagate. Silent swallowing makes the agent unkillable.

### Anti-Pattern 4: Unbounded in-memory trace store
```python
# ❌ BAD — memory leak in long-running agents
class _TraceStore:
    MAX_TRACES = 10_000_000  # effectively unbounded

# ✅ GOOD — bounded with FIFO eviction
class _TraceStore:
    MAX_TRACES = 200  # current value
```
**Why:** Long-running agents would otherwise accumulate traces forever. The 200 cap with FIFO eviction is a deliberate memory-safety tradeoff — old traces fall out of memory but remain on disk for `read_trace()` slow-path lookup.

### Anti-Pattern 5: Checking `is None` instead of `not trace_id` in save_checkpoint
```python
# ❌ BAD — empty string still creates a file at "checkpoints/.jsonl"
def save_checkpoint(trace_id, node_name, state):
    if trace_id is None:
        return

# ✅ GOOD — falsy check covers None AND empty string
def save_checkpoint(trace_id, node_name, state):
    if not trace_id:
        return
```
**Why:** `trace_id` could be `""` (empty string) if a caller forgot to set it. The falsy check is defensive.

---

*Last updated: 2026-07-10. See [ARCHITECTURE.md](ARCHITECTURE.md) for module layout, [API.md](API.md) for function signatures, [CHANGELOG.md](CHANGELOG.md) for version history.*
