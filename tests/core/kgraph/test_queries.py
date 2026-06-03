"""
tests/core/kgraph/test_queries.py
Validates the 'On-Demand Librarian' SQL queries.
"""
import pytest
from core.kgraph.project import ProjectManager
from core.kgraph.storage import GraphStore
from core.kgraph.queries import find_relevant_files, get_dependencies, get_callers

@pytest.fixture
def populated_graph(tmp_path):
    """Create a temporary graph with some nodes and edges using ProjectManager."""
    project_path = tmp_path / "my_proj"
    project_path.mkdir()
    
    pm = ProjectManager(project_path, is_agent_root=False)
    pm.ensure_initialized()
    
    db_path = pm.artifact_root / "kg.db"
    store = GraphStore(db_path)
    project_id = pm.project_id
    
    # Insert nodes (simulating AST parser output)
    store.upsert_file_graph(project_id, "src/auth.py", "hash1", ["core.config"])
    store.upsert_file_graph(project_id, "src/main.py", "hash2", ["src.auth"])
    store.upsert_file_graph(project_id, "core/config.py", "hash3", [])
    
    return project_path, project_id

def test_find_relevant_files(populated_graph):
    """Test keyword-based file search."""
    project_path, project_id = populated_graph
    results = find_relevant_files(project_path, "auth config", top_k=5)
    assert isinstance(results, list)
    assert len(results) > 0

def test_get_dependencies(populated_graph):
    """Test getting outgoing edges (what a file imports)."""
    project_path, project_id = populated_graph
    deps = get_dependencies(project_path, "src/main.py")
    assert isinstance(deps, list)

def test_get_callers(populated_graph):
    """Test getting incoming edges (what imports a file)."""
    project_path, project_id = populated_graph
    # src.auth is imported by src.main.py (stored as module name "src.auth")
    callers = get_callers(project_path, "src/auth.py")
    assert isinstance(callers, list)
    assert len(callers) > 0