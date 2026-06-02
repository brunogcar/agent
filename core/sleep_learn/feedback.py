"""
core/sleep_learn/feedback.py
Dynamic Confidence Scoring (The Feedback Loop).
Reads injection logs and agent trace logs to update rule confidence scores.
Zero coupling: Does not import tracer or workflows. Purely log-driven.
"""
from __future__ import annotations
import json
import time
from pathlib import Path
from typing import Dict, List, Any

from core.config import cfg
from core.sleep_learn.config import _SLEEP_LEARN_DB_PATH, SLEEP_LEARN_COLLECTION_NAME
from core.tracer import tracer

INJECTIONS_LOG = cfg.sleep_learn_log_path / "injections.jsonl"
CONFIDENCE_BOOST = 0.1
CONFIDENCE_PENALTY = -0.2
MIN_CONFIDENCE_THRESHOLD = 0.3

def _get_collection():
    """Lazy load ChromaDB to prevent startup crashes."""
    import chromadb
    client = chromadb.PersistentClient(path=str(_SLEEP_LEARN_DB_PATH))
    return client.get_collection(name=SLEEP_LEARN_COLLECTION_NAME)

def update_rule_confidence(rule_id: str, success: bool) -> dict:
    """
    Updates a single rule's confidence score in ChromaDB.
    Returns a status dict.
    """
    try:
        collection = _get_collection()
        existing = collection.get(ids=[rule_id], include=["metadatas"])
        
        if not existing or not existing['ids']:
            return {"status": "skipped", "reason": "Rule not found"}

        meta = existing['metadatas'][0]
        current_conf = float(meta.get("confidence_score", 0.8))
        delta = CONFIDENCE_BOOST if success else CONFIDENCE_PENALTY
        new_conf = max(0.0, min(1.0, current_conf + delta))

        if new_conf < MIN_CONFIDENCE_THRESHOLD:
            collection.delete(ids=[rule_id])
            return {"status": "purged", "old_conf": current_conf, "new_conf": new_conf}
        
        meta["confidence_score"] = new_conf
        meta["last_evaluated_at"] = int(time.time())
        collection.update(ids=[rule_id], metadatas=[meta])
        
        return {"status": "updated", "old_conf": current_conf, "new_conf": new_conf}
    except Exception as e:
        return {"status": "error", "error": str(e)}

def process_feedback() -> dict:
    """
    Matches pending injections with finished traces from the agent logs.
    Updates confidence scores and archives processed injections.
    """
    stats = {"processed": 0, "boosted": 0, "penalized": 0, "purged": 0, "errors": 0}
    
    if not INJECTIONS_LOG.exists():
        return stats

    # 1. Read pending injections
    pending = []
    with open(INJECTIONS_LOG, "r", encoding="utf-8") as f:
        for line in f:
            try:
                pending.append(json.loads(line))
            except json.JSONDecodeError:
                continue

    if not pending:
        return stats

    # 2. Scan agent logs for trace_finish events matching our trace_ids
    target_ids = {p["trace_id"] for p in pending if "trace_id" in p}
    outcomes = {}  # trace_id -> success (bool)
    
    agent_log = cfg.agent_log_path / f"agent_{time.strftime('%Y%m%d')}.jsonl"
    if agent_log.exists():
        with open(agent_log, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    event = json.loads(line)
                    if event.get("event") == "trace_finish" and event.get("trace_id") in target_ids:
                        outcomes[event["trace_id"]] = event.get("success", False)
                except json.JSONDecodeError:
                    continue

    # 3. Process matches and update ChromaDB
    processed_ids = set()
    for inj in pending:
        tid = inj.get("trace_id")
        if tid in outcomes:
            success = outcomes[tid]
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

    # 4. Rewrite injections log without the processed ones (simple compaction)
    if processed_ids:
        remaining = [p for p in pending if p.get("trace_id") not in processed_ids]
        with open(INJECTIONS_LOG, "w", encoding="utf-8") as f:
            for p in remaining:
                f.write(json.dumps(p) + "\n")

    tracer.step("daemon", "sleep_learn_feedback", "cycle_completed", **stats)
    return stats
