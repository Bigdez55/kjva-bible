"""heptagon/attestation.py — Identity-continuity attestation (neutral).

The generalizable, non-redundant core absorbed from the consuming-project ROOT
`heptagon/attestation.py` (ADR-0002 §3 Cognitive Control / provenance), neutralized: NO
named-member/Council content — identity is whatever state hash the runtime supplies.

The capability the agent-side lacked: a continuity HASH CHAIN. The agent already has
point-in-time snapshot hashes (policy/model) in the determinant record, but nothing that
attests identity *continuity* across turns/restarts. This maintains a chain where each link
is ``SHA-256(prev_head + current_state_hash)`` — so the sequence of states is tamper-evident
and replay-checkable (it advances the lineage, it does not gate or govern).
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass


@dataclass(frozen=True)
class Attestation:
    """One link in the continuity chain."""
    head: str            # sha256 head after this attestation
    prev: str            # previous head ("" for the genesis link)
    chain_length: int    # number of links including this one
    state_hash: str      # the state hash that was attested


class ContinuityAttestation:
    """A tamper-evident SHA-256 chain attesting identity continuity. Neutral: the caller
    supplies each state hash; this class owns only the chaining, never the identity content."""

    def __init__(self) -> None:
        self._head: str = ""
        self._length: int = 0

    def attest(self, state_hash: str) -> Attestation:
        """Advance the chain with ``state_hash`` and return the new link."""
        prev = self._head
        link = "sha256:" + hashlib.sha256((prev + "|" + (state_hash or "")).encode()).hexdigest()
        self._head = link
        self._length += 1
        return Attestation(head=link, prev=prev, chain_length=self._length, state_hash=state_hash or "")

    @property
    def head(self) -> str:
        return self._head

    @property
    def chain_length(self) -> int:
        return self._length

    def verify(self, prev_head: str, state_hash: str, claimed_head: str) -> bool:
        """Check that ``claimed_head`` is the correct link for (prev_head, state_hash)."""
        expect = "sha256:" + hashlib.sha256((prev_head + "|" + (state_hash or "")).encode()).hexdigest()
        return expect == claimed_head
