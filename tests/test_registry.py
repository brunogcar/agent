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


def test_get_tool_actions_returns_empty_for_unknown_tool():
    """get_tool_actions should return [] for unknown tools (never raises)."""
    assert registry.get_tool_actions("nonexistent_tool") == []


def test_get_tool_actions_returns_empty_for_non_meta_tool():
    """get_tool_actions should return [] for tools without @meta_tool."""
    @registry.tool
    def plain_tool(): pass

    # Simulate registration
    registry._registered_tool_fns["plain_tool"] = plain_tool
    try:
        assert registry.get_tool_actions("plain_tool") == []
    finally:
        del registry._registered_tool_fns["plain_tool"]


def test_get_tool_actions_returns_actions_for_meta_tool():
    """get_tool_actions should read __tool_metadata__['actions'] from @meta_tool-decorated tools."""
    @registry.tool
    def meta_tool_example(): pass

    meta_tool_example.__tool_metadata__ = {
        "actions": ["status", "log", "commit"],
        "dispatch": {},
    }

    registry._registered_tool_fns["meta_tool_example"] = meta_tool_example
    try:
        actions = registry.get_tool_actions("meta_tool_example")
        assert actions == ["status", "log", "commit"]
    finally:
        del registry._registered_tool_fns["meta_tool_example"]


def test_get_tool_actions_isolated_from_tool_names():
    """get_tool_actions should not depend on get_tool_names ordering."""
    @registry.tool
    def isolated_tool(): pass

    isolated_tool.__tool_metadata__ = {"actions": ["a", "b"], "dispatch": {}}
    registry._registered_tool_fns["isolated_tool"] = isolated_tool
    try:
        # Even if _registered_tool_names is empty, get_tool_actions works
        names_backup = list(registry._registered_tool_names)
        registry._registered_tool_names = []
        try:
            assert registry.get_tool_actions("isolated_tool") == ["a", "b"]
        finally:
            registry._registered_tool_names = names_backup
    finally:
        del registry._registered_tool_fns["isolated_tool"]
