"""Node: modify — Apply the proposed code change to target_file.

[v1.0] Writes the proposed `new_content` to the target_file using an atomic
write (tempfile + os.replace). Atomic writes ensure the file is never left
in a half-written state if the process is killed mid-write.

If the proposal's `new_content` is empty (LLM parse failure, etc.), the node
skips the write and sets a sentinel error so the decide node can discard the
experiment.

Returns a PARTIAL state dict with the new file content (for the trace log)
and a status flag indicating whether the modify succeeded.

[v1.3 P1-3] Path traversal guard — `target_file` must resolve to a path
inside `project_root`. Was: a malicious or hallucinating LLM could propose
`target_file="../../../etc/passwd"` and the node would happily write to it.
Now blocked with a clear error.

[v1.3 P1-3] Protected file check — `target_file` is checked against
`cfg.is_protected()` (the same list used by the `file` tool). Was: autoresearch
could modify protected files (e.g. `.env`, `pyproject.toml`, agent source)
without any guardrail. Now blocked with a clear error.

[v1.4 N8] Experiment deduplication — `new_content` is md5-hashed BEFORE the
write. If the hash matches any previous experiment's `content_hash` in
`experiment_history`, the write is skipped and `status="failed"` is returned
with a "duplicate" error. Prevents the LLM from re-proposing the exact same
change (which the loop would otherwise re-run + re-evaluate pointlessly).
The hash is stored on `current_experiment.content_hash` so `node_log` can
persist it in `experiment_history` for future dedup checks.
"""
from __future__ import annotations

import hashlib
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

    # [v1.4 N8] Deduplication — skip if this exact content was already tried.
    # md5 is fast and we only need exact-content dedup (semantic dedup is N4,
    # deferred). The hash is stored on the proposal for `node_log` to persist
    # in `experiment_history` so future iterations can dedup against it.
    content_hash = hashlib.md5(new_content.encode("utf-8")).hexdigest()
    history = state.get("experiment_history", []) or []
    for h in history:
        if h.get("content_hash") == content_hash:
            tracer.warning(
                tid, "modify",
                f"duplicate experiment (hash={content_hash[:8]}) — skipping",
            )
            return {
                "status": "failed",
                "error": (
                    f"duplicate experiment — same content as iteration "
                    f"{h.get('iteration', '?')}"
                ),
            }

    # Store the hash on the proposal so node_log persists it in history.
    # Mutates the dict in-place — same pattern as node_decide annotating
    # status/commit/metric on the proposal (see INSTRUCTIONS.md #16).
    proposal["content_hash"] = content_hash

    description = proposal.get("description", "")

    if not new_content:
        tracer.warning(tid, "modify", "proposal has empty new_content — skipping write")
        return {
            "status": "failed",
            "error": "proposal new_content is empty — nothing to modify",
        }

    target_path = Path(project_root) / target_file if project_root else Path(target_file)

    # [v1.3 P1-3] Path traversal guard — target_file must be within project_root.
    # A malicious or hallucinating LLM could propose target_file="../../etc/passwd"
    # and we'd happily write to it. Block with a clear error.
    if project_root:
        try:
            target_path.resolve().relative_to(Path(project_root).resolve())
        except ValueError:
            tracer.error(tid, "modify", f"path traversal blocked: {target_file}")
            return {
                "status": "failed",
                "error": f"path traversal blocked: {target_file}",
            }

    # [v1.3 P1-3] Protected file check — same list used by the `file` tool.
    # Autoresearch should NOT modify .env, pyproject.toml, agent source, etc.
    from core.config import cfg
    if cfg.is_protected(target_path):
        tracer.error(tid, "modify", f"protected file: {target_file}")
        return {
            "status": "failed",
            "error": f"protected file: {target_file}",
        }

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
