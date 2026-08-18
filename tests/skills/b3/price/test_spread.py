"""Tests for skills.b3.price.report.spread.build_spread_sections (v1.6).

Self-contained -- exercises the builder directly with synthetic lists (no
cotahist DB needed). Verifies:
  1. Section count + types (4 sections: 3 charts + 1 KPI table).
  2. Spread computation correctness (best_ask - best_bid).
  3. Spread pct computation (spread / close * 100).
  4. KPI table column_align is set (right-align the Valor column).
  5. Graceful handling of all-None bid/ask (returns a single text section).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# Ensure the repo root is on sys.path so `from skills.b3...` resolves.
# (Tests run with `pytest tests/skills/b3/price/test_spread.py` from repo root.)
_HERE = Path(__file__).resolve().parent
_REPO_ROOT = _HERE.parents[4]  # tests/skills/b3/price/ -> repo root
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# Skip sync guard + HTML auto-generation in tests.
os.environ.setdefault("PLANNER_MODEL", "test")
os.environ.setdefault("PLANNER_PROVIDER", "test")
os.environ.setdefault("EXECUTOR_MODEL", "test")
os.environ.setdefault("EXECUTOR_PROVIDER", "test")
os.environ.setdefault("CVM_SKIP_SYNC", "1")
os.environ.setdefault("CVM_SKIP_HTML", "1")

from skills.b3.price.report.spread import build_spread_sections  # noqa: E402


def _make_synthetic(
    n_days: int = 10,
    base_price: float = 38.0,
    spread_cents: float = 0.02,
) -> tuple[list[str], list[float | None], list[float | None], list[float | None]]:
    """Build synthetic date + best_bid + best_ask + close lists.

    Bid/ask are placed spread_cents apart (ask > bid). Close is the midpoint.
    """
    dates = [f"2024-01-{i+1:02d}" for i in range(n_days)]
    closes = [base_price + i * 0.10 for i in range(n_days)]
    best_bids = [c - spread_cents / 2 for c in closes]
    best_asks = [c + spread_cents / 2 for c in closes]
    return dates, best_bids, best_asks, closes


def test_spread_sections_count_and_types():
    """Section count = 4 (3 charts + 1 KPI table) when bid/ask data present."""
    dates, bids, asks, closes = _make_synthetic(n_days=10)
    sections = build_spread_sections(
        "PETR4", dates, bids, asks, closes,
        volumes=[100_000_000] * 10,
        trade_counts=[15_000] * 10,
    )
    assert len(sections) == 4, f"Expected 4 sections, got {len(sections)}"
    types = [s["type"] for s in sections]
    assert types == ["chart", "chart", "chart", "table"], f"Unexpected types: {types}"
    titles = [s["title"] for s in sections]
    assert "Spread Absoluto" in titles[0]
    assert "Spread Percentual" in titles[1]
    assert "Bid / Ask / Close" in titles[2]
    assert "Estatisticas de Liquidez" in titles[3]


def test_spread_absolute_correctness():
    """Spread absoluto dataset = best_ask - best_bid (one per day)."""
    dates, bids, asks, closes = _make_synthetic(n_days=5, spread_cents=0.04)
    sections = build_spread_sections("TEST4", dates, bids, asks, closes)
    chart = sections[0]
    spread_data = chart["chart_data"]["data"]["datasets"][0]["data"]
    # Each spread should equal 0.04 (4 cents).
    for i, s in enumerate(spread_data):
        assert s is not None
        assert abs(s - 0.04) < 1e-9, f"Day {i}: spread {s} != 0.04"


def test_spread_pct_correctness():
    """Spread pct = spread / close * 100."""
    # Use constant close prices so the spread_pct is the same every day
    # (the default _make_synthetic increases close by 0.10 per day, which
    # would make spread_pct decrease over time and break the strict
    # 1e-9 tolerance assertion below).
    n = 5
    dates = [f"2024-01-{i+1:02d}" for i in range(n)]
    closes = [10.0] * n                       # constant close
    spread_cents = 0.10
    bids = [c - spread_cents / 2 for c in closes]  # 9.95
    asks = [c + spread_cents / 2 for c in closes]  # 10.05
    # spread = 0.10, close = 10.0, spread_pct = 0.10/10*100 = 1.0%.
    sections = build_spread_sections("TEST4", dates, bids, asks, closes)
    chart = sections[1]
    pct_data = chart["chart_data"]["data"]["datasets"][0]["data"]
    for i, p in enumerate(pct_data):
        assert p is not None
        assert abs(p - 1.0) < 1e-9, f"Day {i}: spread_pct {p} != 1.0"


def test_kpi_table_column_align_right():
    """KPI table has column_align=['left', 'right'] for the Valor column."""
    dates, bids, asks, closes = _make_synthetic(n_days=10)
    sections = build_spread_sections("PETR4", dates, bids, asks, closes)
    kpi = sections[3]
    assert kpi["type"] == "table"
    assert kpi["columns"] == ["Metrica", "Valor"]
    assert kpi.get("column_align") == ["left", "right"], \
        f"Expected ['left', 'right'], got {kpi.get('column_align')!r}"


def test_kpi_table_includes_key_metrics():
    """KPI table includes spread medio (R$), spread medio (%), pregões count."""
    dates, bids, asks, closes = _make_synthetic(n_days=10)
    sections = build_spread_sections("PETR4", dates, bids, asks, closes)
    kpi = sections[3]
    labels = [row[0] for row in kpi["rows"]]
    assert "Spread medio (R$)" in labels
    assert "Spread medio (%)" in labels
    assert "Pregoes com cotacao bid/ask" in labels
    assert "Volume medio 252D (R$)" in labels


def test_graceful_all_none_bid_ask():
    """When ALL bid/ask are None, returns a single text section (not a crash)."""
    dates = [f"2024-01-{i+1:02d}" for i in range(5)]
    bids = [None] * 5
    asks = [None] * 5
    closes = [38.0 + i * 0.10 for i in range(5)]
    sections = build_spread_sections("PETR4", dates, bids, asks, closes)
    assert len(sections) == 1, f"Expected 1 section, got {len(sections)}"
    assert sections[0]["type"] == "text"
    assert "sem dados" in sections[0]["text"].lower() or "ausentes" in sections[0]["text"].lower()


def test_graceful_partial_none_bid_ask():
    """When SOME bid/ask are None, the spread for those days is None (skipped)."""
    dates = [f"2024-01-{i+1:02d}" for i in range(5)]
    bids = [37.90, None, 38.10, None, 38.30]
    asks = [38.10, None, 38.30, None, 38.50]
    closes = [38.00, 38.05, 38.20, 38.25, 38.40]
    sections = build_spread_sections("PETR4", dates, bids, asks, closes)
    # Should still produce 4 sections (3 valid spread observations is enough).
    assert len(sections) == 4
    chart = sections[0]
    spread_data = chart["chart_data"]["data"]["datasets"][0]["data"]
    # Days 0, 2, 4 have valid spread = 0.20; days 1, 3 are None.
    assert spread_data[0] is not None and abs(spread_data[0] - 0.20) < 1e-9
    assert spread_data[1] is None
    assert spread_data[2] is not None and abs(spread_data[2] - 0.20) < 1e-9
    assert spread_data[3] is None
    assert spread_data[4] is not None and abs(spread_data[4] - 0.20) < 1e-9


def test_empty_dates_returns_text_section():
    """Empty date list -> single text section (no crash)."""
    sections = build_spread_sections("PETR4", [], [], [], [])
    assert len(sections) == 1
    assert sections[0]["type"] == "text"
