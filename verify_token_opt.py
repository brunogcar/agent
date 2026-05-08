"""
verify_token_opt.py — Smoke-test for the token optimisation changes.

Run from D:/mcp/agent/ after running apply_token_opt_patches.py.

Checks:
  1. core/patch.py imports cleanly and all three public symbols exist.
  2. apply_patch works correctly: success case, not-found, ambiguous.
  3. apply_patches works: multi-patch sequential apply, mid-failure abort.
  4. extract_relevant_sections returns a subset smaller than the original.
  5. file(action="patch") is wired in tools/file_ops.py (string check).
  6. autocode.py CODER_SYSTEM mentions "patches" (patch-first output format).
  7. autocode.py node_write_files handles "patches" key in JSON output.
  8. autocode.py _files_context accepts a hint= parameter.
"""

from __future__ import annotations
import sys, tempfile, textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

PASS = "  OK  "
FAIL = "  FAIL"
results: list[tuple[str, bool, str]] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    results.append((label, ok, detail))
    mark = PASS if ok else FAIL
    print(f"{mark}  {label}" + (f"  ({detail})" if detail else ""))


# ── 1. core/patch.py imports ─────────────────────────────────────────────────
print("\n── 1. core/patch.py imports ──")
try:
    from core.patch import apply_patch, apply_patches, extract_relevant_sections
    check("core.patch imports", True)
    check("apply_patch symbol", callable(apply_patch))
    check("apply_patches symbol", callable(apply_patches))
    check("extract_relevant_sections symbol", callable(extract_relevant_sections))
except ImportError as e:
    check("core.patch imports", False, str(e))
    print("  Cannot continue without core.patch — aborting.")
    sys.exit(1)


# ── 2. apply_patch unit tests ─────────────────────────────────────────────────
print("\n── 2. apply_patch unit tests ──")
with tempfile.TemporaryDirectory() as td:
    p = Path(td) / "sample.py"
    p.write_text("def foo():\n    return 1\n\ndef bar():\n    return 2\n")

    # Success case
    r = apply_patch(p, "    return 1\n", "    return 42\n")
    check("apply_patch success", r.ok, f"lines_changed={r.lines_changed}")
    check("apply_patch content written", "return 42" in p.read_text())
    check("apply_patch backup created", Path(r.backup_path).exists())

    # Not found
    r2 = apply_patch(p, "DOES_NOT_EXIST", "x")
    check("apply_patch not-found -> ok=False", not r2.ok)
    check("apply_patch not-found occurrences=0", r2.occurrences == 0)

    # Ambiguous (both functions have `return`)
    p2 = Path(td) / "ambig.py"
    p2.write_text("x = 1\nx = 1\n")
    r3 = apply_patch(p2, "x = 1\n", "x = 2\n")
    check("apply_patch ambiguous -> ok=False", not r3.ok)
    check("apply_patch ambiguous occurrences=2", r3.occurrences == 2)

    # Empty old
    r4 = apply_patch(p, "", "something")
    check("apply_patch empty old -> ok=False", not r4.ok)


# ── 3. apply_patches unit tests ──────────────────────────────────────────────
print("\n── 3. apply_patches unit tests ──")
with tempfile.TemporaryDirectory() as td:
    p = Path(td) / "multi.py"
    p.write_text("A = 1\nB = 2\nC = 3\n")

    r = apply_patches(p, [
        {"old": "A = 1\n", "new": "A = 10\n"},
        {"old": "B = 2\n", "new": "B = 20\n"},
    ])
    check("apply_patches success", r.ok, f"lines_changed={r.lines_changed}")
    txt = p.read_text()
    check("apply_patches both changes applied", "A = 10" in txt and "B = 20" in txt)

    # Failure mid-way — file should be unchanged
    p2 = Path(td) / "mid.py"
    p2.write_text("X = 1\nY = 2\n")
    original = p2.read_text()
    r2 = apply_patches(p2, [
        {"old": "X = 1\n", "new": "X = 99\n"},
        {"old": "MISSING", "new": "whatever"},
    ])
    check("apply_patches mid-failure -> ok=False", not r2.ok)
    # File should NOT have been written (all-or-nothing)
    check("apply_patches mid-failure file unchanged", p2.read_text() == original)


# ── 4. extract_relevant_sections ─────────────────────────────────────────────
print("\n── 4. extract_relevant_sections ──")
big_file = "\n".join([f"line_{i} = {i}" for i in range(500)])
big_file += "\ndef apply_patch(path, old, new):\n    pass\n"

result = extract_relevant_sections(big_file, hint="apply_patch function", max_chars=6000)
check("extract returns something", len(result) > 0)
check("extract contains hint keyword", "apply_patch" in result)
check("extract smaller than original", len(result) < len(big_file),
      f"{len(result)} < {len(big_file)}")

# Empty hint falls back gracefully
result2 = extract_relevant_sections(big_file, hint="", max_chars=500)
check("extract empty hint fallback", len(result2) <= 500)


# ── 5. file_ops.py wired ─────────────────────────────────────────────────────
print("\n── 5. tools/file_ops.py patch action ──")
fo = ROOT / "tools" / "file_ops.py"
if fo.exists():
    src = fo.read_text(encoding="utf-8")
    check('file_ops has action == "patch"', 'action == "patch"' in src)
    check("file_ops imports apply_patch", "apply_patch" in src)
else:
    check("tools/file_ops.py exists", False, "file missing")


# ── 6. autocode.py CODER_SYSTEM ──────────────────────────────────────────────
print("\n── 6. autocode.py CODER_SYSTEM patch-first ──")
ac = ROOT / "workflows" / "autocode.py"
if ac.exists():
    src = ac.read_text(encoding="utf-8")
    check('CODER_SYSTEM mentions "patches"', '"patches"' in src or "'patches'" in src)
    check("CODER_SYSTEM mentions new_files", "new_files" in src)
    check("CODER_SYSTEM no full-file rewrite instruction",
          "reproduce the ENTIRE file" not in src)
else:
    check("autocode.py exists", False, "file missing — skipping autocode checks")


# ── 7. node_write_files handles patch format ─────────────────────────────────
print("\n── 7. autocode.py node_write_files patch handling ──")
if ac.exists():
    src = ac.read_text(encoding="utf-8")
    check("node_write_files imports apply_patch", "apply_patch" in src)
    check("node_write_files reads patches key", 'data.get("patches"' in src)
    check("node_write_files reads new_files key", 'data.get("new_files"' in src)


# ── 8. _files_context hint parameter ─────────────────────────────────────────
print("\n── 8. autocode.py _files_context hint parameter ──")
if ac.exists():
    src = ac.read_text(encoding="utf-8")
    check("_files_context has hint= param", "hint=" in src)
    check("_files_context calls extract_relevant_sections",
          "extract_relevant_sections" in src)


# ── Summary ───────────────────────────────────────────────────────────────────
print("\n" + "─" * 55)
passed = sum(1 for _, ok, _ in results if ok)
total  = len(results)
print(f"Result: {passed}/{total} checks passed")
if passed == total:
    print("All checks passed. Token optimisation patches are live.\n")
else:
    failed = [label for label, ok, _ in results if not ok]
    print(f"Failed: {failed}\n")
    sys.exit(1)
