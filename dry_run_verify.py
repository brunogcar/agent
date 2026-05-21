"""dry_run_verify.py -- End-to-end graph routing test (dry-run, mocked LLM)"""
from workflows.autocode_helpers.state import _default_state
from workflows.autocode_helpers.graph import build_graph
from core.tracer import tracer
from unittest.mock import patch, MagicMock
import sys
from pathlib import Path
from datetime import datetime

def run_dry_run():
    print("🚀 Starting dry-run graph validation...", file=sys.stderr)
    tid = tracer.new_trace("autocode_dry_run", goal="verify graph routing")
    
    # Initialize base state
    state = _default_state(task="test dry-run routing", dry_run=True)
    state["task_type"] = "feature"
    state["files_map"] = {"test_module.py": "print('dry run ok')"}
    state["test_code"] = "def test_placeholder(): pass"
    state["spec"] = "Write a placeholder test that passes."
    state["current_step"] = 0
    
    # Pre-seed plan as a list (required by node_write_tests)
    state["plan"] = [
        {"id": 1, "label": "write_tests", "description": "Write failing test"},
        {"id": 2, "label": "execute", "description": "Implement feature"},
        {"id": 3, "label": "write_files", "description": "Save code"},
    ]

    # Sequential mock responses matching the autocode workflow steps
    call_idx = [0]
    def mock_complete(*args, **kwargs):
        call_idx[0] += 1
        i = call_idx[0]
        if i == 1:
            # 1. Classification
            return MagicMock(ok=True, text='{"task_type": "feature", "confidence": 0.9}', usage={"total": 10}, elapsed=0.1)
        elif i == 2:
            # 2. Brainstorm/Plan - return dict with "plan" key
            return MagicMock(ok=True, text='{"plan": [{"id": 1, "label": "write_tests", "description": "Write tests"}], "questions": []}', usage={"total": 10}, elapsed=0.1)
        else:
            # 3+ Tests, Execute, Verify, etc.
            # Return a dict that won't overwrite 'plan', 'task', etc.
            return MagicMock(ok=True, text='{"status": "ok", "verification_passed": true, "checks": {}}', usage={"total": 10}, elapsed=0.1)

    with patch("core.llm.llm.complete", side_effect=mock_complete):
        try:
            # [FIX] Compile without recursion_limit; pass it at invoke time
            graph = build_graph().compile()
            result = graph.invoke(state, config={"recursion_limit": 25})
            
            print(f"✅ Dry-run completed. Final status: {result.get('status')}", file=sys.stderr)
            print(f"📜 Trace log: logs/agent_{datetime.now().strftime('%Y%m%d')}.jsonl", file=sys.stderr)
            
            # Cleanup any accidentally created test files
            for f in Path.cwd().glob("test_*.py"):
                f.unlink(missing_ok=True)
                
        except Exception as e:
            print(f"❌ Dry-run failed: {e}", file=sys.stderr)
            import traceback
            traceback.print_exc(file=sys.stderr)

if __name__ == "__main__":
    run_dry_run()