"""
core/memory_backend/procedural/validate.py — Quality filters for extracted rules.
"""
from __future__ import annotations

# Blacklisted phrases that indicate the LLM failed to find a rule or outputted generic garbage
BLACKLIST_PHRASES = [
    "no insight", "no specific", "no reusable", "not applicable",
    "as an ai", "i cannot", "please provide", "generic advice",
    "always write clean", "always test", "make sure to",
]

# Heuristic keywords that suggest a procedural rule (condition -> action)
PROCEDURAL_KEYWORDS = [
    "when ", "if ", "always ", "never ", "to fix ", "use ", 
    "ensure ", "check ", "avoid ", "instead of", "before ",
]

def is_valid_rule(rule_text: str) -> tuple[bool, str]:
    """
    Validate the extracted rule text.
    Returns (is_valid, reason).
    """
    if not rule_text or not isinstance(rule_text, str):
        return False, "empty_or_invalid_type"
        
    text_lower = rule_text.lower().strip()
    
    # Length checks
    if len(text_lower) < 20:
        return False, "too_short"
    if len(text_lower) > 800:
        return False, "too_long"
        
    # Blacklist check
    for phrase in BLACKLIST_PHRASES:
        if phrase in text_lower:
            return False, f"blacklisted_phrase_{phrase.replace(' ', '_')}"
            
    # Heuristic check: Must contain at least one procedural keyword
    has_keyword = any(kw in text_lower for kw in PROCEDURAL_KEYWORDS)
    if not has_keyword:
        return False, "missing_procedural_keyword"
        
    return True, "ok"