# ⚙️ Configuration System Architecture

The configuration system (`core/config.py`) is the single source of truth for all runtime settings. It uses a singleton pattern, loads from `.env` at import time, and provides validated, typed access to paths, models, limits, and feature flags.

## 🏗️ Architecture Overview

### Design Principles

1. **Single Source of Truth**: All configuration lives in `.env`, loaded once at startup
2. **Singleton Pattern**: Access via `cfg` object, never instantiate `Config` directly
3. **Pathlib Throughout**: All paths are `pathlib.Path` objects (cross-platform)
4. **Fail-Fast Validation**: Invalid config raises exceptions at import time
5. **No Hardcoding**: Model names, paths, and limits all come from environment

### Usage Pattern

```python
from core.config import cfg

# Access paths
print(cfg.agent_root)           # Path: D:/mcp/agent
print(cfg.workspace_root)       # Path: D:/mcp/agent/workspace
print(cfg.memory_chroma_path)   # Path: D:/mcp/agent/memory_db/chroma

# Access models (from .env, never hardcoded)
print(cfg.planner_model)        # e.g., "qwen/qwen3.5-9b"
print(cfg.executor_model)       # e.g., "hermes-3-llama-3.1-8b"

# Access limits
print(cfg.autocode_max_retries) # int: 3
print(cfg.memory_top_k)         # int: 5

# Check protected files
if cfg.is_protected("server.py"):
    print("Cannot edit this file!")
```

---

## 📁 Path Configuration

All paths are `pathlib.Path` objects, resolved to absolute paths.

| Config Attribute | Env Variable | Default | Purpose |
|------------------|--------------|---------|---------|
| `agent_root` | `AGENT_ROOT` | Parent of `core/` | Root directory of the agent codebase |
| `workspace_root` | `WORKSPACE_ROOT` | `{agent_root}/workspace` | Isolated workspace for agent operations |
| `memory_root` | `MEMORY_ROOT` | `{agent_root}/memory_db` | ChromaDB and SQLite storage |
| `memory_chroma_path` | (derived) | `{memory_root}/chroma` | ChromaDB vector store location |
| `memory_db_path` | (derived) | `{memory_root}/agent.db` | Agent metadata SQLite DB |
| `task_db_path` | (derived) | `{memory_root}/task.db` | Gateway task queue SQLite DB |
| `workspace_autocode` | (derived) | `{workspace_root}/autocode` | Autocode workflow scratch space |
| `workspace_index` | (derived) | `{workspace_root}/.index` | File indexing cache |
| `log_path` | (derived) | `{agent_root}/logs` | JSONL trace logs |

### Path Resolution Helpers

```python
# Resolve relative paths within agent_root
path = cfg.resolve_agent_path("tools/web.py")
# Returns: Path("D:/mcp/agent/tools/web.py")

# Resolve relative paths within workspace_root
path = cfg.resolve_workspace_path("data/sales.csv")
# Returns: Path("D:/mcp/agent/workspace/data/sales.csv")
```

---

## 🤖 Model Configuration

Model identifiers are loaded from `.env` and must match exactly what appears in your LLM provider's `/v1/models` response.

| Config Attribute | Env Variable | Required | Purpose |
|------------------|--------------|----------|---------|
| `planner_model` | `PLANNER_MODEL` | ✅ Yes | Long-context reasoning, memory summaries, vision |
| `executor_model` | `EXECUTOR_MODEL` | ❌ No (falls back to planner) | Code generation, analysis, synthesis |
| `router_model` | `ROUTER_MODEL` | ❌ No (falls back to planner) | Fast task classification |
| `vision_model` | `VISION_MODEL` | ❌ No (falls back to planner) | Multimodal image analysis |

### Model Registry

The `cfg.model_registry` dict provides per-role configuration:

```python
cfg.model_registry = {
    "planner": {
        "model": cfg.planner_model,
        "base_url": cfg.lm_studio_base_url,
        "timeout": 90,  # from PLANNER_TIMEOUT
    },
    "executor": {
        "model": cfg.executor_model,
        "base_url": cfg.lm_studio_base_url,
        "timeout": 120,  # from EXECUTOR_TIMEOUT
    },
    "router": {
        "model": cfg.router_model,
        "base_url": cfg.lm_studio_base_url,
        "timeout": 15,  # from ROUTER_TIMEOUT
    },
    "vision": {
        "model": cfg.vision_model,
        "base_url": cfg.lm_studio_base_url,
        "timeout": 60,  # from VISION_TIMEOUT
    },
}
```

---

## 🌐 External Services

| Config Attribute | Env Variable | Default | Purpose |
|------------------|--------------|---------|---------|
| `lm_studio_base_url` | `LM_STUDIO_BASE_URL` | `http://localhost:1234/v1` | OpenAI-compatible LLM endpoint |
| `searxng_url` | `SEARXNG_URL` | `http://localhost:8080` | Privacy-focused search engine |

---

## 🧠 Memory Tuning

| Config Attribute | Env Variable | Default | Purpose |
|------------------|--------------|---------|---------|
| `memory_delete_threshold` | `MEMORY_DELETE_THRESHOLD` | `0.4` | Decay score below which memories are pruned |
| `memory_decay_days` | `MEMORY_DECAY_DAYS` | `30` | Days until decay floor (0.3) is reached |
| `memory_top_k` | `MEMORY_TOP_K` | `5` | Default results per recall query |
| `memory_max_entry_bytes` | `MAX_MEMORY_BYTES` | `50000` | Max bytes per memory entry (50KB) |
| `max_tags_per_entry` | `MAX_TAGS_PER_ENTRY` | `6` | Max tags per memory entry |
| `max_tag_length` | `MAX_TAG_LENGTH` | `50` | Max characters per tag |

---

## 🛠️ Tool & System Limits

### Web Tool Limits

| Config Attribute | Env Variable | Default | Purpose |
|------------------|--------------|---------|---------|
| `web_max_text_chars` | `WEB_MAX_TEXT_CHARS` | `8000` | Max characters per scraped page |
| `web_snippet_chars` | `WEB_SNIPPET_CHARS` | `300` | Max characters per search snippet |
| `web_max_search_results` | `WEB_MAX_SEARCH_RESULTS` | `10` | Max search results to return |

### CLI Tool Limits

| Config Attribute | Env Variable | Default | Purpose |
|------------------|--------------|---------|---------|
| `cli_max_command_chars` | `CLI_MAX_COMMAND_LENGTH` | `4096` | Max shell command length |
| `cli_max_arguments` | `CLI_MAX_ARGUMENTS` | `20` | Max arguments per command |

### File Tool Limits

| Config Attribute | Env Variable | Default | Purpose |
|------------------|--------------|---------|---------|
| `file_max_read_chars` | `FILE_MAX_READ_CHARS` | `50000` | Max characters per file read |

### Autocode & Execution Limits

| Config Attribute | Env Variable | Default | Purpose |
|------------------|--------------|---------|---------|
| `execution_timeout` | `EXECUTOR_TIMEOUT` | `120` | Seconds for code execution sandbox |
| `sandbox_timeout` | `SANDBOX_TIMEOUT` | `30` | Seconds for quick sandbox checks |
| `autocode_max_retries` | `AUTOCODE_MAX_RETRIES` | `3` | Max TDD iterations before rollback |
| `autocode_max_file_chars` | `AUTOCODE_MAX_FILE_CHARS` | `6000` | Max file size for autocode context |
| `autocode_debug` | `AUTOCODE_DEBUG` | `0` | Set to `1` for verbose trace logging |

### Timeout Hierarchy

| Config Attribute | Env Variable | Default | Purpose |
|------------------|--------------|---------|---------|
| `planner_timeout` | `PLANNER_TIMEOUT` | `180` | Planner LLM call timeout |
| `router_timeout` | `ROUTER_TIMEOUT` | `60` | Router LLM call timeout |
| `autocode_graph_timeout` | `AUTOCODE_GRAPH_TIMEOUT` | `300` | Total autocode workflow timeout |
| `max_retries` | `AUTOCODE_MAX_RETRIES` | `3` | Alias for autocode_max_retries |

**Validation Rule**: `autocode_graph_timeout` must be >= max(planner_timeout, execution_timeout, router_timeout)

---

## 🛡️ Protected Files

The `cfg.protected_files` frozenset lists files that the autocode workflow and file tools are forbidden from editing:

```python
cfg.protected_files = frozenset({
    "server.py",
    "registry.py",
    "core/config.py",
    "core/tracer.py",
    "core/llm.py",
    "core/memory.py",
    "core/gateway.py",
})
```

### Checking Protection

```python
if cfg.is_protected("server.py"):
    print("Cannot edit this file!")

if cfg.is_protected("tools/web.py"):
    print("This file is safe to edit")
```

**Implementation Details**:
- Case-insensitive filename matching
- Checks both filename and relative path within `agent_root`
- Handles symlinks and path normalization

---

## 🔒 SSRF Protection

The `cfg.allowed_internal_hosts` frozenset defines which internal hosts the `web` tool can access:

| Config Attribute | Env Variable | Default | Purpose |
|------------------|--------------|---------|---------|
| `allowed_internal_hosts` | `ALLOWED_INTERNAL_HOSTS` | `localhost,127.0.0.1,::1` | Comma-separated allowlist |

### Production vs Development

**Development** (default): Allows localhost for LM Studio, SearXNG, etc.
```ini
ALLOWED_INTERNAL_HOSTS=localhost,127.0.0.1,::1
```

**Production**: Block all private/localhost access
```ini
ALLOWED_INTERNAL_HOSTS=
```

### Startup Warning

If `allowed_internal_hosts` is non-empty and not in CLI test mode, a warning is logged once:
```
[WARNING] SSRF: localhost access allowed by default for development.
Set ALLOWED_INTERNAL_HOSTS='' for production.
```

---

## 🌐 Gateway Configuration

| Config Attribute | Env Variable | Default | Purpose |
|------------------|--------------|---------|---------|
| `gateway_host` | `GATEWAY_HOST` | `127.0.0.1` | REST API bind address |
| `gateway_port` | `GATEWAY_PORT` | `8000` | REST API port |
| `gateway_secret` | `GATEWAY_SECRET` | `changeme` | Bearer token for auth |

**Security Note**: The gateway refuses to start in production mode (`ENV=production`) if `GATEWAY_SECRET` is still `changeme`.

---

## 🌍 Environment Detection

| Config Attribute | Env Variable | Default | Purpose |
|------------------|--------------|---------|---------|
| `env` | `ENV` | `development` | `development` or `production` |
| `is_dev` | (derived) | `True` if env == "development" | Convenience flag |
| `is_windows` | (derived) | `True` if os.name == "nt" | Platform detection |

---

## ✅ Validation Rules

The `Config.__init__()` method enforces these validations at startup:

### Path Validations
- `agent_root` must be an absolute path
- `agent_root` must exist on the filesystem

### Limit Validations
- `autocode_max_retries` > 0
- `autocode_max_file_chars` > 0
- `autocode_graph_timeout` >= max(node timeouts)
- `memory_max_entry_bytes` must be 1-10,000,000
- `max_tags_per_entry` must be 1-50
- `max_tag_length` must be 1-200
- `web_max_text_chars` must be 1-100,000
- `web_snippet_chars` must be 1-5,000
- `web_max_search_results` must be 1-50
- `cli_max_command_chars` must be 1-49,999
- `cli_max_arguments` must be 1-100
- `file_max_read_chars` must be 1-1,000,000

**Failure Mode**: Invalid config raises `ValueError` or `FileNotFoundError` at import time, preventing the server from starting with bad settings.

---

## 🔧 Helper Methods

### `ensure_dirs()`

Creates all required directories if they don't exist:

```python
cfg.ensure_dirs()
# Creates: memory_root, memory_chroma_path, workspace_root,
#          workspace_autocode, workspace_index, log_path
```

### `resolve_agent_path(relative: str) -> Path`

Resolves a relative path within `agent_root`:

```python
path = cfg.resolve_agent_path("tools/web.py")
# Returns: Path("D:/mcp/agent/tools/web.py").resolve()
```

### `resolve_workspace_path(relative: str) -> Path`

Resolves a relative path within `workspace_root`:

```python
path = cfg.resolve_workspace_path("data/sales.csv")
# Returns: Path("D:/mcp/agent/workspace/data/sales.csv").resolve()
```

### `is_protected(path: str | Path) -> bool`

Checks if a path matches the protected files list:

```python
if cfg.is_protected("server.py"):
    print("Cannot edit!")
```

---

## 📊 Complete `.env` Reference

```ini
# ── Paths (no trailing slash) ──────────────────────────────────────────────
AGENT_ROOT=D:/mcp/agent
WORKSPACE_ROOT=D:/mcp/agent/workspace
MEMORY_ROOT=D:/mcp/agent/memory_db

# ── LM Studio ──────────────────────────────────────────────────────────────
LM_STUDIO_BASE_URL=http://localhost:1234/v1
FASTMCP_LOG_LEVEL=error

# ── Model Roles (Match your LM Studio loaded models exactly) ───────────────
PLANNER_MODEL=qwen-qwen3.5-9b
EXECUTOR_MODEL=granite-4.0-h-tiny@q2_k
ROUTER_MODEL=granite-4.0-350m
VISION_MODEL=qwen-qwen3.5-9b

# ── External Services ──────────────────────────────────────────────────────
SEARXNG_URL=http://localhost:8080

# ── Memory Tuning ──────────────────────────────────────────────────────────
MEMORY_DELETE_THRESHOLD=0.4
MEMORY_DECAY_DAYS=30
MEMORY_TOP_K=5
MAX_MEMORY_BYTES=50000
MAX_TAGS_PER_ENTRY=6
MAX_TAG_LENGTH=50

# ── Web Tool Limits ────────────────────────────────────────────────────────
WEB_MAX_TEXT_CHARS=8000
WEB_SNIPPET_CHARS=300
WEB_MAX_SEARCH_RESULTS=10

# ── CLI Tool Limits ────────────────────────────────────────────────────────
CLI_MAX_COMMAND_LENGTH=4096
CLI_MAX_ARGUMENTS=20

# ── File Tool Limits ───────────────────────────────────────────────────────
FILE_MAX_READ_CHARS=50000

# ── Execution & Autocode ───────────────────────────────────────────────────
EXECUTION_TIMEOUT=120
SANDBOX_TIMEOUT=30
AUTOCODE_MAX_RETRIES=3
AUTOCODE_MAX_FILE_CHARS=6000
AUTOCODE_DEBUG=0

# ── Timeouts ───────────────────────────────────────────────────────────────
PLANNER_TIMEOUT=180
ROUTER_TIMEOUT=60
AUTOCODE_GRAPH_TIMEOUT=300

# ── SSRF Protection ────────────────────────────────────────────────────────
ALLOWED_INTERNAL_HOSTS=localhost,127.0.0.1,::1

# ── Gateway ────────────────────────────────────────────────────────────────
GATEWAY_HOST=127.0.0.1
GATEWAY_PORT=8000
GATEWAY_SECRET=changeme

# ── Environment ────────────────────────────────────────────────────────────
ENV=development
```

---

## ⚠️ AI Agent Instructions for Configuration

If you are an AI assistant modifying `core/config.py`:

1. **Never Hardcode Model Names**: Always use `cfg.planner_model`, `cfg.executor_model`, etc. Never write `"qwen"` or `"hermes"` in code.

2. **Preserve Validation**: Never remove or weaken the validation rules in `__init__()`. They prevent the server from starting with invalid config.

3. **Protected Files**: Never remove files from `cfg.protected_files` without explicit user approval. These protect core infrastructure.

4. **Pathlib Throughout**: All new path attributes must be `pathlib.Path` objects, not strings.

5. **Environment Variables**: All new config values must come from `os.getenv()` with sensible defaults. Never hardcode production values.

6. **Singleton Pattern**: Never instantiate `Config` directly. Always use the `cfg` singleton at module level.

7. **SSRF Warning**: Never remove the `_warn_ssrf_default_enabled()` function. It alerts users to production security risks.

8. **Type Hints**: All new attributes must have proper type hints (e.g., `self.my_value: int = ...`).

9. **Documentation**: Update this CONFIG.md when adding new config attributes.

10. **Backward Compatibility**: When renaming env variables, support both old and new names for at least one release cycle.

---

## 🔮 Future Enhancements (Planned)

- **Config Hot-Reload**: Watch `.env` for changes and reload without restart
- **Config Validation Schema**: Use Pydantic for declarative validation rules
- **Config Secrets Manager**: Integrate with HashiCorp Vault or AWS Secrets Manager
- **Config Diff Tool**: Show what changed between `.env` versions
- **Config Migration**: Automatic upgrade of old `.env` formats

---

*Last updated: Phase 4 complete. All validations enforced, SSRF protection active, protected files list finalized.*