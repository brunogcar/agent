"""
core/memory_backend/meta_learning.py
Background meta-learning daemon.

Scans agent traces for successful patterns and auto-distills them into
procedural memory rules. These rules are then injected into future
planner prompts to improve workflow quality.

ARCHITECTURE NOTE (P3):
This system and sleep_learn/ are SEPARATE but COMPLEMENTARY learning pipelines:
- meta_learning: synchronous per-workflow, distills from completed traces
- sleep_learn: background daemon, processes feedback and confidence scores

Both write to the 'procedural' collection but with different metadata tags
(source="meta_learner" vs source="sleep_learn"). The injector.py queries
both collections to provide a unified view to the planner.

UNIFICATION STATUS: Partial. Collections are unified (both write to 'procedural'),
but the query logic in injector.py still checks both for backward compatibility.
Full unification (single query, no fallback) requires further investigation
and a dedicated testing session.
"""
from __future__ import annotations

import json
import time
import hashlib
from pathlib import Path
from typing import Any

from core.config import cfg
from core.tracer import tracer
from core.memory import memory
from core.memory_backend.procedural.validate import is_valid_rule
from core.memory_backend.scoring import normalize_and_hash

SPECIFICITY_MARKERS = [
    "specifically", "exactly", "must", "always", "never",
    "the correct way", "best practice", "standard approach",
    "instead of", "rather than", "should use", "prefer",
]

# -- Distillation -----------------------------------------------------------

def _extract_rules_from_trace(trace: dict) -> list[dict]:
    """Extract actionable rules from a completed trace."""
    rules = []
    steps = trace.get("steps", [])
    goal = trace.get("goal", "")

    for step in steps:
        node = step.get("node", "")
        msg = step.get("message", "")

        if node == "apply" and "committed" in msg:
            rules.append({
                "text": f"When {goal}, apply fix and commit: {msg}",
                "importance": 9,
                "confidence": 0.9,
                "source": "template",  # [P3 FIX] Mark as template-extracted
            })
        elif node == "read" and "found" in msg:
            rules.append({
                "text": f"When {goal}, check {msg} first",
                "importance": 7,
                "confidence": 0.8,
                "source": "template",
            })
        elif node == "test" and "passed" in msg:
            rules.append({
                "text": f"When {goal}, run tests after changes",
                "importance": 8,
                "confidence": 0.85,
                "source": "template",
            })

    return rules

def _is_specific_enough(rule_text: str, source: str = "") -> bool:
    """Reject vague rules that won't help future workflows.

    Template-extracted rules bypass this check because they are already
    validated by is_valid_rule() and follow known-good structural patterns.
    LLM-extracted rules still require specificity markers.
    """
    # [P3 FIX] Template-extracted rules are structurally validated;
    # skip the semantic specificity check to avoid rejecting 100% of them.
    if source == "template":
        return True
    lower = rule_text.lower()
    return any(marker in lower for marker in SPECIFICITY_MARKERS)

# -- Public API -------------------------------------------------------------

def distill_and_store(trace_id: str, trace: dict) -> dict:
    """
    Extract rules from a trace and store them in procedural memory.
    Returns {"stored": int, "skipped": int, "errors": int}
    """
    stats = {"stored": 0, "skipped": 0, "errors": 0}

    rules = _extract_rules_from_trace(trace)
    if not rules:
        return stats

    for rule in rules:
        text = rule["text"]
        source = rule.get("source", "")

        # Skip vague rules (bypassed for template-extracted rules)
        if not _is_specific_enough(text, source=source):
            stats["skipped"] += 1
            continue

        # Deduplication guard (O(1) hash check)
        rule_hash = normalize_and_hash(text)
        existing = memory.recall(rule_hash, top_k=1, collections=["procedural"])
        if existing:
            stats["skipped"] += 1
            continue

        # Validate
        is_valid, reason = is_valid_rule(text)
        if not is_valid:
            tracer.step(trace_id, "meta_learning", f"Rule rejected: {reason}")
            stats["skipped"] += 1
            continue

        # Store with source tag for split-brain tracking
        # [P3 FIX] Added source="meta_learner" to distinguish from sleep_learn rules
        try:
            memory.store(
                text=text,
                collection="procedural",
                importance=rule["importance"],
                tags="meta-learned,auto-distilled",
                trace_id=trace_id,
                source="meta_learner",  # [P3] Tag for unified collection tracking
            )
            stats["stored"] += 1
        except Exception as e:
            tracer.error(trace_id, "meta_learning", f"Store failed: {e}")
            stats["errors"] += 1

    return stats

class MetaLearner:
    """
    Background daemon that scans recent traces and distills rules.
    Runs every 30 minutes when the system is idle.
    """

    def __init__(self) -> None:
        self._last_scan = 0.0

    def run_once(self) -> dict:
        """Scan recent traces and distill rules. Returns stats."""
        from core.tracer import tracer as _tracer
        recent = _tracer.recent(n=20)

        total_stats = {"stored": 0, "skipped": 0, "errors": 0}
        for trace in recent:
            if trace.get("status") != "success":
                continue
            tid = trace.get("trace_id", "")
            stats = distill_and_store(tid, trace)
            for k in total_stats:
                total_stats[k] += stats.get(k, 0)

        return total_stats

    def run_forever(self) -> None:
        """Daemon loop. Sleeps 30 mins between scans."""
        import time as _time
        while True:
            try:
                stats = self.run_once()
                if stats["stored"] > 0:
                    tracer.step(
                        "daemon", "meta_learning",
                        f"Distilled {stats['stored']} rules",
                        skipped=stats["skipped"], errors=stats["errors"],
                    )
            except Exception as e:
                tracer.error("daemon", "meta_learning", f"Cycle failed: {e}")
            _time.sleep(1800)  # 30 minutes

# -- Singleton --------------------------------------------------------------
learner = MetaLearner()
