"""Tests for core/memory_backend/rule_schema.py — the unified procedural rule schema.

THE L3 CONTRACT — the keystone of the Memory + Sleep_Learn merge.
Covers: normalize_rule_fields, validate_tags, normalize_tags, build_unified_metadata.
"""
from __future__ import annotations

import pytest

from core.memory_backend.rule_schema import (
    SCHEMA_VERSION,
    VALID_TAG_PREFIXES,
    VALID_SOURCES,
    VALID_OUTCOMES,
    normalize_rule_fields,
    validate_tags,
    normalize_tags,
    compute_text_hash,
    build_unified_metadata,
)


# ── normalize_rule_fields ────────────────────────────────────────────────────

class TestNormalizeRuleFields:
    def test_importance_only_derives_confidence(self):
        imp, conf = normalize_rule_fields(importance=8)
        assert imp == 8
        assert conf == 0.8

    def test_confidence_only_derives_importance(self):
        imp, conf = normalize_rule_fields(confidence=0.85)
        assert imp == 8  # Python round(8.5) = 8 (banker's rounding)
        assert conf == 0.85

    def test_both_set_keeps_both(self):
        imp, conf = normalize_rule_fields(importance=7, confidence=0.3)
        assert imp == 7
        assert conf == 0.3

    def test_neither_set_raises(self):
        with pytest.raises(ValueError):
            normalize_rule_fields()

    def test_importance_clamped_to_1_10(self):
        imp, conf = normalize_rule_fields(importance=15)
        assert imp == 10
        imp, conf = normalize_rule_fields(importance=0)
        assert imp == 1

    def test_confidence_clamped_to_0_1(self):
        imp, conf = normalize_rule_fields(confidence=1.5)
        assert conf == 1.0
        imp, conf = normalize_rule_fields(confidence=-0.5)
        assert conf == 0.0


# ── validate_tags ────────────────────────────────────────────────────────────

class TestValidateTags:
    def test_empty_tags_valid(self):
        assert validate_tags("")[0] is True
        assert validate_tags("   ")[0] is True

    def test_valid_tags(self):
        assert validate_tags("source:sleep_learn")[0] is True
        assert validate_tags("source:llm,domain:python,category:bugfix")[0] is True
        assert validate_tags("status:active,evidence:multi_trace")[0] is True

    def test_invalid_prefix_rejected(self):
        is_valid, err = validate_tags("bad_tag")
        assert is_valid is False
        assert "must start with" in err

    def test_mixed_valid_invalid(self):
        is_valid, err = validate_tags("source:llm,bad_tag")
        assert is_valid is False
        assert "bad_tag" in err

    def test_too_many_tags(self):
        tags = ",".join(f"domain:d{i}" for i in range(11))
        is_valid, err = validate_tags(tags)
        assert is_valid is False
        assert "Too many" in err

    def test_tag_too_long(self):
        long_tag = "source:" + "x" * 50
        is_valid, err = validate_tags(long_tag)
        assert is_valid is False
        assert "exceeds 50" in err


# ── normalize_tags ───────────────────────────────────────────────────────────

class TestNormalizeTags:
    def test_adds_source_tag_if_missing(self):
        result = normalize_tags("domain:python", "sleep_learn")
        assert "source:sleep_learn" in result
        assert "domain:python" in result

    def test_preserves_existing_source_tag(self):
        result = normalize_tags("source:llm,domain:python", "sleep_learn")
        # Should NOT add a second source tag
        assert result.count("source:") == 1
        assert "source:llm" in result

    def test_empty_tags_gets_source_only(self):
        result = normalize_tags("", "meta_learner")
        assert result == "source:meta_learner"

    def test_empty_tags_no_source(self):
        result = normalize_tags("", "")
        assert result == ""


# ── compute_text_hash ────────────────────────────────────────────────────────

class TestComputeTextHash:
    def test_consistent_hash(self):
        assert compute_text_hash("test rule") == compute_text_hash("test rule")

    def test_different_text_different_hash(self):
        assert compute_text_hash("rule A") != compute_text_hash("rule B")

    def test_hash_length(self):
        assert len(compute_text_hash("test")) == 16  # SHA-256 truncated to 16


# ── build_unified_metadata ───────────────────────────────────────────────────

class TestBuildUnifiedMetadata:
    def test_meta_learning_writer(self):
        """meta_learning sets importance, no confidence."""
        meta = build_unified_metadata(
            text="When parsing JSON, handle JSONDecodeError",
            source="meta_learner",
            importance=8,
            tags="category:bugfix",
            goal="fix JSON parsing",
            outcome="success",
            source_trace_ids="trace_001",
        )
        assert meta["type"] == "procedural"
        assert meta["source"] == "meta_learner"
        assert meta["importance"] == 8
        assert meta["confidence"] == 0.8  # derived
        assert "source:meta_learner" in meta["tags"]
        assert "category:bugfix" in meta["tags"]
        assert meta["outcome"] == "success"
        assert meta["version"] == 1
        assert meta["schema_version"] == SCHEMA_VERSION
        assert meta["provenance_count"] == 1
        assert meta["text_hash"] != ""

    def test_sleep_learn_writer(self):
        """sleep_learn sets confidence, no importance."""
        meta = build_unified_metadata(
            text="When parsing JSON, handle JSONDecodeError",
            source="sleep_learn",
            confidence=0.85,
            source_memory_id="mem_123",
        )
        assert meta["source"] == "sleep_learn"
        assert meta["confidence"] == 0.85
        assert meta["importance"] == 8  # Python round(8.5) = 8 (banker's rounding)
        assert "source:sleep_learn" in meta["tags"]
        assert meta["goal"] == ""  # not provided
        assert meta["outcome"] == "unknown"  # default
        assert meta["reasoning"] == ""  # Commit 3 adds this
        assert meta["version"] == 1

    def test_invalid_source_raises(self):
        with pytest.raises(ValueError):
            build_unified_metadata(text="test", source="invalid_source", importance=5)

    def test_neither_importance_nor_confidence_raises(self):
        with pytest.raises(ValueError):
            build_unified_metadata(text="test", source="llm")

    def test_invalid_outcome_graceful(self):
        """Invalid outcome is silently set to 'unknown' (graceful degradation)."""
        meta = build_unified_metadata(
            text="test", source="llm", importance=5, outcome="bogus"
        )
        assert meta["outcome"] == "unknown"

    def test_text_truncation(self):
        """Goal + reasoning are truncated to prevent bloat."""
        meta = build_unified_metadata(
            text="test",
            source="llm",
            importance=5,
            goal="x" * 500,
            reasoning="y" * 2000,
        )
        assert len(meta["goal"]) == 200
        assert len(meta["reasoning"]) == 1000

    def test_source_trace_ids_truncation(self):
        """source_trace_ids capped at 500 chars (minimax's point)."""
        long_ids = ",".join(f"trace_{i:04d}" for i in range(100))
        meta = build_unified_metadata(
            text="test", source="llm", importance=5, source_trace_ids=long_ids
        )
        assert len(meta["source_trace_ids"]) <= 500

    def test_provenance_count(self):
        """provenance_count = number of trace IDs (minimax's field)."""
        meta = build_unified_metadata(
            text="test", source="llm", importance=5,
            source_trace_ids="trace_1,trace_2,trace_3"
        )
        assert meta["provenance_count"] == 3

    def test_all_fields_present(self):
        """Every field in the unified schema is present in the output."""
        meta = build_unified_metadata(text="test", source="llm", importance=5)
        required_fields = {
            "type", "source", "source_trace_ids", "source_memory_id",
            "importance", "confidence", "reinforcement_count", "last_reinforced",
            "goal", "outcome", "reasoning", "tools_used", "tags",
            "created_at", "last_accessed_at", "recall_count", "updated_at",
            "version", "schema_version", "provenance_count", "text_hash",
        }
        assert required_fields.issubset(set(meta.keys()))
