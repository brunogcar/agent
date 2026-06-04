
# 🔴 VRAM Context Pruning Middleware

The VRAM Context Pruner (`core/context_pruner.py`) is a deterministic, tool-aware middleware layer that intercepts massive tool outputs **before** they are appended to the LangGraph state. It prevents context window overflow, attention dilution, and VRAM OOM crashes on 16GB hardware.

## 🎯 Why This Exists

When the agent uses the `web` tool to scrape a page, or the `python_exec` tool to run a script that generates a massive `pandas` dataframe or a 5,000-line `pytest` traceback, the raw text output can easily exceed 50,000 characters. Appending this directly to the LangGraph state causes:

1. **Context Window Overflow** — Crashes the LLM or triggers massive swap lag.
2. **Attention Dilution** — The Planner gets lost in HTML boilerplate and misses the actual error message.
3. **VRAM OOM** — The next LLM call fails because the KV cache cannot fit the bloated context.

## 🏗️ Architecture Overview

### The Interception Boundary

The pruner lives in a **shared helper module** (`core/context_pruner.py`) that is called directly by heavy tools (`web.py`, `python_exec.py`, `cli.py`) right before they return.

```
Tool Logic
    ↓
[core/context_pruner.py] ← Interception Point
    ├── 1. Size Check (<8,000 chars? → return as-is)
    ├── 2. Structural Clean (strip HTML for web)
    ├── 3. Artifact Preservation (save full output to disk)
    ├── 4. Tool-Aware Truncation (head+tail or tail-only)
    └── 5. Metadata Injection (_pruned, _artifact_path, _recovery_hint)
    ↓
LangGraph State (safe, bounded context)
```

**Why not the MCP dispatcher?** Because LangGraph workflows import tools directly (e.g., `from tools.web import web`). If the pruner lived in `server.py`, autonomous workflows would bypass it and still crash.

### The 5-Step Pipeline

| Step | Action | Purpose |
|------|--------|---------|
| **1. Size Check** | If `len(text) <= 8000`, return unchanged. | Zero overhead for small outputs. |
| **2. Structural Clean** | For `web`: strip HTML tags via regex. | Removes 80% of web bloat instantly. |
| **3. Artifact Preservation** | Save full raw text to `.artifacts/{trace_id}_{tool}_{uuid}.txt`. | Full fidelity is never lost; agent can recover via `file` tool. |
| **4. Tool-Aware Truncation** | `python_exec`/`cli`: keep LAST 8k chars. `web`: keep first 4k + last 4k. | Preserves critical content (errors at end of tracebacks, titles at start of HTML). |
| **5. Metadata Injection** | Add `_pruned: true`, `_artifact_path`, `_recovery_hint` to the return dict. | Tells the LLM exactly what happened and how to recover missing details. |

## 📦 Artifact Lifecycle

### Storage Location
```
.artifacts/
    ├── abc123_web_1a2b3c.txt    # Full scraped HTML
    ├── def456_python_exec_4d5e6f.txt  # Full pandas output
    └── ghi789_cli_7g8h9i.txt     # Full CLI stdout
```

### Automatic Cleanup
A background thread in `server.py` startup runs `cleanup_old_artifacts()` to delete files older than 7 days. This prevents silent disk bloat.

### Recovery Pattern
When the LLM sees `_pruned: true`:
```python
# Tool result includes:
{
  "status": "success",
  "output": "... [truncated content] ...",
  "_pruned": true,
  "_artifact_path": ".artifacts/abc123_web_1a2b3c.txt",
  "_recovery_hint": "Use file(path='.artifacts/abc123_web_1a2b3c.txt') to read full output."
}

# LLM should then:
file(action="read", path=".artifacts/abc123_web_1a2b3c.txt")
```

## ⚙️ Configuration

| Setting | Default | Description |
|---------|---------|-------------|
| `MAX_CHARS` | 8000 | Hard character limit for truncated outputs (~2,000-2,500 tokens). |
| `MAX_ARTIFACT_BYTES` | 10MB | Skip saving artifacts larger than this to prevent disk bloat. |
| Cleanup TTL | 7 days | Artifacts older than this are auto-deleted on server startup. |

## 🛡️ Security & Safety

### Atomic Writes
Artifacts are written to a `.tmp` file first, then atomically renamed. This prevents the Planner from reading a half-written file if the server crashes mid-write.

### Path Sanitization
Filenames are generated using `uuid4().hex[:6]`—no user input is ever used in artifact paths. This prevents path traversal attacks.

### Fail-Open Design
If artifact saving fails (disk full, permissions), the pruner still returns the truncated content. The tool call does not fail; the agent just loses the recovery option.

## 🚨 AI Agent Instructions

If you are an AI assistant modifying `core/memory_backend/pruner.py` or the heavy tools:

1. **Never remove artifact preservation.** The full output must always be saved to disk before truncation.
2. **Never bypass tool-aware truncation.** Different tools have different critical-content locations (errors at end of tracebacks, titles at start of HTML).
3. **Never move the pruner to the MCP dispatcher.** LangGraph workflows import tools directly and would bypass it.
4. **Never increase `MAX_CHARS` without VRAM analysis.** 8,000 chars is calibrated for 16GB hardware with Qwen 9B + Granite MoE loaded.
5. **Always preserve structured metadata.** The `_pruned`, `_artifact_path`, and `_recovery_hint` keys are how the LLM knows to recover missing data.

## 🔮 Future Enhancements

- **Keyword-Aware Extraction**: For `python_exec`, detect `Traceback`/`Exception` keywords and preserve ±1,000 chars around matches.
- **DataFrame Schema Compression**: For pandas outputs, convert to `{shape, dtypes, head(), tail(), null_summary}` instead of raw truncation.
- **Async Artifact Writes**: Use `asyncio.to_thread()` to make artifact saving non-blocking for ultra-low-latency tools.
