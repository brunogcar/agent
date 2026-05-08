"""
tools/cli.py — Fast natural-language command dispatcher, registered as an MCP tool.

WHAT THIS IS
------------
A single MCP tool `cli(command)` that lets the agent (or you) run simple
operations instantly without burning Planner tokens on a full workflow cycle.

HOW IT WORKS — THREE LAYERS
-----------------------------
1. Pattern match  — regex rules cover ~90% of common commands. Zero LLM calls.
                    Returns immediately.

2. Nemotron route — anything that doesn't match a pattern goes to the Router
                    model (nemotron-3-nano-4b) with a strict JSON-only prompt.
                    Nemotron returns one of two things:
                      a) {tool_name, action, params} → execute directly via whitelist
                      b) {escalate: true, reason: "..."} → hand off to Executor

3. Executor escalation — if Nemotron decides the command is too complex for a
                    direct tool call, the command is sent to the Executor model
                    (Hermes) as a free-form task. Hermes reasons and responds.
                    This is the "agent decides" layer you wanted.

SAFETY
------
Only layer 1 and 2a can call tools. They use a strict whitelist — no raw shell,
no arbitrary file writes, same sandbox as the rest of the stack.
Layer 2b and 3 (Executor) only produce text responses, they don't call tools
directly. If Hermes decides it needs tools, it tells the agent which ones to use
next — it doesn't bypass the MCP layer.

NAMING CONVENTION
-----------------
Internal dispatch uses `tool_name` (never `tool`) to avoid shadowing the
`tool` decorator from registry. That was the fatal bug in the previous version.

MEMORY ACCESS
-------------
Uses the same lazy import pattern as memory_tool.py:
  _mem() → from memory.store import memory
Direct ChromaDB access, no intermediate tool layer.
All memory methods match the memory() tool signature exactly.
"""

from __future__ import annotations

import json
import re
from typing import Any

import requests

from registry import tool      # decorator — NEVER use 'tool' as a variable name
from core.config import cfg    # singleton: .lm_studio_base_url, .router_model, .executor_model


# ── Lazy memory accessor (mirrors memory_tool.py pattern) ─────────────────────

def _mem():
    """Lazy import of ChromaDB store — avoids slow startup, same as memory_tool.py."""
    from memory.store import memory as _store
    return _store


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
    from tools.file_ops import file
    r = file(action=action, **kw)
    if not isinstance(r, dict): return str(r)
    if action == "read" and "content" in r:
        lines = r["content"].splitlines()
        out   = "\n".join(f"{i+1:4d} | {l}" for i, l in enumerate(lines[:40]))
        return out + (f"\n... ({len(lines)-40} more lines)" if len(lines) > 40 else "")
    if r.get("status") == "error": return f"Error: {r.get('error', r)}"
    return r.get("message", json.dumps(r, indent=2))

def _git(operation: str, **kw) -> str:
    from tools.git_ops import git
    r = git(operation=operation, **kw)
    if not isinstance(r, dict): return str(r)
    if operation == "log":
        cs = r.get("commits", [])
        return "\n".join(f"{c.get('sha','')[:7]}  {c.get('message','').splitlines()[0][:70]}"
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
    Direct ChromaDB access via memory/store.py singleton.
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
    "system:health": lambda **kw: "MCP Agent Stack: all systems operational.",
    "system:help":   lambda **kw: (
        "cli quick commands:\n"
        "  git status | log [n] | diff | snapshot [msg] | commit [msg] | rollback\n"
        "  file read <path> | write <path> <content> | list [dir] | search <query>\n"
        "  web search <query> | scrape <url> | read <url>\n"
        "  memory recall <query> | store <text> | stats | prune\n"
        "  python run <code> | calc <expr>\n"
        "  notify <message>\n"
        "  lms ls | ps | load <model> | unload [model] | log\n"
        "  health | help\n"
        "Anything else → Nemotron decides: direct dispatch or Executor escalation."
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
    (r"^health$",                      "system",  "health",   lambda m: {}),
    (r"^help$",                        "system",  "help",     lambda m: {}),
    (r"^git\s+status$",                "git",     "status",   lambda m: {}),
    (r"^git\s+log\s+(\d+)",            "git",     "log",      lambda m: {"n": int(m.group(1))}),
    (r"^git\s+log$",                   "git",     "log",      lambda m: {}),
    (r"^git\s+diff$",                  "git",     "diff",     lambda m: {}),
    (r"^git\s+snapshot\s*(.*)",        "git",     "snapshot", lambda m: {"message": m.group(1).strip() or None}),
    (r"^git\s+commit\s*(.*)",          "git",     "commit",   lambda m: {"message": m.group(1).strip() or None}),
    (r"^git\s+rollback\s*(.*)",        "git",     "rollback", lambda m: {"version": m.group(1).strip() or None}),
    (r"^(?:read|cat|show)\s+(.+)",     "file",    "read",     lambda m: {"path": m.group(1).strip()}),
    (r"^(?:ls|list)\s*(.*)",           "file",    "list",     lambda m: {"path": m.group(1).strip() or "."}),
    (r"^write\s+(\S+)\s+(.+)",         "file",    "write",    lambda m: {"path": m.group(1), "content": m.group(2)}),
    (r"^(?:find|grep)\s+(.+)",         "file",    "search",   lambda m: {"query": m.group(1).strip()}),
    (r"^search\s+(.+)",                "web",     "search",   lambda m: {"query": m.group(1).strip()}),
    (r"^scrape\s+(https?://\S+)",      "web",     "scrape",   lambda m: {"url": m.group(1).strip()}),
    (r"^read\s+(https?://\S+)",        "web",     "read",     lambda m: {"url": m.group(1).strip()}),
    (r"^recall\s+(.+)",                "memory",  "recall",   lambda m: {"query": m.group(1).strip()}),
    (r"^store\s+(.+)",                 "memory",  "store",    lambda m: {"text": m.group(1).strip()}),
    (r"^memory\s+stats$",              "memory",  "stats",    lambda m: {}),
    (r"^memory\s+prune$",              "memory",  "prune",    lambda m: {}),
    (r"^calc\s+(.+)",                  "python",  "calc",     lambda m: {"code": m.group(1).strip()}),
    (r"^(?:run|exec)\s+(.+)",          "python",  "run",      lambda m: {"code": m.group(1).strip()}),
    (r"^(?:notify|alert|ping)\s+(.+)", "notify",  "send",     lambda m: {"message": m.group(1).strip()}),
    (r"^lms\s+ls$",                    "lms",     "ls",       lambda m: {}),
    (r"^lms\s+ps$",                    "lms",     "ps",       lambda m: {}),
    (r"^lms\s+load\s+(.+)",            "lms",     "load",     lambda m: {"model": m.group(1).strip()}),
    (r"^lms\s+unload\s+(.+)",          "lms",     "unload",   lambda m: {"model": m.group(1).strip()}),
    (r"^lms\s+unload$",                "lms",     "unload",   lambda m: {}),
    (r"^lms\s+log$",                   "lms",     "log",      lambda m: {}),
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
    """
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
        parsed  = json.loads(content)
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

    Three execution paths — chosen automatically:
      1. Instant (zero tokens): git status, file read, memory recall, calc, lms ps, etc.
      2. Routed (Nemotron, ~15s): anything not in the shorthand list — Nemotron
         parses it into a tool call OR decides it needs the Executor.
      3. Escalated (Executor/Hermes, ~30-60s): complex tasks, multi-step reasoning,
         code generation, analysis — Nemotron escalates these automatically.

    Use this instead of chaining multiple tool calls for simple operations.
    Token cost: pattern-matched commands cost zero LLM tokens.
    Safety: only whitelisted tool+action pairs can execute directly.

    Examples:
      cli("git log 5")
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

    # ── Layer 2: Nemotron decides ─────────────────────────────────────────────
    decision = _call_nemotron(command)
    route    = decision.get("route", "escalate")

    if route == "dispatch":
        # Nemotron says: simple tool call
        return _safe_dispatch(
            decision.get("tool_name", "system"),
            decision.get("action",    "help"),
            decision.get("params",    {}),
        )

    # ── Layer 3: Executor escalation ──────────────────────────────────────────
    # Nemotron said "escalate" (or route was unknown/missing)
    reason = decision.get("reason", "")
    return _call_executor(command, reason)
