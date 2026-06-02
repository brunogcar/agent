"""
core/sleep_learn - Meta-Learning Daemon (Phase 1: Passive Observation)
"""
from .daemon import run_daemon_cycle
from .sweeper import sweep_recent_observations

from .injector import inject_rules_into_prompt, get_relevant_rules
