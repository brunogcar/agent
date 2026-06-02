"""
core/sleep_learn/filters.py
Quality and safety gates for learned rules.
Rejects generic, overly short, or dangerous rules before they reach storage.
"""
from __future__ import annotations

from core.sleep_learn.config import SLEEP_LEARN_MIN_RULE_WORDS

# Anti-patterns: Rules that are too generic to be useful
_BLACKLIST_PHRASES = [
    "be careful", "always remember", "think step by step", 
    "make sure to", "it is important to", "don't forget"
]

# Safety: Dangerous operations that should never be blindly recommended
_DANGEROUS_PATTERNS = [
    "os.system", "subprocess.call", "eval(", "exec(", 
    "rm -rf", "sudo ", "chmod 777", "drop table"
]

def is_quality_rule(rule_text: str) -> tuple[bool, str]:
    """
    Validates a distilled rule.
    Returns (is_valid, reason).
    """
    if not rule_text or not rule_text.strip():
        return False, "Empty rule"

    lower_rule = rule_text.lower()
    
    # 1. Safety check FIRST: Reject rules promoting dangerous operations
    for pattern in _DANGEROUS_PATTERNS:
        if pattern in lower_rule:
            return False, f"Safety violation: contains '{pattern}'"

    # 2. Check for generic platitudes
    for phrase in _BLACKLIST_PHRASES:
        if phrase in lower_rule:
            return False, f"Contains generic phrase: '{phrase}'"

    # 3. Length check last
    words = rule_text.split()
    if len(words) < SLEEP_LEARN_MIN_RULE_WORDS:
        return False, f"Too short ({len(words)} words < {SLEEP_LEARN_MIN_RULE_WORDS})"

    return True, "Passed all gates"
