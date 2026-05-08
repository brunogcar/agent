"""
apply_token_opt_patches_v3.py — Exact-match patches for current repo state.
"""
from __future__ import annotations
import ast, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent

def patch(filepath, old, new, label):
    p = ROOT / filepath
    if not p.exists():
        print(f"  SKIP  {label} -- file not found ({filepath})"); return False
    content = p.read_text(encoding="utf-8")
    if old not in content:
        first = new.strip().splitlines()[0].strip()
        if first in content:
            print(f"  SKIP  {label} -- already applied"); return True
        print(f"  MISS  {label} -- target not found in {filepath}")
        print(f"         First search line: {old.splitlines()[0][:80]}")
        return False
    updated = content.replace(old, new)
    try: ast.parse(updated)
    except SyntaxError as e:
        print(f"  FAIL  {label} -- syntax error: {e}"); return False
    p.write_text(updated, encoding="utf-8")
    print(f"  OK    {label}"); return True

print("=== Token optimisation patches v3 ===\n")

# 1. file_ops: error message (read from live repo)
patch(
    "tools/file_ops.py",
    '"read | write | list | backup | read_many | search | compress"',
    '"read | write | patch | list | backup | read_many | search | compress"',
    "file_ops: add patch to error message",
)

# 2. autocode: CODER_SYSTEM (the current prompt in your repo)
patch(
    "workflows/autocode.py",
    '''CODER_SYSTEM = """\\
You are the Executor model acting as a focused Python developer.

Rules:
- Implement ONLY what is described in the current step.
- Make the tests pass -- no more, no less (YAGNI).
- If modifying an existing file, reproduce the ENTIRE file content.
- Output JSON ONLY:
  {"files": {"<relative/path.py>": "<full file content>"}, "explanation": "<one sentence>"}
No prose before or after the JSON."""''',
    '''CODER_SYSTEM = """\\
You are the Executor model acting as a focused Python developer.

CRITICAL: Prefer targeted patches over full file rewrites to save tokens.

For EXISTING files -- output patches (str_replace):
  {
    "patches": [
      {"path": "<file>", "old": "<exact existing text>", "new": "<replacement>"},
      ...
    ],
    "new_files": {},
    "explanation": "<one sentence>"
  }
  - old must be the EXACT text from the file (copy-paste, do not paraphrase).
  - old must be unique enough to appear only once -- include surrounding lines.
  - Multiple patches to the same file are applied sequentially.

For NEW files -- use new_files:
  {
    "patches": [],
    "new_files": {"<relative/path.py>": "<full file content>"},
    "explanation": "<one sentence>"
  }

If you must rewrite a whole existing file (major restructure only):
  put it in new_files with the same path -- it will overwrite.

Output ONLY the JSON. No prose before or after."""''',
    "autocode: CODER_SYSTEM uses patch-first output",
)

print("\nDone.")