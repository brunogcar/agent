# core/__init__.py
"""MCP Agent core package.

NOTE: This module intentionally does NOT auto-start background daemons.
All daemon startup is coordinated in server.py to avoid import side-effects
and ensure proper initialization order (config → ChromaDB warmup → daemons).
"""
