"""
tests/core/kgraph/test_test_mapper.py
Validates the persistent test index and smart mapping logic.
"""
import pytest
import json
from pathlib import Path
from core.kgraph.test_index import load_test_index, save_test_index
from core.kgraph.test_mapper import get_targeted_tests, CRITICAL_PATHS

def test_atomic_save_and_load(tmp_path):
    """Ensure index is saved and loaded correctly with project path validation."""
    project_path = tmp_path / "my_project"
    project_path.mkdir()
    
    index = {
        "version": 1,
        "project_path": str(project_path.resolve()),
        "entries": {"test_a.py": {"targets": ["src/a.py"]}}
    }
    
    save_test_index(project_path, index)
    loaded = load_test_index(project_path)
    
    assert loaded["entries"]["test_a.py"]["targets"] == ["src/a.py"]

def test_load_rejects_wrong_project_path(tmp_path):
    """Ensure index is rejected if project_path doesn't match (prevents cross-project contamination)."""
    project_a = tmp_path / "project_a"
    project_b = tmp_path / "project_b"
    project_a.mkdir()
    project_b.mkdir()
    
    # Save with project_a's path
    index = {"version": 1, "project_path": str(project_a.resolve()), "entries": {}}
    save_test_index(project_a, index)
    
    # Try to load from project_b
    loaded = load_test_index(project_b)
    assert loaded["entries"] == {}  # Should be empty because paths don't match

@pytest.mark.asyncio
async def test_critical_paths_force_full_suite(tmp_path):
    """Modifying a critical path must immediately trigger full suite fallback."""
    project_path = tmp_path / "proj"
    project_path.mkdir()
    
    # Pick any critical path
    crit_path = list(CRITICAL_PATHS)[0] 
    
    result = await get_targeted_tests(
        project_path=project_path,
        modified_files=[crit_path],
        project_id="test_id"
    )
    
    assert result["fallback"] is True
    assert "Critical path" in result["warnings"][0]

@pytest.mark.asyncio
async def test_zombie_test_files_filtered(tmp_path):
    """If a mapped test file doesn't exist on disk, it must be filtered out."""
    project_path = tmp_path / "proj"
    project_path.mkdir()
    (project_path / ".understand").mkdir()
    
    # Create a fake index with a zombie test file
    index = {
        "version": 1,
        "project_path": str(project_path.resolve()),
        "entries": {
            "tests/test_zombie.py": {
                "mtime": 0, "size": 0, "md5": "fake",
                "targets": ["src/real_file.py"]
            }
        }
    }
    save_test_index(project_path, index)
    
    # Create the source file so it maps
    (project_path / "src").mkdir()
    (project_path / "src/real_file.py").touch()
    
    # Note: tests/test_zombie.py does NOT exist on disk
    
    result = await get_targeted_tests(
        project_path=project_path,
        modified_files=["src/real_file.py"],
        project_id="test_id"
    )
    
    # Because the test file doesn't exist, it should fall back to full suite
    assert result["fallback"] is True
    assert any("Zombie test file" in w for w in result["warnings"])
