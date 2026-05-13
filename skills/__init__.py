"""
skills/ -- Specialised data-gathering skill domains for the MCP agent.

Each subdomain lives in skills/<name>/__init__.py and exports:
  MANIFEST: dict  -- domain metadata, modes, parameters, examples
  route(mode, **params) -> dict  -- routes calls to the right function

The single MCP-visible entry point is skills/dispatcher.py (@tool skill).
Nothing else in this package should be decorated with @tool.

Registered domains (auto-discovered by dispatcher.py):
  b3_api  -- B3 Brazilian stock exchange public data API
"""
