<- Back to [Consult Overview](../CONSULT.md)

# 📝 API Reference

## 🔧 Tool Signature

```python
@tool
def consult(
    question: str,
    context: str = "",
) -> dict:
    """Consult the configured AI advisor for high-level help.
    Use for breaking deadlocks, architectural decisions, or complex logic reviews.
    Do not use for routine code generation or simple questions.
    """
```

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `question` | `str` | **Yes** | The core question, architecture decision, or code snippet to analyze |
| `context` | `str` | No | Supporting background (logs, error traces, file contents). Truncated to ~2000 tokens if oversized. |

---

## 📤 Output

All responses are flat `dict`s with a `status` key:

### Success
```json
{
  "status": "success",
  "provider": "openai",
  "model": "gpt-4o",
  "advice": "...",
  "warnings": ["Context truncated from ~5000 to 2000 tokens..."]
}
```
> `warnings` is omitted when no truncation occurred.

### Disabled
```json
{
  "status": "disabled",
  "error": "Consultor is disabled. Set CONSULTOR_MODEL in .env to enable."
}
```

### Rate Limited
```json
{
  "status": "rate_limited",
  "error": "Rate limit exceeded for openai. Please wait before consulting again."
}
```

### LLM Error
```json
{
  "status": "error",
  "provider": "openai",
  "model": "gpt-4o",
  "error": "HTTP 503: Service unavailable"
}
```

---

## 🔒 Security

| Feature | Implementation |
|---------|---------------|
| **Kill-switch** | Returns `disabled` immediately if `cfg.consultor_model` is falsy — no network call |
| **Rate-limit guard** | `check_rate_limit(provider)` blocks the call before any HTTP request |
| **Context truncation** | `_estimate_tokens()` + hard 2000-token ceiling prunes oversized `context` before dispatch |
| **No local FS access** | `consult` only processes text passed by the caller. Never reads files or executes code directly |
| **Isolated config** | Uses dedicated `CONSULTOR_*` env vars resolved through `cfg.model_registry`. Never shares keys with local LM Studio |

---

*Last updated: 2026-07-03. See [ARCHITECTURE.md](ARCHITECTURE.md) for file maps and design decisions, [CHANGELOG.md](CHANGELOG.md) for version history, [INSTRUCTIONS.md](INSTRUCTIONS.md) for AI editing rules.*
