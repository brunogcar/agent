"""
skills/ -- Skill domains for the MCP agent.

Each sub-folder is a domain. Dispatcher auto-discovers all of them.
The only MCP-visible tool is skill() in dispatcher.py.

Domains:
  b3/           -- B3 Brazilian stock exchange (sub-domains: b3_api)
  cvm/          -- CVM Brazilian SEC (sub-domains: cvm_dfp_itr, cvm_register)
  news/         -- Financial news (standalone, no sub-domains)

Adding a new domain: create skills/<name>/__init__.py with MANIFEST + route().
Adding a new sub-domain: create skills/<domain>/<name>/__init__.py with MANIFEST + route().
No other files need to change.
"""
