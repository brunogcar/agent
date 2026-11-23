"""webui/services/sync.py — data source sync service.

[WebUI v1.5] HARDENING REWRITE (fixes the 5 stacked sync-page bugs from the
multi-LLM review):

  1. Thread-safe SSE publish — the old code called asyncio.Queue.put_nowait()
     directly from the sync worker THREAD (asyncio.Queue is not thread-safe;
     events only surfaced on the 15s keepalive tick or corrupted state).
     Now subscribe() captures the running loop and _publish() schedules
     queue puts via loop.call_soon_threadsafe().
  2. tz-aware freshness — the old code subtracted tz-aware ISO timestamps
     (cotahist/brapi write UTC "+00:00") from naive datetime.now() →
     TypeError → swallowed → those sources showed "stale" FOREVER. Now
     timestamps go through sync_guard._parse_sync_ts() (UTC → local, strip
     tzinfo) — one definition of staleness, shared with the skills.
  3. domain_map DELETED — the old 8-entry map drifted from the real source
     list (13/21 sources fell through to data_source(domain="") and failed,
     and it still listed brapi). Now syncs dispatch through
     skills/_base/sync_guard._trigger_sync() — the SAME code path the skills
     use — with the full _SYNC_REGISTRY allow-list.
  4. Job registry — _jobs is now guarded by the lock, deduped (one running
     job per source — a second click returns the existing job) and capped
     (finished jobs pruned beyond 50).
  5. PT-BR errors — raw str(e) no longer reaches the UI; exceptions are
     logged server-side and the UI gets a short PT-BR message.

Freshness check is cheap (SELECT MAX(synced_at) per DB). Sync is expensive
(downloads ZIPs from CVM/B3 APIs) — always runs in a daemon thread, never
on the event loop.

[v1.20] SETTINGS + SYSTEM LOG:
  - freshness() reads the stale threshold from the settings store
    (sync.stale_hours, default 24 — the SYNC_FRESHNESS_HOURS constant was
    the hardcoded pre-v1.20 value; skills keep their own constant).
  - The sync job lifecycle (started/completed/failed + the bulk per-ticker
    progress lines) now ALSO lands in the system log ring buffer
    (webui/services/syslog.py) — the 📜 drawer shows syncs from ANY page,
    not just the Sincronização page's SSE log.
  - start_scheduler()/stop_scheduler(): the periodic auto-sync
    (sync.schedule_hours; 0 = off) — a daemon thread that re-reads the
    interval every cycle (settings changes apply without a restart) and
    fires trigger_sync_all(stale_only=True) per interval. Started by the
    app lifespan unless --no-sync.
"""
from __future__ import annotations

import asyncio
import sys
import threading
import time
import traceback
import uuid
from datetime import datetime, timedelta
from typing import Any

from skills._freshness import get_freshness
from skills._base.sync_guard import (
    _parse_sync_ts,
    _SYNC_REGISTRY,
    _trigger_sync,
    SYNC_FRESHNESS_HOURS,
)

from webui.services.settings import settings_service
from webui.services.syslog import syslog

# Sources that can be triggered from the WebUI sync page. Mirrors the
# sync_guard registry (single source of truth). brapi is gone (paid API).
def syncable_sources() -> list[str]:
    """Allow-list of triggerable sync sources (sync_guard registry keys)."""
    return sorted(_SYNC_REGISTRY.keys())


# [v1.5 fix1] Per-ticker sources — bridge and b3_dividends sync ONE ticker
# per call (the skill flows pass the company via ensure_fresh); the painel
# has no company, so the plain registry kwargs (ticker="") hard-fail with
# {"status": "error", "ticker is required"}. These two get a BULK entry
# point instead: refresh every tracked ticker (seeded from acoes.db when
# the tracking table is empty). NOT a domain_map revival — same registry
# keys, just a different entry point for the two sources whose engines
# are per-ticker by design.
_BULK_SYNC: dict[str, tuple[str, str]] = {
    "bridge":       ("data_sources.cvm.bridge.sync_engine", "sync_all"),
    "b3_dividends": ("data_sources.b3.dividends.sync_engine", "sync_all"),
}


class SyncService:
    """Data source sync service — freshness check + background sync."""

    _MAX_FINISHED_JOBS = 50  # prune finished jobs beyond this many
    _SCHED_TICK = 30.0       # scheduler wake-up cadence (settings re-read)

    def __init__(self) -> None:
        # job_id → status dict (guarded by _lock — written by worker threads,
        # read by request handlers)
        self._jobs: dict[str, dict] = {}
        # job_id of the currently RUNNING job per source (dedupe guard)
        self._running_by_source: dict[str, str] = {}
        # SSE subscribers: (event_loop, bounded queue) pairs. The loop is
        # captured at subscribe() time so the worker thread can hand events
        # to the correct loop thread-safely.
        self._subscribers: list[tuple[asyncio.AbstractEventLoop, asyncio.Queue]] = []
        self._lock = threading.Lock()
        # [v1.20] periodic auto-sync scheduler state
        self._sched_stop = threading.Event()
        self._sched_thread: threading.Thread | None = None
        self._sched_last_fire = 0.0

    # ── freshness ────────────────────────────────────────────────────────────

    def freshness(self) -> dict[str, dict[str, Any]]:
        """Freshness status for all data sources.

        One get_freshness() pass; each timestamp parsed via sync_guard's
        tz-aware parser. Returns {"dfp": {"last_sync": ..., "stale": ...}}.

        [v1.20] The threshold is the sync.stale_hours SETTING (default 24 —
        the old SYNC_FRESHNESS_HOURS constant). Every consumer (Painel
        box, Sincronização page, "Sincronizar tudo", the startup check)
        flows through here, so one settings change moves them all.
        """
        fresh = get_freshness()
        hours = settings_service().get("sync.stale_hours", SYNC_FRESHNESS_HOURS)
        try:
            hours = float(hours)
        except (TypeError, ValueError):
            hours = SYNC_FRESHNESS_HOURS
        max_age = timedelta(hours=hours)
        out: dict[str, dict] = {}
        for source, ts_str in fresh.items():
            stale = True
            if ts_str:
                ts = _parse_sync_ts(ts_str)
                if ts is not None:
                    # Both local-naive now (UTC stamps were converted) — safe.
                    stale = (datetime.now() - ts) > max_age
            out[source] = {
                "last_sync": ts_str or "",
                "stale": stale,
                "status": "stale" if stale else "fresh",
            }
        return out

    # ── SSE pub/sub (thread-safe) ───────────────────────────────────────────

    def subscribe(self) -> asyncio.Queue:
        """Subscribe to sync progress events (SSE). Returns a bounded queue.

        MUST be called from the event loop thread (it captures the running
        loop so worker threads can schedule puts onto it).
        """
        q: asyncio.Queue = asyncio.Queue(maxsize=200)
        loop = asyncio.get_running_loop()
        with self._lock:
            self._subscribers.append((loop, q))
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        with self._lock:
            self._subscribers = [(l, sq) for (l, sq) in self._subscribers if sq is not q]

    @staticmethod
    def _put(q: asyncio.Queue, event: dict) -> None:
        """Put an event on a subscriber queue (runs ON the event loop)."""
        try:
            q.put_nowait(event)
        except asyncio.QueueFull:
            pass  # slow subscriber — drop the event, keep the stream alive

    def _publish(self, event: dict) -> None:
        """Push an event to all SSE subscribers (called from worker threads).

        asyncio.Queue is NOT thread-safe — schedule the put on each
        subscriber's event loop via call_soon_threadsafe (fix for the
        cross-thread put_nowait race).
        """
        with self._lock:
            subs = list(self._subscribers)
        for loop, q in subs:
            try:
                loop.call_soon_threadsafe(self._put, q, event)
            except RuntimeError:
                # Loop closed (stale subscriber) — drop it.
                with self._lock:
                    self._subscribers = [(l, sq) for (l, sq) in self._subscribers if sq is not q]

    # ── job registry ────────────────────────────────────────────────────────

    def trigger_sync(self, source: str) -> dict:
        """Trigger a background sync for one source. Returns the job dict.

        Raises ValueError for sources outside the sync_guard allow-list.
        Returns the EXISTING running job when one is already in flight
        (dedupe — two clicks can't run two concurrent syncs of the same
        source writing to the same SQLite DB).
        """
        if source not in _SYNC_REGISTRY:
            raise ValueError(f"unknown source '{source}'")
        with self._lock:
            running = self._running_by_source.get(source)
            if running and running in self._jobs \
                    and self._jobs[running].get("status") == "running":
                job = dict(self._jobs[running])
                job["already_running"] = True
                return job
            job_id = str(uuid.uuid4())[:8]
            self._prune_finished_locked()
            self._jobs[job_id] = {
                "job_id": job_id,
                "source": source,
                "status": "running",
                "started_at": datetime.now().isoformat(timespec="seconds"),
                "progress": 0,
                "message": f"Sincronizando {source}…",
            }
            self._running_by_source[source] = job_id
        threading.Thread(
            target=self._run_sync, args=(job_id, source), daemon=True
        ).start()
        return dict(self._jobs[job_id])

    def _prune_finished_locked(self) -> None:
        """Cap the finished-job history (caller holds the lock)."""
        finished = [jid for jid, j in self._jobs.items() if j.get("status") != "running"]
        if len(finished) > self._MAX_FINISHED_JOBS:
            for jid in finished[: len(finished) - self._MAX_FINISHED_JOBS]:
                self._jobs.pop(jid, None)

    def _finish_job(self, job_id: str, source: str, status: str, message: str) -> None:
        with self._lock:
            if job_id in self._jobs:
                self._jobs[job_id]["status"] = status
                self._jobs[job_id]["progress"] = 100
                self._jobs[job_id]["message"] = message
            if self._running_by_source.get(source) == job_id:
                del self._running_by_source[source]

    def _run_sync(self, job_id: str, source: str) -> None:
        """Run the actual sync in a background thread.

        Dispatches through sync_guard._trigger_sync() — the same code path
        the skills use — so ALL registered sources work (the old 8-entry
        domain_map left 13 sources broken and still listed brapi).
        Per-ticker sources (bridge, b3_dividends) go through their bulk
        sync_all() entry points instead (see _BULK_SYNC).
        """
        try:
            self._publish({"event": "sync.started", "job_id": job_id, "source": source})
            syslog.log("info", "sync", f"{source}: sincronização iniciada")
            if source in _BULK_SYNC:
                result = self._run_bulk_sync(job_id, source)
            else:
                result = _trigger_sync(source)
            status = result.get("status", "unknown")
            if status == "ok":
                self._finish_job(job_id, source, "completed", f"Sync {source}: concluído")
                syslog.log("info", "sync", f"{source}: sincronização concluída")
            else:
                self._finish_job(job_id, source, "failed", f"Sync {source}: falhou")
                syslog.log("error", "sync", f"{source}: sincronização FALHOU")
            self._publish({
                "event": "sync.completed" if status == "ok" else "sync.failed",
                "job_id": job_id,
                "source": source,
                "status": "completed" if status == "ok" else "failed",
            })
        except Exception as e:
            # Log the real traceback server-side; UI gets a short PT-BR line.
            print(f"[webui-sync] job {job_id} ({source}) FAILED: {e}\n"
                  f"{traceback.format_exc()}", file=sys.stderr)
            syslog.log("error", "sync",
                       f"{source}: erro interno ({type(e).__name__})")
            self._finish_job(job_id, source, "failed", f"Sync {source}: erro interno")
            self._publish({
                "event": "sync.failed",
                "job_id": job_id,
                "source": source,
                "status": "failed",
            })

    def _run_bulk_sync(self, job_id: str, source: str) -> dict:
        """[v1.5 fix1] Bulk path for per-ticker sources (bridge, b3_dividends).

        Calls the engine's sync_all(force=True) with a progress callback
        that publishes sync.progress SSE events — the painel log shows
        "PETR4: ok (12/380)" lines as the loop advances.
        """
        import importlib
        module_path, fn_name = _BULK_SYNC[source]
        mod = importlib.import_module(module_path)
        bulk_fn = getattr(mod, fn_name)

        def _on_progress(p: dict) -> None:
            msg = (f"{p.get('ticker', '')}: {p.get('status', '')} "
                   f"({p.get('done', '?')}/{p.get('total', '?')})")
            self._publish({
                "event": "sync.progress",
                "job_id": job_id,
                "source": source,
                "message": msg,
            })
            syslog.log("info", "sync", f"{source}: {msg}")

        result = bulk_fn(force=True, trace_id="", on_progress=_on_progress)
        # Shape like _trigger_sync's contract so _run_sync's status logic
        # sees a plain ok/error status.
        status = result.get("status", "unknown")
        return {"status": status, "source": source, "result": result}

    def trigger_sync_all(self, stale_only: bool = True) -> dict:
        """[v1.5 fix1] Trigger background syncs for every syncable source.

        Powers the painel's "Sincronizar tudo" button. With stale_only=True
        (the default) sources fresh within the 24h window are skipped —
        one click brings everything up to date without re-downloading
        hundreds of MB that are already current. The per-source buttons
        still force unconditionally.

        Each source still gets its own job/thread (dedupe applies — a
        source already syncing is counted, not re-triggered).
        """
        fresh = self.freshness() if stale_only else {}
        started: list[dict] = []
        skipped_fresh = 0
        already_running = 0
        for source in syncable_sources():
            if stale_only and not fresh.get(source, {}).get("stale", True):
                skipped_fresh += 1
                continue
            job = self.trigger_sync(source)
            if job.get("already_running"):
                already_running += 1
            else:
                started.append(job)
        return {
            "started": started,
            "skipped_fresh": skipped_fresh,
            "already_running": already_running,
            "total_sources": len(syncable_sources()),
        }

    def job_status(self, job_id: str) -> dict | None:
        with self._lock:
            j = self._jobs.get(job_id)
            return dict(j) if j else None

    def all_jobs(self) -> list[dict]:
        with self._lock:
            return [dict(j) for j in self._jobs.values()]

    # ── [v1.20] periodic auto-sync scheduler ──────────────────────────────────

    def start_scheduler(self) -> None:
        """Start the periodic auto-sync (sync.schedule_hours; 0 = off).

        Idempotent; the interval is re-read every cycle so a settings
        change applies without a restart. Fires trigger_sync_all(stale_only
        =True) — the "Sincronizar tudo" semantics, deduped per source.
        """
        if self._sched_thread is not None and self._sched_thread.is_alive():
            return
        self._sched_stop.clear()
        self._sched_last_fire = time.monotonic()
        self._sched_thread = threading.Thread(
            target=self._sched_loop, name="webui-sync-scheduler", daemon=True,
        )
        self._sched_thread.start()

    def stop_scheduler(self) -> None:
        """Signal the scheduler to stop (app shutdown)."""
        self._sched_stop.set()

    def _sched_loop(self) -> None:
        while not self._sched_stop.wait(self._SCHED_TICK):
            try:
                interval = settings_service().get("sync.schedule_hours", 0)
                interval = float(interval) if interval else 0.0
            except (TypeError, ValueError):
                interval = 0.0
            if interval <= 0:
                continue
            if time.monotonic() - self._sched_last_fire < interval * 3600.0:
                continue
            self._sched_last_fire = time.monotonic()
            h = f"{interval:g}".replace(".", ",")
            syslog.log("info", "sync",
                       f"Agenda automática: sincronizando fontes desatualizadas "
                       f"(intervalo de {h}h)")
            try:
                res = self.trigger_sync_all(stale_only=True)
                n = len(res.get("started", []))
                syslog.log("info", "sync",
                           f"Agenda automática: {n} fonte(s) iniciada(s), "
                           f"{res.get('skipped_fresh', 0)} já atualizada(s)")
            except Exception as e:
                syslog.log("error", "sync",
                           f"Agenda automática falhou: {type(e).__name__}: {e}")
