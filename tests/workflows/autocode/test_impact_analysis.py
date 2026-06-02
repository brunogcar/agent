"""
tests/workflows/autocode/test_impact_analysis.py
Validates AST mapper handles edge cases gracefully and async execution works.
"""
import pytest
import asyncio
import tempfile
import os
from workflows.autocode_helpers.impact_analysis import get_file_dependencies, clear_ast_cache

@pytest.mark.asyncio
async def test_valid_file_parsing():
    with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
        f.write("import os\nfrom core.config import cfg\n\ndef my_func():\n    pass\n")
        f.flush()
        path = f.name
    
    try:
        result = await get_file_dependencies(path)
        assert result["status"] == "success"
        assert "os" in result["imports"]
        assert "core.config" in result["imports"]
        assert "my_func" in result["defines"]
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
        result = await get_file_dependencies(path)
        assert result["status"] == "failed"
        assert "SyntaxError" in result["reason"]
        assert result["imports"] == []
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
        # First parse
        res1 = await get_file_dependencies(path)
        assert res1["status"] == "success"
        
        # Modify file
        with open(path, 'a') as f:
            f.write("\nimport os")
            
        # Second parse should hit file, not cache
        res2 = await get_file_dependencies(path)
        assert "os" in res2["imports"]
    finally:
        os.unlink(path)
        clear_ast_cache()
