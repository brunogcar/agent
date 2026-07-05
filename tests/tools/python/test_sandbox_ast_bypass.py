"""Tests for AST sandbox MRO traversal and __builtins__ blocking.

[BUGFIX-SECURITY] Verifies that _validate_sandbox_ast blocks:
  - MRO traversal vectors: __class__, __base__, __bases__, __subclasses__, __mro__
  - __builtins__ attribute access

These bypass import-based restrictions by finding already-loaded classes
(e.g., subprocess.Popen) in the Python interpreter's class hierarchy.
"""
from __future__ import annotations

import pytest

from tools.python import _validate_sandbox_ast


class TestSandboxMRORBlocking:
    """MRO traversal must be blocked in sandbox mode."""

    def test_mro_traversal_via_subclasses_blocked(self):
        """().__class__.__base__.__subclasses__() must be blocked."""
        code = "[x for x in ().__class__.__base__.__subclasses__() if x.__name__ == 'Popen']"
        safe, err = _validate_sandbox_ast(code)
        assert safe is False
        # ast.walk() order may hit __subclasses__ before __class__ — either is valid
        assert "__subclasses__" in err or "__class__" in err

    def test_mro_traversal_via_mro_blocked(self):
        """().__class__.__mro__ must be blocked."""
        code = "().__class__.__mro__"
        safe, err = _validate_sandbox_ast(code)
        assert safe is False
        assert "__mro__" in err

    def test_mro_traversal_via_base_blocked(self):
        """().__class__.__base__ must be blocked."""
        code = "().__class__.__base__"
        safe, err = _validate_sandbox_ast(code)
        assert safe is False
        assert "__base__" in err

    def test_mro_traversal_via_bases_blocked(self):
        """().__class__.__bases__ must be blocked."""
        code = "().__class__.__bases__"
        safe, err = _validate_sandbox_ast(code)
        assert safe is False
        assert "__bases__" in err

    def test_mro_traversal_via_class_blocked(self):
        """().__class__ must be blocked."""
        code = "().__class__"
        safe, err = _validate_sandbox_ast(code)
        assert safe is False
        assert "__class__" in err

    def test_mro_indirect_chain_blocked(self):
        """Chained MRO access must be blocked at the first dunder."""
        code = "(1).__class__.__base__.__subclasses__()[42]"
        safe, err = _validate_sandbox_ast(code)
        assert safe is False
        # ast.walk() order may hit __subclasses__ before __class__ — either is valid
        assert "__subclasses__" in err or "__class__" in err


class TestSandboxBuiltinsBlocking:
    """__builtins__ access must be blocked in sandbox mode."""

    def test_builtins_attribute_access_blocked(self):
        """__builtins__.__import__('os') must be blocked."""
        code = "__builtins__.__import__('os')"
        safe, err = _validate_sandbox_ast(code)
        assert safe is False
        # Caught by ast.Name check for __builtins__
        assert "__builtins__" in err

    def test_builtins_getitem_blocked(self):
        """__builtins__['eval'] must be blocked."""
        code = "__builtins__['eval']"
        safe, err = _validate_sandbox_ast(code)
        assert safe is False
        # Caught by Subscript check (eval is dangerous) — __builtins__ may not be in msg
        assert "eval" in err or "__builtins__" in err

    def test_builtins_getattr_blocked(self):
        """__builtins__.__getattribute__('open') must be blocked."""
        code = "__builtins__.__getattribute__('open')"
        safe, err = _validate_sandbox_ast(code)
        assert safe is False
        # Caught by ast.Name check for __builtins__
        assert "__builtins__" in err


class TestSandboxDictBlocking:
    """__dict__ attribute access must be blocked in sandbox mode."""

    def test_dict_attribute_access_blocked(self):
        """obj.__dict__ must be blocked."""
        code = "().__dict__"
        safe, err = _validate_sandbox_ast(code)
        assert safe is False
        assert "__dict__" in err


class TestSandboxSafeCodeStillWorks:
    """Legitimate sandbox code must still pass after hardening."""

    def test_simple_math(self):
        """Basic math operations must be allowed."""
        code = "x = 1 + 2; print(x)"
        safe, err = _validate_sandbox_ast(code)
        assert safe is True
        assert err == ""

    def test_list_comprehension(self):
        """List comprehensions must be allowed."""
        code = "[x * 2 for x in range(10)]"
        safe, err = _validate_sandbox_ast(code)
        assert safe is True
        assert err == ""

    def test_dict_operations(self):
        """Dictionary operations must be allowed."""
        code = "d = {'a': 1, 'b': 2}; print(d['a'] + d['b'])"
        safe, err = _validate_sandbox_ast(code)
        assert safe is True
        assert err == ""

    def test_string_methods(self):
        """String methods must be allowed."""
        code = "s = 'hello'; print(s.upper())"
        safe, err = _validate_sandbox_ast(code)
        assert safe is True
        assert err == ""

    def test_safe_builtin_type(self):
        """type(x) as a function call (not attribute) must be allowed."""
        code = "type(42)"
        safe, err = _validate_sandbox_ast(code)
        assert safe is True
        assert err == ""
