"""data_sources — External data connectors for the agent.

Data sources are domain-specific data pipelines that sync from external APIs
(CVM, B3, etc.) into local SQLite DBs, plus a query interface. They follow
the same hub-and-spoke pattern as the old skills/ layer, but with a cleaner
separation: data_sources/ handles raw data storage + retrieval; the skills/
layer (future) handles domain reasoning that combines multiple data sources.

Usage:
    data_source(domain="cvm", sub_domain="dfp", mode="sync")
    data_source(domain="cvm", sub_domain="dfp", mode="query", params='{"company":"PETR4"}')
    data_source(domain="cvm", sub_domain="itr", mode="status")
"""
