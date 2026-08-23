"""data_sources/ddm/_base/sync_base.py -- Shared sync-engine infrastructure.

The 7 DDM sync_engine.py files split into two clean groups:

  - Multi-page (inflation, juros, poupanca): sync_all() iterates over a
    catalog of slugs, fetches each slug concurrently via ThreadPoolExecutor
    (max_workers=3), parses each HTML response, then sequentially writes
    all observations to the DB in a single connection.

  - Single-page (acoes, dividends, fluxo, focus): sync_all() makes one
    HTTP call, parses the single HTML response, then writes all
    observations to the DB in a single connection. Optionally runs a
    DELETE FROM <table> before the INSERT (the "B4 stale-row cleanup"
    pattern) for full-refresh sources.

This module provides:
  - BaseDDMSyncEngine class with:
      * _progress(msg), _now(), _today_date() static methods.
      * _record_sync_state(conn, slug, last_date, row_count, synced_at)
        static method (the INSERT-OR-REPLACE into sync_state -- identical
        SQL across all 7 sources; only the `last_date` value computation
        differs, and that's done by the caller).
      * sync_single_page(...) classmethod -- the acoes/dividends/fluxo/focus
        pattern. Takes callbacks for fetch / parse / connect / ensure_schema
        / row-mapping / last_date computation / result-extras.
      * sync_multi_page(...) classmethod -- the inflation/juros/poupanca
        pattern. Takes callbacks for fetch / parse-pipeline / connect /
        ensure_schema / row-mapping + a catalog dict.

The per-source sync_engine.py keeps:
  - sync_all(force) -- the public entry point; calls the base method.
  - sync_index(slug, force) -- multi-page: real per-slug sync; single-page:
    alias for sync_all (slug ignored or validated).

[Phase 3, Commit 1] Extracted from the 7 sync_engine.py files.
"""

from __future__ import annotations

import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import Any, Callable


class BaseDDMSyncEngine:
    """Base class for DDM sync engines.

    Subclasses set:
        SOURCE_NAME: str  -- e.g. "inflation" (for the log prefix
                             "[ddm.inflation]").

    Provides:
        _progress(msg)               -- print to stderr.
        _now()                       -- ISO timestamp (UTC).
        _today_date()                -- YYYY-MM-DD (local).
        _record_sync_state(conn, slug, last_date, row_count, synced_at)
            -- INSERT OR REPLACE into sync_state. Identical SQL across all
               7 sources.
        sync_single_page(**kwargs)   -- single-page sync pattern.
        sync_multi_page(**kwargs)    -- multi-page sync pattern with TPE.
    """

    SOURCE_NAME: str = ""

    @staticmethod
    def _progress(msg: str) -> None:
        print(msg, file=sys.stderr, flush=True)

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _today_date() -> str:
        """Return today's date as YYYY-MM-DD (local)."""
        return datetime.now().strftime("%Y-%m-%d")

    @staticmethod
    def _record_sync_state(
        conn,
        slug: str,
        last_date: str,
        row_count: int,
        synced_at: str,
    ) -> None:
        """Write (or update) the sync_state row for a slug.

        Identical SQL across all 7 DDM sources. The `last_date` value is
        source-specific (computed by the caller before invoking this):

          - inflation/juros/poupanca/dividends: max(o.get("ref_date"|"record_date"))
          - acoes: _today_date() (scrape date -- no ref_date in payload).
          - fluxo: max(ref_date) from DESC-sorted observations.
          - focus: _today_date() as the ref_date.
        """
        conn.execute(
            "INSERT OR REPLACE INTO sync_state "
            "(slug, last_date, synced_at, row_count) "
            "VALUES (?, ?, ?, ?)",
            (slug, last_date, synced_at, row_count),
        )

    # ────────────────────────────────────────────────────────────────────
    # Single-page sync (acoes, dividends, fluxo, focus)
    # ────────────────────────────────────────────────────────────────────

    @classmethod
    def sync_single_page(
        cls,
        *,
        fetch_fn: Callable[..., dict],
        parse_fn: Callable[[str], list[dict]],
        connect_fn: Callable[..., Any],
        ensure_schema_fn: Callable[[Any], None],
        insert_sql: str,
        row_mapper: Callable[[dict, str], tuple],
        slug: str,
        table_name: str | None = None,
        full_refresh: bool = False,
        compute_last_date: Callable[[list[dict]], str] | None = None,
        result_extras: Callable[[list[dict], str, str], dict] | None = None,
        force: bool = False,
    ) -> dict:
        """Single-page sync: fetch + parse + write to DB + record sync_state.

        Args:
            fetch_fn:          callable(force=force) -> page dict.
            parse_fn:          callable(html) -> list[observation dicts].
            connect_fn:        callable(read_only=False) -> sqlite3.Connection.
            ensure_schema_fn:  callable(conn) -> None (creates tables if missing).
            insert_sql:        the INSERT OR REPLACE INTO ... SQL with ? placeholders.
            row_mapper:        callable(observation_dict, now_iso) -> tuple (matches insert_sql).
            slug:              the sync_state slug (e.g. "acoes", "dividends", "fluxo", "focus").
            table_name:        the table to DELETE FROM when full_refresh=True
                               (e.g. "stocks", "dividends", "fluxo_observations").
            full_refresh:      if True, run `DELETE FROM <table_name>` before INSERT.
                               Used by acoes, dividends (Phase 2 B4 cleanup), and
                               fluxo (Phase 3 B4 cleanup -- new in this commit).
                               NOT used by focus (accumulates history by ref_date).
            compute_last_date: callable(observations) -> str. If None, last_date="".
            result_extras:     callable(observations, last_date, now) -> dict of
                               extra keys to merge into the result dict
                               (e.g. fluxo returns {"last_date": ...},
                                focus returns {"ref_date": ...}).
            force:             passed to fetch_fn.

        Returns:
            {"status": "ok", "rows": <int>, "synced_at": <iso>, ...extras}
            or the upstream error dict if fetch_fn returned an error.
        """
        page = fetch_fn(force=force)
        if page.get("status") != "ok":
            return page

        observations = parse_fn(page.get("html", ""))
        now = cls._now()

        last_date = ""
        if compute_last_date:
            ld = compute_last_date(observations)
            if ld:
                last_date = ld

        conn = connect_fn(read_only=False)
        ensure_schema_fn(conn)
        try:
            if full_refresh and table_name:
                # [B4 stale-row cleanup] Full-refresh pattern: delete ALL
                # existing rows before re-inserting. This removes rows that
                # DDM dropped from the page (INSERT OR REPLACE only touches
                # rows in the new payload, leaving stale rows behind).
                conn.execute(f"DELETE FROM {table_name}")
            rows = [row_mapper(obs, now) for obs in observations]
            conn.executemany(insert_sql, rows)
            cls._record_sync_state(conn, slug, last_date, len(observations), now)
            conn.commit()
        finally:
            conn.close()

        label = f"[ddm.{cls.SOURCE_NAME}]"
        cls._progress(
            f"{label} sync_all: {len(rows)} observations synced"
            + (f" (last_date={last_date})" if last_date else "")
        )

        result: dict = {
            "status": "ok",
            "rows": len(rows),
            "synced_at": now,
        }
        if result_extras:
            result.update(result_extras(observations, last_date, now))
        return result

    # ────────────────────────────────────────────────────────────────────
    # Multi-page sync (inflation, juros, poupanca)
    # ────────────────────────────────────────────────────────────────────

    @classmethod
    def sync_multi_page(
        cls,
        *,
        catalog: dict,
        fetch_fn: Callable[[str, bool], dict],
        parse_pipeline_fn: Callable[[str], list[dict]],
        connect_fn: Callable[..., Any],
        ensure_schema_fn: Callable[[Any], None],
        insert_sql: str,
        row_mapper: Callable[[dict, str, str], tuple],
        compute_last_date: Callable[[list[dict]], str] | None = None,
        max_workers: int = 3,
        force: bool = False,
    ) -> dict:
        """Multi-page sync: TPE over catalog slugs, sequential DB writes.

        Args:
            catalog:           dict[slug, metadata_tuple] (e.g. INDEX_CATALOG).
            fetch_fn:          callable(slug, force) -> page dict.
            parse_pipeline_fn: callable(html) -> list[observation dicts].
                               For inflation: parse_historical_table.
                               For juros/poupanca: parse_matrix_only +
                                   flatten_matrix_to_observations (combined
                                   into a single callable by the caller).
            connect_fn:        callable(read_only=False) -> sqlite3.Connection.
            ensure_schema_fn:  callable(conn) -> None.
            insert_sql:        the INSERT OR REPLACE INTO ... SQL.
            row_mapper:        callable(observation_dict, slug, now_iso) -> tuple.
            compute_last_date: callable(observations) -> str. If None, defaults
                               to max(o.get("ref_date", "")) which is the
                               most common pattern (inflation/juros/poupanca).
            max_workers:       TPE max_workers (default 3).
            force:             passed to fetch_fn.

        Returns:
            {"status": "ok"|"partial", "indices_synced": <int>,
             "indices_failed": <int>, "rows_total": <int>,
             "results": {slug: sync_result, ...}, "synced_at": <iso>}
        """
        slugs = list(catalog.keys())
        now = cls._now()

        index_synced = 0
        index_failed = 0
        rows_total = 0
        per_index: dict[str, dict] = {}

        # Concurrent fetch + parse, then sequential DB writes (single connection).
        fetch_results: dict[str, list[dict]] = {}
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_slug = {
                executor.submit(fetch_fn, slug, force): slug
                for slug in slugs
            }
            for future in as_completed(future_to_slug):
                slug = future_to_slug[future]
                try:
                    page = future.result()
                except Exception as e:
                    fetch_results[slug] = []
                    per_index[slug] = {"status": "error", "slug": slug,
                                       "error": str(e)}
                    index_failed += 1
                    continue
                if page.get("status") != "ok":
                    fetch_results[slug] = []
                    per_index[slug] = page
                    index_failed += 1
                    continue
                fetch_results[slug] = parse_pipeline_fn(page.get("html", ""))

        conn = connect_fn(read_only=False)
        ensure_schema_fn(conn)
        try:
            for slug, observations in fetch_results.items():
                if not observations and slug not in per_index:
                    # Already errored above; skip.
                    continue
                if slug in per_index and per_index[slug].get("status") == "error":
                    continue
                rows = [row_mapper(obs, slug, now) for obs in observations]
                conn.executemany(insert_sql, rows)

                if compute_last_date:
                    last_date = compute_last_date(observations) or ""
                else:
                    # Default: max(ref_date) -- the inflation/juros/poupanca pattern.
                    last_date = ""
                    if observations:
                        last_date = max(
                            (o.get("ref_date") or "") for o in observations
                        )

                cls._record_sync_state(
                    conn, slug, last_date, len(observations), now,
                )
                index_synced += 1
                rows_total += len(rows)
                per_index[slug] = {"status": "ok", "slug": slug,
                                   "rows": len(rows), "synced_at": now}
            conn.commit()
        finally:
            conn.close()

        status = "ok" if index_failed == 0 else "partial"
        label = f"[ddm.{cls.SOURCE_NAME}]"
        cls._progress(
            f"{label} sync_all: {index_synced}/{len(slugs)} indices, "
            f"{rows_total} total rows ({index_failed} failed)"
        )
        return {
            "status":         status,
            "indices_synced": index_synced,
            "indices_failed": index_failed,
            "rows_total":     rows_total,
            "results":        per_index,
            "synced_at":      now,
        }
