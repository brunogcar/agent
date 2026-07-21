"""tests/core/test_atomic_write.py — unit tests for core/atomic_write.py.

7 tests covering:
  - creates_file (basic happy path)
  - overwrites_existing (target already exists)
  - creates_parent_dirs (target's parent dir doesn't exist)
  - no_tmp_leak_on_success (no .tmp files left behind after success)
  - no_tmp_leak_on_failure (os.replace patched to raise — tempfile cleaned up)
  - unicode_content (non-ASCII chars round-trip cleanly)
  - empty_content (writing "" works — edge case for f.flush + fsync)

Phase A of the centralize-workflow-utils refactor (v1.5 of core/standalone).
"""
from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import pytest


def test_creates_file(tmp_path: Path):
    """Basic happy path — atomic_write creates a new file with the given content."""
    from core.atomic_write import atomic_write
    target = tmp_path / "out.txt"
    atomic_write(target, "hello world")
    assert target.read_text(encoding="utf-8") == "hello world"


def test_overwrites_existing(tmp_path: Path):
    """atomic_write replaces existing file content (os.replace is atomic)."""
    from core.atomic_write import atomic_write
    target = tmp_path / "out.txt"
    target.write_text("OLD CONTENT", encoding="utf-8")
    atomic_write(target, "NEW CONTENT")
    assert target.read_text(encoding="utf-8") == "NEW CONTENT"


def test_creates_parent_dirs(tmp_path: Path):
    """atomic_write creates missing parent directories (mkdir -p semantics)."""
    from core.atomic_write import atomic_write
    target = tmp_path / "a" / "b" / "c" / "out.txt"
    assert not target.parent.exists()
    atomic_write(target, "nested")
    assert target.read_text(encoding="utf-8") == "nested"
    assert target.parent.is_dir()  # parents created


def test_no_tmp_leak_on_success(tmp_path: Path):
    """After a successful write, no .tmp files should remain in the dir."""
    from core.atomic_write import atomic_write
    target = tmp_path / "out.txt"
    atomic_write(target, "content")
    # Find any files matching the tempfile pattern `.{name}.*.tmp`.
    leftovers = list(tmp_path.glob(".*.tmp"))
    assert leftovers == [], f"tempfile leaked on success: {leftovers}"


def test_no_tmp_leak_on_failure(tmp_path: Path):
    """If os.replace raises, the tempfile must be cleaned up before re-raising."""
    from core.atomic_write import atomic_write
    target = tmp_path / "out.txt"

    # Patch os.replace inside the atomic_write module to raise — simulates
    # a permission error, cross-filesystem rename, or other os.replace failure.
    with patch("core.atomic_write.os.replace", side_effect=OSError("simulated")):
        with pytest.raises(OSError, match="simulated"):
            atomic_write(target, "content")

    # No tempfile should be left behind in the target dir.
    leftovers = list(tmp_path.glob(".*.tmp"))
    assert leftovers == [], f"tempfile leaked on failure: {leftovers}"
    # The target file itself must NOT exist (the write failed before os.replace).
    assert not target.exists()


def test_unicode_content(tmp_path: Path):
    """Non-ASCII unicode content round-trips cleanly through the write."""
    from core.atomic_write import atomic_write
    target = tmp_path / "out.txt"
    # Mix of CJK + accented Latin + emoji — exercises UTF-8 multibyte.
    content = "héllo wörld — 日本語 test 🚀\nline 2: café"
    atomic_write(target, content)
    assert target.read_text(encoding="utf-8") == content


def test_empty_content(tmp_path: Path):
    """Writing an empty string is a valid edge case (f.flush + fsync on no bytes)."""
    from core.atomic_write import atomic_write
    target = tmp_path / "empty.txt"
    atomic_write(target, "")
    assert target.read_text(encoding="utf-8") == ""
    assert target.stat().st_size == 0
