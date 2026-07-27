"""tests/data_sources/cvm/bridge/test_parse_escala.py -- parse_escala helper tests.

Standalone tests for the parse_escala function in data_sources.cvm._db.
No fixtures needed.

Originally part of tests/data_sources/cvm/test_bridge.py; split as part of
test-reorg.
"""
from __future__ import annotations


class TestParseEscala:
    """Test the parse_escala helper (v1.2.1)."""

    def test_mil(self):
        from data_sources.cvm._db import parse_escala
        assert parse_escala("MIL") == 1000.0

    def test_milhoes(self):
        from data_sources.cvm._db import parse_escala
        assert parse_escala("MILHOES") == 1000000.0

    def test_unidade(self):
        from data_sources.cvm._db import parse_escala
        assert parse_escala("UNIDADE") == 1.0

    def test_empty(self):
        from data_sources.cvm._db import parse_escala
        assert parse_escala("") == 1.0

    def test_none(self):
        from data_sources.cvm._db import parse_escala
        assert parse_escala(None) == 1.0

    def test_lowercase(self):
        from data_sources.cvm._db import parse_escala
        assert parse_escala("mil") == 1000.0

    def test_numeric_string(self):
        from data_sources.cvm._db import parse_escala
        assert parse_escala("1000") == 1000.0

    def test_unknown_returns_unit(self):
        from data_sources.cvm._db import parse_escala
        assert parse_escala("UNKNOWN") == 1.0
