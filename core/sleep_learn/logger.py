"""
core/sleep_learn/logger.py
Dedicated JSONL logger for the Sleep & Learn daemon.
Writes to logs/sleep_learn/sleep_learn_YYYYMMDD.jsonl
"""
import json
import threading
from datetime import datetime, timezone
from core.config import cfg

_lock = threading.Lock()

def log_event(event_data: dict) -> None:
    """Appends a structured event to the daily sleep_learn JSONL log."""
    log_dir = cfg.sleep_learn_log_path
    log_dir.mkdir(parents=True, exist_ok=True)
    
    log_file = log_dir / f"sleep_learn_{datetime.now().strftime('%Y%m%d')}.jsonl"
    
    if "_timestamp_utc" not in event_data:
        event_data["_timestamp_utc"] = datetime.now(timezone.utc).isoformat()
        
    with _lock:
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(event_data, ensure_ascii=False) + "\n")
