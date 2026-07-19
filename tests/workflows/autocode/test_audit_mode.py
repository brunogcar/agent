"""Tests for F7 audit mode (v3.7)."""
from __future__ import annotations

import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path


class TestAuditScan:
    """Test node_audit_scan."""

    def test_scan_walks_python_files(self, base_state, temp_workspace):
        """Scan should find .py files in project_root."""
        # Create a few test files
        (temp_workspace / "main.py").write_text("def main():\n    pass\n")
        (temp_workspace / "utils.py").write_text("def foo() -> int:\n    return 42\n")
        (temp_workspace / "__pycache__").mkdir()
        (temp_workspace / "__pycache__" / "cached.py").write_text("# cached")
        
        base_state["project_root"] = str(temp_workspace)
        from workflows.autocode_impl.nodes.audit_scan import node_audit_scan
        result = node_audit_scan(base_state)
        
        scan = result.get("impact", {}).get("audit_scan", {})
        assert scan["total_files"] == 2  # main.py + utils.py (not __pycache__)
        assert scan["total_lines"] >= 3

    def test_scan_finds_missing_type_hints(self, base_state, temp_workspace):
        """Scan should find functions without return type annotations."""
        (temp_workspace / "untyped.py").write_text("def foo():\n    pass\ndef bar() -> int:\n    return 1\n")
        
        base_state["project_root"] = str(temp_workspace)
        from workflows.autocode_impl.nodes.audit_scan import node_audit_scan
        result = node_audit_scan(base_state)
        
        scan = result.get("impact", {}).get("audit_scan", {})
        missing = scan.get("missing_type_hints", [])
        assert any(m["function"] == "foo" for m in missing)
        assert not any(m["function"] == "bar" for m in missing)

    def test_scan_skips_pycache(self, base_state, temp_workspace):
        """Scan should skip __pycache__ directories."""
        (temp_workspace / "app.py").write_text("pass\n")
        (temp_workspace / "__pycache__").mkdir()
        (temp_workspace / "__pycache__" / "app.cpython.pyc").write_text("binary")
        
        base_state["project_root"] = str(temp_workspace)
        from workflows.autocode_impl.nodes.audit_scan import node_audit_scan
        result = node_audit_scan(base_state)
        
        scan = result.get("impact", {}).get("audit_scan", {})
        assert scan["total_files"] == 1

    def test_scan_returns_status(self, base_state, temp_workspace):
        base_state["project_root"] = str(temp_workspace)
        from workflows.autocode_impl.nodes.audit_scan import node_audit_scan
        result = node_audit_scan(base_state)
        assert result.get("status") == "audit_scan_complete"


class TestAuditRouting:
    """Test route_after_classify for audit."""

    def test_audit_routes_to_scan(self, base_state):
        from workflows.autocode_impl.routes import route_after_classify
        base_state["task_type"] = "audit"
        assert route_after_classify(base_state) == "node_audit_scan"

    def test_feature_routes_to_validate(self, base_state):
        from workflows.autocode_impl.routes import route_after_classify
        base_state["task_type"] = "feature"
        assert route_after_classify(base_state) == "node_validate_input"

    def test_create_skill_routes_to_create_skill(self, base_state):
        from workflows.autocode_impl.routes import route_after_classify
        base_state["task_type"] = "create_skill"
        assert route_after_classify(base_state) == "node_create_skill"


class TestAuditReport:
    """Test node_audit_report."""

    def test_report_calls_llm(self, base_state):
        from workflows.autocode_impl.nodes.audit_report import node_audit_report
        base_state["impact"] = {"audit_scan": {"total_files": 5, "total_lines": 100}}
        with patch("workflows.autocode_impl.nodes.audit_report._call") as mock_call:
            mock_call.return_value = "## Audit Report\n\nAll good."
            result = node_audit_report(base_state)
        assert mock_call.called
        assert "Audit Report" in result.get("result", "")
        assert result.get("status") == "success"

    def test_report_fails_without_scan(self, base_state):
        from workflows.autocode_impl.nodes.audit_report import node_audit_report
        base_state["impact"] = {}
        result = node_audit_report(base_state)
        assert result.get("status") == "failed"
