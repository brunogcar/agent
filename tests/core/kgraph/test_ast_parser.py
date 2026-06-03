"""
tests/core/kgraph/test_ast_parser.py
Validates AST parsing, caching, and string parsing.
"""
import pytest
from core.kgraph.ast_parser import parse_file_dependencies, parse_dependencies_from_string, clear_ast_cache

@pytest.mark.asyncio
async def test_parse_file_dependencies(tmp_path):
    """Test parsing a real file from disk."""
    file_path = tmp_path / "test.py"
    file_path.write_text("import os\nfrom pathlib import Path\n")
    
    result = await parse_file_dependencies("proj1", str(file_path))
    assert "os" in result
    assert "pathlib" in result
    clear_ast_cache()

@pytest.mark.asyncio
async def test_parse_dependencies_from_string():
    """Test parsing dependencies directly from a string (no disk I/O)."""
    content = "import sys\nimport json\n"
    result = await parse_dependencies_from_string("proj1", content)
    
    assert "sys" in result
    assert "json" in result
    clear_ast_cache()

@pytest.mark.asyncio
async def test_cache_invalidation(tmp_path):
    """Test that changing file content invalidates the cache."""
    file_path = tmp_path / "test.py"
    file_path.write_text("import os\n")
    
    res1 = await parse_file_dependencies("proj1", str(file_path))
    assert "os" in res1
    
    file_path.write_text("import sys\n")
    res2 = await parse_file_dependencies("proj1", str(file_path))
    assert "sys" in res2
    assert "os" not in res2
    clear_ast_cache()