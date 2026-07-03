<- Back to [CLI Overview](../CLI.md)

# 📝 API Reference

## 🔧 Tool Signature

```python
@tool
@meta_tool(
    _CLI_META_DISPATCH,
    doc_sections=[
        "4-Layer Dispatch Architecture:",
        " 1. Pattern match — regex for common commands (zero tokens)",
        " 2. Shell whitelist — safe subprocess execution (zero tokens)",
        " 3. Router — LLM classifies ambiguous commands",
        " 4. Executor — complex tasks escalated to planner workflow",
        "",
        "Security:",
        " - shell=False prevents command chaining",
        " - ALLOWED_COMMANDS whitelist controls binaries",
        " - BLOCKED_FLAGS prevents arbitrary code execution",
        " - core.path_guard validates all filesystem paths",
        "",
        "Proxy Actions:",
        " Each action routes to a specific tool (file, git, web, etc.)",
        " and formats the result for human-readable output.",
    ],
)
def cli(
    command: str = "",
    trace_id: str = "",
) -> dict[str, Any]:
    """..."""
```

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `command` | `str` | `""` | Natural-language command string (e.g., `"git status"`, `"read file.py"`) |
| `trace_id` | `str` | `""` | Execution trace identifier for observability |

**Returns:** `{"status": "success", "output": "...", "trace_id": "..."}` — always `status: "success"` even when the routed action fails (failure is in `output` string).

---

## ⚡ Actions

### System

| Action | Shortcut | Params | Description |
|--------|----------|--------|-------------|
| `health` | `health` | — | System health check |
| `help` | `help` | — | Show available CLI commands |

### File (routes to `tools/file.py`)

| Action | Shortcut | Required Params | Optional Params | Description |
|--------|----------|-----------------|-----------------|-------------|
| `read_file` | `read `, `cat `, `show ` | `path` | — | Read file with line numbers (first 40 lines) |
| `write_file` | `write ` | `path`, `content` | — | Write content to file |
| `list_directory` | `ls `, `list ` | `path` | — | List directory contents |
| `patch_file` | `patch ` | `path`, `old`, `new` | — | Apply single str_replace patch |
| `search_files` | `find `, `grep ` | `query` | — | Full-text search across workspace |
| `backup_file` | `backup ` | `path` | — | Backup a file |

### Git (routes to `tools/git.py`)

| Action | Shortcut | Required Params | Optional Params | Description |
|--------|----------|-----------------|-----------------|-------------|
| `status` | `git status` | — | — | Working tree status |
| `log` | `git log [N]` | — | `n` (default 10) | Commit history (formatted) |
| `diff` | `git diff` | — | — | Unstaged changes |
| `snapshot` | `git snapshot [msg]` | — | `message` | Safe checkpoint commit |
| `commit` | `git commit <msg>` | `message` | — | Stage all + commit |
| `rollback` | `git rollback [--force]` | — | `force` | Reset to HEAD |

### Web (routes to `tools/web.py`)

| Action | Shortcut | Required Params | Description |
|--------|----------|-----------------|-------------|
| `search` | `search ` | `query` | Web search (top 5 results formatted) |
| `scrape` | `scrape ` | `url` | Scrape webpage (first 3000 chars) |
| `read` | `read ` | `url` | Read webpage (first 3000 chars) |

### Python (routes to `tools/python_exec.py`)

| Action | Shortcut | Required Params | Optional Params | Description |
|--------|----------|-----------------|-----------------|-------------|
| `run` | `run `, `exec ` | `code` | — | Execute Python code |
| `calc` | `calc ` | `code` | — | Calculate expression |
| `data` | `data ` | `code` | — | Run data analysis code |

**Note:** `calc` and `data` currently execute with `mode="run"` (default). The `action` parameter is mapped to `mode` via `mode_map` in the handler for future extensibility.

### Memory (routes to `core/memory.py`)

| Action | Shortcut | Required Params | Optional Params | Description |
|--------|----------|-----------------|-----------------|-------------|
| `recall` | `recall ` | `query` | `top_k`, `min_score` | Recall from ChromaDB |
| `store` | `store ` | `text` | `memory_type`, `importance`, `tags` | Store in ChromaDB |
| `stats` | `memory stats` | — | — | Memory statistics |
| `prune` | `memory prune` | — | — | Prune low-score memories |

### Notify (routes to `tools/notify.py`)

| Action | Shortcut | Required Params | Description |
|--------|----------|-----------------|-------------|
| `send` | `notify `, `alert `, `ping ` | `message` | Send notification |

### Cleanup

| Action | Shortcut | Required Params | Optional Params | Description |
|--------|----------|-----------------|-----------------|-------------|
| `autocode` | `cleanup autocode [N]` | — | `days` (default 7) | Delete old autocode runs |
| `dry_run` | `dry run cleanup` | — | `days` (default 7) | Preview cleanup without deleting |

### Skill (routes to `skills/dispatcher.py`)

| Action | Shortcut | Required Params | Optional Params | Description |
|--------|----------|-----------------|-----------------|-------------|
| `call` | `skill <domain> <mode> [arg]` | `domain`, `mode` | `arg` | Call skill domain. `arg` maps to `ticker=` (query) or `files=` (sync) |

### LMS (routes to `http://localhost:1234`)

| Action | Shortcut | Required Params | Optional Params | Description |
|--------|----------|-----------------|-----------------|-------------|
| `ls` | `lms ls` | — | — | List downloaded models |
| `ps` | `lms ps` | — | — | List loaded models |
| `load` | `lms load <model>` | `model` | — | Load a model |
| `unload` | `lms unload [model]` | — | `model` | Unload model or all |
| `log` | `lms log` | — | — | Get LM Studio logs (last 2000 chars) |

---

## 🔒 Security

### Layer 0: Input Sanitization (`_sanitize_command`)

| Check | Behavior |
|-------|----------|
| **Type** | Must be `str` |
| **Null bytes** | `\x00` → `ValueError` |
| **Control chars** | `\x00-\x1f`, `\x7f-\x9f` → `ValueError` |
| **Dangerous patterns** | Substring match: `rm -rf`, `passwd`, `hacked`, `root@`, `/etc/passwd`, `chmod 777`, `del /f`, `format`, `diskpart`, `rd /s`, `rmdir /s` |
| **Length** | Max `cfg.cli_max_command_chars` (default 4096) |
| **Arg count** | Max `cfg.cli_max_arguments` (default 50) |

### Layer 2: Shell Execution (`_shell_exec`)

| Check | Implementation |
|-------|---------------|
| **Parse** | `shlex.split(command, posix=(os.name != "nt"))` — no shell injection |
| **Allowlist** | `ALLOWED_COMMANDS` frozenset — 30+ safe binaries |
| **Flag block** | `BLOCKED_FLAGS` — `-c`, `-m`, `--command`, `--module`, `-e`, `--eval` |
| **Operator block** | `SHELL_OPERATORS` — `|`, `||`, `&&`, `;`, `>`, `>>`, `<`, `&`, `` ` ``, `$(` |
| **Path guard** | `resolve_path()` + `_is_within()` for all non-flag tokens against **both** `agent_root` and `workspace_root` |
| **Execution** | `subprocess.run(shell=False, timeout=30)` |
| **Output cap** | `strip()` stdout/stderr, fallback to returncode |

**Allowed commands:** `ls`, `dir`, `cat`, `type`, `head`, `tail`, `grep`, `findstr`, `wc`, `cp`, `copy`, `mv`, `move`, `mkdir`, `rmdir`, `touch`, `stat`, `du`, `df`, `pwd`, `cd`, `git`, `gh`, `python`, `python3`, `pip`, `pytest`, `uname`, `whoami`, `date`, `echo`, `which`, `where`, `systeminfo`, `ipconfig`, `hostname`, `tasklist`, `ver`, `diff`, `md5sum`, `sha256sum`

**Blocked flags:** Prevents `python -c "import os; os.system(...)"`, `python -m module`, etc.

### Proxy Action Security

Proxy handlers route to `tools/file.py`, `tools/git.py`, etc. — these tools have their own path guards and cancellation guards. CLI does not bypass them.

**Error redaction:** `_safe_dispatch` redacts dangerous patterns from handler exceptions before returning them to the user.

---

## 📤 Output

All actions return `{"status": "success", "output": "...", "trace_id": "..."}` via `_ok()`.

**Important:** `cli()` always returns `status: "success"` regardless of whether the routed action succeeded or failed. A failed proxy action returns `{"status": "success", "output": "Error: ..."}`. This is by design — the CLI meta-tool successfully routed the command; the failure is in the output. For programmatic error detection, inspect `output` for `"Error:"` prefix.

**v2 plan:** Add `format="json"` parameter for structured error responses.

---

*Last updated: 2026-07-03. See [ARCHITECTURE.md](ARCHITECTURE.md) for file maps and design decisions, [CHANGELOG.md](CHANGELOG.md) for version history, [INSTRUCTIONS.md](INSTRUCTIONS.md) for AI editing rules.*
