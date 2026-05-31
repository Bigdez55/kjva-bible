"""Compatibility facade for the active KJVA inference backend.

Serving inference is owned by ``KJVA/ai/xmind``.  This module exists only so
legacy backend imports keep working; it must not load MLX or execute model
policy directly.
"""
from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from KJVA.ai.xmind.kjva_byte_backend import (  # noqa: E402
    BYTE_OFFSET,
    BOS_ID,
    EOS_ID,
    PAD_ID,
    XmindKJVAInference,
    get_engine,
)

KJVAInference = XmindKJVAInference

__all__ = [
    "BYTE_OFFSET",
    "BOS_ID",
    "EOS_ID",
    "PAD_ID",
    "KJVAInference",
    "XmindKJVAInference",
    "get_engine",
]

