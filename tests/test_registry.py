"""
tests/test_registry.py -- Unit tests for tool auto-discovery and MCP registration safety.
"""
from __future__ import annotations
import types
import pytest
from unittest.mock import MagicMock, patch
import registry

def test_tool_decorator_marks_function():
    """@tool should add _is_mcp_tool = True to the function."""
    @registry.tool
    def my_dummy_tool():
        pass
        
    assert getattr(my_dummy_tool, "_is_mcp_tool", False) is True

def test_tool_decorator_preserves_function():
    """@tool should not break the original function execution."""
    @registry.tool
    def add(a, b):
        return a + b
        
    assert add(2, 3) == 5

def test_register_all_tools_discovers_and_registers():
    """register_all_tools should find @tool functions and register them with FastMCP."""
    mock_mcp = MagicMock()
    
    # 🔴 FIX: Use a real module type to prevent MagicMock's truthy attribute traps
    fake_module = types.ModuleType("fake_module")
    
    @registry.tool
    def dummy_tool(): pass
    
    def not_a_tool(): pass
    
    fake_module.dummy_tool = dummy_tool
    fake_module.not_a_tool = not_a_tool

    # 🔴 FIX: Patch the specific references inside the registry module
    with patch("registry.pkgutil.iter_modules") as mock_iter, \
         patch("registry.importlib.import_module") as mock_import:
         
        # Simulate finding one module in tools/ and one in skills/
        mock_iter.side_effect = [
            [(None, "fake_tool", False)],  # tools/
            [(None, "fake_skill", False)]  # skills/
        ]
        mock_import.return_value = fake_module
        
        count = registry.register_all_tools(mock_mcp)
        
    # Should register the tool twice (once for tools/, once for skills/)
    assert count == 2
    assert mock_mcp.tool.call_count == 2

def test_register_all_tools_skips_skills_subpackages():
    """register_all_tools must skip sub-packages in skills/ (is_pkg=True)."""
    mock_mcp = MagicMock()
    
    with patch("registry.pkgutil.iter_modules") as mock_iter, \
         patch("registry.importlib.import_module") as mock_import:
         
        # Simulate tools/ empty, skills/ has a sub-package
        mock_iter.side_effect = [
            [],  # tools/
            [(None, "b3", True)]  # skills/ sub-package
        ]
        
        count = registry.register_all_tools(mock_mcp)
        
    assert count == 0
    mock_import.assert_not_called()

def test_register_all_tools_handles_import_errors_gracefully(capsys):
    """If a tool module fails to import, it should log to stderr and continue."""
    mock_mcp = MagicMock()
    
    with patch("registry.pkgutil.iter_modules") as mock_iter, \
         patch("registry.importlib.import_module") as mock_import:
         
        mock_iter.side_effect = [
            [(None, "broken_tool", False)], 
            [] 
        ]
        mock_import.side_effect = ImportError("Simulated import failure")
        
        count = registry.register_all_tools(mock_mcp)
            
    assert count == 0
    
    # 🔴 FIX: Use pytest's native capsys to avoid breaking unittest.mock's internal imports
    captured = capsys.readouterr()
    assert "WARNING" in captured.err or "Failed to import" in captured.err

def test_register_all_tools_never_writes_to_stdout(capsys):
    """CRITICAL: registry must NEVER print to stdout (corrupts MCP JSON-RPC)."""
    mock_mcp = MagicMock()
    
    with patch("registry.pkgutil.iter_modules", return_value=[]):
        registry.register_all_tools(mock_mcp)
        
    captured = capsys.readouterr()
    assert captured.out == "", "STDOUT was written to! This will corrupt the MCP channel."