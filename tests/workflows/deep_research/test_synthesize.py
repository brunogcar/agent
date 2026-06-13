"""Tests for synthesize node helpers."""
from __future__ import annotations

import pytest

from workflows.deep_research_core.nodes.synthesize import (
    _parse_score,
    _is_converged,
    _merge_knowledge,
)


def test_parse_score_plain_number():
    assert _parse_score("85") == 85.0


def test_parse_score_in_sentence():
    assert _parse_score("I rate this 92 out of 100") == 92.0


def test_parse_score_no_number():
    assert _parse_score("no idea") == 0.0


def test_is_converged_true():
    old = "The sky is blue. The grass is green. The ocean is deep."
    new = "The sky is blue. The grass is green. The ocean is deep."
    assert _is_converged(old, new) is True


def test_is_converged_false():
    old = "The sky is blue."
    new = "The sky is red and the ocean is deep."
    assert _is_converged(old, new) is False


def test_merge_knowledge_empty_prev():
    assert _merge_knowledge("", "new") == "new"


def test_merge_knowledge_with_prev():
    result = _merge_knowledge("old", "new")
    assert "old" in result
    assert "new" in result
