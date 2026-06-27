"""Tests for data loading with SSRF and UNC blocking."""
import json
from pathlib import Path

import pytest

from tools.report_core.data import load_data


class TestDataLoader:
    """Data loading with path guard and SSRF blocking."""

    def test_inline_data(self):
        data, err = load_data(data={"x": [1, 2], "y": [3, 4]})
        assert err == ""
        assert data == {"x": [1, 2], "y": [3, 4]}

    def test_no_data_or_path(self):
        data, err = load_data()
        assert data is None
        assert "Provide either" in err

    def test_url_blocked_http(self):
        data, err = load_data(data_path="http://evil.com/data.csv")
        assert data is None
        assert "local file path" in err

    def test_url_blocked_https(self):
        data, err = load_data(data_path="https://example.com/data.json")
        assert data is None
        assert "local file path" in err

    def test_url_blocked_ftp(self):
        data, err = load_data(data_path="ftp://server.com/data.csv")
        assert data is None
        assert "local file path" in err

    def test_url_blocked_file_protocol(self):
        data, err = load_data(data_path="file:///etc/passwd")
        assert data is None
        assert "local file path" in err

    def test_unc_blocked_double_backslash(self):
        data, err = load_data(data_path=r"\\server\share\data.csv")
        assert data is None
        assert "UNC paths are not allowed" in err

    def test_unc_blocked_double_slash(self):
        data, err = load_data(data_path="//server/share/data.csv")
        assert data is None
        assert "UNC paths are not allowed" in err

    def test_json_file(self, tmp_path, monkeypatch):
        monkeypatch.setattr("tools.report_core.data.resolve_path", lambda p, **kw: (Path(p), ""))
        p = tmp_path / "test.json"
        p.write_text(json.dumps({"a": 1}), encoding="utf-8")
        data, err = load_data(data_path=str(p))
        assert err == ""
        assert data == {"a": 1}

    def test_csv_file(self, tmp_path, monkeypatch):
        monkeypatch.setattr("tools.report_core.data.resolve_path", lambda p, **kw: (Path(p), ""))
        p = tmp_path / "test.csv"
        csv_lines = ["name,value", "foo,1", "bar,2"]
        p.write_text("\n".join(csv_lines), encoding="utf-8")
        data, err = load_data(data_path=str(p))
        assert err == ""
        assert hasattr(data, "columns")  # pandas DataFrame

    def test_unsupported_suffix(self, tmp_path, monkeypatch):
        monkeypatch.setattr("tools.report_core.data.resolve_path", lambda p, **kw: (Path(p), ""))
        p = tmp_path / "test.txt"
        p.write_text("hello", encoding="utf-8")
        data, err = load_data(data_path=str(p))
        assert data is None
        assert "Unsupported" in err

    def test_missing_file(self, tmp_path, monkeypatch):
        monkeypatch.setattr("tools.report_core.data.resolve_path", lambda p, **kw: (Path(p), ""))
        data, err = load_data(data_path=str(tmp_path / "missing.json"))
        assert data is None
        assert "File not found" in err
