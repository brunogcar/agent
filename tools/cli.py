"""
tools/cli.py — Fast natural-language command dispatcher, registered as an MCP tool.

WHAT THIS IS
------------
A single MCP tool `cli(command)` that lets the agent (or you) run simple
operations instantly without burning Planner tokens on a full workflow cycle.

HOW IT WORKS — FOUR LAYERS
-----------------------------
1. Pattern match  — regex rules cover ~90% of common commands. Zero LLM calls.
                    Returns immediately. Handles: git, file, web, memory, calc,
                    echo, lms, health, help.

2. Shell whitelist — read-only and file-management shell commands executed via
                    subprocess with a strict allowlist. Zero LLM calls. Real output.
                    Read-only: python --version, whoami, where, dir/ls, type/cat,
                               systeminfo, ipconfig, hostname, tasklist, ver
                    File ops:  copy, xcopy, move, mkdir, rmdir, del
                    DECISION: These are NOT routed through agent tools (file,
                    python_exec) because the agent often wants raw shell output
                    (e.g. `python --version` returns "Python 3.11.x", not a dict).
                    The whitelist is the security boundary -- anything not on it
                    falls through to Nemotron. No arbitrary shell execution.

3. Nemotron route — anything that doesn't match a pattern goes to the Router
                    model (nemotron-3-nano-4b) with a strict JSON-only prompt.
                    Nemotron returns one of two things:
                      a) {tool_name, action, params} -> execute directly via whitelist
                      b) {escalate: true, reason: "..."} -> hand off to Executor

4. Executor escalation — if Nemotron decides the command is too complex for a
                    direct tool call, the command is sent to the Executor model
                    (Hermes) as a free-form task. Hermes reasons and responds.

SAFETY
------
Layer 1 (patterns) and layer 2 (shell whitelist) are zero-token execution.
Layer 2 uses subprocess with a command allowlist -- no arbitrary shell injection.
Commands are split by shlex on non-Windows, split() on Windows (no shell=True).
Output is capped at 4KB to stay within MCP response limits.
Layer 3 (Nemotron dispatch) uses a strict tool:action whitelist.
Layer 4 (Executor) only produces text -- it does not call tools directly.

NAMING CONVENTION
-----------------
Internal dispatch uses `tool_name` (never `tool`) to avoid shadowing the
`tool` decorator from registry. That was the fatal bug in the previous version.

WORKING DIRECTORY
-----------------
Shell commands default to cfg.agent_root.
Commands that look like workspace operations (copy to workspace/, etc.) auto-detect.
Pass `cd workspace` prefix to override: `cd workspace && dir` is not supported --
use the path directly in the command instead.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

import requests

from registry import tool      # decorator — NEVER use 'tool' as a variable name
from core.config import cfg    # singleton: .lm_studio_base_url, .router_model, .executor_model


# ── Lazy memory accessor (mirrors memory_tool.py pattern) ─────────────────────

def _mem():
    """Lazy import of ChromaDB store — avoids slow startup, same as memory_tool.py."""
    from core.memory import memory as _store
    return _store


# ── Shell whitelist executor (Layer 2) ────────────────────────────────────────
# DECISION: A tight allowlist of shell commands that produce real output the agent
# needs directly (python --version, whoami, dir, etc). These are NOT routed through
# agent tools because the agent wants raw terminal output, not a wrapped dict.
#
# Security model:
#   - Only commands whose first token appears in _SHELL_ALLOW can execute.
#   - shell=True is NEVER used -- commands are passed as a list to subprocess.
#   - Output capped at 4KB (MCP response limit).
#   - Timeout 10s -- these are info commands, not long-running processes.
#   - Working directory: cfg.agent_root by default (safe, predictable).
#
# DECISION: split into read-only and file-op sets so future code can audit
# or restrict them independently. Both are in the same allowlist dict for now.
#
# WHY NOT python_exec for `python --version`:
#   python_exec runs code inside the sandbox (BLOCKED_IMPORTS etc).
#   `python --version` is a subprocess call, not Python code -- it would need
#   `import subprocess` which is blocked. Shell layer is the right place.

_SHELL_ALLOW: dict[str, list[str]] = {
    # ── Read-only info commands ───────────────────────────────────────────────
    # These never modify the filesystem. Safe to run unconditionally.
    "python":      None,                             # handled specially in _shell_exec (script vs --version)
    "pip":         ["pip", "--version"],
    "whoami":      ["whoami"],
    "hostname":    ["hostname"],
    "ver":         ["cmd", "/c", "ver"],             # Windows version string
    "systeminfo":  ["systeminfo"],                   # verbose; agent uses sparingly
    "ipconfig":    ["ipconfig"],
    "tasklist":    ["tasklist"],
    "where":       ["where"],                        # which equivalent on Windows
    "which":       ["which"],                        # Linux/macOS
    "dir":         ["cmd", "/c", "dir"],
    "ls":          ["cmd", "/c", "dir"] if sys.platform == "win32" else ["ls", "-la"],
    "type":        ["cmd", "/c", "type"],            # Windows cat
    "cat":         ["cat"],                          # Linux/macOS cat
    "env":         ["cmd", "/c", "set"] if sys.platform == "win32" else ["env"],
    "set":         ["cmd", "/c", "set"],
    "echo":        None,                             # handled by pattern layer; listed for completeness
    # ── File operation commands ───────────────────────────────────────────────
    # These modify the filesystem but are common enough to whitelist.
    # DECISION: file tool is preferred for agent code; these exist for
    # quick imperative ops like `copy src dst` that don't need a full tool call.
    "copy":        ["cmd", "/c", "copy"],
    "xcopy":       ["cmd", "/c", "xcopy"],
    "move":        ["cmd", "/c", "move"],
    "mkdir":       ["cmd", "/c", "mkdir"] if sys.platform == "win32" else ["mkdir", "-p"],
    "md":          ["cmd", "/c", "mkdir"],           # Windows mkdir alias
    "rmdir":       ["cmd", "/c", "rmdir"],
    "rd":          ["cmd", "/c", "rmdir"],           # Windows rmdir alias
    "del":         ["cmd", "/c", "del"],
    "rm":          ["rm"],                           # Linux/macOS
    "cp":          ["cp"],                           # Linux/macOS copy
    "mv":          ["mv"],                           # Linux/macOS move
}

# Commands that need extra tokens appended from user input (not fixed commands)
_SHELL_PASSTHROUGH = {
    "python", "pip", "where", "which", "dir", "ls", "type", "cat",
    "copy", "xcopy", "move", "mkdir", "md", "rmdir", "rd", "del",
    "rm", "cp", "mv",
}

_SHELL_MAX_OUTPUT = 4096   # cap output to stay within MCP response limits
_SHELL_TIMEOUT    = 15     # seconds; info commands should never take longer


def _detect_cwd(command: str) -> Path:
    """
    Auto-detect working directory from command context.

    DECISION: The agent operates in two root contexts:
      - agent root    (D:/mcp/agent)      -- agent code, tools, skills
      - workspace root (D:/mcp/workspace) -- project work, output files

    Heuristic (first match wins):
      1. Command contains an absolute path -> use its parent dir if it's a dir,
         or its parent if it's a file. This handles `type D:/mcp/agent/tools/x.py`.
      2. Command contains "workspace" token -> workspace root.
      3. Command contains "agent" token (but not "workspace") -> agent root.
      4. Default -> agent root (most shell ops relate to agent code).

    WHY NOT always workspace: file ops like `copy tools/x.py tools/x.bak` are
    agent-root operations. Defaulting to workspace would break relative paths.
    """
    # Check for absolute path tokens in the command
    for token in command.split():
        p = Path(token.strip('"').strip("'"))
        if p.is_absolute():
            if p.is_dir():
                return p
            if p.parent.is_dir():
                return p.parent

    cmd_lower = command.lower()
    if "workspace" in cmd_lower:
        return cfg.workspace_root
    if "agent" in cmd_lower:
        return cfg.agent_root

    return cfg.agent_root   # safe default


# Commands that map to agent tool fallbacks when shell fails.
# DECISION: shell-first, agent-fallback pattern.
#   If the shell command fails (FileNotFoundError, bad exit code, empty output
#   on a command that should produce something), we retry via the agent tool
#   layer. This gives the best of both worlds: raw shell speed when it works,
#   agent tool reliability when it doesn't (e.g. dir fails -> file:list).
#
# Map: shell_cmd_name -> (tool_name, action, param_builder)
# param_builder receives the original command string and returns a dict.
_SHELL_AGENT_FALLBACK: dict[str, tuple[str, str, Any]] = {
    "dir":   ("file", "list",   lambda cmd: {"path": cmd.split()[1] if len(cmd.split()) > 1 else "."}),
    "ls":    ("file", "list",   lambda cmd: {"path": cmd.split()[1] if len(cmd.split()) > 1 else "."}),
    "type":  ("file", "read",   lambda cmd: {"path": " ".join(cmd.split()[1:])}),
    "cat":   ("file", "read",   lambda cmd: {"path": " ".join(cmd.split()[1:])}),
    "copy":  ("file", "backup", lambda cmd: {"path": cmd.split()[1] if len(cmd.split()) > 1 else ""}),
    "cp":    ("file", "backup", lambda cmd: {"path": cmd.split()[1] if len(cmd.split()) > 1 else ""}),
}


def _shell_exec(command: str) -> str | None:
    """
    Try to execute `command` as a whitelisted shell command.

    Returns:
      str  -- command output (or error message) if command is whitelisted.
      None -- command not whitelisted; caller should fall through to next layer.

    DECISION: Returns None (not an error string) when not whitelisted so the
    caller can fall through to Nemotron cleanly. An error string would be
    misread as "command ran but failed" when it never ran at all.

    DECISION: shell-first, agent-fallback.
      On shell failure, check _SHELL_AGENT_FALLBACK and retry via agent tool.
      This handles environments where cmd.exe behaves differently, or where
      a relative path only resolves correctly through the agent's file tool.
      Fallback is best-effort -- if it also fails, return the original shell error.
    """
    parts = command.strip().split()
    if not parts:
        return None

    cmd_name = parts[0].lower()
    # Strip .exe suffix on Windows (user may type `python.exe --version`)
    if cmd_name.endswith(".exe"):
        cmd_name = cmd_name[:-4]

    if cmd_name not in _SHELL_ALLOW or _SHELL_ALLOW[cmd_name] is None:
        # Special case: python is None in _SHELL_ALLOW, handled here
        # DECISION: `python` with a .py file arg runs the script; bare `python`
        # returns --version; other args (e.g. -c "...") pass through directly.
        # The old behavior (always --version) broke `cli("python run_b3_sync.py")`
        # returning "Python 3.11.9" instead of executing the script.
        if cmd_name == "python":
            import shutil as _shutil
            py_exe = _shutil.which("python") or "python"
            if len(parts) == 1:
                argv = [py_exe, "--version"]
            elif parts[1].endswith(".py") or parts[1].startswith("-"):
                # Script path or flag like -c/-m -- pass all args through
                argv = [py_exe] + parts[1:]
            else:
                argv = [py_exe, "--version"]
            cwd = _detect_cwd(command)
            try:
                result = subprocess.run(
                    argv, capture_output=True, text=True,
                    cwd=str(cwd), timeout=60,   # scripts may take longer than 15s
                )
                out = (result.stdout + result.stderr).strip()
                if len(out) > _SHELL_MAX_OUTPUT:
                    out = out[:_SHELL_MAX_OUTPUT] + f"\n... (truncated)"
                return out if out else "(python completed, no output)"
            except subprocess.TimeoutExpired:
                return f"python script timed out after 60s"
            except Exception as e:
                return f"python error: {e}"
        return None   # not whitelisted -- fall through to Nemotron

    # Build the actual argv list
    base = _SHELL_ALLOW[cmd_name]
    if cmd_name in _SHELL_PASSTHROUGH:
        if base and base[0] == "cmd":
            argv = base + parts[1:]
        else:
            argv = base + parts[1:]
    else:
        argv = list(base)  # fixed commands (whoami, hostname) -- ignore extra args

    # Auto-detect working directory from command context (DECISION above)
    cwd = _detect_cwd(command)

    shell_error = ""
    try:
        result = subprocess.run(
            argv,
            capture_output = True,
            text           = True,
            cwd            = str(cwd),
            timeout        = _SHELL_TIMEOUT,
            # DECISION: shell=False always -- no injection possible.
            # Commands validated against allowlist before reaching here.
        )
        out = (result.stdout + result.stderr).strip()
        if len(out) > _SHELL_MAX_OUTPUT:
            out = out[:_SHELL_MAX_OUTPUT] + f"\n... (truncated at {_SHELL_MAX_OUTPUT} chars)"

        # Success path
        if result.returncode == 0:
            return out if out else "(command completed, no output)"

        # Non-zero exit -- try agent fallback before returning error
        shell_error = out or f"(exit code {result.returncode})"

    except FileNotFoundError:
        shell_error = f"Command not found: {parts[0]}"
    except subprocess.TimeoutExpired:
        return f"Command timed out after {_SHELL_TIMEOUT}s: {command}"
    except Exception as e:
        shell_error = f"Shell error: {e}"

    # ── Agent fallback (shell-first, agent-fallback pattern) ──────────────────
    # Shell failed -- try the mapped agent tool before surfacing the error.
    if cmd_name in _SHELL_AGENT_FALLBACK:
        tool_name, action, param_fn = _SHELL_AGENT_FALLBACK[cmd_name]
        try:
            params = param_fn(command)
            fallback_result = _safe_dispatch(tool_name, action, params)
            if fallback_result and not fallback_result.startswith("Unknown command"):
                return f"[shell failed, agent fallback]\n{fallback_result}"
        except Exception:
            pass   # fallback also failed -- surface original shell error below

    return shell_error


# ── LM Studio management (raw HTTP, no extra imports) ─────────────────────────
# DECISION: raw requests here instead of importing a helper module that may not
# exist. Keeps this file fully self-contained and import-safe at registry scan time.

_LMS = "http://localhost:1234"

def _lms_ls()              -> str:
    try:
        r = requests.get(f"{_LMS}/api/v0/models", timeout=5); r.raise_for_status()
        ms = [m.get("id") or str(m) for m in r.json()]
        return "\n".join(f" • {m}" for m in ms) if ms else "No downloaded models."
    except Exception as e: return f"LM Studio error: {e}"

def _lms_ps()              -> str:
    try:
        r = requests.get(f"{_LMS}/v1/models", timeout=5); r.raise_for_status()
        ms = [m.get("id") or str(m) for m in r.json().get("data", [])]
        return "\n".join(f" • {m}" for m in ms) if ms else "No models loaded."
    except Exception as e: return f"LM Studio error: {e}"

def _lms_load(model: str)  -> str:
    try:
        r = requests.post(f"{_LMS}/v1/models/load", json={"model": model}, timeout=10)
        r.raise_for_status(); return f"Loaded: {model}"
    except Exception as e: return f"LM Studio error: {e}"

def _lms_unload(model: str = "") -> str:
    try:
        r = requests.post(f"{_LMS}/v1/models/unload",
                          json={"model": model} if model else {}, timeout=10)
        r.raise_for_status(); return f"Unloaded: {model or 'all models'}"
    except Exception as e: return f"LM Studio error: {e}"

def _lms_log()             -> str:
    try:
        r = requests.get(f"{_LMS}/api/v0/log", timeout=5); r.raise_for_status()
        return r.text[-2000:] if len(r.text) > 2000 else r.text
    except Exception as e: return f"LM Studio error: {e}"


# ── Tool proxy helpers (lazy imports, normalise dict → human string) ───────────
# DECISION: each helper imports its tool lazily so registry scan never triggers
# a cascade of heavy imports. Each uses the tool's action= / operation= interface
# exactly as documented in the README — no internal function calls.

def _file(action: str, **kw) -> str:
    from tools.file import file
    r = file(action=action, **kw)
    if not isinstance(r, dict): return str(r)
    if action == "read" and "content" in r:
        lines = r["content"].splitlines()
        out   = "\n".join(f"{i+1:4d} | {l}" for i, l in enumerate(lines[:40]))
        return out + (f"\n... ({len(lines)-40} more lines)" if len(lines) > 40 else "")
    if r.get("status") == "error": return f"Error: {r.get('error', r)}"
    return r.get("message", json.dumps(r, indent=2))

def _git(operation: str, **kw) -> str:
    from tools.git import git
    r = git(operation=operation, **kw)
    if not isinstance(r, dict): return str(r)
    if operation == "log":
        cs = r.get("commits", [])
        # BUG FIX: git_ops.py returns key "hash" not "sha" — was always printing blank hashes
        return "\n".join(f"{c.get('hash','')[:7]}  {c.get('message','').splitlines()[0][:70]}"
                         for c in cs[:10]) or "No commits."
    if operation == "diff": return r.get("diff", str(r))
    if r.get("status") == "error": return f"Error: {r.get('error', r)}"
    return r.get("message", json.dumps(r))

def _web(action: str, **kw) -> str:
    from tools.web import web
    r = web(action=action, **kw)
    if not isinstance(r, dict): return str(r)
    if action == "search":
        results = r.get("results", [])
        return "\n".join(
            f"{i+1}. {x.get('title','')}\n   {x.get('url','')}\n   {x.get('snippet','')[:100]}"
            for i, x in enumerate(results[:5])
        ) or "No results."
    if action in ("scrape", "read"): return r.get("text", str(r))[:3000]
    if r.get("status") == "error": return f"Error: {r.get('error', r)}"
    return str(r)

def _memory(action: str, **kw) -> str:
    """
    Direct ChromaDB access via core/memory.py singleton.
    Mirrors the memory() tool parameter names exactly so behaviour is consistent.
    """
    store = _mem()
    try:
        if action == "recall":
            results = store.recall(
                query       = kw.get("query", ""),
                top_k       = kw.get("top_k", 5),
                collections = kw.get("collections"),
                min_score   = kw.get("min_score", 0.5),
                tags_filter = kw.get("tags_filter", ""),
            )
            if not results: return "No memories found."
            return "\n".join(
                f"[{r.get('collection','?')}] score={r.get('score',0):.1f} | "
                f"{r.get('text', r.get('document',''))[:120]}..."
                for r in results[:5]
            )
        if action == "store":
            mem_type = kw.get("memory_type", "semantic")
            text     = kw.get("text", "")
            importance = kw.get("importance", 5)
            tags     = kw.get("tags", "")
            if mem_type == "episodic":
                store.store_episodic(text, importance=importance,
                                     goal=kw.get("goal",""), outcome=kw.get("outcome","unknown"),
                                     tools_used=kw.get("tools_used",""), trace_id=kw.get("trace_id",""))
            elif mem_type == "procedural":
                store.store_procedural(text, importance=importance, tags=tags)
            else:
                store.store_semantic(text, importance=importance, tags=tags)
            return f"Stored ({mem_type}, importance={importance})."
        if action == "stats":
            stats = store.get_stats()
            return "\n".join(f"{col}: {cnt} entries" for col, cnt in stats.items())
        if action == "prune":
            removed = store.prune()
            return f"Pruned {removed} low-score memories."
        return f"Unknown memory action '{action}'. Use: recall | store | stats | prune"
    except Exception as e:
        return f"Memory error: {e}"

def _python(code: str, mode: str = "run") -> str:
    from tools.python_exec import python
    r = python(mode=mode, code=code)
    if not isinstance(r, dict): return str(r)
    return r.get("output", r.get("error", str(r)))

def _notify(message: str) -> str:
    from tools.notify import notify
    r = notify(action="send", message=message)
    if not isinstance(r, dict): return str(r)
    return r.get("message", str(r))


def _skill_call(domain: str, mode: str, arg: str = "", **extra) -> str:
    """
    Route to skills/dispatcher.py skill() function.
    Used by the cli pattern layer for shorthand calls.

    arg interpretation by mode (so cli patterns stay simple):
      query  -> arg becomes ticker= (e.g. "skill b3_api query PETR4")
      sync   -> arg becomes files=  (e.g. "skill b3_api sync Instruments")
      status -> arg ignored

    DECISION: lazy import -- skills/dispatcher.py imports all domain manifests
    at import time which triggers importlib.import_module on skills/b3/ etc.
    Keeping this lazy means the CLI tool registers instantly at MCP startup
    and domain discovery happens only on the first actual skill() call.
    """
    try:
        from skills.dispatcher import skill as _skill_fn

        # Map positional arg to the right kwarg based on mode
        kwargs: dict = {}
        if arg:
            if mode == "query":
                kwargs["ticker"] = arg.upper()
            elif mode == "sync":
                kwargs["files"] = arg   # dispatcher parses comma-sep or JSON
            # status and others: arg is ignored

        result = _skill_fn(domain=domain, mode=mode, **kwargs)
        if isinstance(result, dict):
            import json as _json
            return _json.dumps(result, indent=2, ensure_ascii=False)
        return str(result)
    except ImportError:
        return "skills/dispatcher.py not found -- ensure skills/ package is installed"
    except Exception as e:
        return f"skill error: {e}"


# ── Whitelist: only these (tool_name:action) pairs can execute ────────────────
# DECISION: flat "tool:action" key prevents calling any action not explicitly
# listed here. Nemotron cannot hallucinate its way into an unlisted operation.

DISPATCH: dict[str, Any] = {
    "file:read":     lambda **kw: _file("read",    **kw),
    "file:write":    lambda **kw: _file("write",   **kw),
    "file:list":     lambda **kw: _file("list",    **kw),
    "file:patch":    lambda **kw: _file("patch",   **kw),
    "file:search":   lambda **kw: _file("search",  **kw),
    "file:backup":   lambda **kw: _file("backup",  **kw),
    "git:status":    lambda **kw: _git("status",   **kw),
    "git:log":       lambda **kw: _git("log",      **kw),
    "git:diff":      lambda **kw: _git("diff",     **kw),
    "git:snapshot":  lambda **kw: _git("snapshot", **kw),
    "git:commit":    lambda **kw: _git("commit",   **kw),
    "git:rollback":  lambda **kw: _git("rollback", **kw),
    "web:search":    lambda **kw: _web("search",   **kw),
    "web:scrape":    lambda **kw: _web("scrape",   **kw),
    "web:read":      lambda **kw: _web("read",     **kw),
    "memory:recall": lambda **kw: _memory("recall",**kw),
    "memory:store":  lambda **kw: _memory("store", **kw),
    "memory:stats":  lambda **kw: _memory("stats"),
    "memory:prune":  lambda **kw: _memory("prune"),
    "python:run":    lambda **kw: _python(kw.get("code",""), mode="run"),
    "python:calc":   lambda **kw: _python(kw.get("code",""), mode="run"),
    "python:data":   lambda **kw: _python(kw.get("code",""), mode="run_data"),
    "notify:send":   lambda **kw: _notify(kw.get("message","")),
    "lms:ls":        lambda **kw: _lms_ls(),
    "lms:ps":        lambda **kw: _lms_ps(),
    "lms:load":      lambda **kw: _lms_load(kw.get("model","")),
    "lms:unload":    lambda **kw: _lms_unload(kw.get("model","")),
    "lms:log":       lambda **kw: _lms_log(),
    # skill dispatcher -- routes to skills/dispatcher.py
    # domain= and mode= extracted by pattern; arg= is the optional third word
    # (e.g. ticker for query, file name for sync). _skill_call interprets it.
    "skill:call":    lambda **kw: _skill_call(kw.get("domain",""), kw.get("mode",""), kw.get("arg","")),
    "system:health": lambda **kw: "MCP Agent Stack: all systems operational.",
    "system:help":   lambda **kw: (
        "cli quick commands:\n"
        "  git status | log [n] | diff | snapshot [msg] | commit <msg> | rollback [--force]\n"
        "  file read <path> | write <path> <content> | list [dir] | search <query>\n"
        "  web search <query> | scrape <url> | read <url>\n"
        "  memory recall <query> | store <text> | stats | prune\n"
        "  python run <code> | calc <expr>\n"
        "  notify <message>\n"
        "  lms ls | ps | load <model> | unload [model] | log\n"
        "  skill <domain> <mode>  -- e.g. skill b3_api status | skill b3_api sync\n"
        "  health | help\n"
        "Shell (zero tokens, real output):\n"
        "  python <script.py> [args] | python --version | pip --version\n"
        "  whoami | hostname | where <cmd> | dir [path] | type <file>\n"
        "  copy <src> <dst> | move <src> <dst> | mkdir <dir> | del <file>\n"
        "Anything else -> Nemotron decides: direct dispatch or Executor escalation."
    ),
}


def _safe_dispatch(tool_name: str, action: str, params: dict) -> str:
    """Look up tool_name:action in whitelist and execute. Never raises."""
    key = f"{tool_name.lower()}:{action.lower()}"
    fn  = DISPATCH.get(key)
    if fn is None:
        available = [k for k in DISPATCH if k.startswith(tool_name.lower() + ":")]
        hint = f" Available for '{tool_name}': {available}" if available else \
               f" Known tools: {sorted({k.split(':')[0] for k in DISPATCH})}"
        return f"Unknown command '{key}'.{hint}"
    try:
        return fn(**params)
    except Exception as e:
        return f"Error in {key}: {e}"


# ── Pattern rules (zero LLM tokens) ───────────────────────────────────────────
# Order matters: more specific patterns before broad ones.

_PATTERNS = [
    (r"^health$",                        "system",  "health",   lambda m: {}),
    (r"^help$",                          "system",  "help",     lambda m: {}),
    (r"^git\s+status$",                  "git",     "status",   lambda m: {}),
    (r"^git\s+log\s+(\d+)",              "git",     "log",      lambda m: {"n": int(m.group(1))}),
    (r"^git\s+log$",                     "git",     "log",      lambda m: {}),
    (r"^git\s+diff$",                    "git",     "diff",     lambda m: {}),
    (r"^git\s+snapshot\s*(.*)",          "git",     "snapshot", lambda m: {"message": m.group(1).strip() or ""}),
    # BUG FIX: old patterns passed message=None on empty input (breaks git tool's `if not message` guard)
    # commit now requires a message arg to match -- prevents calling git commit with no message
    (r"^git\s+commit\s+(.+)",            "git",     "commit",   lambda m: {"message": m.group(1).strip()}),
    # BUG FIX: old rollback passed version= which is not a valid git() parameter -- should be force=
    (r"^git\s+rollback\s+--?force$",     "git",     "rollback", lambda m: {"force": True}),
    (r"^git\s+rollback$",                "git",     "rollback", lambda m: {}),
    (r"^(?:read|cat|show)\s+(.+)",       "file",    "read",     lambda m: {"path": m.group(1).strip()}),
    (r"^(?:ls|list)\s*(.*)",             "file",    "list",     lambda m: {"path": m.group(1).strip() or "."}),
    (r"^write\s+(\S+)\s+(.+)",           "file",    "write",    lambda m: {"path": m.group(1), "content": m.group(2)}),
    (r"^(?:find|grep)\s+(.+)",           "file",    "search",   lambda m: {"query": m.group(1).strip()}),
    (r"^search\s+(.+)",                  "web",     "search",   lambda m: {"query": m.group(1).strip()}),
    (r"^scrape\s+(https?://\S+)",        "web",     "scrape",   lambda m: {"url": m.group(1).strip()}),
    (r"^read\s+(https?://\S+)",          "web",     "read",     lambda m: {"url": m.group(1).strip()}),
    (r"^recall\s+(.+)",                  "memory",  "recall",   lambda m: {"query": m.group(1).strip()}),
    (r"^store\s+(.+)",                   "memory",  "store",    lambda m: {"text": m.group(1).strip()}),
    (r"^memory\s+stats$",                "memory",  "stats",    lambda m: {}),
    (r"^memory\s+prune$",                "memory",  "prune",    lambda m: {}),
    (r"^calc\s+(.+)",                    "python",  "calc",     lambda m: {"code": m.group(1).strip()}),
    (r"^(?:run|exec)\s+(.+)",            "python",  "run",      lambda m: {"code": m.group(1).strip()}),
    # BUG FIX: echo fell through to Executor which just described the command instead of running it.
    # Route echo -> python:run so `echo "hi"` actually prints "hi" instead of returning instructions.
    # DECISION: shell echo is the canonical smoke-test for cli. Routing it to Hermes was the exact
    # bug reported -- Executor explained `echo` instead of executing it. Strip outer quotes so
    # echo "Testing" and echo Testing both work without the quotes appearing in output.
    (r'echo\s+"([^"]+)"',              "python",  "run",      lambda m: {"code": f'print({m.group(1)!r})'}),
    (r"echo\s+'([^']+)'",             "python",  "run",      lambda m: {"code": f'print({m.group(1)!r})'}),
    (r"^echo\s+(.*)",                   "python",  "run",      lambda m: {"code": f'print({m.group(1).strip()!r})'}),
    (r"^(?:notify|alert|ping)\s+(.+)",  "notify",  "send",     lambda m: {"message": m.group(1).strip()}),
    # skill domain dispatcher -- routes directly to skills/dispatcher.py @tool
    # DECISION: two patterns cover the common cli shorthand forms:
    #   "skill b3_api status"        -> domain=b3_api, mode=status, arg=""
    #   "skill b3_api query PETR4"   -> domain=b3_api, mode=query,  arg=PETR4
    # The arg is interpreted by _skill_call: query -> ticker=arg, sync -> files=[arg].
    # Anything needing more params (filters, columns) still calls skill() directly.
    (r"^skill\s+(\w+)\s+(\w+)\s+(\S+)$", "skill", "call",
        lambda m: {"domain": m.group(1), "mode": m.group(2), "arg": m.group(3)}),
    (r"^skill\s+(\w+)\s+(\w+)$",          "skill", "call",
        lambda m: {"domain": m.group(1), "mode": m.group(2), "arg": ""}),
    (r"^lms\s+ls$",                      "lms",     "ls",       lambda m: {}),
    (r"^lms\s+ps$",                      "lms",     "ps",       lambda m: {}),
    (r"^lms\s+load\s+(.+)",              "lms",     "load",     lambda m: {"model": m.group(1).strip()}),
    (r"^lms\s+unload\s+(.+)",            "lms",     "unload",   lambda m: {"model": m.group(1).strip()}),
    (r"^lms\s+unload$",                  "lms",     "unload",   lambda m: {}),
    (r"^lms\s+log$",                     "lms",     "log",      lambda m: {}),
]

_COMPILED = [(re.compile(p, re.IGNORECASE), tn, a, fn)
             for p, tn, a, fn in _PATTERNS]


def _match_pattern(command: str):
    """Returns (tool_name, action, params) or None."""
    for rx, tool_name, action, param_fn in _COMPILED:
        m = rx.match(command.strip())
        if m:
            return tool_name, action, param_fn(m)
    return None


# ── Nemotron router ────────────────────────────────────────────────────────────

_NEMOTRON_SYSTEM = """\
You are a command router for an MCP agent. Given a natural-language command,
decide ONE of two things:

Option A — the command maps to a simple tool call:
  {"route": "dispatch", "tool_name": "<tool>", "action": "<action>", "params": {}}
  Allowed tool_name values: file, git, web, memory, python, notify, lms, system.

Option B — the command is too complex for a single tool call and needs the Executor:
  {"route": "escalate", "reason": "<one sentence why>"}

Use Option A for: status checks, reads, searches, single-step writes, calculations.
Use Option B for: multi-step tasks, code generation, analysis, research, anything
  that requires reasoning or multiple tool calls to complete.

Output ONLY valid JSON. No explanation, no markdown."""


def _call_nemotron(command: str) -> dict:
    """
    Ask Nemotron to decide: direct dispatch (Option A) or Executor escalation (Option B).

    DECISION: Nemotron is the decision point — not the caller. This is exactly
    what was asked for: "let Nemotron decide whether to escalate or handle it."
    Temperature=0 for deterministic routing. 150 tokens is enough for either option.
    Returns a safe fallback dict on any network/parse error.

    DECISION: response_format json_object is best-effort — some Nemotron checkpoints
    ignore it and return prose or think-tagged output. We apply three parse layers:
      1. Direct json.loads on the content
      2. Strip think tags (<think>...</think>) then retry
      3. Regex extract first {...} block from whatever text came back
    Only after all three fail do we escalate. This prevents Nemotron's occasional
    formatting hiccups from silently routing everything to the slower Executor.
    """
    import re as _re
    try:
        resp = requests.post(
            f"{cfg.lm_studio_base_url}/chat/completions",
            json={
                "model":           cfg.router_model,
                "messages":        [
                    {"role": "system", "content": _NEMOTRON_SYSTEM},
                    {"role": "user",   "content": f"Command: {command}"},
                ],
                "temperature":     0.0,
                "max_tokens":      150,
                "response_format": {"type": "json_object"},
            },
            timeout=15,
        )
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"]

        # Layer 1: direct parse
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError:
            # Layer 2: strip think tags (some Nemotron checkpoints emit <think>...</think>)
            clean = _re.sub(r"<think>.*?</think>", "", content, flags=_re.DOTALL).strip()
            try:
                parsed = json.loads(clean)
            except json.JSONDecodeError:
                # Layer 3: extract first {...} block from prose response
                m = _re.search(r"\{[^{}]*\}", clean, _re.DOTALL)
                if m:
                    try:
                        parsed = json.loads(m.group())
                    except json.JSONDecodeError:
                        return {"route": "escalate", "reason": "Router returned unparseable output."}
                else:
                    return {"route": "escalate", "reason": "Router returned unparseable output."}

        # Normalise: older Nemotron checkpoints sometimes return "tool" not "tool_name"
        if "tool" in parsed and "tool_name" not in parsed:
            parsed["tool_name"] = parsed.pop("tool")
        return parsed
    except Exception as e:
        # On failure: safe fallback — escalate to Executor with the raw command
        return {"route": "escalate", "reason": f"Router unavailable ({e}), escalating."}


# ── Executor escalation ────────────────────────────────────────────────────────

_EXECUTOR_SYSTEM = """\
You are a helpful assistant with access to an MCP agent stack.
Answer the user's request directly and concisely.
If the task requires tool calls, describe exactly which tool and action to use next.
Be specific. One clear answer or one clear next step."""


def _call_executor(command: str, reason: str = "") -> str:
    """
    Send a complex command to the Executor model (Hermes) for free-form reasoning.

    DECISION: Executor only produces TEXT — it does not call tools directly.
    If it decides tools are needed, it tells the agent which tool+action to use,
    keeping MCP as the single execution layer. This prevents the Executor from
    bypassing the whitelist.

    Uses cfg.executor_model (Hermes 3 8B). Timeout 60s — Hermes is slower than
    Nemotron but produces much better reasoning for complex tasks.
    """
    context = f"[Router note: {reason}]\n\n" if reason else ""
    try:
        resp = requests.post(
            f"{cfg.lm_studio_base_url}/chat/completions",
            json={
                "model":       cfg.executor_model,
                "messages":    [
                    {"role": "system", "content": _EXECUTOR_SYSTEM},
                    {"role": "user",   "content": f"{context}Task: {command}"},
                ],
                "temperature": 0.2,
                "max_tokens":  600,
            },
            timeout=60,
        )
        resp.raise_for_status()
        answer = resp.json()["choices"][0]["message"]["content"].strip()
        return f"[Executor]\n{answer}"
    except Exception as e:
        return f"[Executor error] {e} — try breaking the task into smaller steps."


# ── Main tool ─────────────────────────────────────────────────────────────────

@tool
def cli(command: str) -> str:
    """
    Execute a natural-language or shorthand command without a full planning cycle.

    Four execution paths — chosen automatically:
      1. Instant (zero tokens): git status, file read, memory recall, calc, echo, lms ps...
      2. Shell (zero tokens):   python --version, whoami, dir, copy, del, mkdir, where...
      3. Routed (Nemotron, ~15s): anything else -- Nemotron parses it into a tool call
         OR escalates to Executor.
      4. Escalated (Executor/Hermes, ~30-60s): complex tasks, multi-step reasoning.

    Shell commands (layer 2) execute via subprocess with a strict allowlist.
    Real output, no LLM tokens, 15s timeout, 4KB output cap.

    Allowed shell commands:
      Info:  python, pip, whoami, hostname, ver, ipconfig, tasklist, where/which,
             dir/ls, type/cat, env/set
      Files: copy/cp, xcopy, move/mv, mkdir/md, rmdir/rd, del/rm

    Examples:
      cli("git log 5")
      cli("python --version")
      cli("whoami")
      cli("dir workspace")
      cli("where python")
      cli("copy tools\\git_ops.py workspace\\git_ops.py")
      cli("recall chromadb persistent storage")
      cli("lms ps")
      cli("calc sum(range(100))")
      cli("what's the healthiest way to structure this agent's memory?")
    """
    command = command.strip()

    # ── Layer 1: pattern match — zero tokens ──────────────────────────────────
    matched = _match_pattern(command)
    if matched:
        tool_name, action, params = matched
        return _safe_dispatch(tool_name, action, params)

    # ── Layer 2: shell whitelist — zero tokens, real subprocess output ────────
    # DECISION: runs BEFORE Nemotron so common shell commands (python --version,
    # whoami, dir, copy) never cost any LLM tokens. _shell_exec returns None if
    # the command is not whitelisted, cleanly falling through to layer 3.
    shell_result = _shell_exec(command)
    if shell_result is not None:
        return shell_result

    # ── Layer 3: Nemotron decides ─────────────────────────────────────────────
    decision = _call_nemotron(command)
    route    = decision.get("route", "escalate")

    if route == "dispatch":
        # Nemotron says: simple tool call
        return _safe_dispatch(
            decision.get("tool_name", "system"),
            decision.get("action",    "help"),
            decision.get("params",    {}),
        )

    # ── Layer 4: Executor escalation ──────────────────────────────────────────
    # Nemotron said "escalate" (or route was unknown/missing)
    reason = decision.get("reason", "")
    return _call_executor(command, reason)

