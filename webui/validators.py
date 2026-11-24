"""webui/validators.py — shared route-boundary patterns.

[v1.22] ONE ticker definition for every layer (the portfolio service,
the portfolio router, the api router). The four copies that existed had
all drifted into rejecting B3's OWN ticker (B3SA3) and BDRs (A1MD34) —
a digit in the stem is legal B3 symbology (B3SA3 = B3 + S + A stem,
"A1MD34" style BDR units), which ``^[A-Za-z]{4,6}\\d...`` (letters-only
stem) can never match.

The pattern (case-insensitive input; the service uppercases first):
  - first character: a letter;
  - stem: 3–5 more ALPHANUMERICS (digits allowed — B3SA3, A1MD34);
  - 1–2 digits (the standard/fraction distinction: PETR3/PETR11);
  - optional trailing letter.
It is a strict superset of the old pattern — nothing that used to be
accepted is rejected now.
"""
from __future__ import annotations

import re

# B3 symbol: letter + 3-5 alphanumerics + 1-2 digits + optional letter.
TICKER_PATTERN = r"^[A-Za-z][A-Za-z0-9]{3,5}\d{1,2}[A-Za-z]?$"
TICKER_RE = re.compile(TICKER_PATTERN)
