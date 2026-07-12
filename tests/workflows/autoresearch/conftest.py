"""Shared fixtures for autoresearch workflow tests.

[v1.0] Provides:
  base_state      — a default AutoresearchState with sensible test values
  mock_subprocess — patches subprocess.run used by setup + run_experiment
  mock_git        — patches subprocess git calls used by decide
  tmp_project     — a temp directory with a fake train.py for end-to-end tests
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from workflows.autoresearch_impl.state import _default_state


@pytest.fixture
def base_state():
    """Base AutoresearchState for autoresearch tests.

    Provides sensible defaults for all fields so individual tests only
    override what they need.
    """
    return _default_state(
        goal="minimize val_bpb",
        trace_id="test-ar-001",
        project_root="/tmp/test-autoresearch-project",
        target_file="train.py",
        metric_name="val_bpb",
        metric_direction="lower",
        time_budget=10,
        branch="autoresearch/test",
        results_path="/tmp/test-autoresearch-results.tsv",
    )


@pytest.fixture
def mock_subprocess():
    """Patch subprocess.run used by setup + run_experiment nodes.

    Returns the MagicMock so individual tests can configure the side_effect
    or return_value to simulate experiment output (including timeouts).
    """
    with patch("workflows.autoresearch_impl.nodes.setup.subprocess.run") as setup_run, \
         patch("workflows.autoresearch_impl.nodes.run_experiment.subprocess.run") as run_run:
        mock = MagicMock()
        # Default: a successful run that prints the metric
        default_result = MagicMock()
        default_result.stdout = "val_bpb: 0.5\n"
        default_result.stderr = ""
        default_result.returncode = 0
        setup_run.return_value = default_result
        run_run.return_value = default_result
        mock.setup_run = setup_run
        mock.run_run = run_run
        mock.default_result = default_result
        yield mock


@pytest.fixture
def mock_git():
    """Patch subprocess git calls used by the decide node.

    Patches the two subprocess.run call sites in decide.py:
      - git add / git commit / git rev-parse (keep path)
      - git reset --hard HEAD / git clean -fd (discard path)

    Returns a MagicMock with .commit_run and .reset_run attributes.
    """
    with patch("workflows.autoresearch_impl.nodes.decide.subprocess.run") as decide_run:
        mock = MagicMock()
        # Default: commit succeeds, returns short SHA
        def _side_effect(cmd, *args, **kwargs):
            # Normalize cmd to a list for matching
            cmd_list = list(cmd) if not isinstance(cmd, str) else cmd.split()
            if "rev-parse" in cmd_list:
                r = MagicMock()
                r.stdout = "abc1234\n"
                r.stderr = ""
                r.returncode = 0
                return r
            # All other git calls (add, commit, reset, clean) succeed
            r = MagicMock()
            r.stdout = ""
            r.stderr = ""
            r.returncode = 0
            return r
        decide_run.side_effect = _side_effect
        mock.decide_run = decide_run
        yield mock


@pytest.fixture
def tmp_project(tmp_path):
    """A temp directory containing a fake train.py that prints the metric.

    Used for end-to-end tests that actually exercise the subprocess.run
    path (no mocks) to verify the integration of modify → run → evaluate.
    """
    project = tmp_path / "project"
    project.mkdir()
    train_py = project / "train.py"
    # The fake script prints the metric so evaluate can extract it.
    train_py.write_text(
        "print('epoch 0: val_bpb: 0.5')\n"
        "print('epoch 1: val_bpb: 0.45')\n",
        encoding="utf-8",
    )
    # Initialize a git repo so decide's git commands work
    subprocess.run(
        ["git", "init"], cwd=str(project),
        capture_output=True, timeout=10,
    )
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=str(project), capture_output=True, timeout=10,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=str(project), capture_output=True, timeout=10,
    )
    subprocess.run(
        ["git", "add", "-A"], cwd=str(project),
        capture_output=True, timeout=10,
    )
    subprocess.run(
        ["git", "commit", "-m", "init"], cwd=str(project),
        capture_output=True, timeout=10,
    )
    return project
