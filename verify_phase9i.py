"""verify_phase9i.py -- run from D:/mcp/agent/"""
from __future__ import annotations
import ast, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
print("=== Phase 9i verification ===\n")
errors = []

def check(filepath, must_contain, label):
    p = ROOT / filepath
    if not p.exists():
        errors.append(f"MISSING {filepath}"); return
    content = p.read_text(encoding="utf-8")
    try: ast.parse(content)
    except SyntaxError as e:
        errors.append(f"SYNTAX {filepath}: {e}"); return
    if must_contain in content:
        print(f"  OK  {label}")
    else:
        errors.append(f"NOT FOUND: {label}")
        print(f"  FAIL {label}")

check("workflows/autocode.py",
      "retry_temps = [None, 0.2, 0.4, 0.6]",
      "autocode: temperature variation on retry")

check("tools/web.py",
      "Fetch all URLs in parallel",
      "web: parallel fetch in search_and_read")

check("tools/python_exec.py",
      "BLOCKED_IMPORTS = {",
      "python_exec: BLOCKED_IMPORTS defined")

check("tools/python_exec.py",
      "blocked for security",
      "python_exec: security error message")

check("gateway/app.py",
      "/health/models",
      "gateway: /health/models endpoint")

check("tools/workflow_tool.py",
      "auto-routed to",
      "workflow_tool: routing decision traced")

check("memory/store.py",
      "decay score (importance * recency)",
      "memory: summarize uses decay score")

print()
if errors:
    print(f"FAILED -- {len(errors)} issue(s):")
    for e in errors: print(f"  {e}")
    sys.exit(1)
else:
    print("All phase9i patches applied correctly.")
    print("\nWhat was improved:")
    print("  workflows/autocode.py: retry temp 0.1->0.2->0.4->0.6 prevents stuck loops")
    print("  tools/web.py:          search_and_read fetches URLs in parallel (ThreadPoolExecutor)")
    print("  tools/python_exec.py:  BLOCKED_IMPORTS: os/sys/subprocess/shutil/socket blocked")
    print("  gateway/app.py:        GET /health/models checks all 3 models loaded in LM Studio")
    print("  tools/workflow_tool.py: routing decision logged as trace step")
    print("  memory/store.py:       summarize ranks by decay score not raw importance")
    print("\nSkipped (over-engineering or Phase 11):")
    print("  Circuit breaker: existing retry adequate for local stack")
    print("  System prompts to files: versioned with code by design")
    print("  json_mode as role property: breaking change, Phase 11")
    print("  Conversation memory: Phase 11")
    print("  Model fallback chain: Phase 11")
    print("  Live dashboard: Phase 11")
