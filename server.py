"""
server.py -- MCP Agent entrypoint.

stdout = MCP stdio protocol channel. NOTHING may print to stdout.
All diagnostics go to stderr or the log file.
"""

from __future__ import annotations

import io
import sys
from pathlib import Path


def _fix_streams() -> None:
    """
    1. Force UTF-8 on both streams (Windows cp1252 crashes on non-ASCII).
    2. Replace stdout with a stderr-backed stream so any accidental
       print() calls during boot go to stderr instead of corrupting
       the MCP JSON-RPC protocol channel.
    """
    # Fix encoding first
    for name in ("stdout", "stderr"):
        stream = getattr(sys, name)
        if hasattr(stream, "buffer") and (
            stream.encoding is None or stream.encoding.lower() != "utf-8"
        ):
            setattr(sys, name,
                    io.TextIOWrapper(stream.buffer, encoding="utf-8",
                                     errors="replace", line_buffering=True))

    # Redirect stdout -> stderr during boot so nothing corrupts the channel.
    # FastMCP.run() will reclaim stdout for the stdio transport.
    # We save the real stdout so FastMCP can restore it.
    sys._real_stdout = sys.stdout       # type: ignore[attr-defined]
    sys.stdout = sys.stderr             # boot-time stdout -> stderr


_fix_streams()

# -- Bootstrap sys.path -------------------------------------------------------
_AGENT_ROOT = Path(__file__).resolve().parent
if str(_AGENT_ROOT) not in sys.path:
    sys.path.insert(0, str(_AGENT_ROOT))

# -- Core imports -------------------------------------------------------------
from core.config import cfg
from core.tracer import tracer

cfg.ensure_dirs()

# -- MCP framework ------------------------------------------------------------
from mcp.server.fastmcp import FastMCP
from registry import register_all_tools

# -- Build the server (stdout still redirected to stderr here) ----------------
try:
    mcp = FastMCP("agent")
    _tool_count = register_all_tools(mcp)
    logger.info("MCP tools registered: %d", _tool_count)
    if _tool_count > 20:
        logger.warning("High tool count (%d) -- watch for LM Studio grammar issues", _tool_count)

    # -- Boot log (all goes to stderr via the redirect above) --------------------
    _boot_tid = tracer.new_trace("startup", goal="server boot")
    tracer.step(_boot_tid, "boot", "MCP Agent ready",
        tools=_tool_count,
        planner=cfg.planner_model,
        executor=cfg.executor_model,
        router=cfg.router_model)
    _W = 56
    print(" ", file=sys.stderr)
    print("= " * _W, file=sys.stderr)
    print("  MCP Agent Stack -- Ready ".center(_W), file=sys.stderr)
    print("= " * _W, file=sys.stderr)
    print(f"  Tools     : {_tool_count} ", file=sys.stderr)
    print(f"  Planner   : {cfg.planner_model} ", file=sys.stderr)
    print(f"  Executor  : {cfg.executor_model} ", file=sys.stderr)
    print(f"  Router    : {cfg.router_model} ", file=sys.stderr)
    print(f"  Workspace : {cfg.workspace_root} ", file=sys.stderr)
    print(f"  Memory    : {cfg.memory_chroma_path} ", file=sys.stderr)
    print(f"  Env       : {cfg.env} ", file=sys.stderr)
    print("= " * _W, file=sys.stderr)
    print(" ", file=sys.stderr)
    tracer.finish(_boot_tid, success=True, result=f"{_tool_count} tools registered")
finally:
    # -- Restore real stdout and hand it to FastMCP's stdio transport -------------
    sys.stdout = sys._real_stdout           # type: ignore[attr-defined]

# -- Cleanup old VRAM artifacts ------------------------------------------------
def _cleanup_artifacts() -> None:
    """Delete .artifacts/ files older than 7 days on startup."""
    try:
        from core.memory_backend.pruner import cleanup_old_artifacts
        cleanup_old_artifacts(max_age_days=7)
        print("[server] Cleaned up old .artifacts/", file=sys.stderr)
    except Exception as e:
        print(f"[server] Artifact cleanup skipped: {e}", file=sys.stderr)

import threading as _threading
_threading.Thread(target=_cleanup_artifacts, daemon=True).start()

# -- Flush Memory Telemetry in background ------------------------------------
def _flush_telemetry_loop() -> None:
    """Flush memory recall telemetry to ChromaDB every 60 seconds."""
    import time as _time
    try:
        from core.memory_backend.telemetry import tracker
        from core.memory import memory as _mem
        while True:
            _time.sleep(60)
            try:
                flushed = tracker.flush(_mem.store)
                if flushed > 0:
                    print(f"[server] Flushed {flushed} memory telemetry updates", file=sys.stderr)
            except Exception as e:
                print(f"[server] Telemetry flush error: {e}", file=sys.stderr)
    except Exception as e:
        print(f"[server] Telemetry loop skipped: {e}", file=sys.stderr)

_threading.Thread(target=_flush_telemetry_loop, daemon=True).start()

# -- Graceful Shutdown: Flush telemetry on exit --------------------------------
import atexit as _atexit
def _shutdown_flush() -> None:
    """Force final telemetry flush before process dies."""
    try:
        from core.memory_backend.telemetry import tracker
        from core.memory import memory as _mem
        flushed = tracker.flush(_mem.store)
        if flushed > 0:
            print(f"[server] Final telemetry flush: {flushed} updates", file=sys.stderr)
    except Exception as e:
        print(f"[server] Shutdown flush skipped: {e}", file=sys.stderr)
_atexit.register(_shutdown_flush)

# -- Warm up ChromaDB in background (avoids cold-start MCP timeout) -----------
def _warmup_chromadb() -> None:
    """Load ChromaDB embedding model before first tool call."""
    try:
        from core.memory import memory as _mem
        # Tiny no-op query to trigger embedding model load
        _mem.recall("warmup", top_k=1, min_score=0.0)
        print("[server] ChromaDB warmup complete", file=sys.stderr)
    except Exception as e:
        print(f"[server] ChromaDB warmup skipped: {e}", file=sys.stderr)

import threading as _threading
_threading.Thread(target=_warmup_chromadb, daemon=True).start()


# -- Warm up LLM models in background (avoids cold-start latency per role) -----
def _warmup_models() -> None:
    """Send a 1-token ping to each role to warm up model weights."""
    try:
        from core.llm import llm
        from core.config import cfg
        import time

        if getattr(cfg, "disable_model_warmup", False):
            print("[server] Model warmup disabled via DISABLE_MODEL_WARMUP", file=sys.stderr)
            return

        roles = llm.list_roles()
        warmed = 0
        failed = 0
        for role_info in roles:
            role = role_info["role"]
            try:
                resp = llm.complete(
                    role=role,
                    system="You are a helpful assistant.",
                    user="ping",
                    max_tokens=1,
                    timeout=30,
                )
                if resp.ok:
                    warmed += 1
                else:
                    failed += 1
                    print(f"[server] Warmup failed for {role}: {resp.error[:100]}", file=sys.stderr)
            except Exception as e:
                failed += 1
                print(f"[server] Warmup error for {role}: {type(e).__name__}: {str(e)[:100]}", file=sys.stderr)
            time.sleep(0.5)  # Stagger to avoid rate limits
        print(f"[server] Model warmup: {warmed}/{len(roles)} roles ready ({failed} failed)", file=sys.stderr)
    except Exception as e:
        print(f"[server] Model warmup skipped: {type(e).__name__}: {e}", file=sys.stderr)

_threading.Thread(target=_warmup_models, daemon=True).start()



# -- Start Meta-Learning Daemon ----------------------------------------------
def _start_meta_learner() -> None:
    try:
        from core.memory_backend.meta_learning import learner
        _threading.Thread(target=learner.run_forever, daemon=True).start()
        print("[server] Meta-Learner daemon started", file=sys.stderr)
    except Exception as e:
        print(f"[server] Meta-Learner failed to start: {e}", file=sys.stderr)

_start_meta_learner()

# -- Start Eviction Flusher ----------------------------------------------------
def _start_eviction_flusher() -> None:
    try:
        from core.memory_backend.eviction import flusher_loop
        _threading.Thread(target=flusher_loop, daemon=True).start()
        print("[server] Eviction Flusher started", file=sys.stderr)
    except Exception as e:
        print(f"[server] Eviction Flusher failed: {e}", file=sys.stderr)

_start_eviction_flusher()

# -- Scan for Incomplete Workflows ---------------------------------------------
def _scan_incomplete_workflows() -> None:
    """Log any workflows that crashed mid-execution."""
    try:
        from workflows.helpers.checkpoint import scan_incomplete
        incomplete = scan_incomplete()
        if incomplete:
            print(f"[server] Found {len(incomplete)} incomplete workflows: {incomplete}", file=sys.stderr)
            print("[server] Use workflow(resume=True, trace_id=...) to resume.", file=sys.stderr)
    except Exception as e:
        print(f"[server] Workflow scan skipped: {e}", file=sys.stderr)

_scan_incomplete_workflows()

# -- Start Memory Diversity Enforcer -----------------------------------------
def _start_diversity_enforcer() -> None:
    """Run memory diversity maintenance when idle."""
    import time as _time
    try:
        from core.memory_backend.maintenance import execute_diversity_maintenance
        from core.memory import memory as _mem
        from core.runtime.activity_tracker import tracker
        
        last_run = 0.0
        while True:
            _time.sleep(1800) # Check every 30 mins
            try:
                # 7 day cooldown
                if (_time.time() - last_run) < (7 * 86400):
                    continue
                    
                # Check idle (4 hours)
                if not tracker.try_acquire_background_slot(min_idle_seconds=14400):
                    continue
                    
                try:
                    print("[server] Running Memory Diversity Enforcement...", file=sys.stderr)
                    result = execute_diversity_maintenance(_mem.store)
                    print(f"[server] Diversity Maintenance: {result.get('metrics', {})}", file=sys.stderr)
                    last_run = _time.time()
                finally:
                    tracker.release_background_slot()
            except Exception as e:
                print(f"[server] Diversity maintenance error: {e}", file=sys.stderr)
    except Exception as e:
        print(f"[server] Diversity enforcer skipped: {e}", file=sys.stderr)

_threading.Thread(target=_start_diversity_enforcer, daemon=True).start()

# -- Start Runtime Watchdog ----------------------------------------------------
def _start_watchdog() -> None:
    try:
        from core.runtime.watchdog import watchdog
        _threading.Thread(target=watchdog.run_forever, daemon=True).start()
        print("[server] Runtime Watchdog started", file=sys.stderr)
    except Exception as e:
        print(f"[server] Watchdog failed to start: {e}", file=sys.stderr)

_start_watchdog()

# -- Run (hands stdout to FastMCP's stdio transport) ----------------------------
if __name__ == "__main__":
    mcp.run()

