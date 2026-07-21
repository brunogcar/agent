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
        UNDERSTAND_BATCH_SIZE     — default 10  (v1.4.1: unused in Phase 1;
                                                kept for backward compat)
        UNDERSTAND_EMBED_BATCH_SIZE — default 100  [v1.4.1 P2-8] Phase-2
                                                embedding batch size
        UNDERSTAND_SKIP_DIRS      — default ""  [v1.7] comma-separated extra
                                                dirs to skip during discovery
                                                (merged with _DEFAULT_SKIP_DIRS)
        UNDERSTAND_TIMEOUT_SECONDS — default 600  [v1.7] understand dispatch
                                                timeout (was hardcoded in base.py)

    Execution & Autocode:
        SANDBOX_TIMEOUT           — default 30
        AUTOCODE_MAX_RETRIES      — default 3  (range-checked in validators.py)
        AUTOCODE_MAX_FILE_CHARS   — default 6000  (range-checked in validators.py)
        AUTOCODE_DEBUG            — default "0" (truthy: == "1")
        DISABLE_MODEL_WARMUP      — default "0" (truthy: == "1")
        AUTOCODE_GRAPH_TIMEOUT    — default 300  (validated >= max role timeout)
        AUTOCODE_HITL_ENABLED     — default "0"  (truthy: == "1") [v3.4 #38]

    Autoresearch (v1.0):
        AUTORESEARCH_TIME_BUDGET       — default 300
        AUTORESEARCH_TARGET_FILE       — default "train.py"
        AUTORESEARCH_METRIC_NAME       — default "val_bpb"
        AUTORESEARCH_METRIC_DIRECTION  — default "lower"

    Autoresearch v1.4 loop control:
        AUTORESEARCH_MAX_ITERATIONS        — default 0 (0=unlimited)
        AUTORESEARCH_CONVERGENCE_WINDOW    — default 10 (N consecutive non-improvements → stop)
        AUTORESEARCH_CONVERGENCE_EPSILON   — default 0.001 (metric plateau threshold)

    Autoresearch v1.5 reflect + cross-run learning:
        AUTORESEARCH_REFLECT_INTERVAL      — default 5 (reflect every N iterations; 0=disabled)

    Autoresearch v1.6 parallel experiments:
        AUTORESEARCH_PARALLEL_COUNT        — default 1 (N parallel proposals + subprocesses per iteration; 1 = v1.5 single-experiment mode)

    Autoresearch v1.9 hardening:
        AUTORESEARCH_RECURSION_LIMIT       — default 1000 (LangGraph recursion_limit for the autoresearch loop; raise for very long overnight runs)
        AUTORESEARCH_LOG_DIR_MAX_MB        — default 1024 (1GB cap on logs/autoresearch/ — when exceeded, new log writes are skipped + a tracer warning is emitted; 0 = no cap)

    Autocode v1.3: GitHub + Swarm integration flags (all default OFF):
        AUTOCODE_PULL_BEFORE_BRANCH, AUTOCODE_PUSH_ON_COMMIT,
        AUTOCODE_OPEN_PR, AUTOCODE_AUTO_MERGE, AUTOCODE_DEBUG_COMMENT_PR,
        AUTOCODE_SWARM_DEBUG, AUTOCODE_SUBAGENT_DEBUG [v1.1],
        AUTOCODE_SWARM_DEBUG_FALLBACK [v3.1 #48],
        AUTOCODE_PARALLEL_SUBAGENT_DEBUG [v3.5 F1],
        AUTOCODE_PARALLEL_SUBAGENT_COUNT [v3.5 F1],
        ROUTER_SWARM_FALLBACK [v1.1 #18]
"""

from __future__ import annotations

import os


def _init_execution(cfg) -> None:
    """Initialize parallel execution, cache, understand, autocode, autoresearch.

    Also initializes the agent timezone (v1.0) — the single source of truth
    for tz-aware datetime operations across the agent (core/time_utils.py,
    tools/notify_ops/, tools/schedule_ops/). Empty string means "use the
    system local timezone" (resolved lazily by core.time_utils.get_timezone()).
    """

    # -- Timezone (v1.0) ---------------------------------------------------
    # Used by core/time_utils.py. Examples: "America/Sao_Paulo",
    # "Europe/London", "UTC". "" (default) = system local timezone.
    cfg.timezone = os.getenv("AGENT_TZ", "").strip()

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
    # [v1.4.1 P2-14] Phase-1 file-parsing no longer uses this knob (the outer
    # batch loop was removed — each file is processed one at a time). Kept
    # for backward compat + in case a future refactor re-introduces batching.
    cfg.understand_batch_size = int(os.getenv("UNDERSTAND_BATCH_SIZE", "10"))
    # [v1.4.1 P2-8] Embedding batch size — Phase-2 batched embedding groups
    # `understand_embed_batch_size` definitions per HTTP call to LM Studio.
    # Default 100 (was hardcoded in parse_and_store._batch_embed_and_store).
    # Raise for fewer HTTP calls (faster on stable connections); lower for
    # smaller request payloads (helps on flaky networks / small LLM context).
    cfg.understand_embed_batch_size = int(os.getenv("UNDERSTAND_EMBED_BATCH_SIZE", "100"))

    # [v1.7] Configurable extra skip-dirs. Comma-separated list merged with
    # ProjectManager._DEFAULT_SKIP_DIRS at runtime (via get_skip_dirs()).
    # Lets operators skip project-specific dirs (e.g. "vendor,third_party")
    # without modifying the canonical default set.
    cfg.understand_skip_dirs = os.getenv("UNDERSTAND_SKIP_DIRS", "")

    # [v1.7] Configurable understand timeout (was hardcoded 600 in base.py).
    # Default 600s = 10min (same as v1.6). Operators with large codebases can
    # raise this; small projects can lower it to fail faster.
    cfg.understand_timeout_seconds = int(os.getenv("UNDERSTAND_TIMEOUT_SECONDS", "600"))

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
    cfg.autocode_adaptive_timeout = os.getenv("AUTOCODE_ADAPTIVE_TIMEOUT", "0") == "1"  # [v1.2 #40] opt-in adaptive timeout by task_type
    cfg.autocode_hitl_enabled = os.getenv("AUTOCODE_HITL_ENABLED", "0") == "1"  # [v3.4 #38] Human-in-the-Loop approval gate (default OFF)
    cfg.autocode_architecture_question_threshold = int(os.getenv("AUTOCODE_ARCHITECTURE_QUESTION_THRESHOLD", "3"))  # [v3.3 F4] configurable threshold

    # -- Autoresearch (v1.0) ------------------------------------------------
    # Autonomous experiment-driven optimization loop. Each experiment run
    # is time-boxed by autoresearch_time_budget; the LLM proposes changes
    # to autoresearch_target_file and the loop keeps/discards based on
    # autoresearch_metric_name + autoresearch_metric_direction.
    cfg.autoresearch_time_budget = int(os.getenv("AUTORESEARCH_TIME_BUDGET", "300"))
    cfg.autoresearch_target_file = os.getenv("AUTORESEARCH_TARGET_FILE", "train.py")
    cfg.autoresearch_metric_name = os.getenv("AUTORESEARCH_METRIC_NAME", "val_bpb")
    cfg.autoresearch_metric_direction = os.getenv("AUTORESEARCH_METRIC_DIRECTION", "lower")
    # [v1.4] Loop-control flags — stop the experiment loop automatically.
    # max_iterations=0 (default) = unlimited (legacy v1.3 behavior).
    cfg.autoresearch_max_iterations = int(os.getenv("AUTORESEARCH_MAX_ITERATIONS", "0"))  # 0=unlimited
    cfg.autoresearch_convergence_window = int(os.getenv("AUTORESEARCH_CONVERGENCE_WINDOW", "10"))  # stop after N consecutive non-improvements
    cfg.autoresearch_convergence_epsilon = float(os.getenv("AUTORESEARCH_CONVERGENCE_EPSILON", "0.001"))  # metric plateau threshold
    # [v1.5 N1] Reflect node — every N iterations the planner LLM reflects on
    # the full experiment history and writes a strategy summary that gets
    # folded into the next proposal prompt. 0 = disabled (legacy v1.4 behavior).
    cfg.autoresearch_reflect_interval = int(os.getenv("AUTORESEARCH_REFLECT_INTERVAL", "5"))  # reflect every N iterations (0=disabled)
    # [v1.6] Parallel experiments — when > 1, each iteration proposes N
    # experiments in parallel (ThreadPoolExecutor of N _call_planner calls),
    # writes them to {project_root}/.autoresearch/parallel/{i}/{target_file},
    # runs N subprocesses in parallel, evaluates N metrics, and decide picks
    # the best. 1 (default) preserves v1.5 single-experiment behavior —
    # nodes branch on this and only the parallel path uses the plural state
    # fields (current_experiments / experiment_outputs / current_metrics).
    cfg.autoresearch_parallel_count = int(os.getenv("AUTORESEARCH_PARALLEL_COUNT", "1"))  # N parallel experiments per iteration (1 = v1.5 mode)
    # [v1.9] Configurable recursion_limit (minimax Risk #2) — was hardcoded
    # to 1000 in workflows/base.py. Operators running overnight with fast
    # experiments may need more (each iteration = 8 nodes; 1000 → ~125 iter).
    # 0 means "use the LangGraph default" (25 — too low for autoresearch).
    cfg.autoresearch_recursion_limit = int(os.getenv("AUTORESEARCH_RECURSION_LIMIT", "1000"))  # LangGraph recursion_limit
    # [v1.9] Log rotation cap (minimax Risk #1) — when the total size of
    # logs/autoresearch/ exceeds this many MB, new log writes are SKIPPED +
    # a tracer.warning is emitted. Prevents unbounded disk usage on long
    # overnight runs (parallel_count=4 × 5 iter/min × 12h = ~14k files).
    # 0 = no cap (write all logs — same as v1.8 behavior).
    cfg.autoresearch_log_dir_max_mb = int(os.getenv("AUTORESEARCH_LOG_DIR_MAX_MB", "1024"))  # 1GB cap on logs/autoresearch/ (0 = no cap)

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
    cfg.autocode_parallel_subagent_debug = os.getenv("AUTOCODE_PARALLEL_SUBAGENT_DEBUG", "0") == "1"  # [v3.5 F1] parallel subagent debug
    cfg.autocode_parallel_subagent_count = int(os.getenv("AUTOCODE_PARALLEL_SUBAGENT_COUNT", "3"))  # [v3.5 F1] number of parallel hypotheses
    cfg.router_swarm_fallback = os.getenv("ROUTER_SWARM_FALLBACK", "0") == "1"  # [v1.1 #18] swarm vote for low-confidence routing
