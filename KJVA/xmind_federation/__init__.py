"""
xmind_federation — Per-member XMIND client for the federated deliberation pattern.

Each federation member is a separate process. Each process imports XMindClient
and creates ONE instance, bound to its own member name + persona. The client
opens libxmind-core.{so,dylib} via ctypes and runs inference in-process.

Federation guarantees:
  • Each process has its own XMindClient → own model_t → own KV cache.
  • Kernel page-cache deduplication shares the mmap'd weights file across
    all member processes (1 physical copy, N virtual mappings).
  • Each member's KV cache, sampler state, and persona context are private.

Identity neutrality:
  The template defines NO specific member names. A consuming project supplies:
    1. `xmind_federation/personas/<member-name>.txt`   — the member's persona prompt
    2. Set env `MEMBER_NAME=<member-name>`   — at daemon startup

The XMindClient reads MEMBER_NAME from the environment (or accepts it
explicitly) and loads `xmind_federation/personas/<MEMBER_NAME>.txt`. If no persona
file exists, a generic placeholder is used and a warning is logged.

Graceful degradation: if libxmind-core or the model file is unavailable,
the client returns deterministic stub responses so daemon orchestration
still works during pre-acquisition / pre-training development.
"""
from .client import XMindClient, DeliberationResult, deliberate_as

__all__ = ["XMindClient", "DeliberationResult", "deliberate_as"]
