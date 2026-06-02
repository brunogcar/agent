"""
workflows/autocode_helpers/test_mapper.py
Maps source files to the tests that cover them using AST reverse-indexing.
"""
from __future__ import annotations
import os
import asyncio
from pathlib import Path
from typing import List, Dict
from workflows.autocode_helpers.impact_analysis import get_file_dependencies

# In-memory reverse index: {"src/file.py": ["tests/test_file.py", ...]}
_TEST_INDEX: Dict[str, List[str]] = {}
_INDEX_BUILT = False

async def _build_test_index(test_root: str = "tests") -> Dict[str, List[str]]:
    """Scans the test directory and builds a reverse index of source files to test files."""
    global _TEST_INDEX, _INDEX_BUILT
    if _INDEX_BUILT:
        return _TEST_INDEX

    _TEST_INDEX = {}
    test_dir = Path(test_root).resolve()
    if not test_dir.exists():
        _INDEX_BUILT = True
        return _TEST_INDEX

    # Find all test files
    test_files = list(test_dir.rglob("test_*.py")) + list(test_dir.rglob("*_test.py"))
    
    for test_file in test_files:
        deps = await get_file_dependencies(str(test_file))
        if deps["status"] == "success":
            for imp in deps["imports"]:
                # Convert import path to potential file path (e.g., "core.config" -> "core/config.py")
                potential_src = imp.replace(".", os.sep) + ".py"
                if potential_src not in _TEST_INDEX:
                    _TEST_INDEX[potential_src] = []
                if str(test_file) not in _TEST_INDEX[potential_src]:
                    _TEST_INDEX[potential_src].append(str(test_file))
            
            # Heuristic: If test file is "test_foo.py", assume it tests "foo.py"
            stem = test_file.stem
            if stem.startswith("test_"):
                potential_heuristic_src = stem[5:] + ".py"
                if potential_heuristic_src not in _TEST_INDEX:
                    _TEST_INDEX[potential_heuristic_src] = []
                if str(test_file) not in _TEST_INDEX[potential_heuristic_src]:
                    _TEST_INDEX[potential_heuristic_src].append(str(test_file))

    _INDEX_BUILT = True
    return _TEST_INDEX

async def get_targeted_tests(modified_files: List[str], test_root: str = "tests") -> Dict[str, any]:
    """
    Given a list of modified source files, returns a precise pytest command string.
    Falls back to full suite if no targeted tests are found or if mapping fails.
    """
    index = await _build_test_index(test_root)
    targeted_test_files = set()
    warnings = []

    for src_file in modified_files:
        norm_src = src_file.replace(os.sep, "/")
        matched_tests = index.get(norm_src, [])
        if matched_tests:
            targeted_test_files.update(matched_tests)
        else:
            warnings.append(f"No specific tests mapped for {src_file}. Falling back to full suite.")

    if targeted_test_files:
        # Format: pytest tests/test_a.py tests/test_b.py
        return {"cmd": f"pytest {' '.join(targeted_test_files)}", "warnings": warnings}
    else:
        return {"cmd": "pytest", "warnings": warnings + ["No targeted tests found, running full suite."]}
