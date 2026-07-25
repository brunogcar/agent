"""data_sources/cvm/vlmo/status_reporter.py -- VLMO sync statistics."""

from __future__ import annotations

from pathlib import Path


def status() -> dict:
    """Return VLMO database statistics."""
    from data_sources.cvm.vlmo.catalog import connect, db_path
    path = db_path()
    if not path.exists():
        return {
            "status": "not_synced",
            "message": "VLMO database not found. Run sync first.",
            "path": str(path),
        }

    conn = connect(read_only=True)
    try:
        doc_count = conn.execute("SELECT COUNT(*) as n FROM vlmo_documents").fetchone()["n"]
        mov_count = conn.execute("SELECT COUNT(*) as n FROM vlmo_movements").fetchone()["n"]

        # Date range
        date_range = conn.execute(
            "SELECT MIN(Data_Movimentacao) as min_date, MAX(Data_Movimentacao) as max_date "
            "FROM vlmo_movements WHERE Data_Movimentacao IS NOT NULL"
        ).fetchone()

        # Company count
        company_count = conn.execute(
            "SELECT COUNT(DISTINCT CNPJ_Companhia) as n FROM vlmo_movements"
        ).fetchone()["n"]

        # Buy vs sell counts
        buy_count = conn.execute(
            "SELECT COUNT(*) as n FROM vlmo_movements WHERE Tipo_Movimentacao = 'Compra'"
        ).fetchone()["n"]
        sell_count = conn.execute(
            "SELECT COUNT(*) as n FROM vlmo_movements WHERE Tipo_Movimentacao = 'Venda'"
        ).fetchone()["n"]

        # Sync state
        sync_row = conn.execute(
            "SELECT * FROM sync_state ORDER BY rowid DESC LIMIT 1"
        ).fetchone()

        return {
            "status": "ok",
            "form": "VLMO",
            "path": str(path),
            "db_size_mb": round(path.stat().st_size / (1024 * 1024), 1),
            "document_count": doc_count,
            "movement_count": mov_count,
            "company_count": company_count,
            "buy_transactions": buy_count,
            "sell_transactions": sell_count,
            "earliest_date": date_range["min_date"] if date_range else "",
            "latest_date": date_range["max_date"] if date_range else "",
            "synced_at": sync_row["synced_at"] if sync_row else "",
            "last_sync_year": sync_row["year"] if sync_row else 0,
        }
    finally:
        conn.close()
