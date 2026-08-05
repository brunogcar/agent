"""tests/skills/b3/index/test_modes.py -- B3 index skill mode tests."""
from unittest.mock import patch


@patch("data_sources.b3.index.query_engine.summary")
@patch("data_sources.b3.index.query_engine.index")
def test_dashboard_returns_tabs(mock_index, mock_summary):
    mock_summary.return_value = {
        "status": "ok", "total_indices": 5, "active_indices": 5,
        "indices": [{"code": "IBOV", "name": "Indice Bovespa", "description": "",
                      "active": True, "last_date": "2024-01-15",
                      "constituent_count": 78, "synced_at": "2024-01-15"}],
    }
    mock_index.return_value = {
        "status": "ok", "index": "IBOV", "name": "Indice Bovespa",
        "ref_date": "2024-01-15", "constituent_count": 1,
        "constituents": [{"ticker": "PETR4", "company_name": "PETROBRAS",
                           "type": "ON NM", "theorical_qty": 1000,
                           "participation": 10.5, "rank": 1}],
    }
    from skills.b3.index.modes.dashboard import dashboard
    result = dashboard()
    assert result["status"] == "ok"
    assert len(result["tabs"]) >= 2  # Resumo + at least 1 index tab


@patch("skills.b3.index.modes.ticker.ticker_search")
def test_ticker_mode(mock_ticker):
    mock_ticker.return_value = {
        "status": "ok", "ticker": "PETR4", "company_name": "PETROBRAS",
        "index_count": 1,
        "indices": [{"index": "IBOV", "name": "Indice Bovespa",
                      "participation": 10.5, "rank": 1, "ref_date": "2024-01-15"}],
    }
    from skills.b3.index.modes.ticker import ticker
    result = ticker(ticker="PETR4")
    assert result["status"] == "ok"
    assert result["index_count"] == 1
