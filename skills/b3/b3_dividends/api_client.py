"""
skills/b3/b3_dividends/api_client.py
B3 dividends API client with retry logic and base64 parameter encoding.

This module encapsulates the HTTP layer, matching the Google Sheets pattern:
  doGetProventos() → JSON.stringify({issuingCompany: ticker, language}) → base64Encode → fetch

The B3 API returns a list with one element: [{ cashDividends: [...], stockDividends: [...], subscriptions: [...] }]
"""
from __future__ import annotations

import base64
import json
import time
from typing import Any

import requests

# [MANUAL VERIFICATION REQUIRED] - Test in browser first
# Base64 of {"issuingCompany":"PETR","language":"pt-br"} = eyJpc3N1aW5nQ29tcGFueSI6IlBFVFIiLCJsYW5ndWFnZSI6InB0LWJyIn0=
_DIVIDENDS_API_URL = (
    "https://sistemaswebb3-listados.b3.com.br/listedCompaniesProxy/CompanyCall/GetListedSupplementCompany/"
)

DOWNLOAD_TIMEOUT = 120  # seconds — B3 API can be slow
MAX_RETRIES = 3
BACKOFF_BASE = 2.0  # seconds — exponential: 2s, 4s, 8s


def build_api_params(ticker: str, language: str = "pt-br") -> str:
    """Build base64-encoded params for the B3 dividends API.

    The B3 API expects the issuing company code (first 4 letters of the ticker,
    e.g., "PETR" for both PETR3 and PETR4). The full ticker (PETR4) is used
    downstream to distinguish the share class.

    Args:
        ticker: Full ticker symbol (e.g., "PETR4", "VALE3").
        language: API language. Default "pt-br".

    Returns:
        Base64-encoded JSON string ready for URL interpolation.

    Note:
        Matches Google Sheets: Utilities.base64Encode(JSON.stringify({issuingCompany, language}))
    """
    # B3 uses the 4-char issuing company code, not the full ticker with share class
    issuing_company = ticker.upper().strip()[:4]
    params = {"issuingCompany": issuing_company, "language": language}
    json_str = json.dumps(params, separators=(",", ":"))
    return base64.b64encode(json_str.encode("utf-8")).decode("utf-8")


def download_json(ticker: str) -> dict:
    """Download dividends data from B3 API with retry and exponential backoff.

    Args:
        ticker: Full ticker symbol (e.g., "PETR4").

    Returns:
        Dict with keys:
            status: "ok" | "error" | "empty"
            data: The parsed JSON payload (list[dict] or None)
            error: Error message string (if status != "ok")
            ticker: The requested ticker
            url: The API URL (for debugging)

    Note:
        Retries on timeout, connection errors, and 5xx status codes.
        Does NOT retry on 4xx (client error) or malformed JSON.
    """
    b64_params = build_api_params(ticker)
    url = f"{_DIVIDENDS_API_URL}{b64_params}"

    last_error = ""
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = requests.get(
                url,
                timeout=DOWNLOAD_TIMEOUT,
                headers={"Accept": "application/json"},
            )
            # Only retry on 5xx or timeout-like conditions
            if resp.status_code >= 500:
                last_error = f"HTTP {resp.status_code}"
                if attempt < MAX_RETRIES:
                    wait = BACKOFF_BASE ** (attempt - 1)
                    time.sleep(wait)
                    continue
                return {
                    "status": "error",
                    "data": None,
                    "error": f"B3 API returned HTTP {resp.status_code} after {MAX_RETRIES} retries",
                    "ticker": ticker,
                    "url": url,
                }

            resp.raise_for_status()
            payload = resp.json()

            # Validate structure: B3 returns a list with one element
            if not isinstance(payload, list):
                return {
                    "status": "error",
                    "data": None,
                    "error": f"Unexpected API response type: {type(payload).__name__} (expected list)",
                    "ticker": ticker,
                    "url": url,
                }

            if not payload:
                return {
                    "status": "empty",
                    "data": None,
                    "error": "B3 API returned empty list — company may not have dividend data",
                    "ticker": ticker,
                    "url": url,
                }

            return {
                "status": "ok",
                "data": payload,
                "error": None,
                "ticker": ticker,
                "url": url,
            }

        except requests.exceptions.Timeout:
            last_error = "Request timeout"
            if attempt < MAX_RETRIES:
                wait = BACKOFF_BASE ** (attempt - 1)
                time.sleep(wait)
                continue
            return {
                "status": "error",
                "data": None,
                "error": f"Request timed out after {MAX_RETRIES} retries",
                "ticker": ticker,
                "url": url,
            }

        except requests.exceptions.ConnectionError as e:
            last_error = f"Connection error: {e}"
            if attempt < MAX_RETRIES:
                wait = BACKOFF_BASE ** (attempt - 1)
                time.sleep(wait)
                continue
            return {
                "status": "error",
                "data": None,
                "error": last_error,
                "ticker": ticker,
                "url": url,
            }

        except requests.exceptions.RequestException as e:
            # Non-retryable request error (4xx, malformed URL, etc.)
            return {
                "status": "error",
                "data": None,
                "error": f"Request failed: {e}",
                "ticker": ticker,
                "url": url,
            }

        except json.JSONDecodeError as e:
            return {
                "status": "error",
                "data": None,
                "error": f"Invalid JSON response: {e}",
                "ticker": ticker,
                "url": url,
            }

    # Should never reach here, but defensive
    return {
        "status": "error",
        "data": None,
        "error": f"Exhausted retries. Last error: {last_error}",
        "ticker": ticker,
        "url": url,
    }
