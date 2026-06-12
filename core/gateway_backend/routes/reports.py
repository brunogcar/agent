"""
core/gateway_backend/routes/reports.py — Report serving endpoints.

Serves generated reports and logs via the existing FastAPI gateway.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import FileResponse, HTMLResponse

from core.config import cfg
from core.gateway_backend.dependencies import check_auth

router = APIRouter()


def _reports_dir() -> Path:
    return cfg.workspace_root / "reports"


def _logs_dir() -> Path:
    r"""Explicit path: D:\mcp\agent\logs\agent"""
    return Path(cfg.agent_root) / "logs" / "agent"


def _list_reports() -> list[dict]:
    """Scan reports directory and return metadata for all reports."""
    reports = _reports_dir()
    if not reports.exists():
        return []

    result = []
    for trace_dir in sorted(reports.iterdir()):
        if not trace_dir.is_dir():
            continue
        manifest_path = trace_dir / "manifest.json"
        metrics_path = trace_dir / "metrics.json"
        entry = {
            "trace_id": trace_dir.name,
            "url": f"/reports/{trace_dir.name}/",
        }
        if manifest_path.exists():
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                entry.update({
                    "title": manifest.get("title", ""),
                    "action": manifest.get("action", ""),
                    "preset": manifest.get("preset", ""),
                    "created_at": manifest.get("created_at", ""),
                    "files": manifest.get("files", []),
                })
            except Exception:
                pass
        if metrics_path.exists():
            try:
                metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
                entry["metrics"] = metrics
            except Exception:
                pass
        result.append(entry)
    return result


def _dir_listing_html(path: Path, url_prefix: str, title: str) -> str:
    items = []
    for item in sorted(path.iterdir()):
        name = item.name
        if item.is_dir():
            name += "/"
        items.append(f'<li><a href="{url_prefix}{name}">{name}</a></li>')

    return f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><title>{title}</title>
<style>
body {{ font-family: ui-sans-serif, system-ui, sans-serif; max-width: 800px; margin: 40px auto; padding: 0 20px; background: #0f172a; color: #e2e8f0; }}
h1 {{ color: #0d9488; font-size: 1.5rem; border-bottom: 1px solid #334155; padding-bottom: 10px; }}
ul {{ list-style: none; padding: 0; }}
li {{ padding: 8px 0; border-bottom: 1px solid #1e293b; }}
a {{ color: #38bdf8; text-decoration: none; }}
a:hover {{ text-decoration: underline; }}
.meta {{ color: #64748b; font-size: 0.85rem; margin-top: 20px; }}
</style>
</head>
<body>
<h1>{title}</h1>
<ul>
{chr(10).join(items) if items else '<li><em>Empty</em></li>'}
</ul>
<p class="meta">Generated {datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")}</p>
</body>
</html>"""


@router.get("/api/reports")
def api_reports(_: None = Depends(check_auth)):
    """JSON array of all reports with metadata."""
    reports = _list_reports()
    return {"reports": reports, "count": len(reports)}


@router.get("/reports/{trace_id}", response_class=HTMLResponse)
def report_dir(trace_id: str):
    """Directory listing for a trace's report files."""
    safe_tid = "".join(c if c.isalnum() or c in "-_" else "_" for c in trace_id)
    trace_dir = _reports_dir() / safe_tid
    if not trace_dir.exists() or not trace_dir.is_dir():
        raise HTTPException(status_code=404, detail=f"Trace '{trace_id}' not found")
    return HTMLResponse(content=_dir_listing_html(trace_dir, f"/reports/{safe_tid}/", f"Report: {safe_tid}"))


@router.get("/reports/{trace_id}/{filename}")
def report_file(trace_id: str, filename: str):
    """Serve a specific report file (HTML, JSON, etc.)."""
    safe_tid = "".join(c if c.isalnum() or c in "-_" else "_" for c in trace_id)
    trace_dir = _reports_dir() / safe_tid
    file_path = trace_dir / filename

    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="File not found")

    # Security: ensure file is inside reports dir
    if not str(file_path.resolve()).startswith(str(trace_dir.resolve())):
        raise HTTPException(status_code=403, detail="Forbidden")

    # Guess media type
    suffix = file_path.suffix.lower()
    media_type = {
        ".html": "text/html",
        ".json": "application/json",
        ".jsonl": "application/jsonlines",
        ".txt": "text/plain",
        ".css": "text/css",
        ".js": "application/javascript",
        ".svg": "image/svg+xml",
        ".png": "image/png",
        ".jpg": "image/jpeg",
    }.get(suffix, "application/octet-stream")

    return FileResponse(path=file_path, media_type=media_type)


@router.get("/logs", response_class=HTMLResponse)
def logs_dir(_: None = Depends(check_auth)):
    """Directory listing of agent log files."""
    logs = _logs_dir()
    if not logs.exists():
        return HTMLResponse(content=_dir_listing_html(Path("."), "/logs/", "Logs (directory not found)"))
    return HTMLResponse(content=_dir_listing_html(logs, "/logs/", "Agent Logs"))


@router.get("/logs/{filename}")
def log_file(filename: str, _: None = Depends(check_auth)):
    """Serve a specific log file."""
    if ".." in filename or not filename:
        raise HTTPException(status_code=400, detail="Invalid filename")

    file_path = _logs_dir() / filename
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="File not found")

    # Security: ensure file is inside logs dir
    if not str(file_path.resolve()).startswith(str(_logs_dir().resolve())):
        raise HTTPException(status_code=403, detail="Forbidden")

    return FileResponse(path=file_path, media_type="text/plain")
