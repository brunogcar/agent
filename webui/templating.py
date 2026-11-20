"""webui/templating.py — ONE shared Jinja2Templates instance.

[WebUI v1.5] pages.py and api.py used to build two separate
Jinja2Templates(directory="webui/templates") envs — CWD-relative (launching
from another directory → TemplateNotFound) and duplicated (two template
caches, globals could drift). This module is the single owner now:

  - Directory resolved from __file__ (works from any CWD).
  - One Jinja env shared by every route module.
"""
from __future__ import annotations

from pathlib import Path

from fastapi.templating import Jinja2Templates

# webui/templating.py → webui/templates/
TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
