"""Tests for report_ok and report_fail contracts."""
from tools.report_core.contracts import report_ok, report_fail


class TestContracts:
    """Standardized return contracts for report tool."""

    def test_report_ok_injects_trace_id(self):
        r = report_ok({"html_path": "/tmp/x.html"}, trace_id="abc123")
        assert r["status"] == "success"
        assert r["trace_id"] == "abc123"
        assert r["html_path"] == "/tmp/x.html"

    def test_report_ok_preserves_extra_fields(self):
        r = report_ok({"html_path": "/tmp/y.html", "type": "chart", "rows": 5}, trace_id="t1")
        assert r["type"] == "chart"
        assert r["rows"] == 5

    def test_report_fail_injects_trace_id(self):
        r = report_fail("boom", trace_id="abc123")
        assert r["status"] == "error"
        assert r["trace_id"] == "abc123"
        assert "boom" in r["error"]

    def test_report_fail_empty_trace_id(self):
        r = report_fail("something broke")
        assert r["status"] == "error"
        assert r["trace_id"] == ""
        assert "something broke" in r["error"]
