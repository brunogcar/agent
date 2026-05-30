"""tests/core/memory/test_budget.py — Context budgeting and attention allocation tests."""
from __future__ import annotations
from core.memory_backend.budget import budget_messages, estimate_tokens, ContextClass

def test_pinned_overflow_truncates_user():
    """If SYSTEM+USER exceed budget, user must be truncated, not dropped."""
    msgs = [
        {"role": "system", "content": "A" * 5000},  # ~1250 tokens
        {"role": "user", "content": "B" * 5000},    # ~1250 tokens
    ]
    result = budget_messages(msgs, max_tokens=2000)
    assert len(result) == 2, "Both system and user should survive"
    assert len(result[1]["content"]) < 5000, "User message was not truncated on overflow"

def test_per_class_caps():
    """Per-class cap should limit any single non-pinned class to ~50% of input budget."""
    msgs = [{"role": "tool", "content": "X" * 1000} for _ in range(20)]
    msgs.insert(0, {"role": "system", "content": "sys"})
    result = budget_messages(msgs, max_tokens=4000)
    
    # Measure in TOKENS, not characters, since the budgeter operates on tokens
    from core.memory_backend.budget import estimate_tokens, ContextClass
    tool_tokens = sum(estimate_tokens(m["content"]) for m in result if m["role"] == "tool")
    total_tokens = sum(estimate_tokens(m["content"]) for m in result)
    
    # input_budget = 3200 (80% of 4000). Class Cap = 50% of input_budget = 1600 tokens.
    # We expect ~6 messages to pass (1500 tokens). Allow 1 message overflow margin.
    assert tool_tokens <= 1850, f"Per-class cap failed; tool used {tool_tokens} tokens (cap is ~1600)"
    assert total_tokens <= 4000, f"Total tokens {total_tokens} exceeded max_tokens {4000}"

def test_token_estimation_safety_margin():
    """estimate_tokens should use conservative 3.5 chars/token."""
    text = "Code heavy test with json { 'key': 'value' }"
    est = estimate_tokens(text)
    expected = int(len(text) / 3.5)
    assert est == expected, f"Token estimation mismatch: {est} vs {expected}"