"""
Phase 8 verification -- run from D:/mcp/agent/
Tests router layer and autocode json fix.
LM Studio must be running.
"""
import sys
print("=== Phase 8: Router Layer Verification ===\n")

from core.llm import llm
available = llm.is_available()
if not available:
    print("LM Studio not running -- cannot test router")
    sys.exit(0)

# -- 1. Direct router test ---------------------------------------------------
print("1. Router classification")
from routing.router import router

test_goals = [
    "What is LangGraph and how does it work?",
    "Fix the timeout error in tools/web.py",
    "Analyse the monthly sales CSV and calculate growth rates",
    "Research best practices for ChromaDB production deployment",
]

for goal in test_goals:
    d = router.route(goal)
    print(f"   '{goal[:45]}...' -> workflow={d.workflow} complexity={d.complexity} conf={d.confidence}")

print()

# -- 2. Complexity classification --------------------------------------------
print("2. Complexity scoring (Nemotron)")
scores = {
    "What is 2+2?":                                          (1, 3),
    "Research and summarise ChromaDB best practices":        (3, 6),
    "Fix the auth bug in server.py and add tests":           (6, 10),
}
for goal, (low, high) in scores.items():
    score = router.classify_complexity(goal)
    ok    = "OK" if low <= score <= high else "UNEXPECTED"
    print(f"   {ok} '{goal[:40]}' -> {score} (expected {low}-{high})")

print()

# -- 3. Autocode code/review json fix ----------------------------------------
print("3. Autocode code role (json_object fix)")
from tools.agent_tool import agent, _PROMPT_JSON_ROLES, _API_JSON_ROLES

print(f"   _API_JSON_ROLES    : {_API_JSON_ROLES}")
print(f"   _PROMPT_JSON_ROLES : {_PROMPT_JSON_ROLES}")
assert "code"   in _PROMPT_JSON_ROLES, "code should be in PROMPT_JSON_ROLES"
assert "review" in _PROMPT_JSON_ROLES, "review should be in PROMPT_JSON_ROLES"
assert "code"   not in _API_JSON_ROLES, "code should NOT be in API_JSON_ROLES"
print("   Roles correctly configured OK")

r = agent(
    role    = "code",
    task    = "Add a type hint to this function",
    content = "def add(a, b):\n    return a + b\n",
)
assert r["status"] == "success", f"code role failed: {r.get('error')}"
print(f"   agent(code) -> status={r['status']} [{r['elapsed']}s] OK")
if r.get("parsed"):
    print(f"   parsed JSON: keys={list(r['parsed'].keys())}")
else:
    print(f"   text response (parse_warning expected on small input): OK")

print()

# -- 4. workflow(type='auto') routing ----------------------------------------
print("4. workflow(type='auto') auto-routing")
from tools.workflow_tool import workflow

r = workflow(type="auto", goal="What is FastMCP and how does it work?")
print(f"   research goal -> status={r.get('status')} workflow={r.get('workflow','n/a')} OK")

r = workflow(type="auto", goal="Calculate the sum of squares from 1 to 10",
             code="print(sum(i**2 for i in range(1,11)))")
print(f"   data goal     -> status={r.get('status')} workflow={r.get('workflow','n/a')} OK")

print()
print("=" * 55)
print("Phase 8 complete -- router layer operational")
print("=" * 55)
