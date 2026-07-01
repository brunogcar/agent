# core/net/default.py
"""Shared default values for tavily, web_ops, browser, research, deep_research.

v1.3: Fixed header comment (was "defaults.py").
"""

# Search
SEARCH_MAX_RESULTS: int = 5
SEARCH_TIMEOUT: int = 30

# Crawl / Map
CRAWL_MAX_DEPTH: int = 3
CRAWL_MAX_BREADTH: int = 10
CRAWL_LIMIT: int = 50

# Extract
EXTRACT_MAX_URLS: int = 10
EXTRACT_DEPTH: str = "basic"

# Scrape
SCRAPE_TIMEOUT: int = 30
SCRAPE_MAX_RETRIES: int = 3

# Browser
BROWSER_TIMEOUT: int = 30
BROWSER_NAV_RETRIES: int = 2

# Retry / Backoff (all tools)
RETRY_MAX_ATTEMPTS: int = 3
RETRY_BASE_DELAY: float = 2.0
RETRY_MAX_DELAY: float = 30.0
RETRY_JITTER: bool = True

# Circuit Breaker
CB_FAILURE_THRESHOLD: int = 5
CB_RECOVERY_TIMEOUT: float = 60.0
CB_HALF_OPEN_MAX_CALLS: int = 1
