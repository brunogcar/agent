"""Node: modify — Apply the proposed code change to target_file.

[v1.0] Writes the proposed `new_content` to the target_file using an atomic
write (tempfile + os.replace). Atomic writes ensure the file is never left
in a half-written state if the process is killed mid-write.

If the proposal's `new_content` is empty (LLM parse failure, etc.), the node
skips the write and sets a sentinel error so the decide node can discard the
experiment.

Returns a PARTIAL state dict with the new file content (for the trace log)
and a status flag indicating whether the modify succeeded.
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

from core.tracer import tracer
from workflows.autoresearch_impl.state import AutoresearchState


def _atomic_write(path: Path, content: str) -> None:
    """Write content to path atomically.

    Writes to a tempfile in the same directory, then os.replace()s it into
    place. os.replace is atomic on POSIX and Windows for same-filesystem
    renames, so readers never see a partial file.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    # tempfile in the same directory guarantees same-filesystem rename
    fd, tmp_path = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=str(path.parent),
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, path)
    except Exception:
        # Clean up the tempfile on failure — don't leak .tmp files
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def node_modify(state: AutoresearchState) -> dict:
    """Apply the proposed change to target_file.

    Returns a partial state dict. On failure, sets status="failed" so the
    decide node knows to discard this experiment (git reset will be a no-op
    since nothing was written).
    """
    tid = state.get("trace_id", "")
    target_file = state.get("target_file", "")
    project_root = state.get("project_root", "")
    proposal = state.get("current_experiment", {}) or {}

    new_content = proposal.get("new_content", "")
    description = proposal.get("description", "")

    if not new_content:
        tracer.warning(tid, "modify", "proposal has empty new_content — skipping write")
        return {
            "status": "failed",
            "error": "proposal new_content is empty — nothing to modify",
        }

    target_path = Path(project_root) / target_file if project_root else Path(target_file)
    tracer.step(
        tid, "modify",
        f"writing {len(new_content)} chars to {target_file} (proposal: {description[:60]})",
    )

    try:
        _atomic_write(target_path, new_content)
    except Exception as e:
        tracer.error(tid, "modify", f"atomic write failed: {e}")
        return {
            "status": "failed",
            "error": f"failed to write {target_file}: {e}",
        }

    return {
        "status": "running",
        "error": "",
    }
