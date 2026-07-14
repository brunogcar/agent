"""core/config_backend/execution.py — Initialize autocode, autoresearch, parallel, cache, understand.

[v1.0] Extracted from ``Config.__init__`` as part of the config_backend split.

Env vars read:
    Parallel Execution (Phase 7):
        MAX_CONCURRENT_WORKERS     — default 3
        MAX_CONCURRENT_INFERENCES  — default 2
        WORKER_TIMEOUT             — default 60
        WORKER_MAX_TOKENS          — default 250

    Agent Tool Cache (Bug #19 fix):
        AGENT_CACHE_MAX           — default 100
        AGENT_CACHE_TTL_SECONDS   — default 300

    Understand Workflow (Bug #17 fix):
        UNDERSTAND_BATCH_SIZE     — default 10

    Execution & Autocode:
        SANDBOX_TIMEOUT           — default 30
        AUTOCODE_MAX_RETRIES      — default 3  (range-checked in validators.py)
        AUTOCODE_MAX_FILE_CHARS   — default 6000  (range-checked in validators.py)
        AUTOCODE_DEBUG            — default "0" (truthy: == "1")
        DISABLE_MODEL_WARMUP      — default "0" (truthy: == "1")
        AUTOCODE_GRAPH_TIMEOUT    — default 300  (validated >= max role timeout)

    Autoresearch (v1.0):
        AUTORESEARCH_TIME_BUDGET       — default 300
        AUTORESEARCH_TARGET_FILE       — default "train.py"
        AUTORESEARCH_METRIC_NAME       — default "val_bpb"
        AUTORESEARCH_METRIC_DIRECTION  — default "lower"

    Autocode v1.3: GitHub + Swarm integration flags (all default OFF):
        AUTOCODE_PULL_BEFORE_BRANCH, AUTOCODE_PUSH_ON_COMMIT,
        AUTOCODE_OPEN_PR, AUTOCODE_AUTO_MERGE, AUTOCODE_DEBUG_COMMENT_PR,
        AUTOCODE_SWARM_DEBUG, AUTOCODE_SUBAGENT_DEBUG [v1.1],
        AUTOCODE_SWARM_DEBUG_FALLBACK [v3.1 #48],
        ROUTER_SWARM_FALLBACK [v1.1 #18]
"""

from __future__ import annotations

import os


def _init_execution(cfg) -> None:
    """Initialize parallel execution, cache, understand, autocode, autoresearch."""

    # -- Parallel Execution (Phase 7) --------------------------------------
    cfg.max_concurrent_workers = int(os.getenv("MAX_CONCURRENT_WORKERS", "3"))
    cfg.max_concurrent_inferences = int(os.getenv("MAX_CONCURRENT_INFERENCES", "2"))
    cfg.worker_timeout = int(os.getenv("WORKER_TIMEOUT", "60"))
    cfg.worker_max_tokens = int(os.getenv("WORKER_MAX_TOKENS", "250"))

    # -- Agent Tool Cache (Bug #19 fix) ------------------------------------
    # Previously hardcoded in tools/agent_ops/cache.py. Now configurable.
    cfg.agent_cache_max = int(os.getenv("AGENT_CACHE_MAX", "100"))
    cfg.agent_cache_ttl_seconds = int(os.getenv("AGENT_CACHE_TTL_SECONDS", "300"))

    # -- Understand Workflow (Bug #17 fix) ---------------------------------
    # Batch size for AST parsing in the understand workflow.
    cfg.understand_batch_size = int(os.getenv("UNDERSTAND_BATCH_SIZE", "10"))

    # -- Execution & Autocode ----------------------------------------------
    cfg.sandbox_timeout = int(os.getenv("SANDBOX_TIMEOUT", "30"))
    cfg.autocode_max_retries = int(os.getenv("AUTOCODE_MAX_RETRIES", "3"))
    cfg.autocode_max_file_chars = int(os.getenv("AUTOCODE_MAX_FILE_CHARS", "6000"))
    cfg.autocode_debug = os.getenv("AUTOCODE_DEBUG", "0") == "1"
    cfg.disable_model_warmup = os.getenv("DISABLE_MODEL_WARMUP", "0") == "1"

    # -- Timeouts ------------------------------------------------------------
    # NOTE: planner_timeout, execution_timeout, router_timeout are derived from
    # model_registry above (single source of truth). Do not set them again here.
    cfg.autocode_graph_timeout = int(os.getenv("AUTOCODE_GRAPH_TIMEOUT", "300"))

    # -- Autoresearch (v1.0) ------------------------------------------------
    # Autonomous experiment-driven optimization loop. Each experiment run
    # is time-boxed by autoresearch_time_budget; the LLM proposes changes
    # to autoresearch_target_file and the loop keeps/discards based on
    # autoresearch_metric_name + autoresearch_metric_direction.
    cfg.autoresearch_time_budget = int(os.getenv("AUTORESEARCH_TIME_BUDGET", "300"))
    cfg.autoresearch_target_file = os.getenv("AUTORESEARCH_TARGET_FILE", "train.py")
    cfg.autoresearch_metric_name = os.getenv("AUTORESEARCH_METRIC_NAME", "val_bpb")
    cfg.autoresearch_metric_direction = os.getenv("AUTORESEARCH_METRIC_DIRECTION", "lower")

    # -- Autocode v1.3: GitHub + Swarm integration flags -------------------
    # All default OFF — autocode behaves exactly as v1.2 unless explicitly opted in.
    # TODO(2.0): Review whether these should be per-task rather than global.
    cfg.autocode_pull_before_branch = os.getenv("AUTOCODE_PULL_BEFORE_BRANCH", "0") == "1"
    cfg.autocode_push_on_commit = os.getenv("AUTOCODE_PUSH_ON_COMMIT", "0") == "1"
    cfg.autocode_open_pr = os.getenv("AUTOCODE_OPEN_PR", "0") == "1"
    cfg.autocode_auto_merge = os.getenv("AUTOCODE_AUTO_MERGE", "0") == "1"
    cfg.autocode_debug_comment_pr = os.getenv("AUTOCODE_DEBUG_COMMENT_PR", "0") == "1"
    cfg.autocode_swarm_debug = os.getenv("AUTOCODE_SWARM_DEBUG", "0") == "1"
    cfg.autocode_subagent_debug = os.getenv("AUTOCODE_SUBAGENT_DEBUG", "0") == "1"  # [v1.1] subagent dispatch
    cfg.autocode_swarm_debug_fallback = os.getenv("AUTOCODE_SWARM_DEBUG_FALLBACK", "0") == "1"  # [v3.1 #48] swarm fallback when debug exhausted
    cfg.router_swarm_fallback = os.getenv("ROUTER_SWARM_FALLBACK", "0") == "1"  # [v1.1 #18] swarm vote for low-confidence routing
