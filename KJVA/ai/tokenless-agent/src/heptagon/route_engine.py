"""ai/tokenless-agent/src/heptagon/route_engine.py
RouteEngine — classifies queries and assigns 3-6-9 step budget profiles
for the Heptagon cognitive architecture.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("tokenless.heptagon.route_engine")

# ── RouteType ─────────────────────────────────────────────────────────────────

class RouteType(IntEnum):
    """
    Routing strategy, ordered by computational cost (ascending).

    Budget 3-6-9:
      DIRECT / DELEGATED   -> max 3 steps (512 tokens)
      RESEARCHED / ESCALATED -> max 6 steps (2048 tokens)
      CREATIVE / ANALYTICAL / EXECUTIVE -> max 9 steps (4096 tokens)
    """
    DIRECT     = 0   # Simple lookup / factual answer
    RESEARCHED = 1   # Multi-source synthesis needed
    CREATIVE   = 2   # Generation / drafting task
    ANALYTICAL = 3   # Data analysis / reasoning chain
    EXECUTIVE  = 4   # Decision-making / action orchestration
    DELEGATED  = 5   # Hand off to sub-agent
    ESCALATED  = 6   # Requires human review


# ── Budget profiles ───────────────────────────────────────────────────────────

_BUDGET_MAP: Dict[RouteType, Dict[str, int]] = {
    RouteType.DIRECT:     {"max_steps": 3, "max_tokens": 512,  "profile": "direct"},
    RouteType.DELEGATED:  {"max_steps": 3, "max_tokens": 512,  "profile": "direct"},
    RouteType.RESEARCHED: {"max_steps": 6, "max_tokens": 2048, "profile": "researched"},
    RouteType.ESCALATED:  {"max_steps": 6, "max_tokens": 2048, "profile": "researched"},
    RouteType.CREATIVE:   {"max_steps": 9, "max_tokens": 4096, "profile": "full"},
    RouteType.ANALYTICAL: {"max_steps": 9, "max_tokens": 4096, "profile": "full"},
    RouteType.EXECUTIVE:  {"max_steps": 9, "max_tokens": 4096, "profile": "full"},
}

# ── Keyword classifier ────────────────────────────────────────────────────────

# Patterns in priority order (first match wins).
_ROUTE_PATTERNS: List[Tuple[RouteType, re.Pattern]] = [
    # ESCALATED — must go to human
    (RouteType.ESCALATED, re.compile(
        r"\b(escalate|human review|legal|compliance|gdpr|audit|regulated|litigation)\b",
        re.IGNORECASE,
    )),
    # EXECUTIVE — orchestration / decision
    (RouteType.EXECUTIVE, re.compile(
        r"\b(execute|deploy|schedule|orchestrate|coordinate|commission|launch|approve|"
        r"provision|rollout|migrate|shut.?down|restart)\b",
        re.IGNORECASE,
    )),
    # ANALYTICAL — reasoning / data
    (RouteType.ANALYTICAL, re.compile(
        r"\b(analyze|analyse|compare|evaluate|diagnose|investigate|assess|benchmark|"
        r"predict|forecast|model|correlation|regression|cluster|anomaly|root.?cause)\b",
        re.IGNORECASE,
    )),
    # CREATIVE — generation / drafting
    (RouteType.CREATIVE, re.compile(
        r"\b(write|draft|generate|compose|create|design|brainstorm|suggest|imagine|"
        r"story|poem|essay|proposal|email|report|summarize|rewrite|paraphrase)\b",
        re.IGNORECASE,
    )),
    # RESEARCHED — multi-step lookup
    (RouteType.RESEARCHED, re.compile(
        r"\b(research|find|search|look up|gather|collect|survey|review|"
        r"what is|how does|explain|describe|list|enumerate|history)\b",
        re.IGNORECASE,
    )),
    # DELEGATED — explicit delegation
    (RouteType.DELEGATED, re.compile(
        r"\b(delegate|hand off|assign|forward|route to|ask)\b",
        re.IGNORECASE,
    )),
]

# Agent suggestion map: route -> preferred Heptagon node_id
_AGENT_SUGGESTION: Dict[RouteType, str] = {
    RouteType.DIRECT:     "l3.kernel.inference",
    RouteType.RESEARCHED: "l5.eval.verifier",
    RouteType.CREATIVE:   "l3.kernel.inference",
    RouteType.ANALYTICAL: "l5.eval.scorer",
    RouteType.EXECUTIVE:  "l7.enforce.invariants",
    RouteType.DELEGATED:  "l4.instr.tracer",
    RouteType.ESCALATED:  "l7.enforce.safety",
}


# ── Route result ──────────────────────────────────────────────────────────────

@dataclass
class RouteResult:
    """Output of RouteEngine.classify()."""
    route_type: RouteType
    max_steps: int
    max_tokens: int
    profile: str
    confidence: float          # 0.0 – 1.0 (1.0 = keyword matched)
    matched_pattern: str       # the regex group that triggered classification
    suggested_agent: str       # preferred node_id
    scores: Dict[str, float] = field(default_factory=dict)

    def budget_profile(self) -> Dict[str, Any]:
        return {
            "profile": self.profile,
            "max_steps": self.max_steps,
            "max_tokens": self.max_tokens,
        }


# ── RouteEngine ───────────────────────────────────────────────────────────────

class RouteEngine:
    """
    Classifies incoming queries into RouteType and applies 3-6-9 budget governance.

    Classification algorithm:
      1. Strip and lowercase the query.
      2. Test each pattern in _ROUTE_PATTERNS (priority order, first match wins).
      3. If no pattern matches, fall back to DIRECT.
      4. Score all routes to provide a confidence breakdown.

    Parsimony principle: prefer lower-cost routes when confidence is equal.
    """

    def __init__(self) -> None:
        logger.debug("RouteEngine: initialised with %d patterns", len(_ROUTE_PATTERNS))

    def classify(self, query: str) -> RouteResult:
        """
        Classify a query and return a RouteResult with budget profile.

        Parameters
        ----------
        query : the raw user or agent query string

        Returns
        -------
        RouteResult with route_type, budget limits, and suggested agent
        """
        if not query or not query.strip():
            return self._make_result(RouteType.DIRECT, 0.5, "empty_query")

        # Priority-ordered pattern matching
        matched_route: Optional[RouteType] = None
        matched_group: str = "none"
        for route_type, pattern in _ROUTE_PATTERNS:
            m = pattern.search(query)
            if m:
                matched_route = route_type
                matched_group = m.group(0).lower()
                break

        if matched_route is None:
            matched_route = RouteType.DIRECT
            matched_group = "default"

        confidence = 1.0 if matched_group != "default" else 0.6
        return self._make_result(matched_route, confidence, matched_group)

    def score_routes(self, query: str) -> Dict[RouteType, float]:
        """
        Score all route types for a query (keyword hit = 1.0, no hit = 0.0).
        Used for transparency / debugging.
        """
        scores: Dict[RouteType, float] = {rt: 0.0 for rt in RouteType}
        for route_type, pattern in _ROUTE_PATTERNS:
            if pattern.search(query):
                scores[route_type] = 1.0
        # Default receives 0.6 if nothing matched
        if all(v == 0.0 for v in scores.values()):
            scores[RouteType.DIRECT] = 0.6
        return scores

    def suggest_agent(self, route: RouteType) -> str:
        """Return the preferred Heptagon node_id for a given route type."""
        return _AGENT_SUGGESTION.get(route, "l3.kernel.inference")

    def budget_for(self, route: RouteType) -> Dict[str, Any]:
        """Return the budget dict for a route type."""
        return dict(_BUDGET_MAP.get(route, _BUDGET_MAP[RouteType.DIRECT]))

    # ── Internal ──────────────────────────────────────────────────────────────

    def _make_result(
        self, route_type: RouteType, confidence: float, matched_pattern: str
    ) -> RouteResult:
        budget = _BUDGET_MAP[route_type]
        scores = self.score_routes("")  # empty for internal fallback
        return RouteResult(
            route_type=route_type,
            max_steps=budget["max_steps"],
            max_tokens=budget["max_tokens"],
            profile=budget["profile"],
            confidence=confidence,
            matched_pattern=matched_pattern,
            suggested_agent=self.suggest_agent(route_type),
            scores={rt.name: s for rt, s in scores.items()},
        )

    def explain(self, query: str) -> str:
        """Human-readable explanation of classification for a query."""
        result = self.classify(query)
        return (
            f"Route: {result.route_type.name} "
            f"(profile={result.profile}, "
            f"max_steps={result.max_steps}, "
            f"max_tokens={result.max_tokens}, "
            f"confidence={result.confidence:.2f}, "
            f"trigger={result.matched_pattern!r}, "
            f"agent={result.suggested_agent})"
        )
