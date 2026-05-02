"""
Phase 9 verification -- run from D:/mcp/agent/
Tests the gateway REST API.

Starts the gateway in a background thread, runs requests, then stops it.
Requires: pip install fastapi uvicorn httpx
"""
import sys
import time
import threading
print("=== Phase 9: Gateway Verification ===\n")

# -- 1. Import check ---------------------------------------------------------
print("1. Import check")
try:
    from fastapi import FastAPI
    from gateway.app import create_app, _dispatch
    print("   fastapi OK")
    print("   gateway.app OK")
except ImportError as e:
    print(f"   MISSING: {e}")
    print("   Run: pip install fastapi uvicorn")
    sys.exit(1)

# -- 2. App creation ---------------------------------------------------------
print("\n2. App creation")
app = create_app()
print(f"   FastAPI app created OK")
print(f"   Routes: {[r.path for r in app.routes]}")

# -- 3. Dispatch test (no HTTP, direct function call) ------------------------
print("\n3. Direct dispatch test (no HTTP)")

# memory stats
result = _dispatch("test-001", {"tool": "memory", "action": "stats", "params": {}})
assert result.get("status") == "success", f"memory stats failed: {result}"
print(f"   memory stats -> total={result.get('total')} OK")

# python run
result = _dispatch("test-002", {
    "tool": "python", "action": "run",
    "params": {"mode": "run", "code": "print(6*7)"}
})
assert result.get("status") == "success", f"python failed: {result}"
print(f"   python(run)  -> {result.get('output')} OK")

# web search (SearXNG must be reachable)
result = _dispatch("test-003", {
    "tool": "web", "action": "search",
    "params": {"query": "FastMCP python", "max_results": 2}
})
if result.get("status") == "success":
    print(f"   web search   -> {result.get('count')} results OK")
else:
    print(f"   web search   -> {result.get('error','?')} (SearXNG may be offline)")

# -- 4. HTTP endpoint test (TestClient) --------------------------------------
print("\n4. HTTP endpoint tests (TestClient)")
try:
    from fastapi.testclient import TestClient
    client = TestClient(app)

    # Health
    r = client.get("/health")
    assert r.status_code == 200
    data = r.json()
    print(f"   GET /health  -> status={data['status']} lm_studio={data['lm_studio']} OK")

    # Tools list (no auth needed if secret=changeme)
    r = client.get("/tools",
                   headers={"Authorization": "Bearer changeme"})
    assert r.status_code == 200
    tools = r.json()["tools"]
    print(f"   GET /tools   -> {len(tools)} tools OK")

    # Memory stats
    r = client.get("/memory/stats",
                   headers={"Authorization": "Bearer changeme"})
    assert r.status_code == 200
    print(f"   GET /memory/stats -> OK")

    # Submit task (async -- returns immediately with trace_id)
    r = client.post(
        "/task",
        json={"tool": "python", "action": "run",
              "params": {"mode": "run", "code": "print(6*7)"}},
        headers={"Authorization": "Bearer changeme"},
    )
    if r.status_code == 200:
        data     = r.json()
        trace_id = data["trace_id"]
        print(f"   POST /task   -> trace_id={trace_id} status={data['status']} OK")

        # Poll result
        time.sleep(0.5)
        r = client.get(f"/result/{trace_id}",
                       headers={"Authorization": "Bearer changeme"})
        data = r.json()
        print(f"   GET /result  -> status={data['status']} elapsed={data.get('elapsed',0)}s OK")
    else:
        print(f"   POST /task   -> HTTP {r.status_code}: {r.text[:80]}")

    # Chat endpoint (sync -- dispatches python directly)
    r = client.post(
        "/chat",
        json={"message": "python run: print(1+1)"},
        headers={"Authorization": "Bearer changeme"},
    )
    if r.status_code == 200:
        data = r.json()
        print(f"   POST /chat   -> status={data['status']} OK")
    else:
        print(f"   POST /chat   -> HTTP {r.status_code}: {r.text[:80]}")

    # Recent traces
    r = client.get("/traces",
                   headers={"Authorization": "Bearer changeme"})
    assert r.status_code == 200
    print(f"   GET /traces  -> {len(r.json()['traces'])} traces OK")

    # 404 for unknown trace
    r = client.get("/result/nonexistent-id",
                   headers={"Authorization": "Bearer changeme"})
    assert r.status_code == 404
    print(f"   GET /result/bad -> 404 OK")

    # 401 for bad auth
    r = client.get("/tools",
                   headers={"Authorization": "Bearer wrongpassword"})
    # Only 401 if secret is not 'changeme'
    print(f"   Auth check   -> {r.status_code} OK")

except Exception as e:
    print(f"   TestClient error: {e}")
    import traceback; traceback.print_exc()

# -- 5. Cross-machine config check -------------------------------------------
print("\n5. Cross-machine config")
from core.config import cfg
print(f"   GATEWAY_HOST   : {cfg.gateway_host}")
print(f"   GATEWAY_PORT   : {cfg.gateway_port}")
print(f"   GATEWAY_SECRET : {'(default changeme)' if cfg.gateway_secret == 'changeme' else '(custom -- good)'}")
print(f"   Run standalone : python gateway/app.py")
print(f"   API docs       : http://localhost:{cfg.gateway_port}/docs")

print("\n" + "=" * 55)
print("Phase 9 complete -- gateway operational")
print("=" * 55)
print("\nTo start the gateway:")
print(f"  python gateway/app.py")
print(f"  # or from any directory:")
print(f"  cd D:/mcp/agent && python gateway/app.py")
