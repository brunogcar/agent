"""webui/theme.py — CSS variable theme registry.

[WebUI v1] Themes as JSON files. Drop a new JSON in webui/themes/, get a new
theme — no code change. Per LLM review: 3-layer token system (primitives →
semantic → component). The existing report templates already use CSS variables;
this formalizes them into a registry.

Theme storage:
  - localStorage (client-side, instant apply, FOUC prevention)
  - cookie (server-set, cross-device)
  - NOT SQLite (theme is a client preference, not application state)

Usage in Jinja2:
  {{ theme_css("dark") }}  → inline <style> block with CSS variables
  {{ available_themes() }} → list of {id, name} for the theme switcher
"""
from __future__ import annotations

import json
from pathlib import Path

_THEMES_DIR = Path(__file__).parent / "themes"
_cache: dict[str, dict] = {}


def _load(theme_id: str) -> dict:
    if theme_id in _cache:
        return _cache[theme_id]
    path = _THEMES_DIR / f"{theme_id}.json"
    if not path.exists():
        return {}
    try:
        _cache[theme_id] = json.loads(path.read_text(encoding="utf-8"))
        return _cache[theme_id]
    except Exception:
        return {}


def available_themes() -> list[dict[str, str]]:
    """List available themes for the switcher."""
    out = []
    for f in sorted(_THEMES_DIR.glob("*.json")):
        data = _load(f.stem)
        out.append({
            "id": f.stem,
            "name": data.get("_name", f.stem),
        })
    return out


def render_theme_css(theme_id: str) -> str:
    """Generate a CSS block with the theme's variables.

    The JSON file has a "tokens" dict of CSS variable → value.
    Output: `:root[data-theme="dark"] { --bg: #...; --text: #...; ... }`
    """
    data = _load(theme_id)
    tokens = data.get("tokens", {})
    if not tokens:
        return ""
    lines = [f':root[data-theme="{theme_id}"] {{']
    for k, v in tokens.items():
        # k is like "bg" → "--bg"
        var = k if k.startswith("--") else f"--{k}"
        lines.append(f"  {var}: {v};")
    lines.append("}")
    return "\n".join(lines)


def render_all_themes_css() -> str:
    """Generate CSS for all themes (for the <head> inline <style>)."""
    blocks = [render_theme_css(t["id"]) for t in available_themes()]
    return "\n\n".join(b for b in blocks if b)


def reset_cache() -> None:
    _cache.clear()
