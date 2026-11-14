"""Cleanup Lab engine — measure disk usage, then clean only what was confirmed.

Python standard library only. The package lives in ``cleanup-lab/engine`` and is
imported as ``cleanup_lab`` by the console (``console/cleanup_api.py``) and by
``labctl cleanup`` (``cleanup_lab.cli``).

The engine is read-only until a task adds a destructive call, and every
destructive call goes through :mod:`cleanup_lab.safety` (CLN-12) and a confirmed
plan (CLN-13). See ``cleanup-lab/README.md`` for the architecture contract and
the eight safety rules.
"""
from __future__ import annotations

__version__ = "0.1.0"
