#!/usr/bin/env python
"""
run_b3_sync.py -- Standalone B3 data sync script.

PURPOSE
-------
Runs the B3 API skill outside the MCP server / python sandbox.
Use this when:
  1. Testing the sync before the MCP server is running
  2. Scheduling daily syncs via Windows Task Scheduler or cron
  3. The agent can't call skill() directly (import sandbox restrictions)

USAGE (from D:/mcp/agent):
  python run_b3_sync.py                          # sync all 5 files
  python run_b3_sync.py Instruments              # sync one file
  python run_b3_sync.py Instruments Trades       # sync two files
  python run_b3_sync.py --force                  # force re-download even if current
  python run_b3_sync.py Instruments --force      # force specific file
  python run_b3_sync.py --status                 # show current sync status only

AGENT USAGE
-----------
The agent cannot call `from skills.b3 import route` inside python:run_data
because `skills` is not in the sandbox allowlist (it imports requests, sqlite3,
core.config which in turn load .env -- all unsafe in a sandboxed eval context).

Correct agent pattern to trigger a sync:
  cli("python D:/mcp/agent/run_b3_sync.py Instruments")

Or better -- now that registry.py scans skills/, the agent just calls:
  skill(domain="b3_api", mode="sync", files=["Instruments"])
directly as an MCP tool call (no Python execution needed).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# ── Bootstrap sys.path so skills/ and core/ are importable ──────────────────
# This makes the script runnable from any working directory.
_AGENT_ROOT = Path(__file__).resolve().parent
if str(_AGENT_ROOT) not in sys.path:
    sys.path.insert(0, str(_AGENT_ROOT))


def _parse_args() -> tuple[list[str] | None, bool, bool]:
    """Parse CLI args. Returns (files, force, status_only)."""
    args      = sys.argv[1:]
    force     = "--force" in args
    status_only = "--status" in args
    args      = [a for a in args if not a.startswith("--")]

    valid = {"Instruments", "Trades", "AfterHours", "Derivatives", "MarginScenario"}
    files = [a for a in args if a in valid]

    # Warn about unrecognised args
    unknown = [a for a in args if a not in valid]
    if unknown:
        print(f"[warn] Unknown file names ignored: {unknown}", file=sys.stderr)
        print(f"[warn] Valid names: {sorted(valid)}", file=sys.stderr)

    return files or None, force, status_only


def main() -> int:
    files, force, status_only = _parse_args()

    try:
        from skills.b3.b3_api import sync, status as get_status
    except ImportError as e:
        print(f"[error] Cannot import skills.b3: {e}", file=sys.stderr)
        print(f"[error] Make sure you are running from D:/mcp/agent", file=sys.stderr)
        print(f"[error] Current dir: {Path.cwd()}", file=sys.stderr)
        return 1

    # Status-only mode
    if status_only:
        result = get_status()
        print(json.dumps(result, indent=2, ensure_ascii=False))
        _print_status_summary(result)
        return 0

    # Sync
    target = files or ["Instruments", "Trades", "AfterHours", "Derivatives", "MarginScenario"]
    print(f"[b3_sync] Syncing: {target}" + (" (forced)" if force else ""), flush=True)

    result = sync(files=files, force=force)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    _print_sync_summary(result)

    # Exit 1 if any file errored
    if result.get("status") == "error":
        return 1
    errors = [
        name for name, r in result.get("results", {}).items()
        if r.get("status") == "error"
    ]
    return 1 if errors else 0


def _print_sync_summary(result: dict) -> None:
    """Print a human-readable summary after sync."""
    print("\n--- SYNC SUMMARY ---")
    for name, r in result.get("results", {}).items():
        status  = r.get("status", "?")
        rows    = r.get("rows", 0)
        elapsed = r.get("elapsed_s", 0)
        date    = r.get("date", "")
        if status == "synced":
            print(f"  OK  {name:20s} {rows:>8,} rows   {elapsed:5.1f}s   {date}")
        elif status == "skipped":
            reason = r.get("reason", "")
            print(f"  --  {name:20s} skipped ({reason})")
        else:
            err = r.get("error", "unknown error")[:60]
            print(f"  ERR {name:20s} {err}")
    print()


def _print_status_summary(result: dict) -> None:
    """Print a human-readable status table."""
    print("\n--- B3 SYNC STATUS ---")
    for name, r in result.get("files", {}).items():
        synced   = r.get("synced", False)
        rows     = r.get("rows", 0)
        date     = r.get("report_date", "not synced")
        size_kb  = r.get("db_size_kb", 0)
        synced_at = r.get("synced_at", "")[:16].replace("T", " ")
        flag     = "OK " if synced else "---"
        print(f"  {flag} {name:20s} {rows:>8,} rows   {size_kb:7.1f} KB   date={date}   synced={synced_at}")
    print()


if __name__ == "__main__":
    sys.exit(main())
