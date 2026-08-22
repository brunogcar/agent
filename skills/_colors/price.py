"""skills/_colors/price.py -- Shared price-range coloring for stock-price UIs.

A reusable module for price-range coloring. Used by DDM acoes + any future
skill that displays stock prices. Migrated from the legacy skills/_price_colors.py
module (now deleted) into the modular skills/_colors/ package.

22 price ranges (red -> pink -> yellow -> green -> teal -> blue gradient):
    X < 1          -> #dc2626 (red)             text: white
    1 <= X < 2     -> #ef4444 (light red)       text: white
    2 <= X < 5     -> #f8bbd0 (light pink)      text: black
    5 <= X < 10    -> #fce4ec (very light pink) text: black
    10 <= X < 15   -> #fff9c4 (pale yellow)     text: black
    15 <= X < 20   -> #ffee58 (light yellow)    text: black
    20 <= X < 25   -> #ffeb3b (yellow)          text: black
    25 <= X < 30   -> #fdd835 (gold)            text: black
    30 <= X < 40   -> #c8e6c9 (cream/mint)      text: black
    40 <= X < 50   -> #a5d6a7 (pale green)      text: black
    50 <= X < 60   -> #66bb6a (light green)     text: white
    60 <= X < 70   -> #43a047 (medium green)    text: white
    70 <= X < 80   -> #2e7d32 (forest green)    text: white
    80 <= X < 90   -> #1b5e20 (dark green)      text: white
    90 <= X < 100  -> #0d9488 (teal)            text: white
    100 <= X < 125 -> #1e3a8a (dark blue)       text: white
    125 <= X < 150 -> #2563eb (royal blue)      text: white
    150 <= X < 175 -> #3b82f6 (medium blue)     text: white
    175 <= X < 200 -> #60a5fa (cornflower)      text: black
    200 <= X < 250 -> #93c5fd (light blue)      text: black
    250 <= X < 300 -> #bfdbfe (very light blue) text: black
    X >= 300       -> #dbeafe (pale ice blue)   text: black

Functions:
  - price_range_color(price)      -> {"bg", "color", "range"}
  - price_range_label(price)      -> "X < 1" / "1 <= X < 2" / ... / "X >= 300"
  - price_distribution(prices)    -> [{"range", "count", "color", "text_color"}, ...]

The 22-range palette is stored in a single constant (ALL_RANGES source:
_RANGES) so adding / reordering ranges only edits one place. The "neon teal"
at 90-100 is a deliberate outlier (matches the reference chart's visual
signature). The 100+ bands use a graduated blue gradient (dark -> pale ice)
so the very-high-price tail still reads as a continuous visual band.
"""
from __future__ import annotations

from typing import Optional


# Each entry: (lo, hi, bg_color, text_color, label)
#   lo: lower bound (inclusive)
#   hi: upper bound (exclusive; None = +inf)
#   bg_color: background hex
#   text_color: text hex ("#000" or "#fff")
#   label: human-readable range label
#
# Text-color heuristic: dark backgrounds get white text, light backgrounds
# get black text. The thresholds below were chosen by visual inspection of
# the reference chart (red/dark-green/teal/blue backgrounds use white text;
# pink/yellow/cream/light-green + light-blue backgrounds use black text).
_RANGES: list[tuple[float, Optional[float], str, str, str]] = [
    (0.0,    1.0,    "#dc2626", "#fff", "X < 1"),
    (1.0,    2.0,    "#ef4444", "#fff", "1 \u2264 X < 2"),
    (2.0,    5.0,    "#f8bbd0", "#000", "2 \u2264 X < 5"),
    (5.0,    10.0,   "#fce4ec", "#000", "5 \u2264 X < 10"),
    (10.0,   15.0,   "#fff9c4", "#000", "10 \u2264 X < 15"),
    (15.0,   20.0,   "#ffee58", "#000", "15 \u2264 X < 20"),
    (20.0,   25.0,   "#ffeb3b", "#000", "20 \u2264 X < 25"),
    (25.0,   30.0,   "#fdd835", "#000", "25 \u2264 X < 30"),
    (30.0,   40.0,   "#c8e6c9", "#000", "30 \u2264 X < 40"),
    (40.0,   50.0,   "#a5d6a7", "#000", "40 \u2264 X < 50"),
    (50.0,   60.0,   "#66bb6a", "#fff", "50 \u2264 X < 60"),
    (60.0,   70.0,   "#43a047", "#fff", "60 \u2264 X < 70"),
    (70.0,   80.0,   "#2e7d32", "#fff", "70 \u2264 X < 80"),
    (80.0,   90.0,   "#1b5e20", "#fff", "80 \u2264 X < 90"),
    (90.0,   100.0,  "#0d9488", "#fff", "90 \u2264 X < 100"),
    # [v2] 7 new bands for the 100-300+ tail (dark blue -> pale ice blue).
    # Dark blue (white text) for 100-175, lighter blue (black text) for
    # 175-300+ so the very-high-price tail still reads as a gradient.
    (100.0,  125.0,  "#1e3a8a", "#fff", "100 \u2264 X < 125"),
    (125.0,  150.0,  "#2563eb", "#fff", "125 \u2264 X < 150"),
    (150.0,  175.0,  "#3b82f6", "#fff", "150 \u2264 X < 175"),
    (175.0,  200.0,  "#60a5fa", "#000", "175 \u2264 X < 200"),
    (200.0,  250.0,  "#93c5fd", "#000", "200 \u2264 X < 250"),
    (250.0,  300.0,  "#bfdbfe", "#000", "250 \u2264 X < 300"),
    (300.0,  None,   "#dbeafe", "#000", "X \u2265 300"),
]


def price_range_color(price: float | None) -> dict:
    """Get the color + range label for a price.

    Returns:
        {"bg": "#dc2626", "color": "#000" or "#fff", "range": "X < 1"}

    Text color is black for light backgrounds, white for dark.
    None price returns {"bg": "", "color": "", "range": "-"}.
    """
    if price is None:
        return {"bg": "", "color": "", "range": "-"}

    try:
        p = float(price)
    except (ValueError, TypeError):
        return {"bg": "", "color": "", "range": "-"}

    # Negative prices (shouldn't happen for stocks, but defensive).
    if p < 0:
        p = 0.0

    for lo, hi, bg, color, label in _RANGES:
        if hi is None:
            if p >= lo:
                return {"bg": bg, "color": color, "range": label}
        elif lo <= p < hi:
            return {"bg": bg, "color": color, "range": label}

    # Fallback (should be unreachable -- the last range covers X >= 300).
    return {"bg": "", "color": "", "range": "-"}


def price_range_label(price: float | None) -> str:
    """Get the range label: 'X < 1', '1 <= X < 2', '2 <= X < 5', ...,
    'X >= 300'.

    Returns "-" for None / unparseable prices.
    """
    return price_range_color(price)["range"]


def price_distribution(prices: list[float | None]) -> list[dict]:
    """Compute the distribution of prices across the 22 ranges.

    Returns: [{"range": "X < 1", "count": 12, "color": "#dc2626",
               "text_color": "#fff"}, ...]
    Includes ALL 22 ranges (even if count=0). Order matches the palette
    (lowest price band first, highest last).
    """
    # Initialize all 22 ranges with count=0.
    buckets: list[dict] = [
        {"range": label, "count": 0, "color": bg, "text_color": color}
        for (_, _, bg, color, label) in _RANGES
    ]

    for price in prices:
        if price is None:
            continue
        try:
            p = float(price)
        except (ValueError, TypeError):
            continue
        if p < 0:
            p = 0.0
        # Find the matching bucket.
        for i, (lo, hi, _bg, _color, _label) in enumerate(_RANGES):
            if hi is None:
                if p >= lo:
                    buckets[i]["count"] += 1
                    break
            elif lo <= p < hi:
                buckets[i]["count"] += 1
                break

    return buckets


# Convenience: list of all 22 ranges as (label, bg, text_color) tuples.
# Useful for building legends / distribution tables without re-deriving.
ALL_RANGES: list[tuple[str, str, str]] = [
    (label, bg, color) for (_, _, bg, color, label) in _RANGES
]
