"""skills/investsite/fetcher.py -- HTTP fetcher for investsite.com.br pages.

Handles:
  - HTTP GET with browser-like headers (investsite blocks bare UAs)
  - Simple in-memory cache (1h TTL) to avoid re-fetching within a session
  - Rate limiting (0.5s between requests) to respect the free site

NO local database — pure live fetching. Each skill call hits the site.
"""

from __future__ import annotations

import sys
import time
from urllib.parse import quote

import httpx

# ── Constants ────────────────────────────────────────────────────────────────

_BASE_URL = "https://www.investsite.com.br"

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
    "Referer": "https://www.investsite.com.br/",
}

_CACHE_TTL_SECONDS = 3600  # 1 hour
_RATE_LIMIT_SECONDS = 0.5  # 0.5s between requests

# In-memory cache: {url: (html, timestamp)}
_cache: dict[str, tuple[str, float]] = {}
_last_request_time: float = 0.0


def _progress(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


# ── Public API ───────────────────────────────────────────────────────────────

def fetch_page(path: str, params: dict | None = None, force: bool = False) -> str:
    """Fetch an investsite page. Returns raw HTML.

    Args:
        path: URL path (e.g., "principais_indicadores.php") or full URL.
        params: Query parameters dict (e.g., {"cod_negociacao": "PETR4"}).
        force: Bypass cache (re-fetch).

    Returns:
        HTML string.
    """
    # Build full URL
    if path.startswith("http"):
        url = path
    else:
        url = f"{_BASE_URL}/{path.lstrip('/')}"

    # Build cache key (URL + sorted params)
    if params:
        param_str = "&".join(f"{k}={v}" for k, v in sorted(params.items()))
        cache_key = f"{url}?{param_str}"
        full_url = f"{url}?{param_str}"
    else:
        cache_key = url
        full_url = url

    # Check cache
    if not force and cache_key in _cache:
        html, ts = _cache[cache_key]
        age = time.time() - ts
        if age < _CACHE_TTL_SECONDS:
            _progress(f"[investsite] Cache hit: {cache_key[:80]}")
            return html

    # Rate limit
    global _last_request_time
    elapsed = time.time() - _last_request_time
    if elapsed < _RATE_LIMIT_SECONDS:
        time.sleep(_RATE_LIMIT_SECONDS - elapsed)

    # Fetch
    _progress(f"[investsite] Fetching: {full_url[:80]}")
    try:
        resp = httpx.get(full_url, headers=_HEADERS, timeout=30, follow_redirects=True)
        resp.raise_for_status()
        _last_request_time = time.time()
    except httpx.HTTPError as e:
        raise ConnectionError(f"Failed to fetch {full_url}: {e}")

    html = resp.text

    # Cache
    _cache[cache_key] = (html, time.time())

    return html


def clear_cache() -> None:
    """Clear the in-memory cache."""
    _cache.clear()


def cache_stats() -> dict:
    """Return cache statistics."""
    now = time.time()
    entries = []
    for key, (_, ts) in _cache.items():
        age = now - ts
        entries.append({"url": key[:100], "age_seconds": round(age, 0),
                        "fresh": age < _CACHE_TTL_SECONDS})
    return {"total": len(_cache), "entries": entries}


# ── URL builders ─────────────────────────────────────────────────────────────

def url_indicators(ticker: str) -> str:
    return f"{_BASE_URL}/principais_indicadores.php?cod_negociacao={ticker}"


def url_statement(ticker: str, statement: str) -> str:
    """Build URL for a financial statement page.

    Args:
        ticker: B3 ticker (PETR4)
        statement: One of: BPA, BPP, DRE, DFC, DVA, shares
    """
    paths = {
        "BPA":    "balanco_patrimonial_ativo.php",
        "BPP":    "balanco_patrimonial_passivo.php",
        "DRE":    "demonstracao_resultado.php",
        "DFC":    "fluxo_caixa.php",
        "DVA":    "demonstracao_valor_adicionado.php",
        "SHARES": "quantidade_acoes.php",
    }
    path = paths.get(statement.upper())
    if not path:
        raise ValueError(f"Unknown statement '{statement}'. Available: {list(paths.keys())}")
    return f"{_BASE_URL}/{path}?cod_negociacao={ticker}"


def url_events(ticker: str, categoria: str = "") -> str:
    """Build URL for periodic info by category.

    Args:
        ticker: B3 ticker
        categoria: Category name (URL-encoded automatically). Empty = all.
    """
    if categoria:
        return (f"{_BASE_URL}/informacoes_periodicas_detalhe.php"
                f"?cod_negociacao={ticker}&categoria={quote(categoria)}")
    return f"{_BASE_URL}/informacoes_periodicas_detalhe.php?cod_negociacao={ticker}"
