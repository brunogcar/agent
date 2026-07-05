"""
Disk-based pytest execution.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from core.config import cfg
from workflows.autocode_impl.state import DEBUG
from workflows.autocode_impl.helpers import _should_copy_file

def run_tests_on_disk(
    files:     dict[str, str],
    test_code: str,
    workspace: Path | None = None,
) -> tuple[bool, str]:
    """
    Run tests using a real pytest subprocess in a temporary directory.
    Returns (passed: bool, output: str).
    Using real pytest exit codes -- LLM cannot hallucinate a pass here.
    """
    if not files or not test_code:
        return False, "No files or tests provided"

    try:
        test_dir = Path(tempfile.mkdtemp(prefix="autocode_test_"))
        try:
            # Copy workspace context (so imports from the real project work)
            # [P1 #6] _should_copy_file expects (path, protected_files: frozenset),
            # not (path, workspace: Path). Pass cfg.protected_files.
            if workspace and workspace.exists():
                for src in workspace.rglob("*"):
                    if src.is_file() and _should_copy_file(src, cfg.protected_files):
                        dst = test_dir / src.relative_to(workspace)
                        dst.parent.mkdir(parents=True, exist_ok=True)
                        try:
                            shutil.copy2(src, dst)
                        except Exception:
                            pass

            # Write the generated implementation files
            for rel_path, content in files.items():
                target = test_dir / rel_path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(content, encoding="utf-8")

            # Write tests
            test_file = test_dir / "test_autocode_feature.py"
            test_file.write_text(test_code, encoding="utf-8")

            cmd  = [sys.executable, "-m", "pytest", str(test_dir),
                    "--tb=short", "--color=no", "-q"]
            if DEBUG:
                cmd.insert(cmd.index("--tb=short"), "-v")

            # FIXED: Explicit encoding for Windows
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=60,
                encoding='utf-8',
                errors='replace'
            )
            output = (result.stdout + result.stderr).strip()
            passed = result.returncode == 0
            return passed, output or "(no output)"

        finally:
            shutil.rmtree(test_dir, ignore_errors=True)

    except subprocess.TimeoutExpired:
        return False, "TimeoutExpired running tests"
    except Exception as e:
        return False, f"Exception during test execution: {e}"