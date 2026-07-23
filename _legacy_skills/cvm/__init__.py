"""
skills/cvm/__init__.py -- CVM domain package entry point.
"""
from __future__ import annotations
from skills.cvm.cvm import route, _discover_sub_domains

MANIFEST = {
    "domain":          "cvm",
    "has_sub_domains": True,
    "description":     "CVM (Brazilian SEC) data. Sub-domains: cvm_dfp_itr (financials), cvm_register (company registry).",
    "source":          "dados.cvm.gov.br + dfp_itr.db (dfp_itr_sync)",
}
