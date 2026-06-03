"""
tests/core/kgraph/test_storage.py
Validates GraphStore SQLite operations and singleton pattern.
"""
from core.kgraph.storage import GraphStore

def test_graph_store_singleton(tmp_path):
    """GraphStore should return the same instance for the same db_path."""
    db_path = tmp_path / "test.db"
    store1 = GraphStore(db_path)
    store2 = GraphStore(db_path)
    assert store1 is store2

def test_upsert_and_get_hash(tmp_path):
    """Test inserting a file node and retrieving its hash."""
    db_path = tmp_path / "test.db"
    store = GraphStore(db_path)
    
    project_id = "test_proj"
    path = "src/main.py"
    content_hash = "abc123"
    deps = ["os", "sys"]
    
    store.upsert_file_graph(project_id, path, content_hash, deps)
    
    retrieved_hash = store.get_file_hash(project_id, path)
    assert retrieved_hash == content_hash

def test_upsert_updates_hash(tmp_path):
    """Test that upserting the same file updates the hash."""
    db_path = tmp_path / "test.db"
    store = GraphStore(db_path)
    
    project_id = "test_proj"
    path = "src/main.py"
    
    store.upsert_file_graph(project_id, path, "hash1", [])
    assert store.get_file_hash(project_id, path) == "hash1"
    
    store.upsert_file_graph(project_id, path, "hash2", [])
    assert store.get_file_hash(project_id, path) == "hash2"