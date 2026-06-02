"""
tests/core/sleep_learn/test_filters.py
Unit tests for the Sleep & Learn quality and safety gates.
"""
from core.sleep_learn.filters import is_quality_rule

def test_rejects_generic_phrases():
    """Rules with platitudes like 'be careful' must be rejected."""
    valid, reason = is_quality_rule("Always be careful when writing code to avoid bugs.")
    assert not valid
    assert "generic phrase" in reason

def test_rejects_dangerous_patterns():
    """Rules promoting dangerous operations must be rejected."""
    valid, reason = is_quality_rule("Use os.system to delete the temporary files quickly.")
    assert not valid
    assert "Safety violation" in reason

def test_rejects_too_short():
    """Rules under the minimum word count must be rejected."""
    valid, reason = is_quality_rule("Fix the bug.")
    assert not valid
    assert "Too short" in reason

def test_accepts_high_quality_rule():
    """Specific, technical, and safe rules must pass all gates."""
    rule = "When parsing JSON from the web tool, always wrap json.loads in a try-except block to handle JSONDecodeError gracefully."
    valid, reason = is_quality_rule(rule)
    assert valid
    assert reason == "Passed all gates"
