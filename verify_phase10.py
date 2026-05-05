"""
verify_phase10.py -- run from D:/mcp/agent/
Confirms all phase10 patches applied and runs the unit test suite.
"""
from __future__ import annotations
import ast, sys, subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent
print("=== Phase 10 verification ===\n")
errors = []


def check(filepath, must_contain, label):
    p = ROOT / filepath
    if not p.exists():
        errors.append(f"MISSING {filepath}"); return
    content = p.read_text(encoding="utf-8")
    try:
        ast.parse(content)
    except SyntaxError as e:
        errors.append(f"SYNTAX {filepath}: {e}"); return
    if must_contain in content:
        print(f"  OK  {label}")
    else:
        errors.append(f"NOT FOUND: {label}")
        print(f"  FAIL {label}")


print("1. Patch checks")
check("gateway/app.py",   "gateway_tasks.db",        "gateway: SQLite task persistence")
check("gateway/app.py",   "_get_task(trace_id)",     "gateway: get_result uses SQLite")
check("gateway/app.py",   "/version",                "gateway: /version endpoint")
check("tools/file_ops.py","action == \"compress\"",  "file: compress action")
check("tools/memory_tool.py", "MAX_MEMORY_BYTES",    "memory_tool: 50KB input guard")

print()
if errors:
    print(f"Patch checks FAILED -- {len(errors)} issue(s):")
    for e in errors: print(f"  {e}")
    print()

print("2. Test files present")
test_files = [
    "tests/__init__.py",
    "tests/test_memory.py",
    "tests/test_tools.py",
    "tests/test_workflows.py",
]
for tf in test_files:
    p = ROOT / tf
    exists = p.exists()
    print(f"  {'OK' if exists else 'MISSING'} {tf}")
    if not exists:
        errors.append(f"MISSING {tf}")

print()
print("3. Running unit tests (pytest)")
result = subprocess.run(
    [sys.executable, "-m", "pytest", "tests/", "-v", "--tb=short", "-q"],
    cwd=str(ROOT),
    capture_output=False,
)
if result.returncode != 0:
    errors.append("pytest returned non-zero exit code")

print()
if errors:
    print(f"FAILED -- {len(errors)} total issue(s)")
    sys.exit(1)
else:
    print("=" * 55)
    print("Phase 10 complete.")
    print("=" * 55)
    print("\nWhat was added:")
    print("  gateway/app.py:        SQLite task persistence (gateway_tasks.db)")
    print("  gateway/app.py:        GET /version returns git commit + branch")
    print("  tools/file_ops.py:     file(action='compress') zips subfolders")
    print("  tools/memory_tool.py:  rejects text > 50KB with clear error")
    print("  tests/test_memory.py:  decay scoring, query rewriter, store/recall")
    print("  tests/test_tools.py:   sandbox, blocked imports, file safety, routing")
    print("  tests/test_workflows.py: state helpers, autocode routing, protected files")
