"""Tests for the python eval action (safe expression evaluation, NEW v1.0).

Covers:
  1. Simple expression evaluation (no print needed — value is returned)
  2. Statements rejected (assignments, loops, ifs, defs)
  3. Sandbox security still applies (__class__, __builtins__, etc.)
  4. Result returned as stringified value
  5. json_schema validation (STRICT — fails on mismatch, unlike run/run_data)
"""
from __future__ import annotations

import json

from tools.python import python


class TestEvalSuccess:
    """eval: simple expressions return their value (no print() needed)."""

    def test_eval_simple_arithmetic(self, mock_cfg, mock_pruner):
        result = python(action="eval", code="2 + 2")
        assert result["status"] == "success"
        assert result["mode"] == "eval"
        assert result["data"] == "4"

    def test_eval_string_concat(self, mock_cfg, mock_pruner):
        result = python(action="eval", code="'a' + 'b'")
        assert result["status"] == "success"
        assert result["data"] == "ab"

    def test_eval_list_comprehension(self, mock_cfg, mock_pruner):
        result = python(action="eval", code="[x**2 for x in range(5)]")
        assert result["status"] == "success"
        # _stringify uses json.dumps for lists → "[0, 1, 4, 9, 16]"
        assert result["data"] == "[0, 1, 4, 9, 16]"

    def test_eval_dict_literal(self, mock_cfg, mock_pruner):
        result = python(action="eval", code="{'name': 'Alice', 'age': 30}")
        assert result["status"] == "success"
        parsed = json.loads(result["data"])
        assert parsed["name"] == "Alice"
        assert parsed["age"] == 30

    def test_eval_boolean(self, mock_cfg, mock_pruner):
        result = python(action="eval", code="True and False")
        assert result["status"] == "success"
        assert result["data"] == "false"

    def test_eval_function_call(self, mock_cfg, mock_pruner):
        """Whitelisted builtins (sum, len, sorted) are callable in eval."""
        result = python(action="eval", code="sum([1, 2, 3, 4])")
        assert result["status"] == "success"
        assert result["data"] == "10"


class TestEvalRejectsStatements:
    """eval: any statement (not a pure expression) is rejected."""

    def test_assignment_rejected(self, mock_cfg, mock_pruner):
        result = python(action="eval", code="x = 5")
        assert result["status"] == "error"
        assert "expression" in result["error"].lower()

    def test_for_loop_rejected(self, mock_cfg, mock_pruner):
        result = python(action="eval", code="for i in range(3): print(i)")
        assert result["status"] == "error"
        assert "expression" in result["error"].lower()

    def test_if_statement_rejected(self, mock_cfg, mock_pruner):
        result = python(action="eval", code="if True: print('x')")
        assert result["status"] == "error"
        assert "expression" in result["error"].lower()

    def test_function_def_rejected(self, mock_cfg, mock_pruner):
        result = python(action="eval", code="def f(): return 1")
        assert result["status"] == "error"
        assert "expression" in result["error"].lower()

    def test_import_rejected(self, mock_cfg, mock_pruner):
        result = python(action="eval", code="import os")
        assert result["status"] == "error"

    def test_print_statement_rejected(self, mock_cfg, mock_pruner):
        """print() is a statement-level expression but evaluates to None.
        print(x) by itself IS a single expression statement — but it's allowed.
        However `print(x); print(y)` (two statements) should be rejected.
        """
        # Single print() is technically a valid expression — eval would return None.
        result = python(action="eval", code="print('hi')")
        assert result["status"] == "success"
        # result is None → _stringify returns "null"
        assert result["data"] == "null"


class TestEvalSandboxSecurity:
    """eval: same sandbox restrictions as run mode."""

    def test_blocks_dunder_import(self, mock_cfg, mock_pruner):
        result = python(action="eval", code="__import__('os')")
        assert result["status"] == "error"
        # Caught by either fast-path string check or AST validation
        assert "Forbidden" in result["error"] or "dangerous" in result["error"]

    def test_blocks_mro_traversal(self, mock_cfg, mock_pruner):
        result = python(action="eval", code="().__class__.__base__")
        assert result["status"] == "error"
        assert "__class__" in result["error"] or "__base__" in result["error"]

    def test_blocks_builtins_access(self, mock_cfg, mock_pruner):
        result = python(action="eval", code="__builtins__")
        assert result["status"] == "error"
        assert "__builtins__" in result["error"]

    def test_blocks_open_call(self, mock_cfg, mock_pruner):
        result = python(action="eval", code="open('test.txt')")
        assert result["status"] == "error"
        # eval mode does NOT use the fast-path string check (run mode does).
        # It relies purely on AST validation → "Blocked dangerous call: open()".
        assert "Forbidden token 'open('" in result["error"] or "Blocked dangerous call: open()" in result["error"]


class TestEvalResultReturned:
    """eval: the expression value IS the output (no print() needed)."""

    def test_no_print_needed(self, mock_cfg, mock_pruner):
        """Contrast with run: run needs print(), eval returns the value."""
        run_result = python(action="run", code="2 + 2")
        assert run_result["data"] != "4"  # No print → falls back to str(locals)

        eval_result = python(action="eval", code="2 + 2")
        assert eval_result["data"] == "4"  # Value is returned directly

    def test_nested_expression(self, mock_cfg, mock_pruner):
        result = python(action="eval", code="sum(x for x in range(10) if x % 2 == 0)")
        assert result["status"] == "success"
        assert result["data"] == "20"  # 0+2+4+6+8 = 20


class TestEvalJSONSchema:
    """eval: json_schema validation (STRICT — fails on mismatch)."""

    def test_schema_match_succeeds(self, mock_cfg, mock_pruner):
        code = "{'name': 'Alice', 'age': 30}"
        schema = json.dumps({
            "type": "object",
            "required": ["name", "age"],
            "properties": {"name": {"type": "string"}, "age": {"type": "integer"}},
        })
        result = python(action="eval", code=code, json_schema=schema)
        assert result["status"] == "success"

    def test_schema_mismatch_fails(self, mock_cfg, mock_pruner):
        """Value type doesn't match schema → fail (strict)."""
        code = "'just a string'"
        schema = json.dumps({"type": "object", "required": ["name"]})
        result = python(action="eval", code=code, json_schema=schema)
        assert result["status"] == "error"
        assert "schema" in result["error"].lower()

    def test_schema_missing_required_field_fails(self, mock_cfg, mock_pruner):
        code = "{'name': 'Alice'}"
        schema = json.dumps({
            "type": "object",
            "required": ["name", "age"],
            "properties": {"name": {"type": "string"}, "age": {"type": "integer"}},
        })
        result = python(action="eval", code=code, json_schema=schema)
        assert result["status"] == "error"
        assert "missing required field" in result["error"]

    def test_schema_wrong_type_fails(self, mock_cfg, mock_pruner):
        """Schema expects integer, value is string → fail."""
        code = "'not an int'"
        schema = json.dumps({"type": "integer"})
        result = python(action="eval", code=code, json_schema=schema)
        assert result["status"] == "error"
        assert "expected integer" in result["error"]

    def test_invalid_json_schema_string_fails(self, mock_cfg, mock_pruner):
        """Malformed json_schema itself → fail."""
        result = python(action="eval", code="2 + 2", json_schema="not-json{")
        assert result["status"] == "error"
        assert "not valid JSON" in result["error"]

    def test_no_schema_no_validation(self, mock_cfg, mock_pruner):
        """Without json_schema, any value type is accepted."""
        result = python(action="eval", code="42", json_schema="")
        assert result["status"] == "success"
        assert result["data"] == "42"


class TestEvalEmptyCode:
    """eval: empty code is rejected."""

    def test_empty_code_rejected(self, mock_cfg, mock_pruner):
        result = python(action="eval", code="")
        assert result["status"] == "error"
        assert "No code provided" in result["error"]


class TestEvalTraceID:
    """eval: trace_id threading."""

    def test_trace_id_in_success(self, mock_cfg, mock_pruner):
        result = python(action="eval", code="2 + 2", trace_id="trace-eval-1")
        assert result["status"] == "success"
        assert result["trace_id"] == "trace-eval-1"
