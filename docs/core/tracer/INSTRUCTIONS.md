<- Back to [Tracer Overview](../TRACER.md)

# 🛡️ AI Tracer Instructions

> **📍 Implementation location (v1.3+):** The Tracer implementation lives in `core/observability/tracer_engine.py`; `core/tracer.py` is a thin facade. For the full observability subsystem editing rules, see [../observability/INSTRUCTIONS.md](../observability/INSTRUCTIONS.md).

## ❌ NEVER DO

1. **NEVER write to stdout** — any `print()` without `file=sys.stderr` will break the MCP connection. Always use `tracer.step()`, `tracer.error()`, or `print(..., file=sys.stderr)`.
2. **Never remove the structlog fallback** — never remove the `try/except ImportError` block for `structlog`. Graceful degradation is critical for environment resilience.
3. **Never remove the `_lock`** from `_FileWriter` or `_TraceStore` — concurrent workflow executions will corrupt the JSONL file or cause race conditions.
4. **Never increase `MAX_TRACES` significantly above 200** — the agent may run for days; unbounded trace storage causes OOM.
5. **Never "fix" silent I/O errors** — `_FileWriter` intentionally ignores non-fatal disk errors. A logging failure should never crash the agent.
6. **Never catch `KeyboardInterrupt` or `SystemExit` in `_FileWriter`** — the agent must shut down cleanly on Ctrl+C.
7. **Never hardcode log paths** — log directory is always `cfg.log_path`. Never hardcode `"logs/"` in the tracer.
8. **Never create `.bak` files** — forbidden by project rules.
9. **Never rewrite the entire file** — surgical edits only. Preserve existing code exactly.
10. **Never skip `compileall` before `pytest`** — catches syntax errors early.
11. **NEVER use a literal string or empty string as `trace_id` in `tracer.step/error/warning/finish`.** Always use the return value of `tracer.new_trace()`. A literal string like `tracer.step("health", ...)` (or `tracer.step("", "node", ...)`) causes trace collisions in the in-memory `_TraceStore` and makes JSONL log queries ambiguous. The signature is `step(trace_id, node, message="")`, so a 2-arg call silently shifts your args left: your "message" becomes `node`, `message` defaults to `""`, and `trace_id` is your literal. *(v1.1 fixed 10 callers that did this.)*

## ✅ ALWAYS DO

11. **Always use `**kwargs` in `step()`/`error()`** for new log fields. They're automatically merged into the JSONL record.
12. **Always check the date on every write** — `_FileWriter` rotates daily. Do not cache the file handle across midnight boundaries.
13. **Always keep trace IDs short (8 chars)** — long UUIDs bloat JSONL logs and make terminal output hard to read.
14. **Always call `tracer.new_trace()` first and pass the returned `trace_id`** to `step()`/`error()`/`warning()`/`finish()`. `tracer.warning()` takes the SAME signature as `step()` — `warning(trace_id, node, message="", **kwargs)` — it is NOT a trace-free escape hatch. For trace-scoped warnings, create the trace first.
15. **Always patch pytest to `D:\mcp\agent\venv\Scripts\pytest.exe`** — per project workflow.
16. **Always include `-W error` and `--tb=short` in pytest commands** — clean output, catch warnings.
17. **Always update this doc** when adding trace methods, changing output formats, or modifying log rotation.

## 🚫 Anti-Patterns & Lessons Learned

### v1.1 — Literal string as `trace_id`
> - **What happened:** 10 callers used `tracer.step("health", ...)`, `tracer.step("", "node", ...)`, `tracer.error("janitor", ...)`, or `tracer.warning("kg_cleanup", f"...")`. Because `step`/`error`/`warning` share the signature `(trace_id, node, message="", **kwargs)`, these calls set `trace_id` to a literal/empty string, causing multiple logical operations to collide under one trace ID in the in-memory `_TraceStore` and producing ambiguous JSONL log queries.
> - **Why it matters:** `read_trace("health")` returned a merged timeline of unrelated health checks; the in-memory store's FIFO eviction dropped real traces prematurely; JSONL queries by `trace_id` were unreliable.
> - **Fix:** Always call `tracer.new_trace(workflow, goal)` first and pass the returned 12-char hex ID. For loops, create ONE trace before the loop and reuse it (not one per iteration). For one-shot operations, create the trace at the top of the function.

*(Add further lessons here as they are learned from future refactors and bug fixes.)*

---

*Last updated: 2026-07-18. See [ARCHITECTURE.md](ARCHITECTURE.md) for file maps, [API.md](API.md) for method details, [CHANGELOG.md](CHANGELOG.md) for version history. For the full observability subsystem editing rules, see [../observability/INSTRUCTIONS.md](../observability/INSTRUCTIONS.md).*
