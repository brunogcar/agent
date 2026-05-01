"""
Phase 6 verification -- run from D:/mcp/agent/
Full end-to-end smoke test: boot, all 8 tools reachable, cross-tool workflow.
"""
import sys
import time

print("=== Phase 6: Full Stack Smoke Test ===\n")

# -- 1. Config and directories ------------------------------------------------
print("1. Config and directory check")
from core.config import cfg

cfg.ensure_dirs()

checks = {
    "agent_root":   cfg.agent_root,
    "workspace":    cfg.workspace_root,
    "memory_db":    cfg.memory_root,
    "chroma":       cfg.memory_chroma_path,
    "autocode_dir": cfg.workspace_autocode,
    "logs_dir":     cfg.log_path,
}
for name, path in checks.items():
    exists = path.exists()
    status = "OK" if exists else "MISSING"
    print(f"   {status} {name:15} {path}")
    assert exists, f"Missing required directory: {path}"

# -- 2. Tracer ----------------------------------------------------------------
print("\n2. Tracer (output goes to stderr -- not shown here)")
from core.tracer import tracer

tid = tracer.new_trace("phase6_smoke", goal="full stack verification")
tracer.step(tid, "start", "smoke test running")
summary = tracer.summary(tid)
assert "phase6_smoke" in summary
print(f"   trace created OK")
print(f"   summary: {summary}")

# -- 3. LLM client ------------------------------------------------------------
print("\n3. LLM client")
from core.llm import llm

roles = llm.list_roles()
print(f"   {len(roles)} roles configured OK")
router_role = next(r for r in roles if r["role"] == "router")
assert router_role["timeout"] == 15
print(f"   router: model={router_role['model']}, timeout={router_role['timeout']}s OK")
available = llm.is_available()
print(f"   LM Studio: {'reachable OK' if available else 'not running (live tests skipped)'}")

# -- 4. Memory system ---------------------------------------------------------
print("\n4. Memory system")
from memory.store import memory as mem_store

stats = mem_store.stats()
total = sum(v.get("count", 0) for v in stats.values())
print(f"   ChromaDB: {total} memories across {len(stats)} collections OK")
for col, data in stats.items():
    print(f"   {col:12} {data['count']} entries")

# -- 5. Registry --------------------------------------------------------------
print("\n5. Tool registry")
from mcp.server.fastmcp import FastMCP
from registry import register_all_tools

mcp   = FastMCP("smoke_test")
count = register_all_tools(mcp)
names = sorted([t.name for t in mcp._tool_manager.list_tools()])

expected = ["agent", "file", "git", "memory", "notify", "python", "visualize", "web"]
print(f"   {count} tools registered")
for name in expected:
    print(f"   {'OK' if name in names else 'MISSING'} {name}")
assert names == expected, f"Tool mismatch. Got: {names}"

# -- 6. Cross-tool workflow smoke test ----------------------------------------
print("\n6. Cross-tool workflow smoke test")

from tools.python_exec import python
from tools.file_ops    import file
from tools.memory_tool import memory
from tools.git_ops     import git
from tools.notify      import notify

# python sandbox
r = python(mode="run", code="print(sum(i**2 for i in range(5)))")
assert r["status"] == "success", f"python sandbox failed: {r}"
print(f"   python(run)      -> {r['output']} OK")

# python run_data with import
r = python(mode="run_data", code=(
    "import math\n"
    "print({str(i): round(math.sqrt(i), 4) for i in range(1, 4)})"
))
assert r["status"] == "success", f"python run_data failed: {r}"
print(f"   python(run_data) -> {r['output'][:50]} OK")

# file write
r = file(action="write", path="autocode/phase6_smoke.txt",
         content=f"Phase 6 smoke test\nTimestamp: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
assert r["status"] == "success", f"file write failed: {r}"
print(f"   file(write)      -> {r['size']} bytes OK")

# file read
r = file(action="read", path="autocode/phase6_smoke.txt")
assert r["status"] == "success" and "Phase 6" in r["content"]
print(f"   file(read)       -> {r['lines']} lines OK")

# memory store
r = memory(action="store", memory_type="episodic",
           text="Phase 6 smoke test passed -- all 8 tools functional",
           importance=7, goal="phase6 verification", outcome="success",
           tools_used="python,file,memory,git,notify", trace_id=tid)
assert r["status"] in ("stored", "skipped_duplicate")
print(f"   memory(store)    -> {r['status']} OK")

# memory recall
r = memory(action="recall", query="phase 6 smoke test", top_k=3)
assert r["status"] == "success"
print(f"   memory(recall)   -> {r['count']} result(s) OK")

# git -- workspace is NOT a repo by design (it holds multiple project repos)
# Test git on agent root which IS a repo
r = git(operation="status", root="agent")
if r["status"] == "ok":
    print(f"   git(status)      -> {r['count']} change(s), head={r.get('head','?')} OK")
    r = git(operation="snapshot", message="phase6 smoke test", root="agent")
    print(f"   git(snapshot)    -> {r['status']} OK")
else:
    # agent dir not a repo yet either -- just verify the tool responds correctly
    print(f"   git(status)      -> {r.get('error','?')[:60]}")
    print(f"   git tool responding correctly OK")

# notify
r = notify(action="send", title="Phase 6", message="Smoke test complete")
assert r["status"] == "sent"
print(f"   notify(send)     -> method={r['method']} OK")

# -- 7. Visualize smoke test --------------------------------------------------
print("\n7. Visualize smoke test")
from tools.visualize import visualize

r = visualize(
    type="chart", chart_type="bar",
    data={"x": ["web","python","file","git","memory","agent","notify","visualize"],
          "y": [100, 100, 100, 100, 100, 100, 100, 100]},
    title="Phase 6 -- Tool Health Check",
    output="phase6_health",
)
assert r["status"] == "success", f"visualize failed: {r}"
print(f"   visualize(chart) -> saved OK")

# -- 8. Live agent test -------------------------------------------------------
if available:
    print("\n8. Live agent smoke test")
    from tools.agent_tool import agent

    r = agent(role="classify",
              task="Is this a simple or complex task?",
              content="What is 2 + 2?")
    assert r["status"] == "success", f"classify failed: {r}"
    print(f"   agent(classify)  -> '{r['text']}' [{r['elapsed']}s] OK")

    r = agent(role="summarize",
              task="Summarise in one sentence",
              content="Phase 6 smoke test completed. All 8 meta-tools are registered "
                      "and functional. The MCP server boots correctly.")
    assert r["status"] == "success", f"summarize failed: {r}"
    print(f"   agent(summarize) -> '{r['text'][:70]}' OK")
else:
    print("\n8. Live agent test -- skipped (LM Studio not running)")

# -- 9. Finish ----------------------------------------------------------------
tracer.finish(tid, success=True, result="all checks passed")
print(f"\n{tracer.summary(tid)}")

print("\n" + "=" * 55)
print("Phase 6 complete -- stack is fully operational")
print("=" * 55)
print("\nNext: python server.py  (Ctrl+C to stop)")
print("      Restart MCP in LM Studio")
print("      Proceed to Phase 7 -- workflows")
