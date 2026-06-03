"""
tests/core/kgraph/test_project.py
Validates ProjectManager dual-structure logic and indexing modes.
"""
from core.kgraph.project import ProjectManager

def test_project_manager_agent_root(tmp_path):
    """For agent_root, source_root should be the path itself."""
    pm = ProjectManager(tmp_path, is_agent_root=True)
    assert pm.source_root == tmp_path.resolve()
    assert pm.artifact_root == tmp_path.resolve() / ".understand"

def test_project_manager_workspace_project(tmp_path):
    """For workspace projects, source_root should be path/code."""
    pm = ProjectManager(tmp_path, is_agent_root=False)
    assert pm.source_root == tmp_path.resolve() / "code"
    assert pm.artifact_root == tmp_path.resolve() / ".understand"

def test_ensure_initialized_creates_dirs(tmp_path):
    """ensure_initialized should create artifact and source directories."""
    pm = ProjectManager(tmp_path, is_agent_root=False)
    pm.ensure_initialized()
    
    assert (tmp_path / ".understand").exists()
    assert (tmp_path / ".understand" / "cache").exists()
    assert (tmp_path / "code").exists()

def test_get_indexing_mode_foreground(tmp_path):
    """Small projects should return 'foreground' mode."""
    (tmp_path / "code").mkdir()
    (tmp_path / "code" / "test.py").write_text("print('hello')")
    
    pm = ProjectManager(tmp_path, is_agent_root=False)
    mode = pm.get_indexing_mode()
    assert mode == "foreground"