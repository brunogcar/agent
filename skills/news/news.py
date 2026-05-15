"""
skills/news/news.py -- News skill (standalone domain, no sub-domains).

PLANNED SOURCES
---------------
  infomoney    -- https://www.infomoney.com.br (Brazilian financial news)
  valoreconomico -- https://valor.globo.com (business newspaper)
  b3_news      -- B3 official news and corporate actions
  cvm_notices  -- CVM official notices and IPO filings

DECISION: news is a standalone domain (no sub-domains) because each source
is a simple scrape/RSS function, not a complex data pipeline like b3_api or cvm_api.
Sources are listed directly as modes: mode="infomoney", mode="valor", etc.

STUB -- implement when ready by adding functions here and registering in MANIFEST modes.
"""

from __future__ import annotations


def headlines(source: str = "infomoney", query: str = "", limit: int = 10) -> dict:
    """
    Fetch latest financial news headlines.

    source: "infomoney" | "valor" | "b3" | "cvm"
    query:  optional keyword filter
    limit:  max headlines to return
    """
    # TODO: implement per-source scrapers
    return {
        "status":  "not_implemented",
        "message": f"News source '{source}' not yet implemented. Coming soon.",
        "source":  source,
        "query":   query,
    }


def corporate_actions(ticker: str = "", limit: int = 20) -> dict:
    """
    Fetch corporate action notices (dividends declared, splits, IPOs).
    Sources: CVM notices + B3 corporate actions feed.
    """
    return {
        "status":  "not_implemented",
        "message": "Corporate actions feed not yet implemented.",
        "ticker":  ticker,
    }
