"""soul_manager — Never-Delete Memory contract for Tokenless Models.

SPDX-License-Identifier: MIT

Package exports the SoulManager, ConsolidationEngine, and message framing
types. All soul data is AES-256-GCM encrypted at rest. Nothing is ever deleted
— only reorganized by retrieval priority (Event → Episode → Semantic → Archive).
"""
from .soul_manager import SoulManager, SoulManagerError, SoulManagerCryptoError
from .consolidation import ConsolidationEngine, MemoryRecord, compute_activation
from .message_framing import CouncilMessage, COUNCIL_PORTS
from .daemon_client import CouncilDaemonAsyncClient, CouncilDaemonSyncClient
from .aes_gcm_bridge import aes_gcm_encrypt, aes_gcm_decrypt, backend_name, AesGcmUnavailable

__all__ = [
    "SoulManager",
    "SoulManagerError",
    "SoulManagerCryptoError",
    "ConsolidationEngine",
    "MemoryRecord",
    "compute_activation",
    "CouncilMessage",
    "COUNCIL_PORTS",
    "CouncilDaemonAsyncClient",
    "CouncilDaemonSyncClient",
    "aes_gcm_encrypt",
    "aes_gcm_decrypt",
    "backend_name",
    "AesGcmUnavailable",
]
