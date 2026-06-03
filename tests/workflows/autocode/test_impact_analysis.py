"""
tests/workflows/autocode/test_impact_analysis.py
Validates the new core.kgraph.ast_parser handles edge cases gracefully and async execution works.
"""
import pytest
import asyncio
import tempfile
import os
from core.kgraph.ast_parser import parse_file_dependencies, clear_ast_cache

@pytest.mark.asyncio
async def test_valid_file_parsing():
    with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
        f.write("import os\nfrom core.config import cfg\n\ndef my_func():\n    pass\n")
        f.flush()
        path = f.name
    
    try:
        result = await parse_file_dependencies("test_project", path)
        assert "os" in result
        assert "core.config" in result
    finally:
        os.unlink(path)
        clear_ast_cache()

@pytest.mark.asyncio
async def test_syntax_error_fallback():
    with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
        f.write("def broken_func(\n    # missing parenthesis and colon")
        f.flush()
        path = f.name
    
    try:
        result = await parse_file_dependencies("test_project", path)
        assert result == frozenset()
    finally:
        os.unlink(path)
        clear_ast_cache()

@pytest.mark.asyncio
async def test_cache_invalidates_on_change():
    with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
        f.write("import sys")
        f.flush()
        path = f.name
    
    try:
        res1 = await parse_file_dependencies("test_project", path)
        assert "sys" in res1
        
        with open(path, 'a') as f:
            f.write("\nimport os")
            
        res2 = await parse_file_dependencies("test_project", path)
        assert "os" in res2
    finally:
        os.unlink(path)
        clear_ast_cache()