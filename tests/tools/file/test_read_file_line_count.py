"""Test the `lines` field returned by read_file / read_multiple_files (v1.2 fix).

v1.2 corrected the `lines` computation from `count("\\n") + 1` to
`len(splitlines())`. The old formula overcounted files ending in a trailing
newline by 1 (e.g. "a\\nb\\nc\\n" reported 4 instead of 3).

One concern per test class — no generic names.

Concerns covered:
  - Full read with trailing newline (the bug case)
  - Full read without trailing newline (was already correct)
  - Empty / single-line files
  - head / tail / max_chars paths still report correct line count
  - read_multiple_files reports correct per-file `lines`
"""

from __future__ import annotations

import pytest
from tools.file import file


# ─────────────────────────────────────────────────────────────────────────────
# Full read — trailing newline (the v1.2 bug case)
# ─────────────────────────────────────────────────────────────────────────────

class TestTrailingNewlineFullRead:
    """read_file must NOT overcount files ending in a trailing newline.

    Pre-v1.2: "a\\nb\\nc\\n" -> count("\\n")+1 = 3+1 = 4  (WRONG)
    v1.2:     "a\\nb\\nc\\n" -> len(splitlines())  = 3      (CORRECT)
    """

    def test_three_lines_with_trailing_newline(self, mock_cfg):
        path = mock_cfg.workspace_root / "trailing.txt"
        path.write_bytes(b"a\nb\nc\n")
        result = file(action="read_file", path=str(path))
        assert result["status"] == "success"
        assert result["lines"] == 3

    def test_one_line_with_trailing_newline(self, mock_cfg):
        path = mock_cfg.workspace_root / "one.txt"
        path.write_bytes(b"only line\n")
        result = file(action="read_file", path=str(path))
        assert result["status"] == "success"
        assert result["lines"] == 1

    def test_many_lines_with_trailing_newline(self, mock_cfg):
        path = mock_cfg.workspace_root / "many.txt"
        path.write_bytes(b"\n".join(b"line%d" % i for i in range(10)) + b"\n")
        result = file(action="read_file", path=str(path))
        assert result["status"] == "success"
        assert result["lines"] == 10


# ─────────────────────────────────────────────────────────────────────────────
# Full read — no trailing newline (was already correct, guard against regression)
# ─────────────────────────────────────────────────────────────────────────────

class TestNoTrailingNewlineFullRead:
    """Files without a trailing newline: count("\\n")+1 == len(splitlines())
    coincidentally, so the old bug was invisible here. v1.2 must keep this
    correct."""

    def test_three_lines_no_trailing_newline(self, mock_cfg):
        path = mock_cfg.workspace_root / "no_trailing.txt"
        path.write_bytes(b"a\nb\nc")
        result = file(action="read_file", path=str(path))
        assert result["status"] == "success"
        assert result["lines"] == 3

    def test_one_line_no_trailing_newline(self, mock_cfg):
        path = mock_cfg.workspace_root / "solo.txt"
        path.write_bytes(b"only line")
        result = file(action="read_file", path=str(path))
        assert result["status"] == "success"
        assert result["lines"] == 1


# ─────────────────────────────────────────────────────────────────────────────
# Empty file
# ─────────────────────────────────────────────────────────────────────────────

class TestEmptyFileLines:
    """Empty file returns lines=0 via the dedicated empty-file branch."""

    def test_empty_file(self, mock_cfg):
        path = mock_cfg.workspace_root / "empty.txt"
        path.write_bytes(b"")
        result = file(action="read_file", path=str(path))
        assert result["status"] == "success"
        assert result["lines"] == 0


# ─────────────────────────────────────────────────────────────────────────────
# head / tail / max_chars paths — lines must reflect returned content
# ─────────────────────────────────────────────────────────────────────────────

class TestTruncationPathsLineCount:
    """`lines` counts the logical lines in the RETURNED (possibly truncated)
    content, not the whole file. head/tail rejoin with "\\n".join() so there is
    no trailing newline — splitlines() and count+1 agree there. The max_chars
    path can leave a trailing newline, so splitlines() is the correct choice."""

    def test_head_reports_returned_line_count(self, mock_cfg):
        path = mock_cfg.workspace_root / "head.txt"
        path.write_bytes(b"l1\nl2\nl3\nl4\nl5\n")
        result = file(action="read_file", path=str(path), head=2)
        assert result["status"] == "success"
        assert result["lines"] == 2

    def test_tail_reports_returned_line_count(self, mock_cfg):
        path = mock_cfg.workspace_root / "tail.txt"
        path.write_bytes(b"l1\nl2\nl3\nl4\nl5\n")
        result = file(action="read_file", path=str(path), tail=2)
        assert result["status"] == "success"
        assert result["lines"] == 2

    def test_max_chars_truncation_line_count(self, mock_cfg):
        """Content longer than max_chars gets truncated; `lines` must count the
        returned (truncated) content via splitlines()."""
        path = mock_cfg.workspace_root / "trunc.txt"
        # 5 lines, each 10 chars + newline = 11 bytes; total 55 bytes
        path.write_bytes(b"0123456789\n" * 5)
        # max_chars=25 keeps ~2 lines worth; exact count depends on slice point
        result = file(action="read_file", path=str(path), max_chars=25)
        assert result["status"] == "success"
        assert result["truncated"] is True
        # lines must equal splitlines() of the returned content
        assert result["lines"] == len(result["content"].splitlines())


# ─────────────────────────────────────────────────────────────────────────────
# read_multiple_files — per-file `lines` correctness
# ─────────────────────────────────────────────────────────────────────────────

class TestReadMultipleFilesLineCount:
    """Each file in the batch reports its own correct `lines`."""

    def test_mixed_trailing_newline_files(self, mock_cfg):
        trailing = mock_cfg.workspace_root / "trailing.txt"
        no_trailing = mock_cfg.workspace_root / "no_trailing.txt"
        trailing.write_bytes(b"a\nb\nc\n")     # 3 lines (trailing newline)
        no_trailing.write_bytes(b"x\ny\nz")    # 3 lines (no trailing newline)
        result = file(
            action="read_multiple_files",
            paths=[str(trailing), str(no_trailing)],
        )
        assert result["status"] == "success"
        assert result["count"] == 2
        lines_by_path = {f["path"]: f["lines"] for f in result["files"]}
        assert lines_by_path[str(trailing)] == 3
        assert lines_by_path[str(no_trailing)] == 3
