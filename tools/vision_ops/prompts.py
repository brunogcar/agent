"""tools/vision_ops/prompts.py — System prompts and modifiers for vision actions.

One base system prompt per action (describe / extract_text / analyse_ui), plus
a JSON-mode variant for each (used when json_mode=True OR json_schema is
provided). Action handlers append:
  1. A format suffix (markdown | json | bullet_points) — controls output shape.
  2. A context-type modifier (screenshot | diagram | photo | document | "")
     — focuses the model on the kind of image the caller passed in.

[DESIGN] WHY MODIFIERS ARE SUFFIXES, NOT SEPARATE PROMPTS:
  - The base prompts encode the action's analytical lens
    (describe = general; extract_text = OCR; analyse_ui = UX critique).
  - Format and context-type are orthogonal dimensions — combining them as
    suffixes gives 3 × 4 = 12 effective prompt variations without 12 prompt
    strings to maintain.
  - Empty string for the default modifier keeps the base prompt pristine
    when no specialization is requested (backward compatibility with v0.x
    callers who only passed task + file_path).

INVARIANTS:
  - The base prompts are stable strings — never mutate them at runtime.
  - Format and context-type lookups use .get(key, "") so an unknown value
    silently degrades to "no suffix" rather than crashing the action.
  - The JSON variants omit the format=json suffix (it would be redundant
    with the JSON-structured prompt). When json_mode=True or json_schema is
    provided, the action handler selects the *_JSON_SYSTEM variant instead
    of base + FORMAT_SUFFIXES["json"].
"""
from __future__ import annotations

from typing import Dict

# ── describe — general image description ───────────────────────────────────
# Preserves the original _VISION_SYSTEM behavior (Overview / Key Elements /
# Text Content / Notable Details) from Pre-v1 tools/vision.py.

DESCRIBE_SYSTEM = """
You are a precise visual analysis specialist.
Describe ONLY what is visible — never hallucinate details.
Structure your response:
Overview: one sentence summary
Key Elements: list of main visible components
Text Content: any readable text, or "none"
Notable Details: patterns, colours, anomalies
"""

DESCRIBE_JSON_SYSTEM = """
You are a precise visual analysis specialist. Output ONLY valid JSON — no prose, no markdown fences.
{
  "overview": "one sentence",
  "elements": ["visible", "elements"],
  "text_content": "readable text or null",
  "colors": ["dominant", "colors"],
  "details": "patterns or anomalies",
  "confidence": "high|medium|low"
}
"""

# ── extract_text — OCR-focused text extraction ─────────────────────────────
# Goal: extract ALL visible text, preserving reading order (top-to-bottom,
# left-to-right). Note text location/region when relevant (e.g. "header",
# "sidebar", "caption"). Distinguish headings, body text, labels, captions.

EXTRACT_TEXT_SYSTEM = """
You are an expert OCR specialist. Extract ALL visible text from the image.
Rules:
- Preserve the original reading order (top-to-bottom, left-to-right).
- Note the location/region of each text block when relevant (e.g., header, sidebar, caption).
- Distinguish headings, body text, labels, and captions where apparent.
- If text is partially obscured or low-confidence, mark it as [unclear].
- If no text is visible, respond with: "No readable text found in the image."
- Do NOT describe non-text visual elements unless they disambiguate the text.
Structure your response:
Source: <document type if inferable, e.g. receipt / screenshot / sign / document>
Text:
<extracted text in reading order, with location notes where helpful>
"""

EXTRACT_TEXT_JSON_SYSTEM = """
You are an expert OCR specialist. Output ONLY valid JSON — no prose, no markdown fences.
{
  "source_type": "document|screenshot|sign|handwriting|other|null",
  "blocks": [
    {
      "location": "header|body|sidebar|caption|footer|other",
      "text": "extracted text",
      "confidence": "high|medium|low"
    }
  ],
  "full_text": "all extracted text concatenated in reading order",
  "has_text": true
}
If no text is visible, return: {"source_type": null, "blocks": [], "full_text": "", "has_text": false}
"""

# ── analyse_ui — UI/UX analysis ────────────────────────────────────────────
# Goal: critique the interface. Cover components, layout, accessibility,
# UX patterns, and design system. Useful for screenshots of web apps,
# mobile apps, dashboards, and design mockups.

ANALYSE_UI_SYSTEM = """
You are a senior UI/UX designer analysing an interface screenshot.
Structure your response:
Components: list of UI elements visible (buttons, inputs, cards, nav, modals, etc.)
Layout: describe the spatial arrangement (grid/flex/stacked), spacing, hierarchy
Accessibility: contrast issues, missing labels, keyboard nav, screen-reader concerns
UX Patterns: identifiable patterns (forms, navigation, onboarding, empty states)
Design System: typography, color palette, spacing scale, component consistency
Strengths: 2-3 things the interface does well
Issues: 2-3 specific problems with severity (CRITICAL / WARNING / INFO)
Recommendations: 2-3 actionable improvements
"""

ANALYSE_UI_JSON_SYSTEM = """
You are a senior UI/UX designer. Output ONLY valid JSON — no prose, no markdown fences.
{
  "components": ["button", "input", "card", "nav", "modal"],
  "layout": {
    "arrangement": "grid|flex|stacked|other",
    "spacing": "consistent|tight|loose|irregular",
    "hierarchy": "clear|unclear|flat"
  },
  "accessibility": {
    "issues": ["contrast", "missing labels", "keyboard nav", "screen reader"],
    "severity": "high|medium|low|none"
  },
  "ux_patterns": ["form", "navigation", "onboarding", "empty state"],
  "design_system": {
    "typography": "consistent|inconsistent|mixed",
    "color_palette": "coherent|incoherent",
    "component_consistency": "high|medium|low"
  },
  "strengths": ["specific strength 1", "specific strength 2"],
  "issues": [
    {"description": "specific problem", "severity": "CRITICAL|WARNING|INFO"}
  ],
  "recommendations": ["actionable improvement 1", "actionable improvement 2"]
}
"""


# ── Format suffixes (appended to base prompt) ──────────────────────────────
# Empty string for "markdown" = no suffix; the base prompt already implies
# structured Markdown output.
# Note: these are NOT appended when the JSON variant is selected — the JSON
# variant already specifies the output shape.

FORMAT_SUFFIXES: Dict[str, str] = {
    "markdown": "",
    "json": "\n\nOutput your response as valid JSON.",
    "bullet_points": "\n\nFormat your response as bullet points only.",
}


# ── Context-type modifiers (appended after format suffix) ─────────────────
# Empty string for "" (the default) = no modifier; base prompt + format suffix
# alone. Each non-empty modifier focuses the model on a specific kind of
# image the caller supplied.
# These apply to BOTH the base prompts and the JSON variants — context_type
# is orthogonal to json_mode.

CONTEXT_TYPE_MODIFIERS: Dict[str, str] = {
    "screenshot": "\n\nThe image is a UI screenshot. Focus on interface elements, layout, and user experience.",
    "diagram": "\n\nThe image is a diagram or flowchart. Focus on structure, connections, and data flow.",
    "photo": "\n\nThe image is a photograph. Focus on subjects, setting, and visual context.",
    "document": "\n\nThe image is a document or scanned text. Focus on text content and document structure.",
}
