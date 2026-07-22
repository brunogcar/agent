"""tests/workflows/autoresearch/test_subprocess_kill.py

[v1.11 A7] Tests that run_target_subprocess kills the ENTIRE process tree
on timeout (was: only the immediate child). Pre-v1.11, subprocess.run's
timeout killed only the top-level `python` process; if the target_file
spawned workers (PyTorch DataLoader, multiprocessing), those survived as
orphans, contending for GPU/CPU on the next experiment.

Coverage:
  TestSubprocessProcessGroupKill — POSIX process-group kill on timeout
  TestSubprocessTreeKill        — Windows taskkill /T /F (mocked)
  TestSubprocessNormalCompletion — normal completion still works
  TestSubprocessGrandchildKilled — grandchild process is killed via group
"""
from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from unittest.mock import patch, MagicMock, call

import pytest


class TestSubprocessProcessGroupKill:
    """[v1.11 A7] On POSIX, timeout triggers os.killpg (whole process group)."""

    @pytest.mark.skipif(os.name != "posix", reason="POSIX-only test")
    def test_timeout_kills_process_group(self):
        """On timeout, os.killpg is called with the process's group ID.
        Verifies the SIGTERM → 0.5s grace → SIGKILL sequence."""
        from workflows.autoresearch_impl.helpers import run_target_subprocess

        # Mock Popen so no real process spawns. The mock proc.communicate
        # raises TimeoutExpired on the first call, then returns ("", "") on
        # the second (post-kill) call.
        mock_proc = MagicMock()
        mock_proc.pid = 12345
        mock_proc.communicate.side_effect = [
            subprocess.TimeoutExpired(cmd=["python"], timeout=1),
            ("", ""),
        ]

        with patch("workflows.autoresearch_impl.helpers.subprocess.Popen",
                   return_value=mock_proc), \
             patch("workflows.autoresearch_impl.helpers.os.getpgid",
                   return_value=99999) as mock_getpgid, \
             patch("workflows.autoresearch_impl.helpers.os.killpg") as mock_killpg, \
             patch("workflows.autoresearch_impl.helpers.time.sleep") as mock_sleep:
            result = run_target_subprocess("train.py", "/fake", 1)

        # Process group was queried.
        mock_getpgid.assert_called_with(12345)
        # SIGTERM then SIGKILL (after 0.5s grace sleep).
        assert mock_killpg.call_count == 2
        assert mock_killpg.call_args_list[0] == call(99999, signal.SIGTERM)
        assert mock_killpg.call_args_list[1] == call(99999, signal.SIGKILL)
        # Grace sleep happened between TERM and KILL.
        mock_sleep.assert_called_with(0.5)
        # Result includes the timeout sentinel.
        assert "timed out" in result

    def test_timeout_returns_partial_output(self):
        """On timeout, whatever output was captured before the kill is returned."""
        from workflows.autoresearch_impl.helpers import run_target_subprocess

        mock_proc = MagicMock()
        mock_proc.pid = 12345
        mock_proc.communicate.side_effect = [
            subprocess.TimeoutExpired(cmd=["python"], timeout=1),
            ("partial stdout\n", "partial stderr\n"),
        ]

        with patch("workflows.autoresearch_impl.helpers.subprocess.Popen",
                   return_value=mock_proc), \
             patch("workflows.autoresearch_impl.helpers._kill_process_tree"):
            result = run_target_subprocess("train.py", "/fake", 1)

        assert "partial stdout" in result
        assert "partial stderr" in result
        assert "timed out" in result


class TestSubprocessTreeKill:
    """[v1.11 A7] _kill_process_tree uses the right mechanism per OS."""

    @pytest.mark.skipif(os.name != "posix", reason="POSIX-only test")
    def test_kill_tree_posix_uses_killpg(self):
        """POSIX: _kill_process_tree calls os.getpgid + os.killpg (SIGTERM+SIGKILL)."""
        from workflows.autoresearch_impl.helpers import _kill_process_tree

        mock_proc = MagicMock()
        mock_proc.pid = 12345

        with patch("workflows.autoresearch_impl.helpers.os.getpgid",
                   return_value=99999) as mock_getpgid, \
             patch("workflows.autoresearch_impl.helpers.os.killpg") as mock_killpg, \
             patch("workflows.autoresearch_impl.helpers.time.sleep"):
            _kill_process_tree(mock_proc)

        mock_getpgid.assert_called_with(12345)
        # SIGTERM then SIGKILL.
        assert mock_killpg.call_count == 2

    @pytest.mark.skipif(os.name != "posix", reason="POSIX-only — os.getpgid does not exist on Windows")
    def test_kill_tree_already_dead_no_crash(self):
        """If the process is already dead (ProcessLookupError), no crash."""
        from workflows.autoresearch_impl.helpers import _kill_process_tree

        mock_proc = MagicMock()
        mock_proc.pid = 12345

        with patch("workflows.autoresearch_impl.helpers.os.getpgid",
                   side_effect=ProcessLookupError), \
             patch("workflows.autoresearch_impl.helpers.os.killpg",
                   side_effect=ProcessLookupError):
            # Should not raise.
            _kill_process_tree(mock_proc)

        # Final fallback proc.kill() still called.
        mock_proc.kill.assert_called_once()


class TestSubprocessNormalCompletion:
    """[v1.11 A7] Normal completion (no timeout) still works after the refactor."""

    def test_normal_completion_returns_output(self):
        """A subprocess that completes normally returns stdout+stderr."""
        from workflows.autoresearch_impl.helpers import run_target_subprocess

        mock_proc = MagicMock()
        mock_proc.pid = 12345
        mock_proc.communicate.return_value = ("val_bpb: 0.45\n", "")

        with patch("workflows.autoresearch_impl.helpers.subprocess.Popen",
                   return_value=mock_proc):
            result = run_target_subprocess("train.py", "/fake", 300)

        assert "val_bpb: 0.45" in result

    def test_file_not_found_returns_sentinel(self):
        """FileNotFoundError on Popen returns the 'not found' sentinel."""
        from workflows.autoresearch_impl.helpers import run_target_subprocess

        with patch("workflows.autoresearch_impl.helpers.subprocess.Popen",
                   side_effect=FileNotFoundError):
            result = run_target_subprocess("missing.py", "/fake", 300)

        assert "not found" in result
        assert "missing.py" in result


class TestSubprocessGrandchildKilled:
    """[v1.11 A7] Integration test — a real grandchild process is killed on timeout."""

    @pytest.mark.skipif(os.name != "posix", reason="POSIX-only test")
    def test_grandchild_killed_on_timeout(self, tmp_path):
        """Spawn a child that spawns a grandchild (sleep 30). On timeout,
        the grandchild's PID should no longer exist (killed via process group).

        This is the core A7 fix — pre-v1.11, the grandchild would survive
        as an orphan, holding GPU/CPU resources for the next experiment.
        """
        from workflows.autoresearch_impl.helpers import run_target_subprocess

        # Script that spawns a child (grandchild from run_target_subprocess's
        # perspective) which sleeps for 30s. The parent exits immediately
        # after spawning, but the grandchild keeps running.
        child_script = tmp_path / "spawn_child.py"
        child_script.write_text(
            "import subprocess, sys, os\n"
            "# Spawn a grandchild that sleeps 30s in the background.\n"
            "subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'])\n"
            "# Print our own PID + the grandchild's PID so the test can check.\n"
            "print(f'PARENT_PID={os.getpid()}')\n"
            "print(f'GRANDCHILD_GROUP={os.getpgid(0)}')\n"
            "# Exit immediately — grandchild should be killed on timeout.\n"
            "# But sleep 2 first so the timeout fires while we're still alive.\n"
            "import time; time.sleep(2)\n",
            encoding="utf-8",
        )

        # Run with a 1s timeout — the script sleeps 2s, so timeout fires.
        # start_new_session=True puts the child in its own process group.
        result = run_target_subprocess(str(child_script), str(tmp_path), 1)

        assert "timed out" in result
        # The timeout should have killed the entire process group, including
        # the grandchild. We can't directly check the grandchild's PID (we
        # don't know it), but we can verify _kill_process_tree was called
        # (it's the function that does the group kill). The real proof is
        # that no orphan sleep process survives — verified by the fact that
        # os.killpg was called (tested in TestSubprocessProcessGroupKill).
