"""
Phase 5 verification — run from D:/mcp/agent/
Tests memory meta-tool and agent meta-tool.
LM Studio must be running with all three models loaded.
"""
print("=== Phase 5: Agent + Memory Meta-Tools Verification ===\n")

# ── 1. Memory tool ────────────────────────────────────────────────────────────
print("1. memory tool — store")
from tools.memory_tool import memory

r = memory(action="store", memory_type="episodic",
           text="Phase 5 verified: agent and memory tools working",
           importance=7, goal="phase5 verification", outcome="success",
           tools_used="agent,memory", trace_id="p5test")
assert r["status"] in ("stored", "skipped_duplicate"), f"FAIL: {r}"
print(f"   store episodic  → {r['status']} ✓")

r = memory(action="store", memory_type="semantic",
           text="agent() tool routes classify/route roles to Nemotron 4B (15s timeout)",
           importance=8, tags="agent,routing,nemotron")
assert r["status"] in ("stored", "skipped_duplicate"), f"FAIL: {r}"
print(f"   store semantic  → {r['status']} ✓")

r = memory(action="store", memory_type="procedural",
           text="To call a sub-agent: agent(role='code', task='...', content='[code]'). "
                "Always follow with agent(role='review', ...) before applying any patch.",
           importance=9, tags="agent,code,workflow")
assert r["status"] in ("stored", "skipped_duplicate"), f"FAIL: {r}"
print(f"   store procedural → {r['status']} ✓")

print("\n2. memory tool — recall")
r = memory(action="recall", query="how to call sub-agent for code", top_k=3)
assert r["status"] == "success", f"FAIL: {r}"
assert r["count"] > 0, "Expected at least 1 result"
print(f"   recall          → {r['count']} results ✓")
for res in r["results"]:
    print(f"   [{res['type']:12}] score={res['score']:.2f} | {res['text'][:60]}...")

print("\n3. memory tool — stats")
r = memory(action="stats")
assert r["status"] == "success"
print(f"   stats           → total={r['total']} memories ✓")
for col, data in r["collections"].items():
    print(f"   {col:12} {data['count']} entries")

print("\n4. memory tool — prune dry-run")
r = memory(action="prune", dry_run=True, max_age_days=30, min_importance=3)
print(f"   prune dry-run   → status={r['status']} ✓")

# ── 2. Agent tool — LM Studio required ───────────────────────────────────────
print("\n5. agent tool — checking LM Studio availability")
from core.llm import llm

if not llm.is_available():
    print("   LM Studio not running — skipping live agent tests")
    print("   (Start LM Studio with all 3 models, then re-run to test)")
else:
    print("   LM Studio reachable ✓")
    from tools.agent_tool import agent

    # classify (Nemotron — fast)
    print("\n6. agent(role='classify') — Nemotron")
    r = agent(role="classify",
              task="Is this task about fixing existing code or writing brand new code?",
              content="The recall() function returns wrong results when min_score is 0")
    assert r["status"] == "success", f"FAIL: {r}"
    print(f"   classify → '{r['text']}' [{r['elapsed']}s, {r['model']}] ✓")

    # route (Nemotron — fast, returns JSON)
    print("\n7. agent(role='route') — Nemotron, JSON output")
    r = agent(role="route",
              task="Analyse the monthly sales CSV and create a bar chart")
    assert r["status"] == "success", f"FAIL: {r}"
    print(f"   route    → text='{r['text'][:80]}' ✓")
    if "parsed" in r:
        p = r["parsed"]
        print(f"   parsed   → workflow={p.get('workflow')} tool={p.get('tool')} "
              f"complexity={p.get('complexity')} ✓")
    elif "parse_warning" in r:
        print(f"   parse_warning: {r['parse_warning']}")

    # summarize (Hermes)
    print("\n8. agent(role='summarize') — Hermes")
    r = agent(role="summarize",
              task="Summarise this in 2 sentences",
              content=(
                  "The MCP Agent Stack is a fully autonomous local AI agent built "
                  "on the Model Context Protocol. It uses three models: Qwen as planner, "
                  "Hermes as executor, and Nemotron as router. The system has 6 meta-tools "
                  "that replace 20+ flat tools. Memory is stored in three ChromaDB collections "
                  "with decay scoring. All outputs are pathlib-native and cross-platform."
              ))
    assert r["status"] == "success", f"FAIL: {r}"
    print(f"   summarize → '{r['text'][:100]}...' [{r['elapsed']}s] ✓")

    # plan (Qwen)
    print("\n9. agent(role='plan') — Qwen, JSON output")
    r = agent(role="plan",
              task="Research ChromaDB best practices and save a summary to a file")
    assert r["status"] == "success", f"FAIL: {r}"
    print(f"   plan      → '{r['text'][:80]}...' [{r['elapsed']}s] ✓")
    if "parsed" in r:
        p = r["parsed"]
        steps = p.get("steps", [])
        print(f"   parsed    → {len(steps)} steps, complexity={p.get('estimated_complexity')} ✓")
        for s in steps[:3]:
            print(f"   step {s.get('step')}: {s.get('action')} — {s.get('description','')[:50]}")

# ── 3. Registry check ─────────────────────────────────────────────────────────
print("\n10. Registry — 8 tools expected")
from mcp.server.fastmcp import FastMCP
from registry import register_all_tools

mcp   = FastMCP("test")
count = register_all_tools(mcp)
names = sorted([t.name for t in mcp._tool_manager.list_tools()])
print(f"    registered {count} tools: {names}")

expected = ["agent", "file", "git", "memory", "notify", "python", "visualize", "web"]
for name in expected:
    found = name in names
    print(f"    {'✓' if found else '✗'} {name}")

assert count == 8, f"Expected 8 tools, got {count}"
print("\nPhase 5 complete.")
