"""ai/tokenless-agent/src/memory/session.py
SessionMemory — per-session conversation buffer with token budget and
extractive summarisation of oldest turns.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger("tokenless.memory.session")

# ── Constants ─────────────────────────────────────────────────────────────────
_CHARS_PER_TOKEN: int = 4          # heuristic: 1 token ≈ 4 characters
_SUMMARY_RATIO: float = 0.5        # compress oldest 50% of turns when summarising
_SUMMARY_SENTENCES: int = 3        # max sentences in extractive summary


# ── Turn dataclass ────────────────────────────────────────────────────────────

@dataclass
class Turn:
    """One exchange unit in the conversation."""
    role: str                          # "user", "assistant", "system"
    content: str
    timestamp: float = field(default_factory=time.monotonic)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def char_count(self) -> int:
        return len(self.content)

    def token_estimate(self) -> int:
        return max(1, self.char_count() // _CHARS_PER_TOKEN)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "role": self.role,
            "content": self.content,
            "timestamp": self.timestamp,
            "metadata": self.metadata,
        }


# ── SessionMemory ─────────────────────────────────────────────────────────────

class SessionMemory:
    """
    Manages the rolling conversation buffer for one AI session.

    Responsibilities:
      - Append turns (add_turn)
      - Return a token-budgeted context window (get_context)
      - Provide aggregate token count (token_count)
      - Compress oldest half of history when requested (summarize_old)
      - Reset to empty state (clear)
    """

    def __init__(self, session_id: str = "") -> None:
        self._session_id = session_id
        self._turns: List[Turn] = []

    # ── Core operations ───────────────────────────────────────────────────────

    def add_turn(
        self,
        role: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Turn:
        """Append a turn to memory and return it."""
        t = Turn(role=role, content=content, metadata=metadata or {})
        self._turns.append(t)
        logger.debug(
            "SessionMemory[%s]: +turn role=%s tokens≈%d total=%d",
            self._session_id, role, t.token_estimate(), len(self._turns),
        )
        return t

    def get_context(self, max_tokens: int = 2048) -> List[Dict[str, Any]]:
        """
        Return the most-recent turns that collectively fit within max_tokens.
        Returned in chronological order (oldest first).
        If max_tokens is 0 or negative, return all turns.
        """
        if max_tokens <= 0:
            return [t.to_dict() for t in self._turns]
        window: List[Turn] = []
        budget = max_tokens
        for turn in reversed(self._turns):
            cost = turn.token_estimate()
            if cost > budget:
                break
            budget -= cost
            window.append(turn)
        window.reverse()
        return [t.to_dict() for t in window]

    def token_count(self) -> int:
        """Return total estimated token count across all stored turns."""
        return sum(t.token_estimate() for t in self._turns)

    def clear(self) -> None:
        """Discard all turns."""
        count = len(self._turns)
        self._turns.clear()
        logger.debug("SessionMemory[%s]: cleared %d turns", self._session_id, count)

    # ── Summarisation ─────────────────────────────────────────────────────────

    def summarize_old(self) -> Optional[str]:
        """
        Extractive summarisation: compress the oldest 50% of turns into a
        single synthetic 'system' turn and replace those turns with it.

        Strategy: pick the longest unique sentence from each compressed turn
        (sentence = clause ending with '.', '!', or '?'). Deduplicate by
        prefix matching. Returns the summary string, or None if nothing to do.
        """
        n = len(self._turns)
        if n < 4:
            # Too few turns to bother summarising
            return None
        split = max(1, int(n * _SUMMARY_RATIO))
        old_turns = self._turns[:split]
        keep_turns = self._turns[split:]

        # Extractive: collect sentences from old turns
        sentences: List[str] = []
        for turn in old_turns:
            raw = turn.content.strip()
            if not raw:
                continue
            # Split on sentence-ending punctuation
            import re
            parts = re.split(r'(?<=[.!?])\s+', raw)
            for part in parts:
                part = part.strip()
                if len(part) > 20:
                    sentences.append(part)

        # Deduplicate: remove sentences that are prefixes of later ones
        unique: List[str] = []
        seen_prefixes: set = set()
        for s in sentences:
            key = s[:40].lower()
            if key not in seen_prefixes:
                unique.append(s)
                seen_prefixes.add(key)

        # Take up to _SUMMARY_SENTENCES
        selected = unique[:_SUMMARY_SENTENCES]
        if not selected:
            # Fallback: just note the turn range was summarised
            selected = [f"[Summary: {split} earlier turns compressed]"]

        summary_content = " ".join(selected)
        summary_turn = Turn(
            role="system",
            content=f"[Context summary] {summary_content}",
            metadata={"summarized_turns": split},
        )

        self._turns = [summary_turn] + keep_turns
        logger.info(
            "SessionMemory[%s]: summarized %d turns → 1 summary turn (%d kept)",
            self._session_id, split, len(keep_turns),
        )
        return summary_content

    # ── Diagnostics ───────────────────────────────────────────────────────────

    def turn_count(self) -> int:
        return len(self._turns)

    def session_id(self) -> str:
        return self._session_id

    def __repr__(self) -> str:
        return (
            f"SessionMemory(session_id={self._session_id!r}, "
            f"turns={len(self._turns)}, tokens≈{self.token_count()})"
        )
