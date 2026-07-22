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


# ===========================================================================
# [v3.11 B3] Audit truncation flag + sort-before-truncate
# ===========================================================================


class TestAuditTruncationFlag:
    """[v3.11 B3] audit_scan must surface a truncated flag when >200 files,
    and the dead-code analysis must use the FULL scanned file set (not the
    capped 200-file subset). Pre-v3.11, the walk broke at 200 files in
    directory-traversal order, then sorted the (already-truncated) subset —
    so the returned list was an arbitrary directory-order-dependent subset,
    NOT the 200 biggest files. Worse, dead-code analysis ran against that
    subset, falsely flagging files whose importers lived in unscanned dirs.
    """

    def test_truncated_flag_set_when_over_200_files(self, base_state, temp_workspace):
        """A repo with >200 .py files must set truncated=True + files_total>200."""
        from workflows.autocode_impl.nodes.audit_scan import node_audit_scan
        # Create 205 .py files so the scan exceeds max_files=200.
        for i in range(205):
            (temp_workspace / f"file_{i:03d}.py").write_text(f"# file {i}\nx = {i}\n", encoding="utf-8")
        base_state["project_root"] = str(temp_workspace)
        base_state["task_type"] = "audit"
        result = node_audit_scan(base_state)
        scan = result["impact"]["audit_scan"]
        assert scan["truncated"] is True
        assert scan["files_total"] == 205
        assert scan["files_scanned"] == 200  # capped

    def test_truncated_flag_not_set_when_under_200(self, base_state, temp_workspace):
        """A repo with <200 .py files must set truncated=False."""
        from workflows.autocode_impl.nodes.audit_scan import node_audit_scan
        for i in range(10):
            (temp_workspace / f"file_{i}.py").write_text(f"# file {i}\n", encoding="utf-8")
        base_state["project_root"] = str(temp_workspace)
        base_state["task_type"] = "audit"
        result = node_audit_scan(base_state)
        scan = result["impact"]["audit_scan"]
        assert scan["truncated"] is False
        assert scan["files_total"] == 10

    def test_sort_before_truncate_returns_biggest_files(self, base_state, temp_workspace):
        """[v3.11 B3] The returned 200-file subset must be the BIGGEST files
        (by line count), not a directory-order-dependent subset. Pre-v3.11,
        the walk broke at 200 in directory order, then sorted — so the subset
        was arbitrary, not the biggest."""
        from workflows.autocode_impl.nodes.audit_scan import _walk_python_files
        # Create 205 files. file_0 has 1000 lines (biggest); file_1..204 have 1 line.
        big_file = temp_workspace / "file_0.py"
        big_file.write_text("\n".join(f"# line {i}" for i in range(1000)) + "\n", encoding="utf-8")
        for i in range(1, 205):
            (temp_workspace / f"file_{i:03d}.py").write_text(f"# small {i}\n", encoding="utf-8")
        files, truncated, files_total = _walk_python_files(str(temp_workspace), max_files=200)
        assert truncated is True
        assert files_total == 205
        # The biggest file (file_0.py with 1000 lines) must be in the returned subset.
        # Pre-v3.11 (directory-order truncation), it might not be (if os.walk
        # visited it after 200 other files were already collected).
        paths = [f["path"] for f in files]
        assert "file_0.py" in paths, (
            "Biggest file (file_0.py) must be in the returned subset — "
            "pre-v3.11 directory-order truncation could miss it."
        )
        # And it must be FIRST (sorted by line count descending).
        assert files[0]["path"] == "file_0.py"
        assert files[0]["lines"] >= 1000  # 1000 "line" lines + 1 trailing = 1001
