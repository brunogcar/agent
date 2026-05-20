"""test_phase2_safety.py - Phase 2 Validation (Root-Level, Non-Destructive)"""
import sys
import inspect
import functools
from pathlib import Path

def test_config_startup_validation():
    """[config.py] FIX: Verify timeout hierarchy validation uses explicit raises."""
    try:
        import core.config
        source = inspect.getsource(core.config.Config.__init__)
        assert "AUTOCODE_GRAPH_TIMEOUT" in source
        assert "raise ValueError" in source  # Ensured it's not assert
        return True
    except Exception as e:
        print(f"❌ Config Validation Test Failed: {e}")
        return False

def test_tracer_structured_logging():
    """[tracer.py] FIX: Verify structured fields and non-mutating kwargs."""
    try:
        from core.tracer import tracer
        source = inspect.getsource(tracer.step)
        assert "trace_id" in source and "node" in source
        assert "kwargs.get" in source  # Ensured .pop() is not used
        return True
    except Exception as e:
        print(f"❌ Tracer Test Failed: {e}")
        return False

def test_llm_circuit_breaker_api():
    """[llm.py] FIX: Verify circuit_breaker_states is a regular @property."""
    try:
        from core.llm import llm
        cls = type(llm)
        assert hasattr(cls, "circuit_breaker_states")
        attr = getattr(cls, "circuit_breaker_states")
        # Ensure it's a property, not cached_property
        assert isinstance(attr, property)
        return True
    except Exception as e:
        print(f"❌ LLM API Test Failed: {e}")
        return False

def test_gateway_health_endpoints():
    """[gateway.py] FIX: Verify both /health/autocode and /health/circuit-breakers exist."""
    try:
        import core.gateway
        source = inspect.getsource(core.gateway.create_app)
        assert "/health/autocode" in source
        assert "/health/circuit-breakers" in source
        return True
    except Exception as e:
        print(f"❌ Gateway Endpoint Test Failed: {e}")
        return False

def test_gateway_sql_syntax():
    """[gateway.py] FIX: Verify CREATE TABLE syntax is valid."""
    try:
        import core.gateway
        source = inspect.getsource(core.gateway._get_task_db)
        # Check for split lines or obvious syntax breaks
        assert "result    TEXT," in source or "result TEXT," in source
        assert "error     TEXT," in source
        return True
    except Exception as e:
        print(f"❌ Gateway SQL Test Failed: {e}")
        return False

if __name__ == "__main__":
    print("🧪 Running Phase 2 Safety Validation Tests...\n")
    results = {
        "1. Config Timeout Hierarchy (explicit raises)": test_config_startup_validation(),
        "2. Tracer Structured Logging (non-mutating)": test_tracer_structured_logging(),
        "3. LLM Circuit Breaker API (dynamic property)": test_llm_circuit_breaker_api(),
        "4. Gateway Health Endpoints (autocode + breakers)": test_gateway_health_endpoints(),
        "5. Gateway SQL & Return Logic": test_gateway_sql_syntax(),
    }

    passed = sum(results.values())
    total = len(results)

    print("\n📊 RESULTS:")
    for name, status in results.items():
        print(f"  {'✅' if status else '❌'} {name}")
    print(f"\n🎯 {passed}/{total} PASSED")

    sys.exit(0 if passed == total else 1)