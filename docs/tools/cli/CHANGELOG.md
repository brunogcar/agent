<- Back to [CLI Overview](../CLI.md)

# 🗺️ Changelog

## 📝 Version History

| Version | Date | Notes |
|------| **v1.1** | 2026-07-18 | **8 P1 fixes.** (1) `python` proxy: fixed `mode=` → `action=` mapping (`run`→`run`, `calc`→`eval`, `data`→`run_data`) — was calling `python(mode=...)` which would TypeError since the python tool has no `mode` param. (2) `_registry.py`: collision guard — `register_action()` now logs a warning when a `tool_name:action_name` is overwritten (was: silent overwrite; patterns.py "read" collision relied on this). (3) 35 new tests: proxy tests (python/memory/lms/skill/notify), integration tests (4-layer flow), Windows command tests (5 skipif + 1 mapping test), `_safe_dispatch` error tests (redaction + graceful failure + trace_id stripping). (4) `lms.py`: hardcoded `http://localhost:1234` → `cfg.lm_studio_base_url` (strips `/v1` suffix). (5) `skill.py`: removed hardcoded `ticker`/`files` mapping → generic `arg` + `**extra` passthrough. |
---|------|-------|
| v1.0 | — | Un-multiplex CLI: `@meta_tool`, path guard, registry metadata, 4-layer dispatch, 8 test files |

---

## ⚠️ Breaking Changes

*(No breaking changes recorded for pre-v1. Add here as they occur.)*

---

## ✅ Completed

| Feature | Status | Notes |
|---------|--------|-------|
| Un-multiplex CLI | ✅ v1.0 | `@meta_tool`, path guard, registry metadata, 4-layer dispatch |
| `@meta_tool` integration | ✅ v1.0 | Auto-generated docstring and `__tool_metadata__` from flattened DISPATCH |
| 4-layer dispatch | ✅ v1.0 | Patterns → Shell → Router → Executor |
| Path guard integration | ✅ v1.0 | `core.path_guard` validates filesystem paths in shell execution |
| Proxy handlers | ✅ v1.0 | Stacked decorators per namespace (file, git, web, python, memory, notify, cleanup, skill, lms) |
| Shell whitelist | ✅ v1.0 | `ALLOWED_COMMANDS`, `BLOCKED_FLAGS`, `SHELL_OPERATORS` |
| Security model | ✅ v1.0 | Layer 0 sanitization, Layer 2 shell execution, error redaction |
| Test restructure | ✅ v1.0 | 8 focused test files with `conftest.py` |

---

## 🔄 In Progress / Next Up

| Feature | Notes | Priority |
|---------|-------|----------|
| ~~Fix `python` proxy `mode` mapping~~ | ✅ v1.1 — `mode=` → `action=` mapping (`run`→`run`, `calc`→`eval`, `data`→`run_data`). | ✅ Done |
| ~~`_CLI_META_DISPATCH` collision guard~~ | ✅ v1.1 — `register_action()` logs warning on overwrite. | ✅ Done |
| ~~Proxy-specific tests~~ | ✅ v1.1 — 20 proxy tests across 5 classes (python/memory/lms/skill/notify). | ✅ Done |
| ~~`cli()` integration test~~ | ✅ v1.1 — 4 integration tests (pattern/shell/router/escalate). | ✅ Done |
| ~~`_shell_exec` Windows command tests~~ | ✅ v1.1 — 5 skipif-Windows + 1 mapping test. | ✅ Done |
| ~~`_safe_dispatch` exception test~~ | ✅ v1.1 — 5 tests (redaction, graceful failure, unknown tool, trace_id stripping). | ✅ Done |
| ~~LMS URL config~~ | ✅ v1.1 — Uses `cfg.lm_studio_base_url` (strips `/v1` suffix). | ✅ Done |
| ~~Skill parameter genericization~~ | ✅ v1.1 — Generic `arg` + `**extra` passthrough. | ✅ Done |
| Browser proxy action | Router already knows `browser`, add pattern layer | P2 |
| Tavily proxy action | Zero-token fast path for research queries | P2 |
| Parallel proxy action | Batch operations without router overhead | P2 |
| Consult proxy | Configurable as extra model via `.env` | P2 |
| Shell whitelist expansion | `diff`, `wc`, `head`, `tail` (read-only, safe) | P2 |
| Structured output mode | `--json` flag for programmatic consumption | P2 |
| Audit logging | All CLI commands to tracer with layer, tool, result | P2 |

---

## 🚫 Deferred / Out of Scope

| # | Feature | Why Deferred | Priority |
|---|---------|------------|----------|
| 1 | Command history / recall | Last N commands from memory | P3 |
| 2 | Fuzzy matching for typos | `gti status` → `git status` | P3 |
| 3 | Router prompt hardening | Stricter JSON schema, adversarial tests | P3 |
| 4 | Regression test corpus | Replay real commands, verify same routing | P3 |
| 5 | Shell timeout config per layer | Patterns 5s, shell 30s, router 15s, executor 60s | P3 |
| 6 | Tab completion metadata | Common prefixes for LLM prompt engineering | P4 |
| 7 | Alias / macro | User-defined shortcuts and mini-workflows | P4 |
| 8 | Interactive mode | Multi-turn session state (conflicts with MCP stdio) | P4 |

---

*Last updated: 2026-07-18 (v1.1 — 8 P1 fixes).*
