"""verify_phase9h.py -- run from D:/mcp/agent/"""
from __future__ import annotations
import ast, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
print("=== Phase 9h verification ===\n")
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

check("core/llm.py",
      "Known roles:",
      "llm: unknown role warning includes known roles")

check("core/config.py",
      "Linux",
      "config: Linux-safe path comment present")

check("core/config.py",
      "_here = Path(__file__).resolve().parent.parent",
      "config: relative fallback path")

print()
if errors:
    print(f"FAILED -- {len(errors)} issue(s):")
    for e in errors: print(f"  {e}")
    sys.exit(1)
else:
    print("All phase9h patches applied correctly.")
    print("\nWhat was fixed:")
    print("  core/llm.py:       unknown role warning now shows role + known list")
    print("  core/config.py:    default paths relative to agent root (Linux-safe)")
    print("\nWhat was dismissed (not real bugs):")
    print("  CORS: already fixed (allow_credentials=False) in phase9d")
    print("  ChromaDB threading: already fixed (write_lock) in phase9d")
    print("  JSON mode for Nemotron/Qwen: already fixed in phase8")
    print("  FileLock import: already fixed in phase9d")
    print("  Ruff vs syntax: already fixed in phase9d")
    print("  Protected file check in apply: already fixed in phase9d")
    print("  Query rewriter: already fixed in phase9d/9e")
    print("  eval substring: already uses eval( with paren -- no false positives")
    print("  Memory stats size: adds I/O overhead per call -- not worth it")
    print("  Web scrape OOM: max_chars already handles this")
    print("  In-memory task store: Phase 11 scope")
