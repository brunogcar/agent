<- Back to [Tracer Overview](../TRACER.md)

# 🛡️ AI Tracer Instructions

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

## ✅ ALWAYS DO

11. **Always use `**kwargs` in `step()`/`error()`** for new log fields. They're automatically merged into the JSONL record.
12. **Always check the date on every write** — `_FileWriter` rotates daily. Do not cache the file handle across midnight boundaries.
13. **Always keep trace IDs short (8 chars)** — long UUIDs bloat JSONL logs and make terminal output hard to read.
14. **Always use `tracer.warning()` for non-trace-scoped logging** — reserve `tracer.step()` for trace-scoped operations with real trace IDs.
15. **Always patch pytest to `D:\mcp\agent\venv\Scripts\pytest.exe`** — per project workflow.
16. **Always include `-W error` and `--tb=short` in pytest commands** — clean output, catch warnings.
17. **Always update this doc** when adding trace methods, changing output formats, or modifying log rotation.

## 🚫 Anti-Patterns & Lessons Learned

*(No entries yet. Add lessons here as they are learned from future refactors and bug fixes. When an AI assistant encounters a bug, fix, or architectural insight during editing, add it here with:*

> - **What happened:** The symptom or bug
> - **Why it matters:** The impact
> - **Fix:** The solution or pattern to follow

*Fill this section with relevant information during edits and refactors.)*

---

*Last updated: 2026-07-04. See [ARCHITECTURE.md](ARCHITECTURE.md) for file maps, [API.md](API.md) for method details, [CHANGELOG.md](CHANGELOG.md) for version history.*
