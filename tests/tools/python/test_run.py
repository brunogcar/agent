"""Tests for the python run action (strict sandbox mode).

Mirrors the structure of tests/tools/consult/test_advise.py. Covers:
  1. Success path (safe code → output)
  2. Forbidden-token fast-path block (eval/exec/open/__import__/compile)
  3. AST validation block (imports, MRO traversal, dangerous attrs)
  4. Sandbox error (e.g., runtime exception inside sandbox)
  5. Empty-code rejection
  6. trace_id threading
  7. json_schema validation (graceful — warning appended on mismatch)
"""
from __future__ import annotations

import json

from tools.python import python


class TestRunSuccess:
    """run: sandbox execution of safe code."""

    def test_run_basic_math(self, mock_cfg, mock_pruner):
        """Safe arithmetic should execute and return output."""
        result = python(action="run", code="print(2 + 2)")
        assert result["status"] == "success"
        assert result["data"] == "4"
        assert result["mode"] == "sandbox"

    def test_run_string_ops(self, mock_cfg, mock_pruner):
        """String operations with whitelisted builtins should work."""
        result = python(action="run", code="print('hello'.upper())")
        assert result["status"] == "success"
        assert result["data"] == "HELLO"

    def test_run_list_comprehension(self, mock_cfg, mock_pruner):
        """List comprehensions are allowed in sandbox."""
        result = python(action="run", code="print(sum([x**2 for x in range(5)]))")
        assert result["status"] == "success"
        assert result["data"] == "30"

    def test_run_no_print_returns_locals(self, mock_cfg, mock_pruner):
        """If no print() is used, fall back to stringified locals."""
        result = python(action="run", code="x = 42\ny = 'test'")
        assert result["status"] == "success"
        assert "42" in result["data"] or "x" in result["data"]


class TestRunForbiddenTokens:
    """run: fast-path string check blocks obvious dangerous tokens."""

    def test_blocks_eval_token(self, mock_cfg, mock_pruner):
        result = python(action="run", code="print(eval('1+1'))")
        assert result["status"] == "error"
        assert "Forbidden token 'eval('" in result["error"]

    def test_blocks_exec_token(self, mock_cfg, mock_pruner):
        result = python(action="run", code="exec('print(1)')")
        assert result["status"] == "error"
        assert "Forbidden token 'exec('" in result["error"]

    def test_blocks_open_token(self, mock_cfg, mock_pruner):
        result = python(action="run", code="open('test.txt')")
        assert result["status"] == "error"
        assert "Forbidden token 'open('" in result["error"]

    def test_blocks_dunder_import_token(self, mock_cfg, mock_pruner):
        result = python(action="run", code="__import__('os')")
        assert result["status"] == "error"
        assert "Forbidden token '__import__'" in result["error"]

    def test_blocks_compile_token(self, mock_cfg, mock_pruner):
        result = python(action="run", code="compile('1', '<s>', 'eval')")
        assert result["status"] == "error"
        assert "Forbidden token 'compile('" in result["error"]


class TestRunASTBlocks:
    """run: AST validation blocks obfuscated escapes."""

    def test_blocks_direct_import(self, mock_cfg, mock_pruner):
        result = python(action="run", code="import os\nprint(os.getcwd())")
        assert result["status"] == "error"
        assert "Imports are not allowed" in result["error"]

    def test_blocks_from_import(self, mock_cfg, mock_pruner):
        result = python(action="run", code="from sys import path\nprint(path)")
        assert result["status"] == "error"
        assert "Imports are not allowed" in result["error"]

    def test_blocks_mro_traversal(self, mock_cfg, mock_pruner):
        result = python(action="run", code="x = ().__class__.__base__")
        assert result["status"] == "error"
        assert "__class__" in result["error"] or "__base__" in result["error"]

    def test_blocks_builtins_name_access(self, mock_cfg, mock_pruner):
        result = python(action="run", code="x = __builtins__")
        assert result["status"] == "error"
        assert "__builtins__" in result["error"]

    def test_blocks_class_def(self, mock_cfg, mock_pruner):
        result = python(action="run", code="class A: pass\nprint('ok')")
        assert result["status"] == "error"
        assert "Class definitions" in result["error"]

    def test_blocks_with_statement(self, mock_cfg, mock_pruner):
        result = python(action="run", code="with open('x') as f: pass")
        # 'open(' is also caught by the fast-path string check first.
        assert result["status"] == "error"


class TestRunSandboxError:
    """run: runtime errors inside the sandbox return fail()."""

    def test_runtime_exception(self, mock_cfg, mock_pruner):
        """A ZeroDivisionError should be surfaced as fail()."""
        result = python(action="run", code="print(1 / 0)")
        assert result["status"] == "error"
        assert "division" in result["error"].lower() or "zero" in result["error"].lower()

    def test_name_error(self, mock_cfg, mock_pruner):
        """Using an undefined name should fail cleanly."""
        result = python(action="run", code="print(undefined_name)")
        assert result["status"] == "error"
        assert "undefined_name" in result["error"]


class TestRunEmptyCode:
    """run: empty/whitespace code is rejected at the facade."""

    def test_empty_code_rejected(self, mock_cfg, mock_pruner):
        result = python(action="run", code="")
        assert result["status"] == "error"
        assert "No code provided" in result["error"]

    def test_whitespace_code_rejected(self, mock_cfg, mock_pruner):
        result = python(action="run", code="   \n  ")
        assert result["status"] == "error"
        assert "No code provided" in result["error"]


class TestRunTraceID:
    """run: trace_id threading."""

    def test_trace_id_in_success(self, mock_cfg, mock_pruner):
        result = python(action="run", code="print('hi')", trace_id="trace-run-1")
        assert result["status"] == "success"
        assert result["trace_id"] == "trace-run-1"

    def test_trace_id_in_error(self, mock_cfg, mock_pruner):
        result = python(action="run", code="import os", trace_id="trace-run-2")
        assert result["status"] == "error"
        assert result["trace_id"] == "trace-run-2"

    def test_no_trace_id_when_absent(self, mock_cfg, mock_pruner):
        result = python(action="run", code="print('hi')")
        assert result["status"] == "success"
        assert "trace_id" not in result


class TestRunJSONSchema:
    """run: json_schema validation (graceful — warnings, not failures)."""

    def test_schema_match_no_warning(self, mock_cfg, mock_pruner):
        """Output that matches the schema should have no warnings."""
        code = "import json\nprint(json.dumps({'name': 'Alice', 'age': 30}))"
        # run mode forbids imports — use direct print instead.
        code = "print('{\"name\": \"Alice\", \"age\": 30}')"
        schema = json.dumps({
            "type": "object",
            "required": ["name", "age"],
            "properties": {
                "name": {"type": "string"},
                "age": {"type": "integer"},
            },
        })
        result = python(action="run", code=code, json_schema=schema)
        assert result["status"] == "success"
        assert "warnings" not in result

    def test_schema_mismatch_appends_warning(self, mock_cfg, mock_pruner):
        """Output that doesn't match the schema should append a warning."""
        code = "print('hello, not json')"
        schema = json.dumps({"type": "object", "required": ["name"]})
        result = python(action="run", code=code, json_schema=schema)
        assert result["status"] == "success"
        assert "warnings" in result
        assert any("not valid JSON" in w for w in result["warnings"])

    def test_schema_field_mismatch_appends_warning(self, mock_cfg, mock_pruner):
        """Output is JSON but missing a required field — warning appended."""
        code = "print('{\"name\": \"Alice\"}')"
        schema = json.dumps({
            "type": "object",
            "required": ["name", "age"],
            "properties": {"name": {"type": "string"}, "age": {"type": "integer"}},
        })
        result = python(action="run", code=code, json_schema=schema)
        assert result["status"] == "success"
        assert "warnings" in result
        assert any("validation failed" in w for w in result["warnings"])

    def test_invalid_json_schema_string_appends_warning(self, mock_cfg, mock_pruner):
        """A malformed json_schema string itself appends a warning."""
        code = "print('hello')"
        result = python(action="run", code=code, json_schema="not-json{")
        assert result["status"] == "success"
        assert "warnings" in result
        assert any("not valid JSON" in w for w in result["warnings"])


class TestRunDuration:
    """run: facade attaches duration_ms."""

    def test_duration_ms_present(self, mock_cfg, mock_pruner):
        result = python(action="run", code="print('hi')")
        assert "duration_ms" in result
        assert isinstance(result["duration_ms"], (int, float))
        assert result["duration_ms"] >= 0
