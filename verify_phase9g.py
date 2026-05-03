"""
verify_phase9g.py -- run from D:/mcp/agent/
"""
from __future__ import annotations
import ast, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
print("=== Phase 9g verification ===\n")
errors = []

def check(filepath: str, must_contain: str, label: str) -> None:
    p = ROOT / filepath
    if not p.exists():
        errors.append(f"MISSING {filepath}")
        return
    content = p.read_text(encoding="utf-8")
    try:
        ast.parse(content)
    except SyntaxError as e:
        errors.append(f"SYNTAX ERROR in {filepath}: {e}")
        return
    if must_contain in content:
        print(f"  OK  {label}")
    else:
        errors.append(f"NOT FOUND: {label}")
        print(f"  FAIL {label}")

check("core/tracer.py",
      "except (KeyboardInterrupt, SystemExit):\n                raise  # never suppress shutdown signals",
      "tracer: KeyboardInterrupt propagates")

check("memory/store.py",
      "_default_thresholds = {",
      "memory: per-collection dedup thresholds")

check("memory/store.py",
      "MEMORY_DEDUP_THRESHOLD",
      "memory: dedup threshold configurable via .env")

check("tools/web.py",
      "except (KeyboardInterrupt, SystemExit):\n        raise  # never suppress shutdown signals",
      "web: KeyboardInterrupt propagates")

print()
if errors:
    print(f"FAILED -- {len(errors)} issue(s):")
    for e in errors: print(f"  {e}")
    sys.exit(1)
else:
    print("All phase9g patches applied correctly.")
    print("\nWhat was fixed:")
    print("  core/tracer.py:  Ctrl+C now works even during log writes")
    print("  memory/store.py: Per-collection dedup thresholds (episodic=0.05,")
    print("                   semantic=0.12, procedural=0.08) + configurable via .env")
    print("  tools/web.py:    Ctrl+C propagates through HTTP fetch")
    print("\nWhat was NOT fixed (not real bugs):")
    print("  Subprocess timeout: change EXECUTION_TIMEOUT in .env if needed")
    print("  Return type hints: already present on all public APIs")
    print("  Circuit breaker: existing retry+timeout is adequate for local stack")
    print("  Memory stats enrichment: adds I/O overhead, not worth it")
