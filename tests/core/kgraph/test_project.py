"""
tests/core/kgraph/test_project.py
Validates ProjectManager dual-structure logic and indexing modes.

[v1.7] Additional tests:
  - get_skip_dirs() — env-override merge with _DEFAULT_SKIP_DIRS.
  - get_embedding_model() — .understand/config.json override + fallback.
"""
from core.kgraph.project import ProjectManager

def test_project_manager_agent_root(tmp_path):
    """For agent_root, source_root should be the path itself."""
    pm = ProjectManager(tmp_path, is_agent_root=True)
    assert pm.source_root == tmp_path.resolve()
    assert pm.artifact_root == tmp_path.resolve() / ".understand"

def test_project_manager_workspace_project(tmp_path):
    """For workspace projects, source_root should be path/code."""
    pm = ProjectManager(tmp_path, is_agent_root=False)
    assert pm.source_root == tmp_path.resolve() / "code"
    assert pm.artifact_root == tmp_path.resolve() / ".understand"

def test_ensure_initialized_creates_dirs(tmp_path):
    """ensure_initialized should create artifact and source directories."""
    pm = ProjectManager(tmp_path, is_agent_root=False)
    pm.ensure_initialized()
    
    assert (tmp_path / ".understand").exists()
    assert (tmp_path / ".understand" / "cache").exists()
    assert (tmp_path / "code").exists()

def test_get_indexing_mode_foreground(tmp_path):
    """Small projects should return 'foreground' mode."""
    (tmp_path / "code").mkdir()
    (tmp_path / "code" / "test.py").write_text("print('hello')")
    
    pm = ProjectManager(tmp_path, is_agent_root=False)
    mode = pm.get_indexing_mode()
    assert mode == "foreground"


# ─── [v1.7] Configurable skip_dirs + per-project embedding model ────────────

def test_get_skip_dirs_returns_default_when_no_env(tmp_path):
    """[v1.7] get_skip_dirs() returns _DEFAULT_SKIP_DIRS when env var is empty."""
    from core.config import cfg
    # Force the env var to be empty.
    orig = getattr(cfg, "understand_skip_dirs", "")
    try:
        cfg.understand_skip_dirs = ""
        skip = ProjectManager.get_skip_dirs()
        assert skip == ProjectManager._DEFAULT_SKIP_DIRS
        assert "node_modules" in skip
        assert ".mypy_cache" in skip
    finally:
        cfg.understand_skip_dirs = orig


def test_get_skip_dirs_merges_env_extras(tmp_path):
    """[v1.7] get_skip_dirs() merges UNDERSTAND_SKIP_DIRS extras with defaults."""
    from core.config import cfg
    orig = getattr(cfg, "understand_skip_dirs", "")
    try:
        cfg.understand_skip_dirs = "vendor,third_party, build_tools"
        skip = ProjectManager.get_skip_dirs()
        # Defaults still present.
        assert "node_modules" in skip
        assert ".git" in skip
        # Extras present (with whitespace stripped).
        assert "vendor" in skip
        assert "third_party" in skip
        assert "build_tools" in skip
        # Empty entries (from leading/trailing/double commas) are filtered.
        assert "" not in skip
    finally:
        cfg.understand_skip_dirs = orig


def test_skip_dirs_class_constant_is_default(tmp_path):
    """[v1.7] ProjectManager.SKIP_DIRS is the pure default (backward compat).

    Tests + callers that read cls.SKIP_DIRS directly should see the same
    set as _DEFAULT_SKIP_DIRS. The env var does NOT affect this attribute
    (callers that want env overrides should use get_skip_dirs()).
    """
    from core.config import cfg
    orig = getattr(cfg, "understand_skip_dirs", "")
    try:
        cfg.understand_skip_dirs = "should_not_appear_in_SKIP_DIRS"
        # The class constant should NOT include the env extra.
        assert "should_not_appear_in_SKIP_DIRS" not in ProjectManager.SKIP_DIRS
        assert ProjectManager.SKIP_DIRS == ProjectManager._DEFAULT_SKIP_DIRS
    finally:
        cfg.understand_skip_dirs = orig


def test_get_embedding_model_fallback(tmp_path):
    """[v1.7] No config.json → returns cfg.embedding_model (global default)."""
    from core.config import cfg
    pm = ProjectManager(tmp_path, is_agent_root=False)
    pm.ensure_initialized()
    # No config.json written.
    assert not (pm.artifact_root / "config.json").exists()
    result = pm.get_embedding_model()
    assert result == cfg.embedding_model


def test_get_embedding_model_override(tmp_path):
    """[v1.7] .understand/config.json with embedding_model key → override."""
    import json
    pm = ProjectManager(tmp_path, is_agent_root=False)
    pm.ensure_initialized()
    (pm.artifact_root / "config.json").write_text(
        json.dumps({"embedding_model": "override-model-v1.7"}), encoding="utf-8"
    )
    assert pm.get_embedding_model() == "override-model-v1.7"


def test_get_embedding_model_missing_key_falls_back(tmp_path):
    """[v1.7] config.json without embedding_model key → falls back to cfg."""
    import json
    from core.config import cfg
    pm = ProjectManager(tmp_path, is_agent_root=False)
    pm.ensure_initialized()
    # config.json exists but doesn't have the embedding_model key.
    (pm.artifact_root / "config.json").write_text(
        json.dumps({"other_key": "value"}), encoding="utf-8"
    )
    assert pm.get_embedding_model() == cfg.embedding_model