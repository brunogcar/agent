"""data_sources/bcb/focus/sync_engine.py -- Sync BCB Focus data to local SQLite.

Three sync entry points:
  1. sync_expectations(indicador, frequency, force=False)
       - sync one indicator (most-recent top=100 expectations)
  2. sync_all(force=False)
       - sync every (indicador, frequency) in DEFAULT_INDICATORS concurrently
  3. sync_indicator(indicador, force=False)
       - sync one indicator using its primary frequency from DEFAULT_INDICATORS

Idempotency: uses INSERT OR REPLACE on the composite primary key per table
  - expectations_monthly: (indicador, data, data_referencia, base_calculo)
  - expectations_annual:   (indicador, data, data_referencia)

Re-syncing replaces existing rows rather than appending duplicates.
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone

from data_sources.bcb.focus.catalog import (
    DEFAULT_INDICATORS, connect, ensure_schema,
)
from data_sources.bcb.focus.fetcher import (
    fetch_expectations, fetch_expectations_concurrent,
)


def _progress(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _table_for_frequency(frequency: str) -> str:
    """Return the SQLite table name for a given frequency."""
    if frequency == "monthly":
        return "expectations_monthly"
    if frequency == "annual":
        return "expectations_annual"
    raise ValueError(f"Unknown frequency: {frequency!r}")


def _record_sync_state(conn, indicador: str, frequency: str,
                       observations: list[dict], now: str) -> None:
    """Write (or update) the sync_state row for an indicator."""
    last_date = ""
    if observations:
        last_date = max(o.get("data", "") for o in observations)
    conn.execute(
        "INSERT OR REPLACE INTO sync_state "
        "(indicador, frequency, last_date, synced_at, row_count) "
        "VALUES (?, ?, ?, ?, ?)",
        (indicador, frequency, last_date, now, len(observations)),
    )


def sync_expectations(indicador: str, frequency: str = "monthly",
                      top: int = 100, force: bool = False) -> dict:
    """Sync one indicator/frequency pair from BCB Focus into focus.db.

    Args:
        indicador: 'IPCA', 'Selic', 'PIB', 'Cambio'.
        frequency: 'monthly' or 'annual'.
        top:       Maximum records to fetch (Olinda $top).
        force:     Re-fetch even if recently synced.

    Returns:
        {"status": "ok"|"error", "indicador": <str>, "frequency": <str>,
         "rows": <int>, "synced_at": <iso>}
    """
    result = fetch_expectations(indicador, frequency=frequency, top=top,
                                force=force)
    if result.get("status") != "ok":
        return result

    observations = result.get("observations", [])
    now = _now()
    table = _table_for_frequency(frequency)

    conn = connect(read_only=False)
    ensure_schema(conn)
    try:
        rows = [
            (indicador, o["data"], o["data_referencia"], o.get("media"),
             o.get("mediana"), o.get("minimo"), o.get("maximo"),
             o.get("numero_respondentes"), o.get("base_calculo"), now)
            for o in observations
        ]
        if frequency == "monthly":
            conn.executemany(
                f"INSERT OR REPLACE INTO {table} "
                "(indicador, data, data_referencia, media, mediana, minimo, "
                "maximo, numero_respondentes, base_calculo, synced_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                rows,
            )
        else:  # annual -- no base_calculo in PK, but the column still exists
            conn.executemany(
                f"INSERT OR REPLACE INTO {table} "
                "(indicador, data, data_referencia, media, mediana, minimo, "
                "maximo, numero_respondentes, base_calculo, synced_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                rows,
            )
        _record_sync_state(conn, indicador, frequency, observations, now)
        conn.commit()
    finally:
        conn.close()

    _progress(f"[bcb.focus] {indicador}/{frequency}: {len(rows)} observations synced")
    return {"status": "ok", "indicador": indicador, "frequency": frequency,
            "rows": len(rows), "synced_at": now}


def sync_all(force: bool = False, top: int = 100) -> dict:
    """Sync EVERY (indicador, frequency) in DEFAULT_INDICATORS concurrently.

    Args:
        force: Re-fetch even if recently synced.
        top:   Maximum records per fetch (default 100).

    Returns:
        {"status": "ok"|"partial", "indicators_synced": <int>,
         "indicators_failed": <int>, "rows_total": <int>,
         "results": {(indicador, frequency): {...}}, "synced_at": <iso>}
    """
    items = list(DEFAULT_INDICATORS)
    fetch_results = fetch_expectations_concurrent(items, top=top, force=force)
    now = _now()

    synced = 0
    failed = 0
    rows_total = 0
    per_pair: dict[tuple[str, str], dict] = {}

    conn = connect(read_only=False)
    ensure_schema(conn)
    try:
        for (indicador, frequency), fetched in fetch_results.items():
            if fetched.get("status") != "ok":
                failed += 1
                per_pair[(indicador, frequency)] = fetched
                continue
            observations = fetched.get("observations", [])
            table = _table_for_frequency(frequency)
            rows = [
                (indicador, o["data"], o["data_referencia"], o.get("media"),
                 o.get("mediana"), o.get("minimo"), o.get("maximo"),
                 o.get("numero_respondentes"), o.get("base_calculo"), now)
                for o in observations
            ]
            conn.executemany(
                f"INSERT OR REPLACE INTO {table} "
                "(indicador, data, data_referencia, media, mediana, minimo, "
                "maximo, numero_respondentes, base_calculo, synced_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                rows,
            )
            _record_sync_state(conn, indicador, frequency, observations, now)
            synced += 1
            rows_total += len(rows)
            per_pair[(indicador, frequency)] = {
                "status": "ok", "indicador": indicador,
                "frequency": frequency, "rows": len(rows), "synced_at": now,
            }
        conn.commit()
    finally:
        conn.close()

    status = "ok" if failed == 0 else "partial"
    _progress(f"[bcb.focus] sync_all: {synced}/{len(items)} indicators, "
              f"{rows_total} total rows ({failed} failed)")
    return {
        "status": status,
        "indicators_synced": synced,
        "indicators_failed": failed,
        "rows_total": rows_total,
        "results": per_pair,
        "synced_at": now,
    }


def sync_indicator(indicador: str, force: bool = False,
                   top: int = 100) -> dict:
    """Sync one indicator using its primary frequency from DEFAULT_INDICATORS.

    Convenience wrapper -- looks up the indicator's primary frequency, then
    delegates to sync_expectations.

    Args:
        indicador: 'IPCA', 'Selic', 'PIB', 'Cambio'.
        force:     Re-fetch even if recently synced.
        top:       Maximum records to fetch.

    Returns:
        Same shape as sync_expectations.
    """
    freq = None
    for ind, f in DEFAULT_INDICATORS:
        if ind == indicador:
            freq = f
            break
    if freq is None:
        return {"status": "error", "indicador": indicador,
                "error": f"Indicator {indicador!r} not in DEFAULT_INDICATORS"}
    return sync_expectations(indicador, frequency=freq, top=top, force=force)
