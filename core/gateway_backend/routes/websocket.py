"""core/gateway_backend/routes/websocket.py — WebSocket endpoint for real-time task progress.

v1.1: New endpoint /ws — client connects via WebSocket, submits a task,
receives progress events as they happen (instead of polling /result/{trace_id}).

Protocol:
  Client sends JSON: {"goal": "...", "workflow": "auto", "tool": null, "action": null, "params": {}}
  Server streams:
    {"event": "started", "trace_id": "..."}
    {"event": "progress", "step": "routing", "detail": "..."}
    {"event": "completed", "result": {...}, "elapsed": 12.5}
    OR
    {"event": "failed", "error": "...", "elapsed": 5.2}

The WebSocket handler runs the task in a background thread (same as /task),
but streams tracer events to the client as they happen. When the task
completes, the final result is sent and the connection closes.

Auth: Bearer token via query param ?token=<GATEWAY_SECRET> (WebSocket
doesn't support custom headers in browsers, so query param is the standard
approach used by FastAPI/Socket.io/etc.)
"""
from __future__ import annotations

import asyncio
import json
import time
import threading
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from core.tracer import tracer
from core.config import cfg

router = APIRouter()


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for real-time task progress streaming.

    Auth: ?token=<GATEWAY_SECRET> query param (browsers can't set
    custom headers on WebSocket connections).
    """
    # ── Auth via query param ────────────────────────────────────────────
    token = websocket.query_params.get("token", "")
    secret = (getattr(cfg, "gateway_secret", "") or "").strip()
    if not secret or token != secret:
        await websocket.accept()
        await websocket.send_json({"event": "auth_failed", "error": "Invalid or missing token"})
        await websocket.close(code=4001)
        return

    await websocket.accept()

    # ── Wait for client to send a task ──────────────────────────────────
    try:
        raw = await asyncio.wait_for(websocket.receive_text(), timeout=60.0)
    except asyncio.TimeoutError:
        await websocket.send_json({"event": "timeout", "error": "No task received within 60s"})
        await websocket.close(code=4002)
        return
    except WebSocketDisconnect:
        return

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        await websocket.send_json({"event": "error", "error": "Invalid JSON"})
        await websocket.close(code=4003)
        return

    goal = payload.get("goal", "")
    if not goal:
        await websocket.send_json({"event": "error", "error": "goal is required"})
        await websocket.close(code=4003)
        return

    # ── Create trace + dispatch in background ───────────────────────────
    trace_id = tracer.new_trace(
        payload.get("workflow", "auto"),
        goal=goal[:60],
    )

    await websocket.send_json({"event": "started", "trace_id": trace_id})

    # Progress streaming: poll the tracer for new events every 200ms
    # and send them to the client. The actual task runs in a thread.
    result_container: list[Any] = []
    error_container: list[str] = []
    start_time = time.time()
    last_event_count = 0

    def _run_task():
        """Run the task in a background thread."""
        try:
            from core.gateway_backend.dependencies import get_dispatcher
            dispatcher = get_dispatcher()
            result = dispatcher.dispatch(trace_id, payload)
            result_container.append(result)
        except Exception as e:
            error_container.append(str(e))

    task_thread = threading.Thread(target=_run_task, daemon=True)
    task_thread.start()

    # ── Stream progress while task runs ─────────────────────────────────
    try:
        while task_thread.is_alive():
            task_thread.join(timeout=0.2)  # Check every 200ms

            # Stream any new tracer events
            trace = tracer.get(trace_id)
            if trace:
                events = trace.get("events", [])
                if len(events) > last_event_count:
                    for event in events[last_event_count:]:
                        await websocket.send_json({
                            "event": "progress",
                            "step": event.get("event", ""),
                            "detail": event.get("msg", "")[:200],
                            "ts": event.get("ts", 0),
                        })
                    last_event_count = len(events)

        # Task completed — send final result
        elapsed = round(time.time() - start_time, 2)

        # Stream any remaining events
        trace = tracer.get(trace_id)
        if trace:
            events = trace.get("events", [])
            if len(events) > last_event_count:
                for event in events[last_event_count:]:
                    await websocket.send_json({
                        "event": "progress",
                        "step": event.get("event", ""),
                        "detail": event.get("msg", "")[:200],
                        "ts": event.get("ts", 0),
                    })

        if error_container:
            await websocket.send_json({
                "event": "failed",
                "error": error_container[0],
                "elapsed": elapsed,
            })
        else:
            result = result_container[0] if result_container else None
            await websocket.send_json({
                "event": "completed",
                "result": result,
                "elapsed": elapsed,
            })

    except WebSocketDisconnect:
        pass  # Client disconnected — let the thread finish in background
    except Exception as e:
        try:
            await websocket.send_json({
                "event": "failed",
                "error": f"WebSocket error: {e}",
                "elapsed": round(time.time() - start_time, 2),
            })
        except Exception:
            pass

    finally:
        try:
            await websocket.close()
        except Exception:
            pass
