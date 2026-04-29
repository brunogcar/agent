"""
Phase 3 verification — run from D:/mcp/agent/
"""
from memory.store import memory

print("=== Phase 3: Memory System Verification ===\n")

# 1 - Stats before
print("1. Initial stats:")
for col, data in memory.stats().items():
    print(f"   {col:12} {data['count']} entries")

# 2 - Store one of each type
print("\n2. Storing test memories...")

r1 = memory.store_episodic(
    "Phase 3 test: stored episodic memory successfully",
    importance=6, goal="verify memory system", outcome="success",
    tools_used="memory", trace_id="test-001"
)
print(f"   episodic   → {r1['status']}")

r2 = memory.store_semantic(
    "The memory system uses three ChromaDB collections: episodic, semantic, procedural",
    importance=7, tags="memory,architecture", source="phase3_verify"
)
print(f"   semantic   → {r2['status']}")

r3 = memory.store_procedural(
    "To recall memories: use memory.recall(query) — searches all collections by default",
    importance=8, tags="memory,howto", outcome="success"
)
print(f"   procedural → {r3['status']}")

# 3 - Recall
print("\n3. Recall test (query: 'how to recall memories'):")
results = memory.recall("how to recall memories", top_k=3)
for r in results:
    print(f"   [{r['type']:12}] score={r['score']:.2f} | {r['text'][:60]}...")

# 4 - Context string
print("\n4. Context string output:")
ctx = memory.recall_context("chromadb collections memory", top_k=2)
for line in ctx.splitlines():
    print(f"   {line[:90]}")

# 5 - Stats after
print("\n5. Final stats:")
for col, data in memory.stats().items():
    print(f"   {col:12} {data['count']} entries")

# 6 - Dry-run prune
print("\n6. Prune dry-run (should find nothing — memories just created):")
result = memory.prune(max_age_days=30, min_importance=3, dry_run=True)
print(f"   status: {result['status']}")

print("\nPhase 3 complete.")
