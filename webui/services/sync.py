"""webui/services/sync.py — data source sync service.

[WebUI v1] Wraps the existing freshness helper + data_source dispatcher
for the WebUI. Non-blocking — sync runs in background, progress pushed
via SSE.

Freshness check is cheap (SELECT MAX(synced_at) per DB). Sync is
expensive (downloads ZIPs from CVM/B3 APIs) — must NOT block the event
loop.
"""
from __future__ import annotations

import asyncio
import threading
from datetime import datetime
from typing import Any

from skills._freshness import get_freshness


class SyncService:
    """Data source sync service — freshness check + background sync."""

    def __init__(self) -> None:
        # In-memory job registry (job_id → status dict)
        self._jobs: dict[str, dict] = {}
        # SSE subscribers (asyncio.Queue per subscriber)
        self._subscribers: list[asyncio.Queue] = []
        self._lock = threading.Lock()

    def freshness(self) -> dict[str, dict[str, Any]]:
        """Get freshness status for all data sources.

        Returns: {"dfp": {"last_sync": "2026-...", "stale": False}, ...}
        """
        fresh = get_freshness()
        out: dict[str, dict] = {}
        now = datetime.now()
        for source, ts_str in fresh.items():
            stale = True
            if ts_str:
                try:
                    # Parse ISO timestamp
                    ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                    # Stale if > 24h old
                    stale = (now - ts).total_seconds() > 86400
                except Exception:
                    stale = True
            out[source] = {
                "last_sync": ts_str or "",
                "stale": stale,
                "status": "stale" if stale else "fresh",
            }
        return out

    def subscribe(self) -> asyncio.Queue:
        """Subscribe to sync progress events (SSE). Returns a queue."""
        q: asyncio.Queue = asyncio.Queue()
        with self._lock:
            self._subscribers.append(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        with self._lock:
            if q in self._subscribers:
                self._subscribers.remove(q)

    def _publish(self, event: dict) -> None:
        """Push an event to all SSE subscribers."""
        with self._lock:
            for q in self._subscribers:
                try:
                    q.put_nowait(event)
                except asyncio.QueueFull:
                    pass  # drop if subscriber is slow

    def trigger_sync(self, source: str) -> str:
        """Trigger a background sync for one source. Returns job_id."""
        import uuid
        job_id = str(uuid.uuid4())[:8]
        self._jobs[job_id] = {
            "job_id": job_id,
            "source": source,
            "status": "running",
            "started_at": datetime.now().isoformat(),
            "progress": 0,
            "message": f"Starting sync for {source}",
        }
        # Run sync in a daemon thread (sync code is blocking)
        thread = threading.Thread(
            target=self._run_sync, args=(job_id, source), daemon=True
        )
        thread.start()
        return job_id

    def _run_sync(self, job_id: str, source: str) -> None:
        """Run the actual sync in a background thread."""
        try:
            self._publish({"event": "sync.started", "job_id": job_id, "source": source})
            # Use the existing data_source dispatcher
            from data_sources.dispatcher import data_source
            # Resolve source → domain/sub_domain
            # (source keys match the freshness dict: "dfp", "itr", "cotahist", etc.)
            domain_map = {
                "dfp": ("cvm", "dfp"), "itr": ("cvm", "itr"), "fca": ("cvm", "fca"),
                "fre": ("cvm", "fre"), "cad": ("cvm", "cad"),
                "cotahist": ("b3", "cotahist"), "brapi": ("b3", "brapi"),
                "sgs": ("bcb", "sgs"),
            }
            domain, sub_domain = domain_map.get(source, ("", source))
            result = data_source(domain=domain, sub_domain=sub_domain, mode="sync")
            status = result.get("status", "unknown")
            self._jobs[job_id]["status"] = "completed" if status == "ok" else "failed"
            self._jobs[job_id]["progress"] = 100
            self._jobs[job_id]["message"] = f"Sync {source}: {status}"
            self._publish({
                "event": "sync.completed",
                "job_id": job_id,
                "source": source,
                "status": self._jobs[job_id]["status"],
            })
        except Exception as e:
            self._jobs[job_id]["status"] = "failed"
            self._jobs[job_id]["message"] = str(e)
            self._publish({
                "event": "sync.failed",
                "job_id": job_id,
                "source": source,
                "error": str(e),
            })

    def job_status(self, job_id: str) -> dict | None:
        return self._jobs.get(job_id)

    def all_jobs(self) -> list[dict]:
        return list(self._jobs.values())
