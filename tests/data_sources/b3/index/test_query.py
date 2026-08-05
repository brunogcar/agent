"""tests/data_sources/b3/index/test_query.py -- B3 index query tests."""
from data_sources.b3.index import query_engine


def test_index_returns_constituents(index_db):
    res = query_engine.index("IBOV")
    assert res["status"] == "ok"
    assert res["constituent_count"] == 2
    assert res["constituents"][0]["ticker"] == "PETR4"


def test_index_not_found(index_db):
    assert query_engine.index("XXXX")["status"] == "not_found"


def test_search(index_db):
    res = query_engine.search("IBOV")
    assert res["status"] == "ok"
    assert res["count"] >= 1


def test_summary(index_db):
    res = query_engine.summary()
    assert res["status"] == "ok"
    assert res["active_indices"] == 2


def test_ticker_search(index_db):
    res = query_engine.ticker_search("PETR4")
    assert res["status"] == "ok"
    assert res["index_count"] == 2
