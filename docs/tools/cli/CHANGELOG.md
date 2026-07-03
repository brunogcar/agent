<- Back to [CLI Overview](../CLI.md)

# 🗺️ Changelog

## 📝 Version History

| Version | Date | Notes |
|---------|------|-------|
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
| Fix `python` proxy `mode` mapping | `calc`/`data` actions should set `mode` correctly before calling `python_exec` | P1 |
| `_CLI_META_DISPATCH` collision guard | Assert no duplicate keys during flattening, or use namespaced keys | P1 |
| Proxy-specific tests | Add tests for python, memory, notify, cleanup, skill, lms, web proxies | P1 |
| `cli()` integration test | Full 4-layer flow test through the facade | P1 |
| `_shell_exec` Windows command tests | Real `dir`, `type`, `copy`, `move`, `del` tests on Windows | P1 |
| `_safe_dispatch` exception test | Verify error redaction and graceful handler failures | P1 |
| LMS URL config | Move `http://localhost:1234` to `cfg.lms_base_url` | P1 |
| Skill parameter genericization | Remove hardcoded `ticker`/`files` mapping from `skill.py` | P1 |
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

*Last updated: 2026-07-03. See [ARCHITECTURE.md](ARCHITECTURE.md) for file maps, [API.md](API.md) for action details, [INSTRUCTIONS.md](INSTRUCTIONS.md) for AI editing rules.*
