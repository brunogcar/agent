"""test_phase1_fixes.py - Phase 1 Validation (Root-Level, Non-Destructive)"""
import sys
import inspect
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

def test_state_reducer_and_fields():
    """[state.py + verify.py] FIX 1, 2: Verify reducer removed, add_messages used, tdd_source_code exists."""
    try:
        from workflows.autocode_helpers import state
        from langgraph.graph.message import add_messages

        # 1. Verify _state_reducer was removed
        assert not hasattr(state, '_state_reducer'), "❌ _state_reducer still exists in state.py"

        # 2. Verify messages uses LangGraph's add_messages reducer
        hints = state.AutocodeState.__annotations__
        assert 'messages' in hints, "❌ 'messages' field missing"
        msg_type = str(hints['messages'])
        assert 'add_messages' in msg_type, f"❌ 'messages' missing add_messages reducer"

        # 3. Verify tdd_source_code exists (fixes verify.py field mismatch)
        assert 'tdd_source_code' in hints, "❌ 'tdd_source_code' field missing"
        return True
    except Exception as e:
        print(f"❌ State/Field Test Failed: {e}")
        return False

def test_graph_builder():
    """[graph.py] FIX 1: Verify StateGraph doesn't receive custom reducer."""
    try:
        from workflows.autocode_helpers import graph
        source = inspect.getsource(graph.build_graph)
        assert 'state_reducer=' not in source, "❌ graph.py still passes state_reducer="
        assert '_state_reducer' not in source, "❌ graph.py still references _state_reducer"
        return True
    except Exception as e:
        print(f"❌ Graph Test Failed: {e}")
        return False

def test_timeout_fallback():
    """[helpers.py + state.py] FIX 3, 4: Verify _call() defaults to NODE_TIMEOUTS."""
    try:
        from workflows.autocode_helpers.state import NODE_TIMEOUTS
        from workflows.autocode_helpers.helpers import _call

        with patch('core.llm.llm.complete') as mock_complete:
            mock_complete.return_value = MagicMock(ok=True, text="ok", usage={'total': 5}, elapsed=0.1)
            
            # Call without timeout -> should fallback to config
            _call(role="planner", system="sys", user="usr")
            
            mock_complete.assert_called_once()
            actual_timeout = mock_complete.call_args.kwargs.get('timeout')
            expected_timeout = NODE_TIMEOUTS.get("planner", NODE_TIMEOUTS["default"])
            
            assert actual_timeout == expected_timeout, f"❌ Timeout fallback broken. Got {actual_timeout}, expected {expected_timeout}"
        return True
    except Exception as e:
        print(f"❌ Timeout Test Failed: {e}")
        return False

def test_atomic_write_and_verify_handling():
    """[helpers.py + verify.py] FIX 5, 6: Atomic writes + specific exception handlers."""
    try:
        # 1. Test atomic write
        from workflows.autocode_helpers.helpers import _write_files
        import core.config

        with tempfile.TemporaryDirectory() as tmpdir:
            orig = core.config.cfg.agent_root
            core.config.cfg.agent_root = Path(tmpdir)
            result = _write_files({"files_map": {"test.txt": "ok"}, "trace_id": "t1"})
            core.config.cfg.agent_root = orig
            
            assert result.get("files_written") == ["test.txt"], "❌ Atomic write failed"
            assert (Path(tmpdir) / "test.txt").read_text() == "ok"

        # 2. Verify verify.py has specific exception handlers
        import workflows.autocode_helpers.nodes.verify as verify_mod
        source = inspect.getsource(verify_mod.node_verify)
        assert "FileNotFoundError" in source, "❌ verify.py missing FileNotFoundError handler"
        assert "TimeoutExpired" in source, "❌ verify.py missing TimeoutExpired handler"
        assert "tdd_source_code" in source, "❌ verify.py still using old generated_code field"
        return True
    except Exception as e:
        print(f"❌ Write/Verify Test Failed: {e}")
        return False

if __name__ == "__main__":
    print("🧪 Running Phase 1 Validation Tests...\n")
    results = {
        "1. State Reducer & Fields (state.py/verify.py)": test_state_reducer_and_fields(),
        "2. Graph Builder Cleanup (graph.py)": test_graph_builder(),
        "3. Timeout Fallback (helpers.py/state.py)": test_timeout_fallback(),
        "4. Atomic Write & Verify Errors (helpers.py/verify.py)": test_atomic_write_and_verify_handling(),
    }

    passed = sum(results.values())
    total = len(results)

    print("\n📊 RESULTS:")
    for name, status in results.items():
        print(f"  {'✅' if status else '❌'} {name}")
    print(f"\n🎯 {passed}/{total} PASSED")

    sys.exit(0 if passed == total else 1)