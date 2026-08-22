"""tests/data_sources/bcb/sgs/test_query.py - query_engine tests with temp DB."""
from __future__ import annotations
from data_sources.bcb.sgs import query_engine


def test_series_returns_oldest_first(sgs_db):
    res = query_engine.series(code=11, days=10)
    assert res["status"] == "ok"
    assert res["count"] == 3
    dates = [o["ref_date"] for o in res["observations"]]
    assert dates == sorted(dates)


def test_series_not_found(sgs_db):
    res = query_engine.series(code=999999, days=10)
    assert res["status"] == "not_found"


def test_series_requires_code(sgs_db):
    assert query_engine.series()["status"] == "error"


def test_last_value(sgs_db):
    res = query_engine.last_value(code=1)
    assert res["status"] == "ok"
    assert res["ref_date"] == "2024-01-04"
    assert abs(res["value"] - 4.9480) < 1e-9


def test_last_value_uses_ref_date_field(sgs_db):
    """v3 fix: query_engine consistently uses 'ref_date' (not 'date')."""
    res = query_engine.last_value(code=11)
    assert res["status"] == "ok"
    assert "ref_date" in res
    assert "date" not in res


def test_range_query(sgs_db):
    res = query_engine.range_query(code=433, start="2024-01-01", end="2024-02-28")
    assert res["status"] == "ok"
    assert res["count"] == 2  # 2024-01-10 + 2024-02-10


def test_search_by_name(sgs_db):
    res = query_engine.search(query="Selic")
    assert res["status"] == "ok"
    assert res["count"] >= 3  # Selic diaria, Meta Copom, Selic acumulada


def test_search_tr_series(sgs_db):
    """v3 fix: series 226 (TR) is in the catalog and searchable."""
    res = query_engine.search(query="TR")
    assert res["status"] == "ok"
    codes = [s["code"] for s in res["series"]]
    assert 226 in codes


def test_summary_returns_all_series(sgs_db):
    res = query_engine.summary()
    assert res["status"] == "ok"
    assert res["count"] == 11
