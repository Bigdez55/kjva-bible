# ai/tokenless-agent/src/materialization/__init__.py
"""Materialization plane package (ADR-0001 §11).

Records when abstract cognition becomes runtime state. Re-exports the §11.2 contract
so callers can simply ``import materialization`` (src is placed on sys.path by the
agent/test harness, matching the `memory.*` / `heptagon.*` import convention).
"""
from __future__ import annotations

from .materialization_record import MaterializationRecord

__all__ = ["MaterializationRecord"]
