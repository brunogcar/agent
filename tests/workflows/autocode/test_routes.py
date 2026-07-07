"""tests/workflows/autocode/test_routes.py
Tests for all 5 route_after_* routing functions.
"""
from __future__ import annotations


class TestRouteAfterClassify:
    def test_unclear_routes_to_end(self):
        from workflows.autocode_impl.routes import route_after_classify
        assert route_after_classify({"task_type": "unclear"}) == "END"

    def test_create_skill_routes_to_create_skill(self):
        from workflows.autocode_impl.routes import route_after_classify
        assert route_after_classify({"task_type": "create_skill"}) == "node_create_skill"

    def test_feature_routes_to_validate(self):
        from workflows.autocode_impl.routes import route_after_classify
        assert route_after_classify({"task_type": "feature"}) == "node_validate_input"


class TestRouteAfterWriteFiles:
    def test_feature_routes_to_impact(self):
        from workflows.autocode_impl.routes import route_after_write_files
        assert route_after_write_files({"task_type": "feature"}) == "node_analyze_impact"

    def test_audit_routes_to_impact(self):
        """[v1.1] audit now routes to analyze_impact (was skipping it)."""
        from workflows.autocode_impl.routes import route_after_write_files
        assert route_after_write_files({"task_type": "audit"}) == "node_analyze_impact"

    def test_edit_routes_to_impact(self):
        """[v1.1] edit now routes to analyze_impact (was skipping it)."""
        from workflows.autocode_impl.routes import route_after_write_files
        assert route_after_write_files({"task_type": "edit"}) == "node_analyze_impact"

    def test_all_tdd_task_types_route_to_impact(self):
        from workflows.autocode_impl.routes import route_after_write_files
        for task_type in ["fix", "fix_error", "refactor", "improve", "feature"]:
            assert route_after_write_files({"task_type": task_type}) == "node_analyze_impact"


class TestRouteAfterRunTests:
    def test_passed_routes_to_verify(self):
        from workflows.autocode_impl.routes import route_after_run_tests
        assert route_after_run_tests({"tdd_status": "passed"}) == "node_verify"

    def test_success_in_results_routes_to_verify(self):
        from workflows.autocode_impl.routes import route_after_run_tests
        assert route_after_run_tests({"tdd_status": "", "test_results": {"success": True}}) == "node_verify"

    def test_max_retries_routes_to_verify(self):
        from workflows.autocode_impl.routes import route_after_run_tests
        assert route_after_run_tests({"tdd_status": "max_retries_exceeded"}) == "node_verify"

    def test_stuck_routes_to_verify(self):
        """[#39] stuck status bails to verify, skips doomed debug loop."""
        from workflows.autocode_impl.routes import route_after_run_tests
        assert route_after_run_tests({"tdd_status": "stuck"}) == "node_verify"

    def test_failed_routes_to_debug(self):
        from workflows.autocode_impl.routes import route_after_run_tests
        assert route_after_run_tests({"tdd_status": "failed"}) == "node_systematic_debug"


class TestRouteAfterVerify:
    def test_passed_routes_to_report(self):
        from workflows.autocode_impl.routes import route_after_verify
        assert route_after_verify({"verification_passed": True}) == "report"

    def test_failed_routes_to_end(self):
        from workflows.autocode_impl.routes import route_after_verify
        assert route_after_verify({"verification_passed": False}) == "END"


class TestRouteAfterAnalyzeImpact:
    def test_always_routes_to_run_tests(self):
        from workflows.autocode_impl.routes import route_after_analyze_impact
        assert route_after_analyze_impact({}) == "node_run_tests"
