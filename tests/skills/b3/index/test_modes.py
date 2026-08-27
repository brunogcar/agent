"""tests/skills/b3/index/test_modes.py -- B3 index skill mode tests."""
from unittest.mock import patch


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
