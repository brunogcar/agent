"""
apply_phase9h_patches.py -- run from D:/mcp/agent/

Phase 9h: final cleanup.

  1. core/llm.py:          silent fallback now logs role name + known roles
  2. core/config.py:       Linux-safe default paths (relative fallback)
  3. tools/python_exec.py: document that forbidden tokens already use paren form
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
        if new.strip().splitlines()[0].strip() in content:
            print(f"  SKIP  {label} -- already applied"); return True
        print(f"  MISS  {label} -- target not found in {filepath}"); return False
    updated = content.replace(old, new)
    try:
        ast.parse(updated)
    except SyntaxError as e:
        print(f"  FAIL  {label} -- syntax error: {e}"); return False
    p.write_text(updated, encoding="utf-8")
    print(f"  OK    {label}"); return True


print("=== Phase 9h patches ===\n")

# 1. llm.py: silent fallback now includes role name and known roles
patch(
    "core/llm.py",
    "            print(f\"[llm] WARNING: unknown role '{role}', falling back to executor\", file=__import__(\"sys\").stderr)",
    """            import sys as _sys
            known = sorted(self._roles.keys())
            print(
                f"[llm] WARNING: unknown role {role!r} -- falling back to executor. "
                f"Known roles: {known}",
                file=_sys.stderr,
            )""",
    "llm: unknown role warning includes known roles list",
)

# 2. config.py: Linux-safe default paths
patch(
    "core/config.py",
    '        self.agent_root    = Path(os.getenv("AGENT_ROOT",    "D:/mcp/agent"))\n        self.workspace_root= Path(os.getenv("WORKSPACE_ROOT","D:/mcp/workspace"))\n        self.memory_root   = Path(os.getenv("MEMORY_ROOT",   "D:/mcp/memory_db"))',
    '        # Default paths are relative to agent root so they work on Linux\n        # without D:/... paths. Set AGENT_ROOT etc in .env to override.\n        _here = Path(__file__).resolve().parent.parent\n        self.agent_root    = Path(os.getenv("AGENT_ROOT",     str(_here)))\n        self.workspace_root= Path(os.getenv("WORKSPACE_ROOT", str(_here / "workspace")))\n        self.memory_root   = Path(os.getenv("MEMORY_ROOT",    str(_here / "memory_db")))',
    "config: Linux-safe default paths",
)

# 3. python_exec.py: verify forbidden tokens use paren form (document only)
from pathlib import Path as _P
_pe = _P("tools/python_exec.py")
if _pe.exists():
    src = _pe.read_text()
    if '"eval("' in src or "'eval('" in src:
        print("  OK    python_exec: FORBIDDEN_IN_SANDBOX already uses eval( form")
    else:
        print("  NOTE  python_exec: check FORBIDDEN_IN_SANDBOX manually")

print("\nDone. Run: python verify_phase9h.py to confirm.")
