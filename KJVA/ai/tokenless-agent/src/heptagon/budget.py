"""ai/tokenless-agent/src/heptagon/budget.py
BudgetGovernor — Heptagon Layer 6 (Calibration) 3-6-9 step and token budget
enforcement for all Tokenless AI route types.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

logger = logging.getLogger("tokenless.heptagon.budget")

# ── Budget profiles ───────────────────────────────────────────────────────────
# 3-6-9 system: three tiers of computational budget tied to route complexity.

BUDGET_PROFILES: Dict[str, Dict[str, int]] = {
    "direct": {
        "max_steps":  3,
        "max_tokens": 512,
    },
    "researched": {
        "max_steps":  6,
        "max_tokens": 2048,
    },
    "full": {
        "max_steps":  9,
        "max_tokens": 4096,
    },
}

# Profile upgrade order (parsimony: prefer cheaper tier)
_UPGRADE_ORDER: list = ["direct", "researched", "full"]

# ── BudgetState ───────────────────────────────────────────────────────────────

@dataclass
class BudgetState:
    """Runtime consumption counters for one agent request."""
    profile: str
    max_steps: int
    max_tokens: int
    steps_used: int = 0
    tokens_used: int = 0
    upgrades: int = 0

    def steps_remaining(self) -> int:
        return max(0, self.max_steps - self.steps_used)

    def tokens_remaining(self) -> int:
        return max(0, self.max_tokens - self.tokens_used)

    def steps_exceeded(self) -> bool:
        return self.steps_used >= self.max_steps

    def tokens_exceeded(self) -> bool:
        return self.tokens_used >= self.max_tokens

    def exceeded(self) -> bool:
        return self.steps_exceeded() or self.tokens_exceeded()

    def utilisation(self) -> Dict[str, float]:
        return {
            "steps": self.steps_used / self.max_steps if self.max_steps else 0.0,
            "tokens": self.tokens_used / self.max_tokens if self.max_tokens else 0.0,
        }

    def to_dict(self) -> Dict[str, Any]:
        return {
            "profile": self.profile,
            "max_steps": self.max_steps,
            "max_tokens": self.max_tokens,
            "steps_used": self.steps_used,
            "tokens_used": self.tokens_used,
            "steps_remaining": self.steps_remaining(),
            "tokens_remaining": self.tokens_remaining(),
            "exceeded": self.exceeded(),
            "upgrades": self.upgrades,
        }


# ── BudgetGovernor ────────────────────────────────────────────────────────────

class BudgetGovernor:
    """
    Enforces the 3-6-9 budget system for one agent request lifecycle.

    Usage
    -----
        gov = BudgetGovernor(profile="direct")
        gov.check_step()      # raises BudgetExceededError if at limit
        gov.check_tokens(50)  # raises BudgetExceededError if would exceed
        gov.upgrade()         # promote to next tier if needed

    Profile tier order: direct (3/512) -> researched (6/2048) -> full (9/4096).
    Parsimony: NEVER upgrade unless explicitly called.
    """

    class BudgetExceededError(RuntimeError):
        """Raised when a step or token budget is exceeded."""

    def __init__(self, profile: str = "direct") -> None:
        if profile not in BUDGET_PROFILES:
            raise ValueError(
                f"Unknown budget profile '{profile}'. "
                f"Valid options: {list(BUDGET_PROFILES.keys())}"
            )
        cfg = BUDGET_PROFILES[profile]
        self._state = BudgetState(
            profile=profile,
            max_steps=cfg["max_steps"],
            max_tokens=cfg["max_tokens"],
        )
        logger.debug(
            "BudgetGovernor: profile=%s max_steps=%d max_tokens=%d",
            profile, cfg["max_steps"], cfg["max_tokens"],
        )

    # ── Step governance ───────────────────────────────────────────────────────

    def check_step(self) -> None:
        """
        Consume one step from the budget.

        Raises
        ------
        BudgetExceededError if steps_used would exceed max_steps.
        """
        if self._state.steps_used >= self._state.max_steps:
            raise self.BudgetExceededError(
                f"Step budget exhausted: {self._state.steps_used}/{self._state.max_steps} "
                f"steps used (profile={self._state.profile})"
            )
        self._state.steps_used += 1
        logger.debug(
            "BudgetGovernor: step %d/%d (profile=%s)",
            self._state.steps_used, self._state.max_steps, self._state.profile,
        )

    # ── Token governance ──────────────────────────────────────────────────────

    def check_tokens(self, count: int) -> None:
        """
        Consume `count` tokens from the budget.

        Parameters
        ----------
        count : number of tokens to consume (must be > 0)

        Raises
        ------
        BudgetExceededError if tokens_used + count would exceed max_tokens.
        ValueError if count is not positive.
        """
        if count <= 0:
            raise ValueError(f"Token count must be positive, got {count}")
        if self._state.tokens_used + count > self._state.max_tokens:
            raise self.BudgetExceededError(
                f"Token budget would be exceeded: "
                f"{self._state.tokens_used + count}/{self._state.max_tokens} tokens "
                f"(profile={self._state.profile})"
            )
        self._state.tokens_used += count
        logger.debug(
            "BudgetGovernor: tokens %d/%d (+%d) (profile=%s)",
            self._state.tokens_used, self._state.max_tokens, count, self._state.profile,
        )

    # ── Remaining ─────────────────────────────────────────────────────────────

    def remaining(self) -> Dict[str, int]:
        """Return remaining steps and tokens."""
        return {
            "steps": self._state.steps_remaining(),
            "tokens": self._state.tokens_remaining(),
        }

    def exceeded(self) -> bool:
        """Return True if any budget limit has been reached or exceeded."""
        return self._state.exceeded()

    # ── Reset ─────────────────────────────────────────────────────────────────

    def reset(self, profile: Optional[str] = None) -> None:
        """
        Reset counters, optionally switching to a different profile.
        Upgrade count is preserved across resets.
        """
        upgrades = self._state.upgrades
        target = profile or self._state.profile
        if target not in BUDGET_PROFILES:
            raise ValueError(f"Unknown budget profile '{target}'")
        cfg = BUDGET_PROFILES[target]
        self._state = BudgetState(
            profile=target,
            max_steps=cfg["max_steps"],
            max_tokens=cfg["max_tokens"],
            upgrades=upgrades,
        )
        logger.debug("BudgetGovernor: reset to profile=%s", target)

    # ── Upgrade ───────────────────────────────────────────────────────────────

    def upgrade(self) -> bool:
        """
        Promote to the next budget tier (direct -> researched -> full).
        Current consumption is preserved and limits are extended.

        Returns True if an upgrade occurred, False if already at maximum tier.
        """
        current_idx = _UPGRADE_ORDER.index(self._state.profile)
        next_idx = current_idx + 1
        if next_idx >= len(_UPGRADE_ORDER):
            logger.warning(
                "BudgetGovernor: already at maximum tier (%s), cannot upgrade",
                self._state.profile,
            )
            return False
        next_profile = _UPGRADE_ORDER[next_idx]
        cfg = BUDGET_PROFILES[next_profile]
        old_profile = self._state.profile
        self._state.profile = next_profile
        self._state.max_steps = cfg["max_steps"]
        self._state.max_tokens = cfg["max_tokens"]
        self._state.upgrades += 1
        logger.info(
            "BudgetGovernor: upgraded %s -> %s (steps=%d tokens=%d)",
            old_profile, next_profile, cfg["max_steps"], cfg["max_tokens"],
        )
        return True

    # ── Diagnostics ───────────────────────────────────────────────────────────

    def state(self) -> BudgetState:
        """Return the current BudgetState snapshot."""
        return self._state

    def profile(self) -> str:
        return self._state.profile

    def max_steps(self) -> int:
        return self._state.max_steps

    def max_tokens(self) -> int:
        return self._state.max_tokens

    def steps_used(self) -> int:
        return self._state.steps_used

    def tokens_used(self) -> int:
        return self._state.tokens_used

    def utilisation(self) -> Dict[str, float]:
        return self._state.utilisation()

    def summary(self) -> str:
        s = self._state
        return (
            f"BudgetGovernor[{s.profile}]: "
            f"steps {s.steps_used}/{s.max_steps} "
            f"tokens {s.tokens_used}/{s.max_tokens} "
            f"upgrades={s.upgrades}"
        )

    def __repr__(self) -> str:
        return self.summary()

    @staticmethod
    def all_profiles() -> Dict[str, Dict[str, int]]:
        return dict(BUDGET_PROFILES)
