"""
skills/b3/__init__.py -- B3 domain package entry point.

Exposes MANIFEST for dispatcher auto-discovery and delegates
all routing to b3.py which handles sub-domain discovery.
"""

from __future__ import annotations
from skills.b3.b3 import route, _discover_sub_domains

MANIFEST = {
    "domain":          "b3",
    "has_sub_domains": True,
    "description":     "B3 (Brasil Bolsa Balcao) Brazilian stock exchange data. Sub-domains: b3_api (and future: b3_dividends, b3_cotacoes).",
    "source":          "arquivos.b3.com.br (official B3 public API)",
}
