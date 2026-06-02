"""
core/kgraph - Codebase Knowledge Graph Infrastructure.
Provides deterministic AST parsing, SQLite graph storage, and project isolation.
"""
from .project import ProjectManager
from .storage import GraphStore
from .vectors import get_project_vector_collection
from .ast_parser import parse_file_dependencies, clear_ast_cache
from .test_index import load_test_index, save_test_index
from .test_mapper import get_targeted_tests, rebuild_test_index, CRITICAL_PATHS

__all__ = [
    "ProjectManager",
    "GraphStore",
    "get_project_vector_collection",
    "parse_file_dependencies",
    "clear_ast_cache",
    "load_test_index",
    "save_test_index",
    "get_targeted_tests",
    "rebuild_test_index",
    "CRITICAL_PATHS",
]
