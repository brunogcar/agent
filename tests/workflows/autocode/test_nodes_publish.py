"""tests/workflows/autocode/test_nodes_publish.py — Phase 16-21 node tests.

Focused per-node tests for the publish chain nodes. Each node gets 2 tests
covering the happy path + skip condition.

Covers:
  - node_commit         (mock _git_commit, skip when not verified)
  - node_push           (mock _github_push, skip when push disabled)
  - node_create_pr      (mock _github_pr_create, skip when PR disabled)
  - node_merge_pr       (mock _github_pr_merge, skip when auto-merge disabled)
  - node_distill_memory (mock distill_workflow, non-fatal on exception)
  - node_report         (mock report tool, non-fatal on exception)

LLM/git/github/memory calls are mocked per-test — no real external calls.
"""
from __future__ import annotations

from unittest.mock import patch, MagicMock

import pytest


# ---------------------------------------------------------------------------
# node_commit
# ---------------------------------------------------------------------------


class TestNodeCommit:
    def test_skips_when_not_verified(self, base_state):
        from workflows.autocode_impl.nodes.commit import node_commit
        base_state["verify"]["passed"] = False
        result = node_commit(base_state)
        assert result["status"] == "skipped"
        assert result["vcs"]["commit_sha"] == ""

    def test_commits_when_verified(self, base_state):
        from workflows.autocode_impl.nodes.commit import node_commit
        base_state["verify"]["passed"] = True
        base_state["task"] = "add feature"
        with patch("workflows.autocode_impl.nodes.commit._git_commit",
                   return_value={"committed": True, "sha": "abc123"}):
            result = node_commit(base_state)
        assert result["status"] == "done"
        assert result["vcs"]["commit_sha"] == "abc123"

    def test_dry_run_skips_git_commit(self, base_state):
        from workflows.autocode_impl.nodes.commit import node_commit
        base_state["verify"]["passed"] = True
        base_state["dry_run"] = True
        with patch("workflows.autocode_impl.nodes.commit._git_commit") as mock_commit:
            result = node_commit(base_state)
            mock_commit.assert_not_called()
        assert result["status"] == "dry_run"
        assert result["vcs"]["commit_sha"] == "(dry-run)"


# ---------------------------------------------------------------------------
# node_push
# ---------------------------------------------------------------------------


class TestNodePush:
    def test_skips_when_push_disabled(self, base_state, mocker):
        from workflows.autocode_impl.nodes.push import node_push
        base_state["verify"]["passed"] = True
        base_state["vcs"]["branch"] = "autocode/feature"
        mocker.patch("core.config.cfg.autocode_push_on_commit", False)
        result = node_push(base_state)
        assert result["vcs"]["pushed"] is False

    def test_pushes_when_enabled(self, base_state, mocker):
        from workflows.autocode_impl.nodes.push import node_push
        base_state["verify"]["passed"] = True
        base_state["vcs"]["branch"] = "autocode/feature"
        mocker.patch("core.config.cfg.autocode_push_on_commit", True)
        with patch("workflows.autocode_impl.nodes.push._github_push", return_value=True):
            result = node_push(base_state)
        assert result["vcs"]["pushed"] is True

    def test_skips_when_not_verified(self, base_state):
        from workflows.autocode_impl.nodes.push import node_push
        base_state["verify"]["passed"] = False
        assert node_push(base_state) == {}


# ---------------------------------------------------------------------------
# node_create_pr
# ---------------------------------------------------------------------------


class TestNodeCreatePr:
    def test_skips_when_pr_disabled(self, base_state, mocker):
        from workflows.autocode_impl.nodes.create_pr import node_create_pr
        base_state["verify"]["passed"] = True
        base_state["vcs"]["pushed"] = True
        base_state["vcs"]["branch"] = "autocode/feature"
        mocker.patch("core.config.cfg.autocode_open_pr", False)
        result = node_create_pr(base_state)
        assert result["vcs"]["pr_number"] == 0
        assert result["vcs"]["pr_url"] == ""

    def test_creates_pr_when_enabled(self, base_state, mocker):
        from workflows.autocode_impl.nodes.create_pr import node_create_pr
        base_state["verify"]["passed"] = True
        base_state["vcs"]["pushed"] = True
        base_state["vcs"]["branch"] = "autocode/feature"
        mocker.patch("core.config.cfg.autocode_open_pr", True)
        with patch("workflows.autocode_impl.nodes.create_pr._github_pr_create",
                   return_value={"number": 42, "url": "https://github.com/x/y/pull/42"}):
            result = node_create_pr(base_state)
        assert result["vcs"]["pr_number"] == 42
        assert "pull/42" in result["vcs"]["pr_url"]

    def test_skips_when_branch_not_pushed(self, base_state, mocker):
        from workflows.autocode_impl.nodes.create_pr import node_create_pr
        base_state["verify"]["passed"] = True
        base_state["vcs"]["pushed"] = False
        mocker.patch("core.config.cfg.autocode_open_pr", True)
        result = node_create_pr(base_state)
        assert result["vcs"]["pr_number"] == 0


# ---------------------------------------------------------------------------
# node_merge_pr
# ---------------------------------------------------------------------------


class TestNodeMergePr:
    def test_skips_when_auto_merge_disabled(self, base_state, mocker):
        from workflows.autocode_impl.nodes.merge_pr import node_merge_pr
        base_state["verify"]["passed"] = True
        base_state["vcs"]["pr_number"] = 42
        mocker.patch("core.config.cfg.autocode_auto_merge", False)
        with patch("workflows.autocode_impl.nodes.merge_pr._github_pr_merge") as mock_merge:
            result = node_merge_pr(base_state)
            mock_merge.assert_not_called()
        assert result == {}

    def test_merges_when_enabled(self, base_state, mocker):
        from workflows.autocode_impl.nodes.merge_pr import node_merge_pr
        base_state["verify"]["passed"] = True
        base_state["vcs"]["pr_number"] = 42
        mocker.patch("core.config.cfg.autocode_auto_merge", True)
        with patch("workflows.autocode_impl.nodes.merge_pr._github_pr_merge", return_value=True) as mock_merge:
            result = node_merge_pr(base_state)
            mock_merge.assert_called_once_with(42, base_state["trace_id"])
        assert result == {}

    def test_skips_when_no_pr_number(self, base_state, mocker):
        from workflows.autocode_impl.nodes.merge_pr import node_merge_pr
        base_state["verify"]["passed"] = True
        base_state["vcs"]["pr_number"] = 0
        mocker.patch("core.config.cfg.autocode_auto_merge", True)
        with patch("workflows.autocode_impl.nodes.merge_pr._github_pr_merge") as mock_merge:
            result = node_merge_pr(base_state)
            mock_merge.assert_not_called()
        assert result == {}


# ---------------------------------------------------------------------------
# node_distill_memory
# ---------------------------------------------------------------------------


class TestNodeDistillMemory:
    def test_skips_for_create_skill_task_type(self, base_state):
        from workflows.autocode_impl.nodes.memory import node_distill_memory
        base_state["task_type"] = "create_skill"
        with patch("core.memory_backend.procedural.distill.distill_workflow") as mock_distill:
            result = node_distill_memory(base_state)
            mock_distill.assert_not_called()
        assert result == {}

    def test_stores_distilled_insight(self, base_state):
        from workflows.autocode_impl.nodes.memory import node_distill_memory
        base_state["task_type"] = "feature"
        with patch("workflows.autocode_impl.nodes.memory.distill_workflow",
                   return_value={"status": "stored", "stored": 1, "skipped": 0}):
            result = node_distill_memory(base_state)
        assert "stored=1" in result["memory"]["notes"]
        assert "stored" in result["memory"]["notes"]

    def test_non_fatal_on_exception(self, base_state):
        from workflows.autocode_impl.nodes.memory import node_distill_memory
        base_state["task_type"] = "feature"
        with patch("workflows.autocode_impl.nodes.memory.distill_workflow",
                   side_effect=RuntimeError("LLM down")):
            result = node_distill_memory(base_state)
        # Must NOT raise — distillation failure is non-fatal (code already committed).
        assert "distill_failed" in result["memory"]["notes"]
        assert "LLM down" in result["memory"]["notes"]


# ---------------------------------------------------------------------------
# node_report
# ---------------------------------------------------------------------------


class TestNodeReport:
    def test_generates_report_without_crash(self, base_state):
        from workflows.autocode_impl.nodes.report import node_report
        base_state["verify"]["passed"] = True
        base_state["vcs"]["commit_sha"] = "abc123"
        base_state["files_state"]["files_map"] = {"out.py": {}}
        with patch("tools.report.report") as mock_report:
            mock_report.return_value = {"status": "ok"}
            result = node_report(base_state)
            mock_report.assert_called_once()
        # Report node always returns {} (best-effort — no state mutation).
        assert result == {}

    def test_non_fatal_on_exception(self, base_state):
        from workflows.autocode_impl.nodes.report import node_report
        base_state["verify"]["passed"] = True
        with patch("tools.report.report", side_effect=RuntimeError("report tool broken")):
            # Must NOT raise — report generation is best-effort.
            result = node_report(base_state)
        assert result == {}
