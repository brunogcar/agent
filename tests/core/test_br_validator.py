"""
tests/core/test_br_validator.py
Adversarial tests for Brazilian financial data parsing.
"""
import pytest
from datetime import datetime
from core.br_validator import parse_brl, parse_br_date, validate_ticker, B3Dividend

class TestParseBRL:
    def test_standard_format(self):
        assert parse_brl("R$ 1.000,50") == 1000.50

    def test_negative_format(self):
        assert parse_brl("-R$ 50,00") == -50.00

    def test_no_symbol(self):
        assert parse_brl("1.234,56") == 1234.56

    def test_whitespace_and_messy(self):
        assert parse_brl("  R$   10,00  ") == 10.00

    def test_already_float(self):
        assert parse_brl(150.75) == 150.75

    def test_empty_string(self):
        assert parse_brl("") == 0.0

    def test_invalid_raises(self):
        with pytest.raises(ValueError):
            parse_brl("R$ abc")

class TestParseBRDate:
    def test_standard_br_format(self):
        dt = parse_br_date("31/12/2025")
        assert dt == datetime(2025, 12, 31)

    def test_iso_format(self):
        dt = parse_br_date("2025-12-31")
        assert dt == datetime(2025, 12, 31)

    def test_invalid_raises(self):
        with pytest.raises(ValueError):
            parse_br_date("31-12-2025")  # Hyphens instead of slashes for BR format

class TestValidateTicker:
    def test_standard_ticker(self):
        assert validate_ticker("petr4") == "PETR4"

    def test_double_digit_ticker(self):
        assert validate_ticker("TAEE11") == "TAEE11"

    def test_index_ticker(self):
        assert validate_ticker("IBOV") == "IBOV"

    def test_whitespace(self):
        assert validate_ticker("  itsa4  ") == "ITSA4"

    def test_invalid_raises(self):
        with pytest.raises(ValueError):
            validate_ticker("PETR-4") # Hyphen not allowed

class TestPydanticModel:
    def test_b3_dividend_auto_conversion(self):
        """Verify Pydantic intercepts strings and converts them automatically."""
        raw_data = {
            "ticker": "vale3",
            "value_brl": "R$ 0,75",
            "date_ex": "15/05/2026",
            "date_payment": "2026-06-01"
        }
        
        div = B3Dividend(**raw_data)
        
        assert div.ticker == "VALE3"
        assert div.value_brl == 0.75
        assert div.date_ex == datetime(2026, 5, 15)
        assert div.date_payment == datetime(2026, 6, 1)