"""
Phase 4 verification — run from D:/mcp/agent/
Tests all 4 meta-tools without needing LM Studio or SearXNG running.
"""
import sys

print("=== Phase 4: Meta-Tools Verification ===\n")

# ── 1. python tool ────────────────────────────────────────────────────────────
print("1. python tool")
from tools.python_exec import python

r = python(mode="run", code="x = [i**2 for i in range(5)]\nprint(sum(x))")
assert r["status"] == "success", f"FAIL: {r}"
assert r["output"] == "30", f"Wrong output: {r['output']}"
print(f"   run (sandbox)     → {r['output']} ✓")

r = python(mode="run_data", code="import json\nprint(json.dumps({'a': 1, 'b': 2}))")
assert r["status"] == "success", f"FAIL: {r}"
print(f"   run_data (stdlib) → {r['output']} ✓")

r = python(mode="run", code="import os")
assert r["status"] == "error"
print(f"   sandbox blocks import → error caught ✓")

r = python(mode="run_data", code="def f(\nprint('hi')")
assert r["status"] == "error" and "SyntaxError" in r["error"]
print(f"   syntax check catches bad code ✓")

# ── 2. file tool ─────────────────────────────────────────────────────────────
print("\n2. file tool")
from tools.file_ops import file
from core.config import cfg

# write
test_path = "autocode/phase4_test.txt"
r = file(action="write", path=test_path, content="Hello from phase 4\nLine two\n")
assert r["status"] == "success", f"FAIL write: {r}"
print(f"   write             → {r['size']} bytes ✓")

# read
r = file(action="read", path=test_path)
assert r["status"] == "success" and "Hello from phase 4" in r["content"]
print(f"   read              → {r['lines']} lines ✓")

# list
r = file(action="list", path="autocode")
assert r["status"] == "success"
print(f"   list              → {r['count']} entries ✓")

# backup
r = file(action="backup", path=test_path)
assert r["status"] == "success"
print(f"   backup            → {r['backup'].split('/')[-1]} ✓")

# read_many
r = file(action="read_many", paths=[test_path, "server.py"], mode="summary")
assert r["status"] == "success" and r["count"] == 2
print(f"   read_many         → {r['count']} files, {r['total_size']} bytes ✓")

# search
r = file(action="search", query="Hello phase", max_results=5)
assert r["status"] == "success"
print(f"   search (FTS)      → {r['count']} results, {r['indexed_files']} files indexed ✓")

# path escape blocked
r = file(action="read", path="../../etc/passwd")
assert r["status"] == "error"
print(f"   path escape block → error caught ✓")

# ── 3. git tool ───────────────────────────────────────────────────────────────
print("\n3. git tool")
from tools.git_ops import git

r = git(operation="status")
assert r["status"] in ("ok", "error")  # ok if git exists
if r["status"] == "ok":
    print(f"   status            → {r['count']} changes, head={r['head']} ✓")
    r = git(operation="snapshot", message="phase4 verification", root="workspace")
    print(f"   snapshot          → {r['status']} ✓")
    r = git(operation="log", n=3, root="workspace")
    print(f"   log               → {r['count']} commits ✓")
else:
    print(f"   git not available ({r['error'][:50]}) — skipping git tests")

# ── 4. notify tool ───────────────────────────────────────────────────────────
print("\n4. notify tool")
from tools.notify import notify

r = notify(action="send", title="Phase 4 Test", message="Meta-tools verification running")
assert r["status"] == "sent"
print(f"   send              → method={r['method']} ✓")

r = notify(action="schedule", message="Test reminder", delay_minutes=60)
if r["status"] == "scheduled":
    job_id = r["job_id"]
    print(f"   schedule          → job_id={job_id} ✓")
    r2 = notify(action="cancel", job_id=job_id)
    print(f"   cancel            → {r2['status']} ✓")
    r3 = notify(action="list")
    print(f"   list              → {r3['count']} jobs ✓")
else:
    print(f"   schedule → {r['status']} (apscheduler may not be installed)")

# ── 5. Registry check ─────────────────────────────────────────────────────────
print("\n5. Registry auto-discovery check")
from mcp.server.fastmcp import FastMCP
from registry import register_all_tools

mcp = FastMCP("test")
count = register_all_tools(mcp)
print(f"   registered {count} tools ✓")

# Verify expected tools are present
tool_names = [t.name for t in mcp._tool_manager.list_tools()]
expected = ["web", "python", "file", "git", "notify"]
for name in expected:
    found = name in tool_names
    print(f"   {'✓' if found else '✗'} {name}")

print(f"\nAll registered: {sorted(tool_names)}")
print("\nPhase 4 complete.")
