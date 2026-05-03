"""
verify_phase9f.py -- run from D:/mcp/agent/
Confirms all phase9f patches are applied correctly.
"""
from __future__ import annotations
import ast, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
print("=== Phase 9f verification ===\n")

errors = []

def check(filepath: str, must_contain: str, label: str) -> None:
    p = ROOT / filepath
    if not p.exists():
        errors.append(f"MISSING {filepath}")
        return
    content = p.read_text(encoding="utf-8")
    # Syntax check
    if filepath.endswith(".py"):
        try:
            ast.parse(content)
        except SyntaxError as e:
            errors.append(f"SYNTAX ERROR in {filepath}: {e}")
            return
    if must_contain in content:
        print(f"  OK  {label}")
    else:
        errors.append(f"NOT FOUND in {filepath}: {label!r}")
        print(f"  FAIL {label}")

# 1. Gateway dev-mode warning
check("gateway/app.py",
      '[SECURITY] Gateway in DEVELOPMENT MODE',
      "gateway: dev-mode security warning")

# 2. Adaptive fetch multiplier
check("memory/store.py",
      "fetch_multiplier = max(2, 5 - top_k // 5)",
      "memory: adaptive fetch multiplier")

# 3. Procedural prune doc
check("memory/store.py",
      "AUTOMATIC pruning",
      "memory: procedural prune doc clarified")

# 4. Exponential backoff
check("workflows/autocode.py",
      "Exponential backoff: retry 1=2s",
      "autocode: exponential backoff")

# 5. Protected files expanded
check("core/config.py",
      '"memory/store.py"',
      "config: memory/store.py protected")
check("core/config.py",
      '"gateway/app.py"',
      "config: gateway/app.py protected")
check("core/config.py",
      '"core/llm.py"',
      "config: core/llm.py protected")

print()
if errors:
    print(f"FAILED -- {len(errors)} issue(s):")
    for e in errors:
        print(f"  {e}")
    sys.exit(1)
else:
    print("All phase9f patches applied correctly.")
    print("\nSummary of improvements:")
    print("  gateway/app.py:        dev-mode warning on every request")
    print("  memory/store.py:       adaptive fetch (2-4x instead of always 4x)")
    print("  memory/store.py:       procedural prune behaviour documented clearly")
    print("  workflows/autocode.py: exponential backoff (2s/4s/8s between retries)")
    print("  core/config.py:        protected files expanded (llm.py, store.py, app.py)")
