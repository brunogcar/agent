"""data_sources/bcb/focus/query_engine.py -- Read-only queries against focus.db.

Functions:
  - expectations(indicador, frequency, limit=50)  - most recent N expectations
  - last_value(indicador, frequency)              - latest expectation
  - summary()                                     - catalog overview

All queries open a read-only SQLite URI connection (fails if DB missing).
"""

from __future__ import annotations

from data_sources.bcb.focus.catalog import (
    connect, db_path, INDICATOR_CATALOG, DEFAULT_INDICATORS,
)


def _table_for_frequency(frequency: str) -> str:
    if frequency == "monthly":
        return "expectations_monthly"
    if frequency == "annual":
        return "expectations_annual"
    raise ValueError(f"Unknown frequency: {frequency!r}")


def expectations(indicador: str = "", frequency: str = "",
                 limit: int = 50) -> dict:
    """Query the most recent ``limit`` expectations for an indicator.

    Args:
        indicador: 'IPCA', 'Selic', 'PIB', 'Cambio'. Required.
        frequency: 'monthly' or 'annual'. Required.
        limit:     Max results (default 50).

    Returns:
        {"status": "ok", "indicador": <str>, "frequency": <str>, "count": <int>,
         "observations": [{data, data_referencia, media, mediana, minimo,
                           maximo, numero_respondentes, base_calculo}, ...]}
    """
    if not indicador:
        return {"status": "error", "error": "indicador is required"}
    if not frequency:
        return {"status": "error", "error": "frequency is required"}
    if frequency not in ("monthly", "annual"):
        return {"status": "error", "error": f"frequency must be 'monthly' or 'annual', got {frequency!r}"}

    try:
        conn = connect(read_only=True)
    except FileNotFoundError as e:
        return {"status": "not_synced", "error": str(e)}

    try:
        table = _table_for_frequency(frequency)
        rows = conn.execute(
            f"SELECT data, data_referencia, media, mediana, minimo, maximo, "
            f"numero_respondentes, base_calculo FROM {table} "
            f"WHERE indicador = ? ORDER BY data DESC LIMIT ?",
            (indicador, limit),
        ).fetchall()
        if not rows:
            return {"status": "not_found", "indicador": indicador,
                    "frequency": frequency,
                    "error": f"No expectations for {indicador}/{frequency}"}
        return {
            "status": "ok",
            "indicador": indicador,
            "frequency": frequency,
            "count": len(rows),
            "observations": [
                {
                    "data": r["data"],
                    "data_referencia": r["data_referencia"],
                    "media": r["media"],
                    "mediana": r["mediana"],
                    "minimo": r["minimo"],
                    "maximo": r["maximo"],
                    "numero_respondentes": r["numero_respondentes"],
                    "base_calculo": r["base_calculo"],
                }
                for r in rows
            ],
        }
    finally:
        conn.close()


def last_value(indicador: str = "", frequency: str = "") -> dict:
    """Get the most recent expectation for an indicator.

    Returns:
        {"status": "ok", "indicador": <str>, "frequency": <str>,
         "data": <YYYY-MM-DD>, "data_referencia": <str>,
         "media", "mediana", "minimo", "maximo",
         "numero_respondentes", "base_calculo"}
    """
    if not indicador:
        return {"status": "error", "error": "indicador is required"}
    if not frequency:
        return {"status": "error", "error": "frequency is required"}

    try:
        conn = connect(read_only=True)
    except FileNotFoundError as e:
        return {"status": "not_synced", "error": str(e)}

    try:
        table = _table_for_frequency(frequency)
        row = conn.execute(
            f"SELECT data, data_referencia, media, mediana, minimo, maximo, "
            f"numero_respondentes, base_calculo FROM {table} "
            f"WHERE indicador = ? ORDER BY data DESC LIMIT 1",
            (indicador,),
        ).fetchone()
        if not row:
            return {"status": "not_found", "indicador": indicador,
                    "frequency": frequency,
                    "error": f"No expectations for {indicador}/{frequency}"}
        meta = INDICATOR_CATALOG.get(indicador, (indicador, "", "", ""))
        return {
            "status": "ok",
            "indicador": indicador,
            "frequency": frequency,
            "name": meta[2],
            "unit": meta[3],
            "data": row["data"],
            "data_referencia": row["data_referencia"],
            "media": row["media"],
            "mediana": row["mediana"],
            "minimo": row["minimo"],
            "maximo": row["maximo"],
            "numero_respondentes": row["numero_respondentes"],
            "base_calculo": row["base_calculo"],
        }
    finally:
        conn.close()


def summary() -> dict:
    """Catalog overview: every (indicador, frequency) pair + row counts.

    Returns:
        {"status": "ok", "count": <int>,
         "indicators": [{indicador, frequency, description, unit, rows,
                         last_data, last_sync}, ...]}
    """
    try:
        conn = connect(read_only=True)
    except FileNotFoundError as e:
        return {"status": "not_synced", "error": str(e)}

    try:
        out = []
        for indicador, frequency in DEFAULT_INDICATORS:
            meta = INDICATOR_CATALOG.get(indicador, (indicador, "", "", ""))
            table = _table_for_frequency(frequency)
            row = conn.execute(
                f"SELECT COUNT(*) as n, MAX(data) as last_data "
                f"FROM {table} WHERE indicador = ?",
                (indicador,),
            ).fetchone()
            sync_row = conn.execute(
                "SELECT last_date, synced_at, row_count FROM sync_state "
                "WHERE indicador = ?",
                (indicador,),
            ).fetchone()
            out.append({
                "indicador": indicador,
                "frequency": frequency,
                "description": meta[2],
                "unit": meta[3],
                "rows": row["n"] if row else 0,
                "last_data": row["last_data"] if row else "",
                "last_sync": sync_row["synced_at"] if sync_row else "",
                "synced_rows": sync_row["row_count"] if sync_row else 0,
            })
        return {"status": "ok", "count": len(out), "indicators": out}
    finally:
        conn.close()
