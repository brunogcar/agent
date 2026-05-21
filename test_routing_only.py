# test_routing_only.py
from workflows.autocode_helpers.routes import (
    route_after_run_tests,
    route_after_write_files,
    route_after_verify,
)

def test_routes():
    # Test run_tests routing
    assert route_after_run_tests({"tdd_status": "passed"}) == "node_verify"
    assert route_after_run_tests({"test_results": {"success": True}}) == "node_verify"
    assert route_after_run_tests({"tdd_status": "failed"}) == "node_systematic_debug"
    
    # Test write_files routing (TDD loop for features)
    assert route_after_write_files({"task_type": "feature"}) == "node_run_tests"
    assert route_after_write_files({"task_type": "fix"}) == "node_run_tests"
    assert route_after_write_files({"task_type": "create_skill"}) == "node_verify"
    
    # Test verify routing
    assert route_after_verify({"verification_passed": True}) == "node_commit"
    assert route_after_verify({"verification_passed": False}) == "END"
    
    print("✅ All routing tests passed")

if __name__ == "__main__":
    test_routes()