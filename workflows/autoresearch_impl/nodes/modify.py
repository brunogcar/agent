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

[v1.6] When `parallel_count > 1`, writes each of the N proposals in
`current_experiments` to its own temp directory
(`{project_root}/.autoresearch/parallel/{i}/{target_file}`). The real
`target_file` is NOT touched in this mode — `node_decide` later copies the
winner's content back to the real path. Per-proposal failures (empty
new_content, dedup hit, path traversal, protected file) are recorded as
`proposal["status"]="failed"` with an `error` reason — the downstream
`node_run_experiment` skips experiments whose temp file doesn't exist (which
is what happens when modify marked them failed). When `parallel_count == 1`,
the v1.5 single-write path runs unchanged.
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


def _check_target_safety(target_path: Path, target_file: str, project_root: str, tid: str) -> str:
    """Shared safety checks for both single + parallel paths.

    Returns an empty string on success, or a non-empty error message on
    failure (path traversal / protected file / etc.). Split out so the
    parallel path can call it per-proposal without duplicating logic.
    """
    # [v1.3 P1-3] Path traversal guard — target_file must be within project_root.
    if project_root:
        try:
            target_path.resolve().relative_to(Path(project_root).resolve())
        except ValueError:
            return f"path traversal blocked: {target_file}"

    # [v1.3 P1-3] Protected file check — same list used by the `file` tool.
    from core.config import cfg
    if cfg.is_protected(target_path):
        return f"protected file: {target_file}"

    return ""


def node_modify(state: AutoresearchState) -> dict:
    """Apply the proposed change to target_file.

    Returns a partial state dict. On failure, sets status="failed" so the
    decide node knows to discard this experiment (git reset will be a no-op
    since nothing was written).

    [v1.6] When `parallel_count > 1`, writes each proposal in
    `current_experiments` to its own temp dir under
    `{project_root}/.autoresearch/parallel/{i}/`. Per-proposal failures
    (empty content / dedup / path / protected) set `proposal["status"]
    ="failed"` with an `error` reason. The real `target_file` is NOT
    touched — `node_decide` copies the winner back.
    """
    tid = state.get("trace_id", "")
    target_file = state.get("target_file", "")
    project_root = state.get("project_root", "")
    history = state.get("experiment_history", []) or []
    parallel_count = int(state.get("parallel_count", 1) or 1)

    # ── [v1.6] Parallel path: write each proposal to its own temp dir ──────
    if parallel_count > 1:
        proposals = [dict(p) for p in (state.get("current_experiments", []) or [])]
        base_path = Path(project_root) if project_root else Path(".")
        parallel_dir = base_path / ".autoresearch" / "parallel"

        tracer.step(
            tid, "modify",
            f"parallel mode: writing {len(proposals)} proposals to {parallel_dir}",
        )

        for i, proposal in enumerate(proposals):
            # Skip if propose already marked this proposal failed (LLM call
            # failed). The downstream run_experiment will see no temp file
            # and produce a "skipped" sentinel output.
            if proposal.get("status") == "failed":
                continue

            new_content = proposal.get("new_content", "")

            # Empty new_content — mark failed (mirrors v1.5 single path).
            if not new_content:
                tracer.warning(
                    tid, "modify",
                    f"parallel proposal {i} has empty new_content — skipping",
                )
                proposal["status"] = "failed"
                proposal["error"] = "empty new_content"
                continue

            # [v1.4 N8] Dedup check — skip if this exact content was already
            # tried. Hash is stored on the proposal so node_log persists it
            # in experiment_history for future dedup checks.
            content_hash = hashlib.md5(new_content.encode("utf-8")).hexdigest()
            proposal["content_hash"] = content_hash
            is_dup = any(h.get("content_hash") == content_hash for h in history)
            if is_dup:
                tracer.warning(
                    tid, "modify",
                    f"parallel proposal {i} duplicate (hash={content_hash[:8]}) — skipping",
                )
                proposal["status"] = "failed"
                proposal["error"] = "duplicate"
                continue

            # Per-proposal target path inside the temp dir.
            exp_dir = parallel_dir / str(i)
            target_path = exp_dir / target_file

            # [v1.3 P1-3] Safety checks (path traversal + protected file).
            safety_err = _check_target_safety(target_path, target_file, project_root, tid)
            if safety_err:
                tracer.error(tid, "modify", f"parallel proposal {i}: {safety_err}")
                proposal["status"] = "failed"
                proposal["error"] = safety_err
                continue

            try:
                _atomic_write(target_path, new_content)
                tracer.step(
                    tid, "modify",
                    f"parallel proposal {i}: wrote {len(new_content)} chars to {target_path}",
                )
            except Exception as e:
                tracer.error(tid, "modify", f"parallel proposal {i}: write failed: {e}")
                proposal["status"] = "failed"
                proposal["error"] = f"write failed: {e}"

        return {
            "current_experiments": proposals,
            # Mirror the first non-failed proposal for v1.5 backward compat
            # (singular field is used by the v1.5 path when parallel_count==1).
            # Falls back to the first proposal (which may be failed) if all
            # failed — node_decide's parallel path handles this case.
            "current_experiment": next(
                (p for p in proposals if p.get("status") != "failed"),
                proposals[0] if proposals else {},
            ),
            "status": "running",
            "error": "",
        }

    # ── v1.5 single-proposal path (unchanged) ──────────────────────────────
    proposal = state.get("current_experiment", {}) or {}

    new_content = proposal.get("new_content", "")

    # [v1.4 N8] Deduplication — skip if this exact content was already tried.
    # md5 is fast and we only need exact-content dedup (semantic dedup is N4,
    # deferred). The hash is stored on the proposal for `node_log` to persist
    # in `experiment_history` so future iterations can dedup against it.
    content_hash = hashlib.md5(new_content.encode("utf-8")).hexdigest()
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

    safety_err = _check_target_safety(target_path, target_file, project_root, tid)
    if safety_err:
        tracer.error(tid, "modify", safety_err)
        return {
            "status": "failed",
            "error": safety_err,
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
