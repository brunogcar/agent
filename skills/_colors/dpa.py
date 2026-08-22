"""skills/_colors/dpa.py -- Shared DPA-range coloring for dividend UIs.

A reusable module for dividend-per-share (DPA) value coloring. Used by the
DDM dividends dashboard + any future skill that displays DPA / dividend
amounts per share. Mirrors the price.py pattern (single _RANGES constant +
3 thin public functions).

11 DPA ranges (salmon -> pale yellow -> mint -> light blue -> dark royal
blue gradient). The semantics differ from price.py: DPA ranges use
half-open (lo < X <= hi] intervals because dividend values cluster near
zero and the boundaries matter at small decimals.

    X <= 0           -> #f4b5b0 (light red/salmon)    text: black
    0 < X <= 0.15    -> #fff3d6 (pale yellow/cream)   text: black
    0.15 < X <= 0.30 -> #e2efda (light mint)          text: black
    0.30 < X <= 1.0  -> #deebf7 (very light blue)     text: black
    1.0 < X <= 2.0   -> #bdd7ee (light blue)          text: black
    2.0 < X <= 3.0   -> #9bc2e6 (medium-light blue)   text: black
    3.0 < X <= 4.0   -> #8faadc (medium blue)         text: white
    4.0 < X <= 5.0   -> #7b9fcf (steel blue)          text: white
    5.0 < X <= 6.0   -> #5b80c1 (darker blue)         text: white
    6.0 < X <= 7.0   -> #4267b8 (dark blue)           text: white
    X > 7.0          -> #1a3a8a (dark royal blue)     text: white

Functions (mirror price.py):
  - dpa_range_color(value)    -> {"bg", "color", "range"}
  - dpa_range_label(value)    -> "X <= 0" / "0 < X <= 0.15" / ... / "X > 7.0"
  - dpa_distribution(values)  -> [{"range", "count", "color", "text_color"}, ...]

The salmon band (X <= 0) signals a red flag (zero/negative dividend), the
pale-yellow/cream/mint bands show small-but-positive dividends (typical
quarterly payouts), and the blue gradient handles the 0.30+ tail up to the
rare 7.0+ mega-payouts. Text-color heuristic: dark blue backgrounds get
white text, light backgrounds get black text.
"""
from __future__ import annotations

from typing import Optional


# Each entry: (lo, hi, bg_color, text_color, label)
#   lo: strict lower bound (lo < X). None means no lower bound (-inf).
#   hi: inclusive upper bound (X <= hi). None means no upper bound (+inf).
#   bg_color: background hex
#   text_color: text hex ("#000" or "#fff")
#   label: human-readable range label
#
# Matching rule: (lo is None OR lo < X) AND (hi is None OR X <= hi)
# The first matching range wins (the list is ordered from lowest to highest).
#
# Text-color heuristic: light backgrounds (salmon / pale yellow / mint /
# very-light-blue / light-blue / medium-light-blue) get black text; medium
# blue + steel + darker + dark + dark-royal blue backgrounds get white text.
_RANGES: list[tuple[Optional[float], Optional[float], str, str, str]] = [
    (None,   0.0,    "#f4b5b0", "#000", "X \u2264 0"),
    (0.0,    0.15,   "#fff3d6", "#000", "0 < X \u2264 0.15"),
    (0.15,   0.30,   "#e2efda", "#000", "0.15 < X \u2264 0.30"),
    (0.30,   1.0,    "#deebf7", "#000", "0.30 < X \u2264 1.0"),
    (1.0,    2.0,    "#bdd7ee", "#000", "1.0 < X \u2264 2.0"),
    (2.0,    3.0,    "#9bc2e6", "#000", "2.0 < X \u2264 3.0"),
    (3.0,    4.0,    "#8faadc", "#fff", "3.0 < X \u2264 4.0"),
    (4.0,    5.0,    "#7b9fcf", "#fff", "4.0 < X \u2264 5.0"),
    (5.0,    6.0,    "#5b80c1", "#fff", "5.0 < X \u2264 6.0"),
    (6.0,    7.0,    "#4267b8", "#fff", "6.0 < X \u2264 7.0"),
    (7.0,    None,   "#1a3a8a", "#fff", "X > 7.0"),
]


def _matches(value: float, lo: Optional[float], hi: Optional[float]) -> bool:
    """Half-open interval check: (lo is None OR lo < value) AND
    (hi is None OR value <= hi)."""
    if lo is not None and not (lo < value):
        return False
    if hi is not None and not (value <= hi):
        return False
    return True


def dpa_range_color(value: float | None) -> dict:
    """Get the color + range label for a DPA value.

    Returns:
        {"bg": "#f4b5b0", "color": "#000" or "#fff",
         "range": "0.15 < X <= 0.30"}

    Text color is black for light backgrounds, white for dark.
    None value returns {"bg": "", "color": "", "range": "-"}.
    """
    if value is None:
        return {"bg": "", "color": "", "range": "-"}

    try:
        v = float(value)
    except (ValueError, TypeError):
        return {"bg": "", "color": "", "range": "-"}

    for lo, hi, bg, color, label in _RANGES:
        if _matches(v, lo, hi):
            return {"bg": bg, "color": color, "range": label}

    # Fallback (should be unreachable -- the last range covers X > 7.0).
    return {"bg": "", "color": "", "range": "-"}


def dpa_range_label(value: float | None) -> str:
    """Get the range label: 'X <= 0', '0 < X <= 0.15', '0.15 < X <= 0.30',
    ..., 'X > 7.0'.

    Returns "-" for None / unparseable values.
    """
    return dpa_range_color(value)["range"]


def dpa_distribution(values: list[float | None]) -> list[dict]:
    """Compute the distribution of DPA values across the 11 ranges.

    Returns: [{"range": "X <= 0", "count": 3, "color": "#f4b5b0",
               "text_color": "#000"}, ...]
    Includes ALL 11 ranges (even if count=0). Order matches the palette
    (lowest value band first, highest last).
    """
    # Initialize all 11 ranges with count=0.
    buckets: list[dict] = [
        {"range": label, "count": 0, "color": bg, "text_color": color}
        for (_, _, bg, color, label) in _RANGES
    ]

    for value in values:
        if value is None:
            continue
        try:
            v = float(value)
        except (ValueError, TypeError):
            continue
        # Find the matching bucket.
        for i, (lo, hi, _bg, _color, _label) in enumerate(_RANGES):
            if _matches(v, lo, hi):
                buckets[i]["count"] += 1
                break

    return buckets


# Convenience: list of all 11 ranges as (label, bg, text_color) tuples.
# Useful for building legends / distribution tables without re-deriving.
ALL_RANGES: list[tuple[str, str, str]] = [
    (label, bg, color) for (_, _, bg, color, label) in _RANGES
]
