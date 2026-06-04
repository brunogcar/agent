"""
workflows/autocode_helpers/test_mapper.py
Maps source files to the tests that cover them using AST reverse-indexing.
"""
from __future__ import annotations
import os
import asyncio
from pathlib import Path
from typing import List, Dict
from core.kgraph.ast_parser import parse_file_dependencies

# In-memory reverse index: {"src/file.py": ["tests/test_file.py", ...]}
_TEST_INDEX: Dict[str, List[str]] = {}
_INDEX_MTIME: float = 0.0

# P1 Fix: Critical paths that always require the full test suite
CRITICAL_PATHS = {
    "core/config.py", "core/llm.py", "core/memory.py",
    "server.py", "registry.py", "core/gateway.py", "core/tracer.py"
}

async def _build_test_index(test_root: str = "tests") -> Dict[str, List[str]]:
    """Scans the test directory and builds a reverse index of source files to test files."""
    global _TEST_INDEX, _INDEX_MTIME
    test_dir = Path(test_root).resolve()
    if not test_dir.exists():
        return _TEST_INDEX

    # P1 Fix: Rebuild index if the tests directory has been modified
    try:
        current_mtime = test_dir.stat().st_mtime
    except Exception:
        current_mtime = 0.0

    if current_mtime <= _INDEX_MTIME and _TEST_INDEX:
        return _TEST_INDEX

    _TEST_INDEX = {}
    test_files = list(test_dir.rglob("test_*.py")) + list(test_dir.rglob("*_test.py"))

    for test_file in test_files:
        deps = await parse_file_dependencies("default", str(test_file))
        if deps:
            for imp in deps:
                potential_src = imp.replace(".", os.sep) + ".py"
                
                # P1 Fix: Verify source file actually exists to prevent zombie mappings
                if Path(potential_src).exists():
                    if potential_src not in _TEST_INDEX:
                        _TEST_INDEX[potential_src] = []
                    if str(test_file) not in _TEST_INDEX[potential_src]:
                        _TEST_INDEX[potential_src].append(str(test_file))
        
        stem = test_file.stem
        if stem.startswith("test_"):
            potential_heuristic_src = stem[5:] + ".py"
            if Path(potential_heuristic_src).exists():
                if potential_heuristic_src not in _TEST_INDEX:
                    _TEST_INDEX[potential_heuristic_src] = []
                if str(test_file) not in _TEST_INDEX[potential_heuristic_src]:
                    _TEST_INDEX[potential_heuristic_src].append(str(test_file))

    _INDEX_MTIME = current_mtime
    return _TEST_INDEX

async def get_targeted_tests(modified_files: List[str], test_root: str = "tests") -> Dict[str, any]:
    """Given a list of modified source files, returns a precise pytest command string."""
    # P1 Fix: Critical paths always require the full suite
    for src_file in modified_files:
        norm_src = src_file.replace(os.sep, "/")
        if any(cp in norm_src for cp in CRITICAL_PATHS):
            return {
                "cmd": "pytest",
                "warnings": [f"Critical path '{src_file}' modified. Running full test suite to prevent regressions."]
            }

    index = await _build_test_index(test_root)
    targeted_test_files = set()
    warnings = []

    for src_file in modified_files:
        norm_src = src_file.replace(os.sep, "/")
        matched_tests = index.get(norm_src, [])
        
        # P1 Fix: Validate test files still exist before adding
        valid_tests = [t for t in matched_tests if Path(t).exists()]
         
        if valid_tests:
            targeted_test_files.update(valid_tests)
        else:
            warnings.append(f"No specific tests mapped for {src_file}. Falling back to full suite.")

    if targeted_test_files:
        return {"cmd": f"pytest {' '.join(targeted_test_files)}", "warnings": warnings}
    else:
        return {"cmd": "pytest", "warnings": warnings + ["No targeted tests found, running full suite."]}
