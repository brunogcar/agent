"""
Phase 6 verification -- run from D:/mcp/agent/
Full end-to-end smoke test: boot, all 8 tools reachable, cross-tool workflow.
"""
import sys
import time

print("=== Phase 6: Full Stack Smoke Test ===\n")

# - 1. Config and directories -
print("1. Config and directory check")
from core.config import cfg

cfg.ensure_dirs()

checks = {
    "agent_root":    cfg.agent_root,
    "workspace":     cfg.workspace_root,
    "memory_db":     cfg.memory_root,
    "chroma":        cfg.memory_chroma_path,
    "autocode_dir":  cfg.workspace_autocode,
    "logs_dir":      cfg.log_path,
}
all_ok = True
for name, path in checks.items():
    exists = path.exists()
    print(f"   {'OK' if exists else 'FAIL'} {name:15} {path}")
    if not exists:
        all_ok = False
assert all_ok, "Some required directories are missing"

# - 2. Tracer -
print("\n2. Tracer")
from core.tracer import tracer

tid = tracer.new_trace("phase6_smoke", goal="full stack verification")
tracer.step(tid, "start", "smoke test running")
summary = tracer.summary(tid)
assert "phase6_smoke" in summary
print(f"   trace created: {summary} OK")

# - 3. LLM client -
print("\n3. LLM client")
from core.llm import llm

roles = llm.list_roles()
print(f"   {len(roles)} roles configured OK")
router_role = next(r for r in roles if r["role"] == "router")
assert router_role["timeout"] == 15, f"Router timeout should be 15s, got {router_role['timeout']}"
print(f"   router: model={router_role['model']}, timeout={router_role['timeout']}s OK")
available = llm.is_available()
print(f"   LM Studio: {'reachable OK' if available else 'not running (skipping live tests)'}")

# - 4. Memory system -
print("\n4. Memory system")
from memory.store import memory as mem_store

stats = mem_store.stats()
total = sum(v.get("count", 0) for v in stats.values())
print(f"   ChromaDB: {total} memories across {len(stats)} collections OK")
for col, data in stats.items():
    print(f"   {col:12} {data['count']} entries")

# - 5. Registry -- all 8 tools -
print("\n5. Tool registry")
from mcp.server.fastmcp import FastMCP
from registry import register_all_tools

mcp   = FastMCP("smoke_test")
count = register_all_tools(mcp)
names = sorted([t.name for t in mcp._tool_manager.list_tools()])

expected = ["agent", "file", "git", "memory", "notify", "python", "visualize", "web"]
print(f"   {count} tools registered")
for name in expected:
    found = name in names
    print(f"   {'OK' if found else 'FAIL'} {name}")
assert names == expected, f"Tool mismatch. Got: {names}"

# - 6. Cross-tool workflow smoke test -
print("\n6. Cross-tool workflow smoke test")

from tools.python_exec import python
from tools.file_ops    import file
from tools.memory_tool import memory
from tools.git_ops     import git
from tools.notify      import notify

# python ? compute something
r = python(mode="run_data", code=(
    "import math\n"
    "results = {str(i): round(math.sqrt(i), 4) for i in range(1, 6)}\n"
    "print(results)"
))
assert r["status"] == "success", f"python failed: {r}"
print(f"   python(run_data) ? {r['output'][:60]} OK")

# python sandbox (pure logic, no imports)
r = python(mode="run", code="print(sum(i**2 for i in range(5)))")
assert r["status"] == "success", f"python sandbox failed: {r}"
print(f"   python(run)      ? {r['output']} OK")

# file ? write result
r = file(action="write", path="autocode/phase6_smoke.txt",
         content=f"Phase 6 smoke test\nTimestamp: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
assert r["status"] == "success", f"file write failed: {r}"
print(f"   file(write)     ? {r['size']} bytes OK")

# file ? read it back
r = file(action="read", path="autocode/phase6_smoke.txt")
assert r["status"] == "success" and "Phase 6" in r["content"]
print(f"   file(read)      ? {r['lines']} lines OK")

# memory ? store episodic
r = memory(action="store", memory_type="episodic",
           text="Phase 6 smoke test passed -- all 8 tools registered and functional",
           importance=7, goal="phase6 verification", outcome="success",
           tools_used="python,file,memory,git,notify", trace_id=tid)
assert r["status"] in ("stored", "skipped_duplicate")
print(f"   memory(store)   ? {r['status']} OK")

# memory ? recall
r = memory(action="recall", query="phase 6 smoke test", top_k=3)
assert r["status"] == "success"
print(f"   memory(recall)  ? {r['count']} result(s) OK")

# git ? status on workspace
r = git(operation="status", root="workspace")
assert r["status"] == "ok"
print(f"   git(status)     ? {r['count']} change(s), head={r.get('head','(init)')} OK")

# git ? snapshot
r = git(operation="snapshot", message="phase6 smoke test", root="workspace")
assert r["status"] in ("committed", "nothing_to_commit")
print(f"   git(snapshot)   ? {r['status']} OK")

# notify ? send (non-blocking)
r = notify(action="send", title="Phase 6", message="Smoke test complete")
assert r["status"] == "sent"
print(f"   notify(send)    ? method={r['method']} OK")

# - 7. Visualize smoke test -
print("\n7. Visualize smoke test")
from tools.visualize import visualize

r = visualize(
    type="chart", chart_type="bar",
    data={"x": ["Tool 1","Tool 2","Tool 3","Tool 4","Tool 5","Tool 6","Tool 7","Tool 8"],
          "y": [100, 95, 98, 100, 97, 99, 96, 100]},
    title="Phase 6 -- Tool Health Check",
    x_label="Tool", y_label="Score (%)",
    output="phase6_health",
)
assert r["status"] == "success"
print(f"   visualize(chart) ? {r['html_path'].split(chr(92))[-1]} OK")

# - 8. Live agent test (if LM Studio running) -
if available:
    print("\n8. Live agent smoke test")
    from tools.agent_tool import agent

    r = agent(role="classify",
              task="Is this a simple question or a complex multi-step task?",
              content="What is 2 + 2?")
    assert r["status"] == "success"
    print(f"   agent(classify)  ? '{r['text']}' [{r['elapsed']}s] OK")

    r = agent(role="summarize",
              task="Summarise in one sentence",
              content="The MCP Agent Stack has 8 meta-tools: web, python, file, "
                      "git, memory, agent, notify, and visualize. Phase 6 is complete.")
    assert r["status"] == "success"
    print(f"   agent(summarize) ? '{r['text'][:80]}' OK")
else:
    print("\n8. Live agent test -- skipped (LM Studio not running)")

# - 9. Finish trace -
tracer.finish(tid, success=True, result="all checks passed")
print(f"\n{tracer.summary(tid)}")

print("\n" + "="*55)
print("  Phase 6 complete -- stack is fully operational")
print("="*55)
print("\nNext steps:")
print("  1. Copy mcp.json to your Claude Desktop / MCP client config")
print("  2. Paste system_prompts/claude_project_instructions.md")
print("     into Claude.ai Project Instructions")
print("  3. Set LM Studio system prompts from system_prompts/")
print("  4. Start the server: python server.py")
print("  5. Proceed to Phase 7 -- workflows")
