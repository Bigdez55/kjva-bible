"""soul_manager — Never-Delete Memory contract for Tokenless Models.

SPDX-License-Identifier: MIT

Package exports the SoulManager, ConsolidationEngine, and message framing
types. All soul data is AES-256-GCM encrypted at rest. Nothing is ever deleted
— only reorganized by retrieval priority (Event → Episode → Semantic → Archive).
"""
from .soul_manager import SoulManager, SoulManagerError, SoulManagerCryptoError
from .consolidation import ConsolidationEngine, MemoryRecord, compute_activation
from .message_framing import CognitiveBusMessage, COUNCIL_PORTS
from .aes_gcm_bridge import aes_gcm_encrypt, aes_gcm_decrypt, backend_name, AesGcmUnavailable
from .memory_types import ContinuityState, RecallReadiness, MemoryHealth

__all__ = [
    "SoulManager",
    "SoulManagerError",
    "SoulManagerCryptoError",
    "ConsolidationEngine",
    "MemoryRecord",
    "compute_activation",
    "CognitiveBusMessage",
    "COUNCIL_PORTS",
    "aes_gcm_encrypt",
    "aes_gcm_decrypt",
    "backend_name",
    "AesGcmUnavailable",
    # ADR-0002 §4.7 Edge G types
    "ContinuityState",
    "RecallReadiness",
    "MemoryHealth",
]
