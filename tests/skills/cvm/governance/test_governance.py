"""Tests for skills/cvm/governance/ — governance skill.

Uses mocked CGVN query_engine — no database needed.
"""
from __future__ import annotations

from skills.cvm.governance.modes.practices import practices
from skills.cvm.governance.modes.score import score
from skills.cvm.governance.modes.by_chapter import by_chapter


MOCK_PRACTICES = {
    "status": "ok", "company": "PETR4", "cnpj": "33000167000101",
    "data_referencia": "2025-06-30", "count": 2,
    "practices": [
        {"ID_Item": "1.1", "Pratica_Recomendada": "Diretoria independente",
         "Pratica_Adotada": "Sim", "Capitulo": "Conselho", "Principio": "Independência"},
        {"ID_Item": "2.1", "Pratica_Recomendada": "Transações relacionadas",
         "Pratica_Adotada": "Não", "Capitulo": "Transparência", "Principio": "Divulgação"},
    ],
}

MOCK_SCORE = {
    "status": "ok", "company": "PETR4", "cnpj": "33000167000101",
    "data_referencia": "2025-06-30", "total_practices": 2,
    "adopted_sim": 1, "adopted_nao": 1, "adopted_parcialmente": 0,
    "score_pct": 0.5, "partial_pct": 0.0, "not_adopted_pct": 0.5,
}

MOCK_BY_CHAPTER = {
    "status": "ok", "company": "PETR4", "cnpj": "33000167000101",
    "data_referencia": "2025-06-30", "count": 2,
    "by_chapter": [
        {"Capitulo": "Conselho", "total": 1, "adopted": 1, "not_adopted": 0, "partial": 0},
        {"Capitulo": "Transparência", "total": 1, "adopted": 0, "not_adopted": 1, "partial": 0},
    ],
}


def _mock_query(monkeypatch, return_map):
    def fake_query(company="", score=False, by_chapter=False, **kwargs):
        if score:
            return return_map.get("score", MOCK_SCORE)
        elif by_chapter:
            return return_map.get("by_chapter", MOCK_BY_CHAPTER)
        else:
            return return_map.get("practices", MOCK_PRACTICES)
    monkeypatch.setattr("data_sources.cvm.cgvn.query_engine.query", fake_query)


class TestValidation:
    def test_practices_requires_company(self):
        r = practices()
        assert r["status"] == "error"

    def test_score_requires_company(self):
        r = score()
        assert r["status"] == "error"

    def test_by_chapter_requires_company(self):
        r = by_chapter()
        assert r["status"] == "error"


class TestPractices:
    def test_practices_basic(self, monkeypatch):
        _mock_query(monkeypatch, {})
        r = practices(company="PETR4")
        assert r["status"] == "ok"
        assert r["count"] == 2

    def test_practices_has_freshness(self, monkeypatch):
        _mock_query(monkeypatch, {})
        r = practices(company="PETR4")
        assert "data_freshness" in r


class TestScore:
    def test_score_basic(self, monkeypatch):
        _mock_query(monkeypatch, {})
        r = score(company="PETR4")
        assert r["status"] == "ok"
        assert r["total_practices"] == 2
        assert r["score_pct"] == 0.5


class TestByChapter:
    def test_by_chapter_basic(self, monkeypatch):
        _mock_query(monkeypatch, {})
        r = by_chapter(company="PETR4")
        assert r["status"] == "ok"
        assert len(r["by_chapter"]) == 2


class TestRoute:
    def test_route_no_mode_errors(self):
        from skills.cvm.governance import route
        r = route()
        assert r["status"] == "error"

    def test_route_unknown_mode_errors(self):
        from skills.cvm.governance import route
        r = route(mode="nope")
        assert r["status"] == "error"
        assert "Unknown mode" in r["error"]

    def test_route_dashboard_dispatches(self):
        """[v1.8] route() should now accept 'dashboard' (was unknown before)."""
        from skills.cvm.governance import route, MANIFEST
        assert "dashboard" in MANIFEST["modes"]
        # Calling without company should short-circuit to 'company is required'
        # inside the dashboard() function (status=error, not 'Unknown mode').
        r = route(mode="dashboard")
        assert r["status"] == "error"
        assert "company is required" in r["error"]
