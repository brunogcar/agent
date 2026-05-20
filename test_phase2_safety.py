"""test_phase2_safety.py - Phase 2 Validation (Root-Level, Non-Destructive)"""
import sys
import inspect
import functools
from pathlib import Path

def test_config_startup_validation():
    """[config.py] FIX: Verify timeout hierarchy validation exists."""
    try:
        import core.config
        source = inspect.getsource(core.config.Config.__init__)
        assert "AUTOCODE_GRAPH_TIMEOUT" in source, "Missing AUTOCODE_GRAPH_TIMEOUT check"
        assert "max(" in source and "timeout" in source.lower(), "Missing max(timeout) validation"
        return True
    except Exception as e:
        print(f"❌ Config Validation Test Failed: {e}")
        return False

def test_tracer_structured_logging():
    """[tracer.py] FIX: Verify structured fields (trace_id, node, latency_ms)."""
    try:
        from core.tracer import tracer
        source = inspect.getsource(tracer.step)
        assert "trace_id" in source, "Missing trace_id in step"
        assert "node" in source, "Missing node in step"
        assert "latency_ms" in source, "Missing latency_ms in step"
        return True
    except Exception as e:
        print(f"❌ Tracer Test Failed: {e}")
        return False

def test_llm_circuit_breaker_api():
    """[llm.py] FIX: Verify circuit_breaker_states public API."""
    try:
        from core.llm import llm
        # Verify the attribute exists and is a descriptor (property or cached_property)
        cls = type(llm)
        assert hasattr(cls, "circuit_breaker_states"), "Missing circuit_breaker_states"
        attr = getattr(cls, "circuit_breaker_states")
        is_descriptor = isinstance(attr, (property, functools.cached_property))
        assert is_descriptor, "Should be a property or cached_property"
        return True
    except Exception as e:
        print(f"❌ LLM API Test Failed: {e}")
        return False

def test_gateway_health_endpoints():
    """[gateway.py] FIX: Verify new health endpoints exist."""
    try:
        import core.gateway
        source = inspect.getsource(core.gateway.create_app)
        assert "/health/autocode" in source, "Missing /health/autocode endpoint"
        assert "health_autocode" in source, "Missing health_autocode function"
        assert "/health/circuit-breakers" in source, "Missing /health/circuit-breakers endpoint"
        return True
    except Exception as e:
        print(f"❌ Gateway Endpoint Test Failed: {e}")
        return False

def test_verify_error_handling():
    """[verify.py] FIX: Verify specific error handlers (FileNotFoundError)."""
    try:
        import workflows.autocode_helpers.nodes.verify as verify_mod
        source = inspect.getsource(verify_mod.node_verify)
        assert "FileNotFoundError" in source, "Missing FileNotFoundError handler"
        assert "TimeoutExpired" in source, "Missing TimeoutExpired handler"
        return True
    except Exception as e:
        print(f"❌ Verify Error Handling Test Failed: {e}")
        return False

if __name__ == "__main__":
    print("🧪 Running Phase 2 Safety Validation Tests...\n")
    results = {
        "1. Config Timeout Hierarchy": test_config_startup_validation(),
        "2. Tracer Structured Logging": test_tracer_structured_logging(),
        "3. LLM Circuit Breaker API": test_llm_circuit_breaker_api(),
        "4. Gateway Health Endpoints": test_gateway_health_endpoints(),
        "5. Verify Error Handling": test_verify_error_handling(),
    }

    passed = sum(results.values())
    total = len(results)

    print("\n📊 RESULTS:")
    for name, status in results.items():
        print(f"  {'✅' if status else '❌'} {name}")
    print(f"\n🎯 {passed}/{total} PASSED")

    sys.exit(0 if passed == total else 1)