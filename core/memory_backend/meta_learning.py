"""
core/meta_learning.py — "Sleep & Learn" Background Daemon.
Distills recent episodic memories into procedural rules when the agent is idle.
"""
from __future__ import annotations

import time
import json
import logging
import os
from pathlib import Path
from datetime import datetime, timedelta

from core.config import cfg
from core.memory import memory
from core.llm import llm
from core.runtime.activity_tracker import tracker
from core.memory_backend.scoring import normalize_and_hash

logger = logging.getLogger(__name__)

MIN_INTERVAL_SECONDS = 24 * 3600 
IDLE_THRESHOLD_SECONDS = 2 * 3600
LOCK_FILE = cfg.workspace_root / ".meta_learn.lock"

DISTILL_PROMPT = """You are the Meta-Learning Subsystem. Review the following successful episodic memories from the last 24 hours.
Extract a single, highly specific, technical procedural rule that prevents future mistakes or optimizes workflows.
Do not extract generic advice (e.g., "check logs", "write clean code").
If no reusable technical insight exists, return has_insight: false.

Output Format (Strict JSON):
{
  "has_insight": true,
  "rule": "When [specific condition], do [specific action] because [reason].",
  "confidence": 0.0-1.0
}

Episodic Memories:
{memories}
"""

# Technical markers to reject generic platitudes
SPECIFICITY_MARKERS = [
    "import", "def ", "class ", "df.", "pd.", "np.", ".py", "Error", 
    "Exception", "api", "http", "json", "sql", "git", "docker", "pip",
    "chromadb", "langgraph", "mcp", "traceback", "assert", "pytest",
    # Added to catch general technical rules (chunking, retries, etc.)
    "chunk", "row", "limit", "timeout", "retry", "backoff", "cache", 
    "429", "500", "bug", "fix", "crash", "loop", "memory", "vram"
]

class MetaLearner:
    def __init__(self):
        self.last_run = 0.0

    def run_forever(self):
        logger.info("[MetaLearner] Daemon started.")
        while True:
            try:
                time.sleep(1800) # Check every 30 mins
                self._try_distill()
            except Exception as e:
                logger.error(f"[MetaLearner] Loop error: {e}")
                time.sleep(300)

    def _check_lockfile(self) -> bool:
        if LOCK_FILE.exists():
            try:
                mtime = LOCK_FILE.stat().st_mtime
                if (time.time() - mtime) < MIN_INTERVAL_SECONDS:
                    return False
            except Exception:
                pass
        return True

    def _try_distill(self):
        if (time.time() - self.last_run) < MIN_INTERVAL_SECONDS:
            return
        if not self._check_lockfile():
            return
        if not tracker.try_acquire_background_slot(IDLE_THRESHOLD_SECONDS):
            return

        try:
            LOCK_FILE.write_text(str(os.getpid()))
        except Exception:
            tracker.release_background_slot()
            return

        logger.info("[MetaLearner] Agent idle. Starting distillation...")
        
        try:
            self._execute_pipeline()
            self.last_run = time.time()
        except Exception as e:
            logger.error(f"[MetaLearner] Pipeline failed: {e}")
        finally:
            tracker.release_background_slot()
            try:
                if LOCK_FILE.exists():
                    LOCK_FILE.unlink()
            except Exception:
                pass

    def _execute_pipeline(self):
        cutoff = datetime.now() - timedelta(days=1)
        try:
            col = memory.store._col("episodic")
            raw = col.get(include=["documents", "metadatas"], limit=50)
            if not raw or not raw["ids"]:
                return
                
            episodes = []
            for i, doc in enumerate(raw["documents"]):
                meta = raw["metadatas"][i] or {}
                ts = meta.get("timestamp", 0)
                outcome = meta.get("outcome", "").lower()
                if ts > cutoff.timestamp() and (outcome == "success" or meta.get("importance", 0) >= 7):
                    episodes.append(doc)
                    
            if not episodes:
                return

            memory_text = "\n\n---\n\n".join(episodes[:10])
            prompt = DISTILL_PROMPT.format(memories=memory_text)
            
            if tracker.active_inferences > 1:
                logger.info("[MetaLearner] Activity detected, aborting LLM call.")
                return

            resp = llm.complete(
                role="executor",
                system="You are a strict procedural knowledge extractor.",
                user=prompt,
                json_mode=True,
                timeout=60
            )
            
            if not resp.ok or not resp.text:
                return

            self._process_response(resp.text)
            
        except Exception as e:
            logger.error(f"[MetaLearner] Execution error: {e}")

    def _process_response(self, text: str):
        try:
            start = text.find("{")
            end = text.rfind("}") + 1
            if start == -1 or end == 0:
                return
            data = json.loads(text[start:end])
            
            if not data.get("has_insight") or data.get("confidence", 0) < 0.75:
                return
                
            rule = data.get("rule", "").strip()
            if not rule:
                return

            rule_lower = rule.lower()
            if not any(marker in rule_lower for marker in SPECIFICITY_MARKERS):
                logger.debug(f"[MetaLearner] Rejected generic rule: {rule}")
                return

            logger.info(f"[MetaLearner] Extracted rule: {rule}")
            
            # Wider Semantic Dedup
            existing = memory.recall(query=rule, collections=["procedural"], top_k=3, min_score=0.0)
            
            for ex in existing:
                if normalize_and_hash(ex["text"]) == normalize_and_hash(rule):
                    logger.info("[MetaLearner] Exact normalized match found. Reinforcing.")
                    memory.store(text=ex["text"], collection="procedural", tags="meta-learned")
                    return
                    
                if ex.get("distance", 1.0) < 0.15:
                    logger.info(f"[MetaLearner] Near-match found (dist={ex['distance']}). Reinforcing existing.")
                    memory.store(text=ex["text"], collection="procedural", tags="meta-learned")
                    return

            memory.store(
                text=rule,
                collection="procedural",
                tags="meta-learned,auto-distilled",
                importance=8
            )
        except json.JSONDecodeError:
            pass
        except Exception as e:
            logger.error(f"[MetaLearner] Parse/Store error: {e}")

learner = MetaLearner()