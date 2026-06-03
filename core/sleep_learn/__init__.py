"""
core/sleep_learn - Meta-Learning Daemon.
Public API exports for the sleep_learn subsystem.
"""
from .daemon import start_background_daemon
from .sweeper import sweep_recent_observations
from .injector import inject_rules_into_prompt, get_relevant_rules
