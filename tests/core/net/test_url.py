"""tests/core/test_url.py — URL normalization tests.

v1.2: Added for core.net.url module.
"""
from __future__ import annotations

from core.net.url import normalize_url, extract_domain, is_same_domain


class TestNormalizeUrl:
    """Test URL normalization."""

    def test_lowercases_scheme_and_host(self):
        assert normalize_url("HTTPS://EXAMPLE.COM/") == "https://example.com"

    def test_strips_trailing_slash(self):
        assert normalize_url("https://example.com/") == "https://example.com"

    def test_sorts_query_params(self):
        assert normalize_url("https://example.com?b=2&a=1") == "https://example.com?a=1&b=2"

    def test_strips_fragment(self):
        assert normalize_url("https://example.com/page#section") == "https://example.com/page"

    def test_strips_default_http_port(self):
        assert normalize_url("http://example.com:80/") == "http://example.com"

    def test_strips_default_https_port(self):
        assert normalize_url("https://example.com:443/") == "https://example.com"

    def test_preserves_non_default_port(self):
        assert normalize_url("https://example.com:8080/") == "https://example.com:8080"

    def test_empty_path_becomes_slash(self):
        assert normalize_url("https://example.com") == "https://example.com/"


class TestExtractDomain:
    """Test domain extraction."""

    def test_extracts_domain(self):
        assert extract_domain("https://example.com/path") == "example.com"

    def test_extracts_subdomain(self):
        assert extract_domain("https://sub.example.com/path") == "sub.example.com"

    def test_empty_url(self):
        assert extract_domain("") == ""


class TestIsSameDomain:
    """Test domain comparison."""

    def test_same_domain(self):
        assert is_same_domain("https://example.com/a", "https://example.com/b") is True

    def test_different_domain(self):
        assert is_same_domain("https://example.com", "https://other.com") is False

    def test_case_insensitive(self):
        assert is_same_domain("https://EXAMPLE.com", "https://example.com") is True
