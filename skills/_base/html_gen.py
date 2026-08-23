"""skills/_base/html_gen.py — Auto HTML dashboard generation for dashboard mode.

Provides:
  - _auto_generate_html() — pipes successful dashboard mode results through
    tools.report_ops.html.build_dashboard() and writes an HTML file to the
    REPORTS ROOT (workspace/reports/) with a company prefix.

Part of the skills/_base/ package split (was originally in skills/_base.py).
"""
from __future__ import annotations

import os


def _auto_generate_html(skill_name: str, mode: str, kwargs: dict, result: dict) -> None:
    """Auto-generate an HTML dashboard file for dashboard mode results.

    [v5] Every time a skill's route(mode="dashboard", ...) produces a
    successful result with tabs, this function pipes the result into
    tools.report_ops.html.build_dashboard() and writes an HTML file.

    The HTML file is written to the REPORTS ROOT (workspace/reports/) with a
    company prefix: e.g. ``PETR4_valuation_dashboard.html``.

    The html_path is added to the result dict so callers can open it.

    Skipped when:
      - mode != "dashboard"
      - result status != "ok" or no tabs
      - CVM_SKIP_HTML=1 env var is set (for tests)

    NOTE: Re-entrancy is already handled by _SYNC_CHECKED — inner route()
    calls return early from _route_with_sync_guard before reaching here.

    Wrapped in try/except — NEVER breaks the dashboard result. On failure,
    prints a warning and continues without html_path.
    """
    # Only dashboard mode
    if mode != "dashboard":
        return
    # Only successful results with tabs
    if not isinstance(result, dict):
        return
    if result.get("status") != "ok":
        return
    if not result.get("tabs"):
        return
    # Escape hatch for tests
    if os.environ.get("CVM_SKIP_HTML") == "1":
        return

    try:
        from pathlib import Path as _Path
        import shutil as _shutil
        from tools.report_ops import html as _report_html

        # Get company/ticker for the filename prefix.
        # Try kwargs first (company / ticker / underlying / tickers list), then result dict.
        company = (kwargs.get("company") or kwargs.get("ticker") or kwargs.get("underlying") or "").strip()
        if not company:
            tickers = kwargs.get("tickers")
            if isinstance(tickers, list) and tickers:
                company = str(tickers[0]).strip()
        if not company and isinstance(result, dict):
            company = (result.get("company") or result.get("ticker") or "").strip()
            if isinstance(company, list) and company:
                company = str(company[0])
        safe_company = "".join(
            c if c.isalnum() or c in "-_" else "_" for c in company
        ) if company else ""

        # Build the HTML via the report tool (writes to a temp subfolder).
        # build_dashboard creates 3 files: {title}.html, manifest.json, metrics.json
        _trace = f"auto_{skill_name}"
        _title = f"{skill_name} dashboard"
        html_result = _report_html.build_dashboard(
            trace_id=_trace,
            title=_title,
            data=result,
            config={},
        )
        src_path_str = html_result.get("html_path", "")
        if not src_path_str:
            return
        src_path = _Path(src_path_str)
        if not src_path.exists():
            return

        # Move ALL files (HTML + manifest.json + metrics.json) to REPORTS ROOT.
        # Reports root = workspace/reports/ (parent of the trace_id subfolder).
        reports_root = src_path.parent.parent
        prefix = f"{safe_company}_" if safe_company else ""
        sub_dir = src_path.parent  # workspace/reports/auto_{skill_name}/

        # Move the HTML file with company prefix.
        dst_html = reports_root / f"{prefix}{skill_name}_dashboard.html"
        if dst_html.exists():
            dst_html.unlink()
        _shutil.move(str(src_path), str(dst_html))

        # Move manifest.json + metrics.json to root with company prefix.
        for json_name in ("manifest.json", "metrics.json"):
            src_json = sub_dir / json_name
            if src_json.exists():
                json_prefix = f"{prefix}{skill_name}_dashboard_"
                dst_json = reports_root / f"{json_prefix}{json_name}"
                if dst_json.exists():
                    dst_json.unlink()
                _shutil.move(str(src_json), str(dst_json))

        # Remove the now-empty trace_id subfolder (and any empty parents).
        try:
            if sub_dir.exists() and not any(sub_dir.iterdir()):
                sub_dir.rmdir()
        except OSError:
            pass  # not empty or in use — leave it

        result["html_path"] = str(dst_html)
        print(f"  [html] {skill_name} dashboard → {dst_html}", flush=True)
    except Exception as e:
        # Never break the dashboard — just warn + record in result for visibility
        print(f"  [html] {skill_name} dashboard HTML generation failed: {e}", flush=True)
        if isinstance(result, dict):
            if "_html_errors" not in result:
                result["_html_errors"] = []
            result["_html_errors"].append(str(e))
