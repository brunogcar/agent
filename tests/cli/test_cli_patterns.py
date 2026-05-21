"""
Unit tests for cli pattern matching.
"""
import pytest
from tools.cli_ops.patterns import _match_pattern

class TestGitPatterns:
    def test_git_status(self):
        result = _match_pattern("git status")
        assert result == ("git", "status", {})

    def test_git_log_with_count(self):
        result = _match_pattern("git log 10")
        assert result == ("git", "log", {"n": 10})

    def test_git_commit_with_message(self):
        result = _match_pattern("git commit fix bug")
        assert result == ("git", "commit", {"message": "fix bug"})

    def test_git_rollback_force(self):
        result = _match_pattern("git rollback --force")
        assert result == ("git", "rollback", {"force": True})

    def test_git_rollback_no_force(self):
        result = _match_pattern("git rollback")
        assert result == ("git", "rollback", {})

class TestFilePatterns:
    def test_read_file(self):
        result = _match_pattern("read tools/cli.py")
        assert result == ("file", "read", {"path": "tools/cli.py"})

    def test_cat_file(self):
        result = _match_pattern("cat tools/cli.py")
        assert result == ("file", "read", {"path": "tools/cli.py"})

    def test_list_directory(self):
        result = _match_pattern("ls tools/")
        assert result == ("file", "list", {"path": "tools/"})

    def test_list_no_path(self):
        result = _match_pattern("ls")
        assert result == ("file", "list", {"path": "."})

    def test_search(self):
        result = _match_pattern("grep import")
        assert result == ("file", "search", {"query": "import"})

    def test_backup(self):
        result = _match_pattern("backup myfile.txt")
        assert result == ("file", "backup", {"path": "myfile.txt"})

class TestWebPatterns:
    def test_web_search(self):
        result = _match_pattern("search python tutorials")
        assert result == ("web", "search", {"query": "python tutorials"})

    def test_web_scrape(self):
        result = _match_pattern("scrape https://example.com")
        assert result == ("web", "scrape", {"url": "https://example.com"})

    def test_web_read(self):
        result = _match_pattern("read https://example.com")
        assert result == ("web", "read", {"url": "https://example.com"})

class TestMemoryPatterns:
    def test_memory_recall(self):
        result = _match_pattern("recall my query")
        assert result == ("memory", "recall", {"query": "my query"})

    def test_memory_store(self):
        result = _match_pattern("store my text")
        assert result == ("memory", "store", {"text": "my text"})

    def test_memory_stats(self):
        result = _match_pattern("memory stats")
        assert result == ("memory", "stats", {})

    def test_memory_prune(self):
        result = _match_pattern("memory prune")
        assert result == ("memory", "prune", {})

class TestPythonPatterns:
    def test_python_calc(self):
        result = _match_pattern("calc 2+2")
        assert result == ("python", "calc", {"code": "2+2"})

    def test_python_run(self):
        result = _match_pattern("run print('hello')")
        assert result == ("python", "run", {"code": "print('hello')"})

    def test_python_exec(self):
        result = _match_pattern("exec print('hello')")
        assert result == ("python", "run", {"code": "print('hello')"})

    def test_echo_with_quotes(self):
        result = _match_pattern('echo "hello"')
        assert result == ("python", "run", {"code": 'print("hello")'})

    def test_echo_with_single_quotes(self):
        result = _match_pattern("echo 'hello'")
        assert result == ("python", "run", {"code": "print('hello')"})

    def test_echo_no_quotes(self):
        result = _match_pattern("echo hello world")
        assert result == ("python", "run", {"code": "print('hello world')"})

class TestNotifyPatterns:
    def test_notify(self):
        result = _match_pattern("notify hello")
        assert result == ("notify", "send", {"message": "hello"})

    def test_alert(self):
        result = _match_pattern("alert hello")
        assert result == ("notify", "send", {"message": "hello"})

    def test_ping(self):
        result = _match_pattern("ping hello")
        assert result == ("notify", "send", {"message": "hello"})

class TestSkillPatterns:
    def test_skill_with_arg(self):
        result = _match_pattern("skill b3_api query PETR4")
        assert result == ("skill", "call", {"domain": "b3_api", "mode": "query", "arg": "PETR4"})

    def test_skill_no_arg(self):
        result = _match_pattern("skill b3_api status")
        assert result == ("skill", "call", {"domain": "b3_api", "mode": "status", "arg": ""})

class TestLmsPatterns:
    def test_lms_ls(self):
        result = _match_pattern("lms ls")
        assert result == ("lms", "ls", {})

    def test_lms_ps(self):
        result = _match_pattern("lms ps")
        assert result == ("lms", "ps", {})

    def test_lms_load(self):
        result = _match_pattern("lms load my-model")
        assert result == ("lms", "load", {"model": "my-model"})

    def test_lms_unload(self):
        result = _match_pattern("lms unload my-model")
        assert result == ("lms", "unload", {"model": "my-model"})

    def test_lms_unload_all(self):
        result = _match_pattern("lms unload")
        assert result == ("lms", "unload", {})

    def test_lms_log(self):
        result = _match_pattern("lms log")
        assert result == ("lms", "log", {})

class TestSystemPatterns:
    def test_health(self):
        result = _match_pattern("health")
        assert result == ("system", "health", {})

    def test_help(self):
        result = _match_pattern("help")
        assert result == ("system", "help", {})

class TestNoMatch:
    def test_complex_command(self):
        result = _match_pattern("analyze this code and fix it")
        assert result is None

    def test_unknown_command(self):
        result = _match_pattern("xyz123")
        assert result is None

    def test_empty_command(self):
        result = _match_pattern("")
        assert result is None