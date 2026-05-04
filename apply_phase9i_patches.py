"""
apply_phase9i_patches.py -- run from D:/mcp/agent/

Phase 9i: genuine improvements from Gemini + DeepSeek analysis.

  1. workflows/autocode.py:  temperature variation on retry (avoids deterministic loops)
  2. tools/web.py:           parallel fetching in search_and_read
  3. tools/python_exec.py:   sandbox import whitelist (block os/sys/subprocess in run_data)
  4. gateway/app.py:         /health/models endpoint
  5. tools/workflow_tool.py: log routing decision as trace step
  6. memory/store.py:        summarize uses top-k by importance not random 30
"""

from __future__ import annotations
import ast, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def patch(filepath, old, new, label):
    p = ROOT / filepath
    if not p.exists():
        print(f"  SKIP  {label} -- file not found"); return False
    content = p.read_text(encoding="utf-8")
    if old not in content:
        first = new.strip().splitlines()[0].strip()
        if first in content:
            print(f"  SKIP  {label} -- already applied"); return True
        print(f"  MISS  {label} -- target not found in {filepath}"); return False
    updated = content.replace(old, new)
    try:
        ast.parse(updated)
    except SyntaxError as e:
        print(f"  FAIL  {label} -- syntax error: {e}"); return False
    p.write_text(updated, encoding="utf-8")
    print(f"  OK    {label}"); return True


print("=== Phase 9i patches ===\n")

# ── 1. autocode: temperature variation on retry ───────────────────────────────
# If temperature=0 (deterministic), the model produces identical output on
# every retry. The fix: bump temperature slightly on each retry attempt.
patch(
    "workflows/autocode.py",
    '''    context = f"Analysis:\\n{analysis}" if analysis else ""

    node_step(state, "generate", f"generating patch (attempt {retries + 1})")

    r = agent(
        role     = "code",
        task     = task,
        context  = context,
        content  = file_content,
        trace_id = state.get("trace_id", ""),
    )''',
    '''    context = f"Analysis:\\n{analysis}" if analysis else ""

    # Vary temperature on retries -- deterministic models (temp=0) produce
    # identical output each retry and never recover. Each retry gets warmer.
    retry_temps = [None, 0.2, 0.4, 0.6]  # None = use role default (0.1)
    retry_temp  = retry_temps[min(retries, len(retry_temps) - 1)]

    node_step(state, "generate", f"generating patch (attempt {retries + 1})",
              temperature=retry_temp)

    r = agent(
        role        = "code",
        task        = task,
        context     = context,
        content     = file_content,
        trace_id    = state.get("trace_id", ""),
        temperature = retry_temp if retry_temp is not None else -1,
    )''',
    "autocode: temperature variation on retry prevents deterministic loops",
)

# ── 2. web: parallel fetching in search_and_read ─────────────────────────────
# Currently fetches URLs serially. Reuse the ThreadPoolExecutor pattern
# already used in file(read_many).
patch(
    "tools/web.py",
    '''        scraped  = []
        urls     = [r["url"] for r in search_result["results"] if r["url"]]

        for u in urls:
            result = _do_scrape(u, max_chars)
            if result["status"] == "success" and result.get("text"):
                scraped.append({
                    "url":        u,
                    "title":      result.get("title", ""),
                    "text":       result["text"],
                    "word_count": result.get("word_count", 0),
                })''',
    '''        urls    = [r["url"] for r in search_result["results"] if r["url"]]
        scraped = []

        # Fetch all URLs in parallel -- reuses the same pattern as file(read_many)
        from concurrent.futures import ThreadPoolExecutor, as_completed

        def _fetch_one(u):
            return u, _do_scrape(u, max_chars)

        with ThreadPoolExecutor(max_workers=min(len(urls), 4)) as ex:
            futures = {ex.submit(_fetch_one, u): u for u in urls}
            for future in as_completed(futures):
                u, result = future.result()
                if result["status"] == "success" and result.get("text"):
                    scraped.append({
                        "url":        u,
                        "title":      result.get("title", ""),
                        "text":       result["text"],
                        "word_count": result.get("word_count", 0),
                    })

        # Restore original URL order so results are deterministic
        url_order = {u: i for i, u in enumerate(urls)}
        scraped.sort(key=lambda r: url_order.get(r["url"], 999))''',
    "web: parallel fetching in search_and_read",
)

# ── 3. python_exec.py: block dangerous imports in run_data ───────────────────
# run_data currently allows os, sys, subprocess -- real security gap.
# A prompt injection could delete files or start a reverse shell.
patch(
    "tools/python_exec.py",
    '''ALL_ALLOWED = STDLIB_IMPORTS | HEAVY_IMPORTS''',
    '''ALL_ALLOWED = STDLIB_IMPORTS | HEAVY_IMPORTS

# Modules that are never allowed even in run_data -- security boundary.
# These can access the filesystem, network, processes, or environment vars.
BLOCKED_IMPORTS = {
    "os", "sys", "subprocess", "shutil", "socket", "pickle",
    "multiprocessing", "ctypes", "importlib", "builtins",
    "signal", "pty", "tty", "termios", "fcntl", "resource",
}''',
    "python_exec: define BLOCKED_IMPORTS set",
)

patch(
    "tools/python_exec.py",
    '''        blocked = [n for n in imports if n not in ALL_ALLOWED and n not in ("__future__",)]
        if blocked:
            return {
                "status": "error",
                "error": (
                    f"Import(s) not allowed: {blocked}. "
                    f"Allowed stdlib: {sorted(STDLIB_IMPORTS)}. "
                    f"Allowed heavy: {sorted(HEAVY_IMPORTS)}."
                ),
                "mode": "run_data",
            }''',
    '''        # Check blocked imports first (security boundary)
        dangerous = [n for n in imports if n in BLOCKED_IMPORTS]
        if dangerous:
            return {
                "status": "error",
                "error": (
                    f"Import(s) blocked for security: {dangerous}. "
                    "These modules can access filesystem, processes, or network. "
                    "Use the file(), git(), or web() tools instead."
                ),
                "mode": "run_data",
            }

        blocked = [n for n in imports if n not in ALL_ALLOWED and n not in ("__future__",)]
        if blocked:
            return {
                "status": "error",
                "error": (
                    f"Import(s) not in allowed list: {blocked}. "
                    f"Allowed stdlib: {sorted(STDLIB_IMPORTS)}. "
                    f"Allowed heavy: {sorted(HEAVY_IMPORTS)}."
                ),
                "mode": "run_data",
            }''',
    "python_exec: block dangerous imports before allowlist check",
)

# ── 4. gateway: /health/models endpoint ──────────────────────────────────────
patch(
    "gateway/app.py",
    '''    @app.get("/health")
    def health():
        from core.llm import llm
        return {
            "status":    "ok",
            "lm_studio": llm.is_available(),
            "env":       cfg.env,
            "version":   "1.0.0",
        }''',
    '''    @app.get("/health")
    def health():
        from core.llm import llm
        return {
            "status":    "ok",
            "lm_studio": llm.is_available(),
            "env":       cfg.env,
            "version":   "1.0.0",
        }

    @app.get("/health/models")
    def health_models(_: None = Depends(_check_auth)):
        """Check which LM Studio models are loaded and verify required ones."""
        import httpx as _httpx
        required = {
            "planner":  cfg.planner_model,
            "executor": cfg.executor_model,
            "router":   cfg.router_model,
        }
        try:
            resp    = _httpx.get(f"{cfg.lm_studio_base_url}/models", timeout=5)
            loaded  = [m["id"] for m in resp.json().get("data", [])]
            status  = {}
            all_ok  = True
            for role, model in required.items():
                found = any(model.lower() in m.lower() for m in loaded)
                status[role] = {"model": model, "loaded": found}
                if not found:
                    all_ok = False
            return {
                "status":        "ok" if all_ok else "degraded",
                "all_loaded":    all_ok,
                "models":        status,
                "loaded_models": loaded,
            }
        except Exception as e:
            return {
                "status":     "error",
                "error":      str(e),
                "all_loaded": False,
            }''',
    "gateway: /health/models endpoint",
)

# ── 5. workflow_tool: log routing decision as trace step ─────────────────────
patch(
    "tools/workflow_tool.py",
    '''        wf_type  = decision.workflow
        # Attach routing metadata to kwargs so workflows can log it
        kwargs["_routing"] = decision.to_dict()
        # If router says "direct", use the tool it recommended''',
    '''        wf_type  = decision.workflow
        # Attach routing metadata to kwargs so workflows can log it
        kwargs["_routing"] = decision.to_dict()
        # Log the routing decision to the trace so it's visible later
        if trace_id:
            from core.tracer import tracer
            tracer.step(trace_id, "route",
                        f"auto-routed to {wf_type!r}",
                        workflow=wf_type,
                        tool=decision.tool,
                        complexity=decision.complexity,
                        confidence=decision.confidence,
                        reason=decision.reason)
        # If router says "direct", use the tool it recommended''',
    "workflow_tool: log routing decision as trace step",
)

# ── 6. memory: summarize uses top-k by importance not random 30 ──────────────
patch(
    "memory/store.py",
    '''        if len(all_docs) < 3:
            return {"status": "not_enough_data", "count": len(all_docs)}

        # Sort by importance desc, take top_n
        all_docs.sort(key=lambda x: x["importance"], reverse=True)
        top = all_docs[:top_n]''',
    '''        if len(all_docs) < 3:
            return {"status": "not_enough_data", "count": len(all_docs)}

        # Sort by decay score (importance * recency) not just raw importance
        # This favours both recent AND important memories for summarisation
        import time as _time
        now = _time.time()
        for d in all_docs:
            age   = (now - d.get("timestamp", now)) / 86400
            decay = max(0.3, 1.0 - age / cfg.memory_decay_days)
            d["_score"] = d["importance"] * decay
        all_docs.sort(key=lambda x: x["_score"], reverse=True)
        top = all_docs[:top_n]''',
    "memory: summarize ranks by decay score (importance * recency)",
)

print("\nDone. Run: python verify_phase9i.py to confirm.")
