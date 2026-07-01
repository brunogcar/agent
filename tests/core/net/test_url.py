"""Tests for core/net/url.py — URL normalization and domain utilities.

v1.3: Fixed assertions to match actual normalize_url behavior.
"""
from __future__ import annotations

import pytest

from core.net.url import normalize_url, extract_domain, is_same_domain


class TestNormalizeUrl:
    """Tests for normalize_url()."""

    def test_lowercases_scheme_and_host(self):
        assert normalize_url("HTTPS://EXAMPLE.COM/") == "https://example.com/"

    def test_strips_trailing_slash_from_non_root(self):
        """v1.3: Trailing slash is stripped from non-root paths, but root becomes '/'."""
        assert normalize_url("https://example.com/page/") == "https://example.com/page"

    def test_empty_path_becomes_slash(self):
        """Root path always has trailing slash for consistency."""
        assert normalize_url("https://example.com") == "https://example.com/"
        assert normalize_url("https://example.com/") == "https://example.com/"

    def test_strips_default_http_port(self):
        assert normalize_url("http://example.com:80/") == "http://example.com/"

    def test_keeps_non_default_port(self):
        assert normalize_url("https://example.com:8080/") == "https://example.com:8080/"

    def test_sorts_query_params(self):
        assert normalize_url("https://example.com?b=2&a=1") == "https://example.com/?a=1&b=2"

    def test_idempotent(self):
        url = "https://Example.COM:443/PATH/?Z=1&A=2"
        first = normalize_url(url)
        second = normalize_url(first)
        assert first == second


class TestExtractDomain:
    """Tests for extract_domain()."""

    def test_extracts_domain(self):
        assert extract_domain("https://example.com/path") == "example.com"

    def test_extracts_domain_with_port(self):
        assert extract_domain("https://example.com:8080/path") == "example.com"

    def test_extracts_subdomain(self):
        assert extract_domain("https://www.example.com/path") == "www.example.com"


class TestIsSameDomain:
    """Tests for is_same_domain()."""

    def test_same_domain(self):
        assert is_same_domain("https://example.com/a", "https://example.com/b") is True

    def test_different_domain(self):
        assert is_same_domain("https://example.com/a", "https://other.com/b") is False

    def test_www_considered_same(self):
        assert is_same_domain("https://www.example.com/a", "https://example.com/b") is True
