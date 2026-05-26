"""Citadel/governance/rationale_card.py — Council Rationale Card

SPDX-License-Identifier: MIT

Every important user action gets a CouncilRationaleCard so the
system can explain what happened and why.

The interface presents. The Council decides. The card explains.

Source: Tokenless rationale-card interface contract
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class CouncilRationaleCard:
    """User-facing explanation of a governance decision.

    Generated from the underlying DecisionEnvelope so the system
    can explain:
      - what happened
      - who approved it
      - who blocked it
      - why it happened
      - what policy applied
      - what risk was considered
      - what can be changed

    This is how authority becomes visible and trustworthy.
    """
    # What happened
    action_summary: str = ""
    action_timestamp: float = field(default_factory=time.time)

    # Who decided
    approved_by: List[str] = field(default_factory=list)
    blocked_by: List[str] = field(default_factory=list)
    advisory_from: List[str] = field(default_factory=list)

    # Why
    primary_reason: str = ""
    policy_applied: str = ""
    covenant_rule: str = ""          # COV-XXX if applicable
    scripture_basis: str = ""        # Scripture reference if covenant applies

    # Risk
    risk_level: str = "LOW"          # LOW, MEDIUM, HIGH, CRITICAL
    risk_summary: str = ""

    # Economics
    resource_cost: str = ""
    value_assessment: str = ""

    # What can change
    changeable_factors: List[str] = field(default_factory=list)
    appeal_path: str = ""            # How to appeal this decision

    # Provenance
    envelope_id: str = ""            # Link to the full DecisionEnvelope
    degraded_mode: bool = False      # Was the system in degraded mode?
    vacant_seats: List[str] = field(default_factory=list)

    def render_text(self) -> str:
        """Render as human-readable text for the Tokenless interface."""
        lines = []
        lines.append("=== Council Decision ===")
        lines.append(f"Action: {self.action_summary}")

        if self.approved_by:
            lines.append(f"Approved by: {', '.join(self.approved_by)}")
        if self.blocked_by:
            lines.append(f"Blocked by: {', '.join(self.blocked_by)}")
        if self.advisory_from:
            lines.append(f"Advisory from: {', '.join(self.advisory_from)}")

        lines.append(f"Reason: {self.primary_reason}")

        if self.policy_applied:
            lines.append(f"Policy: {self.policy_applied}")
        if self.covenant_rule:
            lines.append(f"Covenant: {self.covenant_rule}")
        if self.scripture_basis:
            lines.append(f"Scripture: {self.scripture_basis}")

        if self.risk_summary:
            lines.append(f"Risk ({self.risk_level}): {self.risk_summary}")

        if self.resource_cost:
            lines.append(f"Cost: {self.resource_cost}")

        if self.changeable_factors:
            lines.append(f"Can change: {', '.join(self.changeable_factors)}")
        if self.appeal_path:
            lines.append(f"Appeal: {self.appeal_path}")

        if self.degraded_mode:
            lines.append(f"WARNING: System in degraded mode. Vacant seats: {', '.join(self.vacant_seats)}")

        return "\n".join(lines)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "action_summary": self.action_summary,
            "action_timestamp": self.action_timestamp,
            "approved_by": self.approved_by,
            "blocked_by": self.blocked_by,
            "primary_reason": self.primary_reason,
            "policy_applied": self.policy_applied,
            "covenant_rule": self.covenant_rule,
            "scripture_basis": self.scripture_basis,
            "risk_level": self.risk_level,
            "envelope_id": self.envelope_id,
            "degraded_mode": self.degraded_mode,
        }
