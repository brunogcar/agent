"""core/config_backend/ — Implementation package for core/config.py.

[v1.0] Extracted from the monolithic ``Config.__init__`` (~430 lines) in
``core/config.py``. Each module here exposes a single ``_init_<section>(cfg)``
builder function that sets a cohesive group of attributes on the ``Config``
instance. The ``Config.__init__`` method imports and calls these builders
in order; the resulting object surface is identical to pre-v1.0.

Modules:
    env_loader    — _find_env_file() + _resolve_role() (helpers, no state)
    paths         — _init_paths(cfg): filesystem path attributes
    providers     — _init_providers(cfg): API keys, base URLs, embeddings, runtime
    models        — _init_models(cfg): model roles, model_registry, derived timeouts
    services      — _init_services(cfg): SearXNG, Tavily, browser, deep_research
    memory        — _init_memory(cfg): memory tuning, diversity, context budgeting
    execution     — _init_execution(cfg): autocode, autoresearch, parallel, cache, understand
    limits        — _init_limits(cfg): tool limits (memory, web, cli, file)
    security      — _init_security(cfg): protected files, SSRF, gateway, environment
    validators    — _validate_config(cfg): inline range checks (raises during __init__)
    validation    — validate_config(): startup validation (called by server.py)

The split is purely structural — no behavior changes. The 213 callers that do
``from core.config import cfg`` continue to work unchanged.
"""
