"""
core/sleep_learn/feedback.py
Dynamic Confidence Scoring (The Feedback Loop).
Reads injection logs and agent trace logs to update rule confidence scores.
Zero coupling: Does not import tracer or workflows. Purely log-driven.
"""
from __future__ import annotations
import json
import time
import glob
from pathlib import Path
from typing import Dict, List, Any
from collections import defaultdict

from core.config import cfg
from core.sleep_learn.config import _SLEEP_LEARN_DB_PATH, SLEEP_LEARN_COLLECTION_NAME
from core.tracer import tracer

INJECTIONS_LOG = cfg.sleep_learn_log_path / "injections.jsonl"
CONFIDENCE_BOOST = 0.1
CONFIDENCE_PENALTY = -0.2
MIN_CONFIDENCE_THRESHOLD = 0.3

# Infrastructure errors that should NOT penalize rules
INFRA_ERROR_KEYWORDS = [
    "timeout", "connection", "ratelimit", "budget", "unreachable", 
    "circuit breaker", "network", "lm studio"
]

def _get_collection():
    """Lazy load ChromaDB to prevent startup crashes."""
    import chromadb
    client = chromadb.PersistentClient(path=str(_SLEEP_LEARN_DB_PATH))
    return client.get_collection(name=SLEEP_LEARN_COLLECTION_NAME)

def _is_infra_failure(error_msg: str) -> bool:
    """Check if a trace failure was due to infrastructure, not logic."""
    if not error_msg: return False
    lower_msg = error_msg.lower()
    return any(kw in lower_msg for kw in INFRA_ERROR_KEYWORDS)

def update_rule_confidence(rule_id: str, success: bool) -> dict:
    """Updates a single rule's confidence score in ChromaDB."""
    try:
        collection = _get_collection()
        existing = collection.get(ids=[rule_id], include=["metadatas"])
        if not existing or not existing['ids']:
            return {"status": "skipped", "reason": "Rule not found"}

        meta = existing['metadatas'][0]
        current_conf = float(meta.get("confidence_score", 0.8))
        delta = CONFIDENCE_BOOST if success else CONFIDENCE_PENALTY
        new_conf = round(max(0.0, min(1.0, current_conf + delta)), 2)

        if new_conf < MIN_CONFIDENCE_THRESHOLD:
            collection.delete(ids=[rule_id])
            return {"status": "purged", "old_conf": current_conf, "new_conf": new_conf}
        
        meta["confidence_score"] = new_conf
        meta["last_evaluated_at"] = int(time.time())
        collection.update(ids=[rule_id], metadatas=[meta])
        return {"status": "updated", "old_conf": current_conf, "new_conf": new_conf}
    except Exception as e:
        return {"status": "error", "error": str(e)}

def _update_recall_counts(rule_counts: Dict[str, int]):
    """Batch updates recall_count and last_accessed_at for injected rules."""
    if not rule_counts: return
    try:
        collection = _get_collection()
        for rule_id, count in rule_counts.items():
            existing = collection.get(ids=[rule_id], include=["metadatas"])
            if existing and existing['ids']:
                meta = existing['metadatas'][0]
                meta["recall_count"] = meta.get("recall_count", 0) + count
                meta["last_accessed_at"] = int(time.time())
                collection.update(ids=[rule_id], metadatas=[meta])
    except Exception as e:
        tracer.warning("daemon", "sleep_learn_feedback", f"Failed to update recall counts: {e}")

def process_feedback() -> dict:
    """
    Matches pending injections with finished traces from the agent logs.
    Updates confidence scores, recall counts, and archives processed injections.
    """
    stats = {"processed": 0, "boosted": 0, "penalized": 0, "purged": 0, "errors": 0}
    
    if not INJECTIONS_LOG.exists():
        return stats

    # 1. Read pending injections
    pending = []
    try:
        with open(INJECTIONS_LOG, "r", encoding="utf-8") as f:
            for line in f:
                try: pending.append(json.loads(line))
                except json.JSONDecodeError: continue
    except PermissionError:
        return stats  # Windows file lock: skip this cycle

    if not pending:
        return stats

    # 2. Count injections per rule (for recall_count update)
    rule_counts = defaultdict(int)
    for inj in pending:
        for rid in inj.get("rule_ids", []):
            rule_counts[rid] += 1

    # 3. Scan agent logs for trace_finish events (Today + Yesterday)
    target_ids = {p["trace_id"] for p in pending if "trace_id" in p}
    outcomes = {}  # trace_id -> success (bool)
    
    # Glob for today and yesterday to handle midnight rollover
    today = time.strftime('%Y%m%d')
    yesterday = time.strftime('%Y%m%d', time.localtime(time.time() - 86400))
    log_patterns = [
        cfg.agent_log_path / f"agent_{today}.jsonl",
        cfg.agent_log_path / f"agent_{yesterday}.jsonl"
    ]
    
    for log_file in log_patterns:
        if not log_file.exists(): continue
        try:
            with open(log_file, "r", encoding="utf-8") as f:
                for line in f:
                    try:
                        event = json.loads(line)
                        if event.get("event") == "trace_finish" and event.get("trace_id") in target_ids:
                            # Check for infrastructure failures
                            if not event.get("success", False):
                                result_msg = event.get("result", "") or event.get("error", "")
                                if _is_infra_failure(result_msg):
                                    outcomes[event["trace_id"]] = None  # Neutral: no boost/penalty
                                    continue
                            outcomes[event["trace_id"]] = event.get("success", False)
                    except json.JSONDecodeError: continue
        except PermissionError:
            continue  # Windows file lock: skip this file

    # 4. Process matches and update ChromaDB
    processed_ids = set()
    for inj in pending:
        tid = inj.get("trace_id")
        if tid in outcomes:
            success = outcomes[tid]
            if success is not None:  # None means infra failure (skip)
                for rule_id in inj.get("rule_ids", []):
                    res = update_rule_confidence(rule_id, success)
                    stats["processed"] += 1
                    if res["status"] == "updated":
                        if success: stats["boosted"] += 1
                        else: stats["penalized"] += 1
                    elif res["status"] == "purged":
                        stats["purged"] += 1
                    elif res["status"] == "error":
                        stats["errors"] += 1
            processed_ids.add(tid)

    # 5. Update recall counts for ALL pending injections (even if trace isn't finished yet)
    _update_recall_counts(rule_counts)

    # 6. Rewrite injections log without the processed ones
    if processed_ids:
        remaining = [p for p in pending if p.get("trace_id") not in processed_ids]
        try:
            with open(INJECTIONS_LOG, "w", encoding="utf-8") as f:
                for p in remaining:
                    f.write(json.dumps(p) + "\n")
        except PermissionError:
            pass  # If locked, we'll retry next cycle

    tracer.step("daemon", "sleep_learn_feedback", "cycle_completed", **stats)
    return stats
