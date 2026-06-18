"""
skills/b3/b3_dividends/sync_engine.py
Orchestrate download → parse → store → state for B3 dividends sync.

This replaces the monolithic sync() from the original dividends.py.
It coordinates api_client, parser, and storage modules, and manages
per-ticker sync state in a JSON file.

State key = full ticker (PETR4, not PETR) so PETR3 and PETR4 are tracked
separately even though they share the same issuing company.
"""
from __future__ import annotations

import json
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from core.config import cfg
from skills.b3.b3_dividends.api_client import download_json
from skills.b3.b3_dividends.parser import parse_all
from skills.b3.b3_dividends.storage import store_to_sqlite

_STATE_FILE_NAME = ".sync_state.json"
_STATE_KEY = "b3_dividends"


def _state_file_path(base_dir: Path) -> Path:
    """Return the path to the sync state JSON file."""
    return base_dir / _STATE_FILE_NAME


def _load_state(base_dir: Path) -> dict:
    """Load sync state from JSON file.

    Returns:
        Dict with structure:
            {
                "b3_dividends": {
                    "PETR4": {"rows": 42, "syncedAt": "...", "elapsed_s": 1.2},
                    "VALE3": {...},
                }
            }
    """
    path = _state_file_path(base_dir)
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}


def _save_state(state: dict, base_dir: Path) -> None:
    """Save sync state to JSON file."""
    path = _state_file_path(base_dir)
    base_dir.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(state, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def sync(ticker: str, force: bool = False) -> dict:
    """Download and store dividends data for a specific ticker.

    Args:
        ticker: Full ticker symbol (e.g., "PETR4", "VALE3", "WEGE3", "SAPR11").
                The first 4 letters are the issuing company code used for the API call.
                The full ticker is used for storage and state tracking.
        force: If True, redownload even if already synced. Default False.

    Returns:
        Dict with keys:
            status: "ok" | "skipped" | "error" | "empty"
            ticker: The requested ticker
            rows: Total rows inserted across all schemas
            schemas: Per-schema row counts
            elapsed_s: Sync duration
            db_path: Path to the SQLite DB
            error: Error message (if status != "ok")

    Note:
        PETR3 and PETR4 share the same issuing company (PETR) but have different
        ISINs. The full ticker is stored so queries distinguish them correctly.
    """
    base_dir = cfg.memory_root / "b3"
    base_dir.mkdir(parents=True, exist_ok=True)

    t0 = time.time()
    state = _load_state(base_dir)
    key = ticker.upper().strip()

    # Check cache
    if key in state.get(_STATE_KEY, {}) and not force:
        cached = state[_STATE_KEY][key]
        return {
            "status": "skipped",
            "reason": "already current",
            "ticker": ticker,
            "rows": cached.get("rows", 0),
            "synced_at": cached.get("syncedAt", ""),
        }

    # Download
    download_result = download_json(ticker)
    if download_result["status"] != "ok":
        return {
            "status": download_result["status"],
            "ticker": ticker,
            "rows": 0,
            "schemas": {},
            "elapsed_s": round(time.time() - t0, 1),
            "db_path": str(base_dir / "dividends.db"),
            "error": download_result.get("error", "Unknown download error"),
        }

    data = download_result["data"]
    if not data or not isinstance(data, list) or not data[0]:
        return {
            "status": "empty",
            "ticker": ticker,
            "rows": 0,
            "schemas": {},
            "elapsed_s": round(time.time() - t0, 1),
            "db_path": str(base_dir / "dividends.db"),
            "error": "No company data in API response",
        }

    company_data = data[0]

    # Parse all dividend types
    parsed = parse_all(company_data, ticker)

    # Store each schema
    total_rows = 0
    per_schema: dict[str, int] = {}

    for schema_name, rows in parsed.items():
        if rows:
            inserted = store_to_sqlite(schema_name, rows, ticker, base_dir)
            total_rows += inserted
            per_schema[schema_name] = inserted
        else:
            per_schema[schema_name] = 0

    elapsed = round(time.time() - t0, 1)

    # Update state
    state.setdefault(_STATE_KEY, {})[key] = {
        "ticker": ticker,
        "rows": total_rows,
        "schemas": per_schema,
        "syncedAt": datetime.utcnow().isoformat(),
        "elapsed_s": elapsed,
    }
    _save_state(state, base_dir)

    return {
        "status": "ok",
        "ticker": ticker,
        "rows": total_rows,
        "schemas": per_schema,
        "elapsed_s": elapsed,
        "db_path": str(base_dir / "dividends.db"),
    }


def sync_all(tickers: list[str], force: bool = False) -> dict:
    """Sync dividends for multiple tickers sequentially.

    Args:
        tickers: List of full ticker symbols.
        force: If True, redownload all even if already synced.

    Returns:
        Dict with per-ticker results and summary.
    """
    results: dict[str, dict] = {}
    total_rows = 0
    errors: list[str] = []

    for ticker in tickers:
        result = sync(ticker, force=force)
        results[ticker] = result
        if result["status"] == "ok":
            total_rows += result.get("rows", 0)
        elif result["status"] == "error":
            errors.append(f"{ticker}: {result.get('error', '')}")

    return {
        "status": "ok" if not errors else "partial_error",
        "tickers_synced": len([r for r in results.values() if r["status"] == "ok"]),
        "tickers_failed": len(errors),
        "total_rows": total_rows,
        "errors": errors,
        "results": results,
    }
