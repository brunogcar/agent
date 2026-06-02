"""
core/kgraph/test_mapper.py
Maps source files to targeted tests using persistent AST indexing.
"""
from __future__ import annotations
import asyncio
from pathlib import Path
from typing import List, Dict, Any, Set
from core.kgraph.test_index import load_test_index, save_test_index, validate_and_update_entry
from core.kgraph.ast_parser import parse_file_dependencies

# Files that always require the full test suite due to global impact
CRITICAL_PATHS: Set[str] = {
    "core/config.py", "core/llm.py", "core/memory.py", 
    "server.py", "registry.py", "core/gateway.py", "core/tracer.py",
    "main.py", "app.py", "manage.py", "settings.py"
}

async def rebuild_test_index(project_path: Path, project_id: str) -> None:
    """
    Scans the test directory and rebuilds the test index.
    Uses hybrid validation to skip unchanged files.
    """
    index = load_test_index(project_path)
    entries = index.get("entries", {})
    
    # Find test directory (support common variations)
    test_dir = None
    for alt in ["tests", "test", "Tests"]:
        if (project_path / alt).exists():
            test_dir = project_path / alt
            break
            
    if not test_dir:
        save_test_index(project_path, index)
        return

    # Find all test files
    test_files = list(test_dir.rglob("test_*.py")) + list(test_dir.rglob("*_test.py"))
    seen_tests = set()
    
    for test_file in test_files:
        rel_path = test_file.relative_to(project_path).as_posix()
        seen_tests.add(rel_path)
        
        entry = entries.get(rel_path, {"targets": []})
        is_valid = await validate_and_update_entry(entry, test_file)
        
        if not is_valid:
            # File changed or new. Re-parse AST to find dependencies.
            deps = await parse_file_dependencies(project_id, str(test_file))
            targets = set()
            
            for dep in deps:
                # Convert module import to potential file path (e.g., "core.config" -> "core/config.py")
                potential = dep.replace(".", "/") + ".py"
                targets.add(potential)
                
            # Heuristic: test_foo.py probably tests foo.py
            stem = test_file.stem
            if stem.startswith("test_"):
                targets.add(stem[5:] + ".py")
                
            entry["targets"] = list(targets)
            
        entries[rel_path] = entry
        
    # Remove stale entries (deleted test files)
    for old_test in list(entries.keys()):
        if old_test not in seen_tests:
            del entries[old_test]
            
    index["entries"] = entries
    save_test_index(project_path, index)

async def get_targeted_tests(
    project_path: Path, 
    modified_files: List[str],
    project_id: str
) -> Dict[str, Any]:
    """
    Determines the targeted tests for a list of modified files.
    Returns a dict with 'tests' (list of paths), 'fallback' (bool), and 'warnings' (list).
    """
    warnings = []
    understand_dir = project_path / ".understand"
    understand_dir.mkdir(parents=True, exist_ok=True)
    
    # 1. Check Critical Paths
    for f in modified_files:
        rel_f = Path(f).as_posix()
        if any(cp in rel_f for cp in CRITICAL_PATHS):
            return {
                "tests": [], 
                "fallback": True, 
                "warnings": [f"Critical path '{f}' modified. Running full test suite."]
            }

    # 2. Load Index (Trigger rebuild if empty/missing)
    index = load_test_index(project_path)
    if not index.get("entries"):
        await rebuild_test_index(project_path, project_id)
        index = load_test_index(project_path)
        
    entries = index.get("entries", {})
    
    # 3. Build reverse map: source_file -> [test_files]
    reverse_map: Dict[str, List[str]] = {}
    for test_file, data in entries.items():
        for target in data.get("targets", []):
            if target not in reverse_map:
                reverse_map[target] = []
            reverse_map[target].append(test_file)
            
    targeted_tests = set()
    index_dirty = False
    
    # 4. Resolve tests for modified files
    for f in modified_files:
        rel_f = Path(f).as_posix()
        tests_for_f = reverse_map.get(rel_f, [])
        
        if not tests_for_f:
            warnings.append(f"No specific tests mapped for {f}. Falling back to full suite.")
            return {
                "tests": [], 
                "fallback": True, 
                "warnings": warnings
            }
            
        # Validate tests exist on disk (Zombie cleanup)
        for t in tests_for_f:
            test_path = project_path / t
            if test_path.exists():
                targeted_tests.add(t)
            else:
                warnings.append(f"Zombie test file detected and skipped: {t}")
                index_dirty = True
                
    if not targeted_tests:
        return {
            "tests": [], 
            "fallback": True, 
            "warnings": warnings + ["No valid targeted tests found."]
        }
        
    # 5. Clean zombies from index if any were found
    if index_dirty:
        for test_file in list(entries.keys()):
            if not (project_path / test_file).exists():
                del entries[test_file]
        index["entries"] = entries
        save_test_index(project_path, index)
        
    return {
        "tests": list(targeted_tests), 
        "fallback": False, 
        "warnings": warnings
    }
