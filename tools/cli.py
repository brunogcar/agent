"""
tools/cli.py — Fast natural-language CLI for the MCP agent stack.

LOCATION: D:/mcp/agent/tools/cli.py
RUN FROM:  D:/mcp/agent/   (so that `core` and `tools` are importable)
    python tools/cli.py "recall chromadb"
    python tools/cli.py "git log 5"
    python tools/cli.py health
    python tools/cli.py --raw "memory stats"

DESIGN — Two-tier dispatch to minimise token spend:
  Tier A — 27 regex pattern rules (zero tokens, works fully offline)
  Tier B — Nemotron 4B fallback (JSON-only prompt, ~20 tokens, <1 s)

DECISION: cli.py lives in tools/ alongside the other meta-tools so it is
co-located with the code it calls, but it is NOT registered with @tool
(it's a human-facing CLI entry-point, not an LLM-facing tool).

DECISION: --raw flag outputs raw JSON for scripting/piping.
DECISION: Colour output only when stdout is a TTY; plain when piped.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

# ── bootstrap: running from repo root allows all imports ─────────────────────
# DECISION: insert repo root so `core.*` and `tools.*` both resolve correctly
# regardless of whether the user cds into tools/ or runs from repo root.
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

try:
    from core.config import cfg
    from core.llm import call_llm
    AGENT_AVAILABLE = True
except ImportError:
    # Graceful degradation: pattern rules still work; LLM fallback disabled.
    AGENT_AVAILABLE = False
    cfg = None  # type: ignore[assignment]

# ── paths ─────────────────────────────────────────────────────────────────────
WORKSPACE: Path = Path(cfg.get("WORKSPACE_ROOT", "D:/mcp/workspace")) if cfg else Path("D:/mcp/workspace")
AGENT_ROOT: Path = _REPO_ROOT

# DECISION: Nemotron 4B is the router model — it is the smallest/fastest model
# in the stack, specifically used for classification and dispatch decisions.
ROUTER_MODEL: str = cfg.get("ROUTER_MODEL", "nvidia/nemotron-3-nano-4b") if cfg else "nvidia/nemotron-3-nano-4b"
ROUTER_TIMEOUT: int = 15

# ── colour helpers ────────────────────────────────────────────────────────────
IS_TTY: bool = sys.stdout.isatty()

def _c(text: str, code: str) -> str:
    return f"\033[{code}m{text}\033[0m" if IS_TTY else text

def green(t: str)  -> str: return _c(t, "32")
def yellow(t: str) -> str: return _c(t, "33")
def cyan(t: str)   -> str: return _c(t, "36")
def red(t: str)    -> str: return _c(t, "31")
def bold(t: str)   -> str: return _c(t, "1")
def dim(t: str)    -> str: return _c(t, "2")


# ╔══════════════════════════════════════════════════════════════════════════╗
# ║  TIER A — PATTERN MATCHING (zero tokens)                                 ║
# ╚══════════════════════════════════════════════════════════════════════════╝

_RULES: list[tuple[re.Pattern, Any]] = []

def _rule(pattern: str) -> Any:
    """Decorator that registers a regex → handler mapping."""
    def decorator(fn: Any) -> Any:
        _RULES.append((re.compile(pattern, re.IGNORECASE), fn))
        return fn
    return decorator


# ── HELP ──────────────────────────────────────────────────────────────────────

@_rule(r"^(help|\?)$")
def cmd_help(_m: re.Match) -> dict:
    lines = [
        bold("MCP Agent CLI — fast natural-language command interface"),
        "",
        bold("MEMORY"),
        "  recall <query>                       search all collections",
        "  recall <query> in <collection>       episodic | semantic | procedural",
        "  store <text>                         store to episodic (importance=5)",
        "  memory stats                         entry counts per collection",
        "  memory prune                         remove low-score entries",
        "",
        bold("WEB"),
        "  search <query>                       SearXNG web search",
        "  scrape <url>                         fetch and extract text from URL",
        "  research <query>                     search + scrape top results",
        "",
        bold("FILE"),
        "  read <path>  /  cat <path>           read file (first 40 lines)",
        "  ls [path]    /  list [path]          list directory contents",
        "  write <path> <content>               write file (backs up existing)",
        "  find <pat>   /  grep <pat>           full-text search workspace",
        "  compress <path>                      compress file or directory",
        "",
        bold("GIT"),
        "  git status                           working tree status",
        "  git log [n]                          last N commits (default 5)",
        "  git diff                             unstaged changes",
        "  git snapshot [msg]                   create rollback point",
        "  git commit <msg>                     commit all staged changes",
        "  git rollback                         undo all uncommitted changes",
        "",
        bold("PYTHON / EXEC"),
        "  run <code>                           sandbox Python (no imports)",
        "  calc <expr>                          evaluate arithmetic expression",
        "  exec <code>                          Python with full stdlib + pandas",
        "",
        bold("AGENT"),
        "  classify <text>                      router classification",
        "  summarize <text>                     one-sentence summary (Planner)",
        "",
        bold("NOTIFY"),
        "  notify <msg>  /  alert <msg>         desktop notification",
        "  ping <msg>                           alias for notify",
        "",
        bold("SYSTEM"),
        "  health                               LM Studio + memory status",
        "",
        bold("FLAGS"),
        "  --raw                                JSON output (for scripting)",
        "",
        dim("Unmatched commands fall back to Nemotron 4B (Tier B)."),
    ]
    return {"type": "help", "lines": lines}


# ── HEALTH ────────────────────────────────────────────────────────────────────

@_rule(r"^(health|status)$")
def cmd_health(_m: re.Match) -> dict:
    result: dict[str, Any] = {"type": "health"}

    # LM Studio reachability
    try:
        import urllib.request
        base = cfg.get("LM_STUDIO_BASE_URL", "http://localhost:1234/v1") if cfg else "http://localhost:1234/v1"
        with urllib.request.urlopen(f"{base}/models", timeout=3) as r:
            models = json.loads(r.read())
            result["lm_studio"] = "ok"
            result["loaded_models"] = [m["id"] for m in models.get("data", [])]
    except Exception as e:
        result["lm_studio"] = f"unreachable ({e})"

    # ChromaDB memory counts
    try:
        import chromadb
        db_path = cfg.get("MEMORY_ROOT", "D:/mcp/memory_db") if cfg else "D:/mcp/memory_db"
        client = chromadb.PersistentClient(path=str(Path(db_path) / "chroma"))
        counts: dict[str, int] = {}
        for col in ("episodic", "semantic", "procedural"):
            try:
                counts[col] = client.get_collection(col).count()
            except Exception:
                counts[col] = 0
        result["memory"] = counts
    except Exception as e:
        result["memory"] = f"unavailable ({e})"

    return result


# ── MEMORY STATS ──────────────────────────────────────────────────────────────

@_rule(r"^memory\s+stats$")
def cmd_memory_stats(_m: re.Match) -> dict:
    h = cmd_health(None)  # type: ignore[arg-type]
    return {"type": "memory_stats", "memory": h.get("memory", {})}


# ── MEMORY PRUNE ──────────────────────────────────────────────────────────────

@_rule(r"^memory\s+prune$")
def cmd_memory_prune(_m: re.Match) -> dict:
    try:
        from memory.store import MemoryStore
        pruned = MemoryStore().prune()
        return {"type": "memory_prune", "pruned": pruned}
    except Exception as e:
        return {"type": "error", "error": str(e)}


# ── RECALL ────────────────────────────────────────────────────────────────────

@_rule(r"^recall\s+(.+?)\s+in\s+(episodic|semantic|procedural)$")
def cmd_recall_in(m: re.Match) -> dict:
    return _do_recall(m.group(1), collections=[m.group(2)])

@_rule(r"^recall\s+(.+)$")
def cmd_recall(m: re.Match) -> dict:
    return _do_recall(m.group(1))

def _do_recall(query: str, collections: list[str] | None = None) -> dict:
    try:
        from memory.store import MemoryStore
        top_k = int(cfg.get("MEMORY_TOP_K", 5)) if cfg else 5
        results = MemoryStore().recall(query=query, collections=collections, top_k=top_k)
        return {"type": "recall", "query": query, "results": results}
    except Exception as e:
        return {"type": "error", "error": str(e)}


# ── STORE ─────────────────────────────────────────────────────────────────────

@_rule(r"^store\s+(.+)$")
def cmd_store(m: re.Match) -> dict:
    # DECISION: CLI stores default to episodic, importance=5 (neutral).
    # Full importance control is available through the memory() meta-tool.
    try:
        from memory.store import MemoryStore
        result = MemoryStore().store(memory_type="episodic", text=m.group(1), importance=5)
        return {"type": "store", "result": result}
    except Exception as e:
        return {"type": "error", "error": str(e)}


# ── WEB SEARCH ────────────────────────────────────────────────────────────────

@_rule(r"^search\s+(.+)$")
def cmd_search(m: re.Match) -> dict:
    try:
        from tools.web import web
        result = web(action="search", query=m.group(1), max_results=5)
        return {"type": "search", "query": m.group(1), **result}
    except Exception as e:
        return {"type": "error", "error": str(e)}


# ── SCRAPE ────────────────────────────────────────────────────────────────────

@_rule(r"^scrape\s+(https?://\S+)$")
def cmd_scrape(m: re.Match) -> dict:
    try:
        from tools.web import web
        result = web(action="scrape", url=m.group(1))
        return {"type": "scrape", "url": m.group(1), **result}
    except Exception as e:
        return {"type": "error", "error": str(e)}


# ── RESEARCH ──────────────────────────────────────────────────────────────────

@_rule(r"^research\s+(.+)$")
def cmd_research(m: re.Match) -> dict:
    try:
        from tools.web import web
        result = web(action="search_and_read", query=m.group(1), max_results=3)
        return {"type": "research", "query": m.group(1), **result}
    except Exception as e:
        return {"type": "error", "error": str(e)}


# ── FILE READ ─────────────────────────────────────────────────────────────────

@_rule(r"^(?:read|cat|show)\s+(.+)$")
def cmd_read(m: re.Match) -> dict:
    try:
        from tools.file_ops import file
        result = file(action="read", path=m.group(1).strip())
        return {"type": "file_read", "path": m.group(1).strip(), **result}
    except Exception as e:
        return {"type": "error", "error": str(e)}


# ── FILE LIST ─────────────────────────────────────────────────────────────────

@_rule(r"^(?:ls|list)(?:\s+(.+))?$")
def cmd_ls(m: re.Match) -> dict:
    path = (m.group(1) or "").strip() or "."
    try:
        from tools.file_ops import file
        result = file(action="list", path=path)
        return {"type": "file_list", "path": path, **result}
    except Exception as e:
        return {"type": "error", "error": str(e)}


# ── FILE WRITE ────────────────────────────────────────────────────────────────

@_rule(r"^write\s+(\S+)\s+(.+)$")
def cmd_write(m: re.Match) -> dict:
    try:
        from tools.file_ops import file
        result = file(action="write", path=m.group(1), content=m.group(2))
        return {"type": "file_write", "path": m.group(1), **result}
    except Exception as e:
        return {"type": "error", "error": str(e)}


# ── FILE FIND / GREP ──────────────────────────────────────────────────────────

@_rule(r"^(?:find|grep)\s+(.+)$")
def cmd_find(m: re.Match) -> dict:
    try:
        from tools.file_ops import file
        result = file(action="search", query=m.group(1))
        return {"type": "file_search", "query": m.group(1), **result}
    except Exception as e:
        return {"type": "error", "error": str(e)}


# ── FILE COMPRESS ─────────────────────────────────────────────────────────────

@_rule(r"^compress\s+(.+)$")
def cmd_compress(m: re.Match) -> dict:
    try:
        from tools.file_ops import file
        result = file(action="backup", path=m.group(1).strip())
        return {"type": "compress", "path": m.group(1).strip(), **result}
    except Exception as e:
        return {"type": "error", "error": str(e)}


# ── GIT STATUS ────────────────────────────────────────────────────────────────

@_rule(r"^git\s+status$")
def cmd_git_status(_m: re.Match) -> dict:
    try:
        from tools.git_ops import git
        result = git(operation="status")
        return {"type": "git_status", **result}
    except Exception as e:
        return {"type": "error", "error": str(e)}


# ── GIT LOG ───────────────────────────────────────────────────────────────────

@_rule(r"^git\s+log(?:\s+(\d+))?$")
def cmd_git_log(m: re.Match) -> dict:
    n = int(m.group(1)) if m.group(1) else 5
    try:
        from tools.git_ops import git
        result = git(operation="log", n=n)
        return {"type": "git_log", "n": n, **result}
    except Exception as e:
        return {"type": "error", "error": str(e)}


# ── GIT DIFF ──────────────────────────────────────────────────────────────────

@_rule(r"^git\s+diff$")
def cmd_git_diff(_m: re.Match) -> dict:
    try:
        from tools.git_ops import git
        result = git(operation="diff")
        return {"type": "git_diff", **result}
    except Exception as e:
        return {"type": "error", "error": str(e)}


# ── GIT SNAPSHOT ──────────────────────────────────────────────────────────────

@_rule(r"^git\s+snapshot(?:\s+(.+))?$")
def cmd_git_snapshot(m: re.Match) -> dict:
    msg = (m.group(1) or "cli snapshot").strip()
    try:
        from tools.git_ops import git
        result = git(operation="snapshot", message=msg)
        return {"type": "git_snapshot", "message": msg, **result}
    except Exception as e:
        return {"type": "error", "error": str(e)}


# ── GIT COMMIT ────────────────────────────────────────────────────────────────

@_rule(r"^git\s+commit\s+(.+)$")
def cmd_git_commit(m: re.Match) -> dict:
    try:
        from tools.git_ops import git
        result = git(operation="commit", message=m.group(1).strip())
        return {"type": "git_commit", **result}
    except Exception as e:
        return {"type": "error", "error": str(e)}


# ── GIT ROLLBACK ──────────────────────────────────────────────────────────────

@_rule(r"^git\s+rollback$")
def cmd_git_rollback(_m: re.Match) -> dict:
    try:
        from tools.git_ops import git
        result = git(operation="rollback")
        return {"type": "git_rollback", **result}
    except Exception as e:
        return {"type": "error", "error": str(e)}


# ── PYTHON RUN (sandbox) ──────────────────────────────────────────────────────

@_rule(r"^run\s+(.+)$")
def cmd_run(m: re.Match) -> dict:
    try:
        from tools.python_exec import python
        result = python(mode="run", code=m.group(1))
        return {"type": "python_run", **result}
    except Exception as e:
        return {"type": "error", "error": str(e)}


# ── CALC ──────────────────────────────────────────────────────────────────────

@_rule(r"^calc\s+(.+)$")
def cmd_calc(m: re.Match) -> dict:
    # DECISION: calc always uses sandbox mode — arithmetic never needs imports.
    expr = m.group(1).strip()
    try:
        from tools.python_exec import python
        result = python(mode="run", code=f"print({expr})")
        return {"type": "calc", "expr": expr, **result}
    except Exception as e:
        return {"type": "error", "error": str(e)}


# ── EXEC (full stdlib) ────────────────────────────────────────────────────────

@_rule(r"^exec\s+(.+)$")
def cmd_exec(m: re.Match) -> dict:
    try:
        from tools.python_exec import python
        result = python(mode="run_data", code=m.group(1))
        return {"type": "python_exec", **result}
    except Exception as e:
        return {"type": "error", "error": str(e)}


# ── CLASSIFY ──────────────────────────────────────────────────────────────────

@_rule(r"^classify\s+(.+)$")
def cmd_classify(m: re.Match) -> dict:
    # DECISION: classification uses the Router (Nemotron) since that is its
    # only job in the stack — task type, workflow selection, model assignment.
    if not AGENT_AVAILABLE:
        return {"type": "error", "error": "core.llm not available"}
    prompt = (
        'Classify this task. Output ONLY JSON: '
        '{"task_type": "...", "workflow": "...", "model": "..."}. '
        f'Task: {m.group(1)}'
    )
    try:
        raw = call_llm(model=ROUTER_MODEL, system="Output only JSON, no prose.",
                       user=prompt, timeout=ROUTER_TIMEOUT)
        data = json.loads(raw)
        return {"type": "classify", **data}
    except Exception as e:
        return {"type": "error", "error": str(e)}


# ── SUMMARIZE ─────────────────────────────────────────────────────────────────

@_rule(r"^summarize\s+(.+)$")
def cmd_summarize(m: re.Match) -> dict:
    # DECISION: summarization uses the Planner (Qwen) — it is the synthesis model.
    if not AGENT_AVAILABLE:
        return {"type": "error", "error": "core.llm not available"}
    planner = cfg.get("PLANNER_MODEL", "qwen/qwen3.5-9b") if cfg else "qwen/qwen3.5-9b"
    try:
        raw = call_llm(model=planner, system="Reply with exactly one sentence summary.",
                       user=m.group(1), timeout=30)
        return {"type": "summarize", "summary": raw.strip()}
    except Exception as e:
        return {"type": "error", "error": str(e)}


# ── NOTIFY / ALERT / PING ─────────────────────────────────────────────────────

@_rule(r"^(?:notify|alert|ping)\s+(.+)$")
def cmd_notify(m: re.Match) -> dict:
    try:
        from tools.notify import notify
        result = notify(action="send", message=m.group(1).strip())
        return {"type": "notify", **result}
    except Exception as e:
        return {"type": "error", "error": str(e)}


# ╔══════════════════════════════════════════════════════════════════════════╗
# ║  TIER B — NEMOTRON FALLBACK                                              ║
# ╚══════════════════════════════════════════════════════════════════════════╝

# DECISION: Tier B is only reached when all 27 Tier A patterns fail.
# Nemotron is prompted to output ONLY a JSON dispatch object so the CLI
# can call the right tool without any further LLM reasoning.

FALLBACK_SYSTEM = """\
You are a command dispatcher. Given a natural language command, output ONLY a
JSON object identifying the tool call. No prose, no explanation.

Format:
{
  "tool": "memory|web|file|git|python|notify|classify|summarize",
  "action": "<action string>",
  "params": { "<key>": "<value>" }
}

Examples:
  "what do you know about chromadb" → {"tool":"memory","action":"recall","params":{"query":"chromadb"}}
  "show recent commits"             → {"tool":"git","action":"log","params":{"n":5}}
  "find files about redis"          → {"tool":"file","action":"search","params":{"query":"redis"}}
"""

def _tier_b_fallback(command: str) -> dict:
    if not AGENT_AVAILABLE:
        return {"type": "error", "error": f"No pattern matched '{command}' and core.llm is unavailable."}

    try:
        raw = call_llm(model=ROUTER_MODEL, system=FALLBACK_SYSTEM,
                       user=command, timeout=ROUTER_TIMEOUT)
        dispatch = json.loads(raw)
    except Exception as e:
        return {"type": "error", "error": f"Tier B parse failed: {e}", "raw": raw if 'raw' in dir() else ""}

    tool   = dispatch.get("tool", "")
    action = dispatch.get("action", "")
    params = dispatch.get("params", {})

    # Re-enter Tier A by reconstructing a canonical command string
    # DECISION: reconstruct a simple command and re-dispatch rather than
    # duplicating tool-call logic here. Keeps fallback thin.
    canonical_map = {
        ("memory",   "recall"):    lambda p: f"recall {p.get('query', '')}",
        ("memory",   "store"):     lambda p: f"store {p.get('text', '')}",
        ("memory",   "stats"):     lambda _: "memory stats",
        ("web",      "search"):    lambda p: f"search {p.get('query', '')}",
        ("web",      "scrape"):    lambda p: f"scrape {p.get('url', '')}",
        ("web",      "search_and_read"): lambda p: f"research {p.get('query', '')}",
        ("file",     "read"):      lambda p: f"read {p.get('path', '')}",
        ("file",     "list"):      lambda p: f"ls {p.get('path', '')}",
        ("file",     "search"):    lambda p: f"find {p.get('query', '')}",
        ("git",      "status"):    lambda _: "git status",
        ("git",      "log"):       lambda p: f"git log {p.get('n', 5)}",
        ("git",      "diff"):      lambda _: "git diff",
        ("git",      "snapshot"):  lambda p: f"git snapshot {p.get('message', '')}",
        ("git",      "commit"):    lambda p: f"git commit {p.get('message', '')}",
        ("git",      "rollback"):  lambda _: "git rollback",
        ("python",   "run"):       lambda p: f"run {p.get('code', '')}",
        ("python",   "run_data"):  lambda p: f"exec {p.get('code', '')}",
        ("notify",   "send"):      lambda p: f"notify {p.get('message', '')}",
        ("classify", "classify"):  lambda p: f"classify {p.get('text', '')}",
        ("summarize","summarize"): lambda p: f"summarize {p.get('text', '')}",
    }

    builder = canonical_map.get((tool, action))
    if builder:
        reconstructed = builder(params)
        return _dispatch(reconstructed)

    return {"type": "error", "error": f"Tier B: unknown tool/action '{tool}/{action}'"}


# ╔══════════════════════════════════════════════════════════════════════════╗
# ║  DISPATCHER                                                              ║
# ╚══════════════════════════════════════════════════════════════════════════╝

def _dispatch(command: str) -> dict:
    """Try each Tier A rule; fall through to Tier B if nothing matches."""
    cmd = command.strip()
    for pattern, handler in _RULES:
        m = pattern.match(cmd)
        if m:
            return handler(m)
    return _tier_b_fallback(cmd)


# ╔══════════════════════════════════════════════════════════════════════════╗
# ║  RENDERERS — tool-aware pretty printing                                  ║
# ╚══════════════════════════════════════════════════════════════════════════╝

def _render(result: dict, raw: bool) -> None:
    if raw:
        print(json.dumps(result, indent=2, default=str))
        return

    t = result.get("type", "")

    if t == "help":
        for line in result["lines"]:
            print(line)

    elif t == "health":
        lm = result.get("lm_studio", "?")
        icon = green("●") if lm == "ok" else red("●")
        print(f"{icon} LM Studio: {lm}")
        for mid in result.get("loaded_models", []):
            print(f"  {dim('└')} {mid}")
        mem = result.get("memory", {})
        if isinstance(mem, dict):
            print(f"\n{bold('Memory')}")
            for col, cnt in mem.items():
                bar = "█" * min(cnt // 5, 20)
                print(f"  {cyan(col):20s} {cnt:>4}  {dim(bar)}")
        else:
            print(f"  memory: {mem}")

    elif t == "memory_stats":
        mem = result.get("memory", {})
        if isinstance(mem, dict):
            for col, cnt in mem.items():
                bar = "█" * min(cnt // 5, 20)
                print(f"  {cyan(col):20s} {cnt:>4}  {dim(bar)}")
        else:
            print(mem)

    elif t == "recall":
        results = result.get("results", [])
        if not results:
            print(dim("  (no memories found)"))
            return
        for r in results:
            col   = r.get("collection", "?")
            score = r.get("score", 0)
            text  = r.get("text", "")
            bar   = "█" * int(score)
            print(f"  [{cyan(col)}] score={yellow(f'{score:.1f}')}  {dim(bar)}")
            print(f"  {text[:120]}")
            print()

    elif t in ("search", "research"):
        for item in result.get("results", []):
            print(f"  {bold(item.get('title', ''))}")
            print(f"  {cyan(item.get('url', ''))}")
            print(f"  {item.get('snippet', item.get('text', ''))[:160]}")
            print()

    elif t == "scrape":
        text = result.get("text", "")
        wc   = result.get("word_count", "?")
        print(f"{dim(f'[{wc} words]')} {result.get('title', '')}")
        print(text[:2000])

    elif t == "file_read":
        content = result.get("content", "")
        lines   = content.splitlines()[:40]
        for i, line in enumerate(lines, 1):
            print(f"  {dim(str(i).rjust(3))}  {line}")
        if len(content.splitlines()) > 40:
            print(dim(f"  ... ({len(content.splitlines())} total lines)"))

    elif t == "file_list":
        for entry in result.get("entries", result.get("files", [])):
            print(f"  {entry}")

    elif t == "file_search":
        for hit in result.get("hits", result.get("results", [])):
            print(f"  {cyan(hit.get('path', ''))}  {hit.get('snippet', '')[:100]}")

    elif t in ("file_write", "compress", "memory_prune", "store", "notify",
               "git_snapshot", "git_commit", "git_rollback"):
        status = result.get("status", "ok")
        icon   = green("✓") if status in ("ok", "success") else red("✗")
        msg    = result.get("message", result.get("result", json.dumps(result)))
        print(f"  {icon} {msg}")

    elif t == "git_status":
        print(result.get("output", result.get("status", "")))

    elif t == "git_log":
        for entry in result.get("commits", []):
            sha  = yellow(entry.get("sha", "")[:7])
            msg  = entry.get("message", "")
            date = dim(entry.get("date", ""))
            print(f"  {sha}  {msg}  {date}")

    elif t == "git_diff":
        diff = result.get("diff", result.get("output", ""))
        # Minimal colour for +/- lines
        for line in diff.splitlines():
            if line.startswith("+"):
                print(green(line))
            elif line.startswith("-"):
                print(red(line))
            else:
                print(line)

    elif t in ("python_run", "python_exec", "calc"):
        output = result.get("output", result.get("result", ""))
        print(f"  {output}")

    elif t == "classify":
        print(f"  task_type : {cyan(result.get('task_type', '?'))}")
        print(f"  workflow  : {result.get('workflow', '?')}")
        print(f"  model     : {result.get('model', '?')}")

    elif t == "summarize":
        print(f"  {result.get('summary', '')}")

    elif t == "error":
        print(red(f"  error: {result.get('error', result)}"))

    else:
        # Generic fallback: pretty-print the dict
        print(json.dumps(result, indent=2, default=str))


# ╔══════════════════════════════════════════════════════════════════════════╗
# ║  ENTRY POINT                                                             ║
# ╚══════════════════════════════════════════════════════════════════════════╝

def main() -> None:
    args = sys.argv[1:]

    raw = False
    if "--raw" in args:
        raw = True
        args = [a for a in args if a != "--raw"]

    if not args:
        print(f"Usage: python tools/cli.py [--raw] \"<command>\"")
        print(f"       python tools/cli.py help")
        sys.exit(0)

    command = " ".join(args)

    t0 = time.monotonic()
    result = _dispatch(command)
    elapsed = time.monotonic() - t0

    _render(result, raw)

    if not raw and result.get("type") != "help":
        tier = dim(f"[{elapsed*1000:.0f}ms]")
        print(f"\n{tier}")


if __name__ == "__main__":
    main()
