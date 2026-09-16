"""webui/i18n.py — JSON-based internationalization.

[WebUI v1] Custom i18n (NOT gettext). JSON files + a 30-line t() function.
Per LLM review consensus (6 of 9 reviewers): gettext's .po/.mo compile step
is overkill for a solo project with ~200-300 strings.

Locale negotiation order (industry standard):
  ?lang= query > cookie > Accept-Language header > default (pt-BR)

Usage in Jinja2 templates:
  {{ t("nav.valuation") }}
  {{ _("company.search_placeholder") }}

Usage in Python:
  from webui.i18n import t
  label = t("nav.valuation", locale="pt-BR")

[Design decision] Domain terms (DRE, DFC, P/L, ROE, EBITDA) are NOT
translated — they're proper nouns in finance. An English-language Brazilian
finance UI still says "DRE" the same way nobody translates "10-K".
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_LOCALES_DIR = Path(__file__).parent / "locales"
DEFAULT_LOCALE = "pt-BR"
SUPPORTED_LOCALES = ("pt-BR", "en-US")

_cache: dict[str, dict[str, str]] = {}


def _load(locale: str) -> dict[str, str]:
    """Load a locale's translation dict (cached). Falls back to default."""
    if locale in _cache:
        return _cache[locale]
    path = _LOCALES_DIR / f"{locale}.json"
    if not path.exists():
        if locale != DEFAULT_LOCALE:
            return _load(DEFAULT_LOCALE)
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        # Flatten nested dict to dot-keys: {"nav": {"valuation": "..."}} → {"nav.valuation": "..."}
        flat: dict[str, str] = {}
        _flatten(data, prefix="", out=flat)
        _cache[locale] = flat
        return flat
    except Exception:
        return {}


def _flatten(d: dict, prefix: str, out: dict[str, str]) -> None:
    """Flatten nested dict to dot-keys."""
    for k, v in d.items():
        key = f"{prefix}.{k}" if prefix else k
        if isinstance(v, dict):
            _flatten(v, key, out)
        else:
            out[key] = str(v)


def negotiate_locale(query_lang: str | None = None, cookie_lang: str | None = None,
                     accept_header: str = "") -> str:
    """Pick the best locale. Priority: query > cookie > Accept-Language > default."""
    if query_lang and query_lang in SUPPORTED_LOCALES:
        return query_lang
    if cookie_lang and cookie_lang in SUPPORTED_LOCALES:
        return cookie_lang
    if accept_header:
        for tag in [t.split(";")[0].strip().lower() for t in accept_header.split(",")]:
            for s in SUPPORTED_LOCALES:
                if tag.startswith(s.lower().split("-")[0]):
                    return s
    return DEFAULT_LOCALE


def t(key: str, locale: str = DEFAULT_LOCALE, **fmt: Any) -> str:
    """Translate a key. Falls back to default locale, then to the key itself.

    Supports str.format interpolation: t("welcome", locale="en-US", name="Bruno")
    → "Welcome, Bruno" (if en-US.json has "welcome": "Welcome, {name}")
    """
    strings = _load(locale)
    s = strings.get(key)
    if s is None and locale != DEFAULT_LOCALE:
        s = _load(DEFAULT_LOCALE).get(key)
    if s is None:
        return key  # missing translation — return the key so failures are visible
    if fmt:
        try:
            return s.format(**fmt)
        except Exception:
            return s
    return s


def available_locales() -> list[dict[str, str]]:
    """List available locales with their display names. For the language switcher."""
    out = []
    for loc in SUPPORTED_LOCALES:
        data = _load(loc)
        out.append({
            "code": loc,
            "name": data.get("_name", loc),  # locales start with a "_name" key
        })
    return out


def reset_cache() -> None:
    """Clear the translation cache (useful for dev mode / hot reload)."""
    _cache.clear()
