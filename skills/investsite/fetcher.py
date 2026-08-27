"""skills/investsite/fetcher.py -- HTTP fetcher for investsite.com.br pages.

Handles:
  - HTTP GET with browser-like headers (investsite blocks bare UAs)
  - Simple in-memory cache (1h TTL) to avoid re-fetching within a session
  - Rate limiting (0.5s between requests) to respect the free site
  - [v2] Session authentication via SESSION_ID cookie
    investsite.com.br now requires login (Cloudflare Turnstile CAPTCHA).
    Two auth paths:
      1. INVESTSITE_SESSION_ID env var (manual — log in via browser, copy cookie)
      2. INVESTSITE_EMAIL + INVESTSITE_PASSWORD env vars (automated via browser_ops)
    If neither is set, fetches will fail with a clear error.

NO local database — pure live fetching. Each skill call hits the site.
"""

from __future__ import annotations

import os
import sys
import time
from urllib.parse import quote

import httpx

# ── Constants ────────────────────────────────────────────────────────────────

_BASE_URL = "https://www.investsite.com.br"
_LOGIN_URL = f"{_BASE_URL}/login.php"

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

# Cached session cookie (set once, reused until it expires)
_session_cookie: str | None = None
_session_cookie_checked: bool = False


def _progress(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


# ── Session management ───────────────────────────────────────────────────────

def _get_session_cookie() -> str | None:
    """Get the investsite SESSION_ID cookie.

    Priority:
      1. Cached in-memory (from previous browser login)
      2. INVESTSITE_SESSION_ID from cfg (loaded from .env by core.config)
      3. INVESTSITE_EMAIL + INVESTSITE_PASSWORD → browser login (automated)

    Returns the cookie value, or None if no auth is configured.
    """
    global _session_cookie, _session_cookie_checked

    # Return cached cookie (from previous browser login)
    if _session_cookie:
        return _session_cookie

    # Use cfg from core.config (ensures .env is loaded)
    email = ""
    password = ""
    session_id = ""
    try:
        from core.config import cfg
        session_id = cfg.investsite_session_id or ""
        email = cfg.investsite_email or ""
        password = cfg.investsite_password or ""
    except Exception:
        # Fallback: os.getenv (in case core.config isn't available)
        session_id = os.getenv("INVESTSITE_SESSION_ID", "")
        email = os.getenv("INVESTSITE_EMAIL", "")
        password = os.getenv("INVESTSITE_PASSWORD", "")

    # Path 1: Manual session cookie from .env
    if session_id:
        _session_cookie = session_id
        _progress(f"[investsite] Using SESSION_ID from .env ({session_id[:20]}...)")
        return _session_cookie

    # Path 2: Automated browser login (only try once per session)
    if _session_cookie_checked:
        return None  # Already tried, failed
    _session_cookie_checked = True

    if email and password:
        _progress("[investsite] Attempting browser login (Cloudflare Turnstile)...")
        cookie = _browser_login(email, password)
        if cookie:
            _session_cookie = cookie
            _progress("[investsite] Browser login successful — session cookie cached.")
            return _session_cookie
        _progress("[investsite] Browser login failed (Turnstile may have blocked it). "
                  "Set INVESTSITE_SESSION_ID in .env manually (see fetcher.py docstring).")

    return None


def _browser_login(email: str, password: str) -> str | None:
    """Log in to investsite via browser_ops (Playwright).

    Opens the login page, fills email + password, waits for Cloudflare
    Turnstile to auto-solve, submits, and extracts the SESSION_ID cookie.

    NOTE: Cloudflare Turnstile detects headless browsers and often won't
    auto-solve. This is a best-effort fallback — the primary auth path
    is INVESTSITE_SESSION_ID (manual cookie from browser).

    Returns the cookie value, or None if login failed.
    """
    try:
        from tools.browser_ops.factory import _get_page
        from tools.browser_ops.loop import _run_browser_async
        from tools.browser_ops.state import _browser_lock
        import asyncio

        async def _do_login():
            with _browser_lock:
                page = _run_browser_async(_get_page("", True), timeout=60)

                # Step 1: Navigate to login page.
                # [fix] Use "domcontentloaded" NOT "networkidle" — Turnstile
                # makes continuous background requests so "networkidle" never
                # fires, causing a hang.
                await page.goto(_LOGIN_URL, wait_until="domcontentloaded", timeout=20000)
                _progress("[investsite] Login page loaded.")

                # Step 2: Wait for form inputs to be ready (short timeout).
                try:
                    await page.wait_for_selector('input[name="email"]', timeout=5000)
                    await page.wait_for_selector('input[name="password"]', timeout=5000)
                except Exception:
                    _progress("[investsite] Login form not found — page may have changed.")
                    return None

                # Step 3: Fill email + password
                await page.fill('input[name="email"]', email)
                await page.fill('input[name="password"]', password)
                _progress("[investsite] Credentials filled.")

                # Step 4: Wait for Cloudflare Turnstile to auto-solve.
                # Turnstile injects a hidden input cf-turnstile-response when solved.
                # In headless mode, this often DOESN'T happen (Turnstile detects
                # automation). Short timeout (10s) — fail fast, don't hang.
                try:
                    await page.wait_for_selector(
                        'input[name="cf-turnstile-response"]',
                        state="attached",
                        timeout=10000
                    )
                    _progress("[investsite] Turnstile solved (token present).")
                except Exception:
                    _progress("[investsite] Turnstile did not auto-solve (headless detected). "
                              "Falling back — set INVESTSITE_SESSION_ID in .env manually.")
                    return None

                # Step 5: Click submit
                await page.click('button[type="submit"]')

                # Step 6: Wait for redirect away from login.php (success).
                # Short timeout (8s) — if Turnstile solved, redirect is fast.
                try:
                    await page.wait_for_url(
                        lambda url: "login.php" not in url,
                        timeout=8000
                    )
                    _progress(f"[investsite] Login successful — redirected to: {page.url}")
                except Exception:
                    _progress("[investsite] Still on login page — login failed.")
                    return None

                # Step 7: Extract SESSION_ID cookie
                cookies = await page.context.cookies(urls=[_BASE_URL])
                for cookie in cookies:
                    if cookie.get("name") == "SESSION_ID":
                        return cookie.get("value")

                _progress("[investsite] SESSION_ID cookie not found after login.")
                return None

        # [fix] Run on the BROWSER event loop (not asyncio.run which creates
        # a new loop). The page object was created on the browser daemon
        # thread's loop — Playwright objects can't be used from a different
        # event loop (causes deadlock).
        return _run_browser_async(_do_login(), timeout=60)

    except ImportError:
        _progress("[investsite] browser_ops not available — cannot do automated login.")
        return None
    except Exception as e:
        _progress(f"[investsite] Browser login error: {e}")
        return None


def _build_headers_with_cookie() -> dict:
    """Build headers with session cookie if available."""
    headers = dict(_HEADERS)
    cookie = _get_session_cookie()
    if cookie:
        headers["Cookie"] = f"SESSION_ID={cookie}"
    return headers


# ── Public API ───────────────────────────────────────────────────────────────

def fetch_page(path: str, params: dict | None = None, force: bool = False) -> str:
    """Fetch an investsite page. Returns raw HTML.

    Args:
        path: URL path (e.g., "principais_indicadores.php") or full URL.
        params: Query parameters dict (e.g., {"cod_negociacao": "PETR4"}).
        force: Bypass cache (re-fetch).

    Returns:
        HTML string.

    Raises:
        ConnectionError: If the fetch fails or login is required but not configured.
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

    # Fetch with session cookie
    headers = _build_headers_with_cookie()
    _progress(f"[investsite] Fetching: {full_url[:80]}")
    try:
        resp = httpx.get(full_url, headers=headers, timeout=30, follow_redirects=False)
        _last_request_time = time.time()

        # Check for login redirect (302 → login.php)
        if resp.status_code == 302 and "login.php" in resp.headers.get("location", ""):
            # Session cookie is missing or expired — try to refresh it.
            # DON'T reset _session_cookie_checked: if browser login already
            # failed, don't retry it on every subsequent fetch (spam).
            global _session_cookie
            old_cookie = _session_cookie
            _session_cookie = None

            new_cookie = _get_session_cookie()
            if new_cookie and new_cookie != old_cookie:
                # Got a new cookie — retry the request
                headers = _build_headers_with_cookie()
                resp = httpx.get(full_url, headers=headers, timeout=30, follow_redirects=True)
                _last_request_time = time.time()
            else:
                raise ConnectionError(
                    "investsite session expired or not configured. "
                    "Set INVESTSITE_SESSION_ID in .env (log in via browser → "
                    "F12 → Application → Cookies → investsite.com.br → SESSION_ID)."
                )

        resp.raise_for_status()
    except httpx.HTTPError as e:
        raise ConnectionError(f"Failed to fetch {full_url}: {e}")

    html = resp.text

    # Check if we got redirected to login page (not a 302, but the page itself)
    if "login.php" in str(resp.url) and "email" in html and "password" in html:
        raise ConnectionError(
            "investsite returned login page. Session cookie may be expired. "
            "Update INVESTSITE_SESSION_ID in .env (log in via browser → F12 → "
            "Application → Cookies → investsite.com.br → SESSION_ID)."
        )

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
