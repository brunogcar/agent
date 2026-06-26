"""Cleanup proxy actions for cli meta-tool.

On-demand cleanup of old autocode runs and other ephemeral artifacts.
All functions auto-register via @register_action decorator.
"""
from __future__ import annotations

import shutil
from datetime import datetime, timedelta
from pathlib import Path

from tools.cli_ops._registry import register_action
from core.config import cfg


def _cleanup_autocode_runs(max_age_days: int = 7, dry_run: bool = False) -> str:
    """Delete autocode run folders older than max_age_days."""
    autocode_base = cfg.workspace_root / "autocode"
    if not autocode_base.exists():
        return "No autocode directory found."

    cutoff = datetime.now() - timedelta(days=max_age_days)
    removed = []
    skipped = []

    for date_dir in autocode_base.iterdir():
        if not date_dir.is_dir() or not date_dir.name.isdigit() or len(date_dir.name) != 8:
            skipped.append(str(date_dir.name))
            continue
        try:
            dir_date = datetime.strptime(date_dir.name, "%Y%m%d")
            if dir_date < cutoff:
                if not dry_run:
                    shutil.rmtree(date_dir, ignore_errors=True)
                removed.append(str(date_dir))
            else:
                skipped.append(str(date_dir.name))
        except (ValueError, OSError) as e:
            skipped.append(f"{date_dir.name} (error: {e})")

    prefix = "[DRY RUN] Would remove" if dry_run else "Removed"
    lines = [f"{prefix} {len(removed)} old autocode date dir(s):"]
    for r in removed:
        lines.append(f"  - {r}")
    if skipped:
        lines.append(f"Kept {len(skipped)} dir(s):")
        for s in skipped:
            lines.append(f"  - {s}")
    return "\n".join(lines)


@register_action(
    "cleanup", "autocode",
    help_text="Clean up old autocode runs older than N days.",
    examples=["cleanup autocode 7", "cleanup autocode"],
)
def _cleanup_autocode(action: str = "", days: int = 7, **params) -> str:
    """Clean up old autocode runs."""
    return _cleanup_autocode_runs(max_age_days=days, dry_run=False)


@register_action(
    "cleanup", "dry_run",
    help_text="Preview what autocode cleanup would remove.",
    examples=["dry run cleanup autocode"],
)
def _cleanup_dry_run(action: str = "", days: int = 7, **params) -> str:
    """Preview what would be cleaned up."""
    return _cleanup_autocode_runs(max_age_days=days, dry_run=True)
