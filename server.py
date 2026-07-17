"""server.py -- MCP Agent entrypoint.

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
    sys._real_stdout = sys.stdout  # type: ignore[attr-defined]
    sys.stdout = sys.stderr  # boot-time stdout -> stderr

_fix_streams()

# -- Bootstrap sys.path -------------------------------------------------------
_AGENT_ROOT = Path(__file__).resolve().parent
if str(_AGENT_ROOT) not in sys.path:
    sys.path.insert(0, str(_AGENT_ROOT))

# -- Core imports -------------------------------------------------------------
from core.config import cfg
from core.tracer import tracer

cfg.ensure_dirs()

# [P1 FIX] Validate config on MCP boot (same as gateway does in factory.py)
# Catches missing env vars, invalid paths, and model misconfigurations
# before any tools or workflows try to use them.
try:
    from core.config_validation import validate_config
    validate_config()
    print("[server] Config validation passed", file=sys.stderr)
except ImportError:
    # config_validation module may not exist yet in older checkouts
    print("[server] WARNING: config_validation not found, skipping", file=sys.stderr)
except Exception as e:
    print(f"[server] WARNING: Config validation failed: {e}", file=sys.stderr)

# -- MCP framework ------------------------------------------------------------
from mcp.server.fastmcp import FastMCP
from registry import register_all_tools

# -- Build the server (stdout still redirected to stderr here) ----------------
try:
    mcp = FastMCP("agent")
    _tool_count = register_all_tools(mcp)
    print(f"[server] MCP tools registered: {_tool_count}", file=sys.stderr)
    if _tool_count > 20:
        print(f"[server] WARNING: High tool count ({_tool_count}) -- watch for LM Studio grammar issues", file=sys.stderr)

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
    print(" MCP Agent Stack -- Ready ".center(_W), file=sys.stderr)
    print("= " * _W, file=sys.stderr)
    print(f" Tools    : {_tool_count} ", file=sys.stderr)
    print(f" Planner  : {cfg.planner_model} ", file=sys.stderr)
    print(f" Executor : {cfg.executor_model} ", file=sys.stderr)
    print(f" Router   : {cfg.router_model} ", file=sys.stderr)
    print(f" Workspace: {cfg.workspace_root} ", file=sys.stderr)
    print(f" Memory   : {cfg.memory_chroma_path} ", file=sys.stderr)
    print(f" Env      : {cfg.env} ", file=sys.stderr)
    print("= " * _W, file=sys.stderr)
    print(" ", file=sys.stderr)
    tracer.finish(_boot_tid, success=True, result=f"{_tool_count} tools registered")
finally:
    # -- Restore real stdout and hand it to FastMCP's stdio transport -------------
    sys.stdout = sys._real_stdout  # type: ignore[attr-defined]

# -- Start HTTP Gateway (background daemon with retry) ------------------------
def _start_gateway() -> None:
    import time as _time
    for attempt in range(3):
        try:
            import uvicorn
            from core.config import cfg
            host = getattr(cfg, "gateway_host", "127.0.0.1")
            port = getattr(cfg, "gateway_port", 8000)
            if port == 0 or port is None:
                print("[gateway] Gateway disabled (port=0)", file=sys.stderr)
                return
            print(f"[gateway] Starting FastAPI gateway at http://{host}:{port}/ (attempt {attempt+1}/3)", file=sys.stderr)
            uvicorn.run(
                "core.gateway:create_app",
                host=host,
                port=port,
                factory=True,
                reload=False,
                log_level="warning",
                access_log=False,
            )
            break  # Clean exit
        except ImportError:
            print("[gateway] uvicorn not installed — gateway disabled.", file=sys.stderr)
            return
        except Exception as e:
            print(f"[gateway] Attempt {attempt+1}/3 failed: {e}", file=sys.stderr)
            if attempt < 2:
                _time.sleep(5)
            else:
                print("[gateway] Giving up after 3 attempts.", file=sys.stderr)

import threading as _threading

# [BUGFIX-4] Threading.Event for coordinated daemon startup.
# Dependent threads wait for this event before accessing shared resources.
# A 60-second timeout prevents indefinite hangs if the warmup thread
# crashes before reaching its finally block or hangs inside the try block.
_CHROMADB_READY_TIMEOUT = 60.0
_chromadb_ready = _threading.Event()

_threading.Thread(target=_start_gateway, daemon=True).start()

# -- Cleanup old VRAM artifacts ------------------------------------------------
def _cleanup_artifacts() -> None:
    """Delete .artifacts/ files older than 7 days on startup."""
    try:
        from core.memory_backend.pruner import cleanup_old_artifacts
        cleanup_old_artifacts(max_age_days=7)
        print("[server] Cleaned up old .artifacts/", file=sys.stderr)
    except Exception as e:
        print(f"[server] Artifact cleanup skipped: {e}", file=sys.stderr)

_threading.Thread(target=_cleanup_artifacts, daemon=True).start()

# -- Flush Memory Telemetry in background ------------------------------------
def _flush_telemetry_loop() -> None:
    """Flush memory recall telemetry to ChromaDB every 60 seconds."""
    import time as _time
    try:
        from core.memory_backend.telemetry import tracker
        from core.memory_engine import memory as _mem
        # [BUGFIX-4] Wait for ChromaDB warmup before first flush to avoid race.
        # Timeout prevents indefinite hang if warmup thread never signals.
        if not _chromadb_ready.wait(timeout=_CHROMADB_READY_TIMEOUT):
            print(f"[server] WARNING: ChromaDB warmup timed out after {_CHROMADB_READY_TIMEOUT}s, "
                  "telemetry flush proceeding anyway", file=sys.stderr)
        while True:
            _time.sleep(60)
            try:
                flushed = tracker.flush(_mem)
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
        from core.memory_engine import memory as _mem
        # v1.0: Guard against _mem being a mock/function during tests —
        # only flush if it's a real MemoryStore with _write_lock.
        if not hasattr(_mem, "_write_lock"):
            return
        flushed = tracker.flush(_mem)
        if flushed > 0:
            print(f"[server] Final telemetry flush: {flushed} updates", file=sys.stderr)
    except Exception as e:
        print(f"[server] Shutdown flush skipped: {e}", file=sys.stderr)
_atexit.register(_shutdown_flush)

# -- Graceful shutdown: checkpoint all GraphStore SQLite instances -----------
def _shutdown_kgraph() -> None:
    """Force WAL checkpoint on all GraphStore instances before process dies."""
    try:
        from core.kgraph.storage import GraphStore
        GraphStore.close_all()
    except Exception as e:
        print(f"[server] KGraph shutdown skipped: {e}", file=sys.stderr)
_atexit.register(_shutdown_kgraph)

# -- Warm up ChromaDB in background (avoids cold-start MCP timeout) -----------
def _warmup_chromadb() -> None:
    """Load ChromaDB embedding model before first tool call."""
    try:
        from core.memory_engine import memory as _mem
        # Tiny no-op query to trigger embedding model load
        _mem.recall("warmup", top_k=1, min_score=0.0)
        print("[server] ChromaDB warmup complete", file=sys.stderr)
    except Exception as e:
        print(f"[server] ChromaDB warmup skipped: {e}", file=sys.stderr)
    finally:
        # [BUGFIX-4] Signal that ChromaDB is ready for dependent threads.
        _chromadb_ready.set()

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
        # [BUGFIX-4] Wait for ChromaDB before starting meta-learner (uses memory.store).
        # Timeout prevents indefinite hang if warmup thread never signals.
        if not _chromadb_ready.wait(timeout=_CHROMADB_READY_TIMEOUT):
            print(f"[server] WARNING: ChromaDB warmup timed out after {_CHROMADB_READY_TIMEOUT}s, "
                  "meta-learner starting anyway", file=sys.stderr)
        _threading.Thread(target=learner.run_forever, daemon=True).start()
        print("[server] Meta-Learner daemon started", file=sys.stderr)
    except Exception as e:
        print(f"[server] Meta-Learner failed to start: {e}", file=sys.stderr)

_start_meta_learner()

# -- Start Sleep & Learn Daemon (moved from core/__init__.py) -----------------
# [P1 FIX] Previously started as an import side-effect in core/__init__.py,
# which caused it to run on ANY import from core (not just server boot).
# Moved here to run only when server.py boots, with proper ChromaDB warmup
# coordination via _chromadb_ready Event.
def _start_sleep_learn() -> None:
    try:
        from core.sleep_learn.daemon import start_background_daemon
        # Wait for ChromaDB before starting (uses memory.store for feedback processing)
        if not _chromadb_ready.wait(timeout=_CHROMADB_READY_TIMEOUT):
            print(f"[server] WARNING: ChromaDB warmup timed out after {_CHROMADB_READY_TIMEOUT}s, "
                  "sleep-learn starting anyway", file=sys.stderr)
        start_background_daemon()
        print("[server] Sleep & Learn daemon started", file=sys.stderr)
    except Exception as e:
        print(f"[server] Sleep & Learn failed to start: {e}", file=sys.stderr)

_start_sleep_learn()

# -- Start Eviction Flusher ----------------------------------------------------
def _start_eviction_flusher() -> None:
    try:
        from core.memory_backend.eviction import flusher_loop
        # [BUGFIX-4] Wait for ChromaDB before starting eviction (uses memory.store).
        # Timeout prevents indefinite hang if warmup thread never signals.
        if not _chromadb_ready.wait(timeout=_CHROMADB_READY_TIMEOUT):
            print(f"[server] WARNING: ChromaDB warmup timed out after {_CHROMADB_READY_TIMEOUT}s, "
                  "eviction flusher starting anyway", file=sys.stderr)
        _threading.Thread(target=flusher_loop, daemon=True).start()
        print("[server] Eviction Flusher started", file=sys.stderr)
    except Exception as e:
        print(f"[server] Eviction Flusher failed: {e}", file=sys.stderr)

_start_eviction_flusher()

# -- Scan for Incomplete Workflows ---------------------------------------------
def _scan_incomplete_workflows() -> None:
    """Log any workflows that crashed mid-execution."""
    try:
        from core.observability.checkpoint import scan_incomplete
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
        from core.memory_engine import memory as _mem
        from core.runtime.activity_tracker import tracker

        # [BUGFIX-4] Wait for ChromaDB before first maintenance check.
        # Timeout prevents indefinite hang if warmup thread never signals.
        if not _chromadb_ready.wait(timeout=_CHROMADB_READY_TIMEOUT):
            print(f"[server] WARNING: ChromaDB warmup timed out after {_CHROMADB_READY_TIMEOUT}s, "
                  "diversity enforcer starting anyway", file=sys.stderr)
        last_run = 0.0
        while True:
            _time.sleep(1800)  # Check every 30 mins
            try:
                # 7 day cooldown
                if (_time.time() - last_run) < (7 * 86400):
                    continue

                # Check idle (4 hours)
                if not tracker.try_acquire_background_slot(min_idle_seconds=14400):
                    continue

                try:
                    print("[server] Running Memory Diversity Enforcement...", file=sys.stderr)
                    result = execute_diversity_maintenance(_mem)
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

# -- Start Schedule Catch-Up (offline missed-fire recovery) -------------------
def _start_schedule_catch_up() -> None:
    """Recover schedule jobs that were due while the server was offline.

    Runs tools.schedule_ops.state.catch_up_missed_jobs() in a daemon thread
    so it never blocks MCP boot. For each persisted job, computes missed
    fires in (last_fired_at, now], applies the job's misfire_grace window +
    misfire_policy (skip/fire_last/fire_all), and delivers via notify. The
    catch-up runs once per process (guarded inside catch_up_missed_jobs).
    See tools/schedule_ops/state.py for the full design.
    """
    try:
        from tools.schedule_ops.state import catch_up_missed_jobs
        # Tiny delay so the scheduler singleton + notify are importable first.
        import time as _time
        _time.sleep(1)
        summary = catch_up_missed_jobs()
        if summary.get("jobs_with_misses", 0) > 0:
            print(f"[server] Schedule catch-up: {summary}", file=sys.stderr)
        else:
            print("[server] Schedule catch-up: no missed jobs", file=sys.stderr)
    except Exception as e:
        print(f"[server] Schedule catch-up skipped: {e}", file=sys.stderr)

_threading.Thread(target=_start_schedule_catch_up, daemon=True).start()

# -- Run (hands stdout to FastMCP's stdio transport) ----------------------------
if __name__ == "__main__":
    mcp.run()
