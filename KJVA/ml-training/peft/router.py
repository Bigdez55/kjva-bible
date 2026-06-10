"""
peft/router.py — Hierarchical Runtime Router

Routes inference through the correct adapter combination using a
hierarchical decision tree:

  Input → Task Router → Domain Router → Layer Router → Budget Router → Safety Router → Output

The router operates at multiple levels:
  Task-level    → which broad capability is needed?
  Domain-level  → which knowledge domain?
  Layer-level   → which layers need which adapters?
  Budget-level  → prune paths that exceed VRAM/latency budget
  Safety-level  → block unsafe adapter combinations
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .base import ActiveExpert, HardwareBudget, RoutePlan


# ---------------------------------------------------------------------------
# Router config
# ---------------------------------------------------------------------------

@dataclass
class RouterConfig:
    top_k_experts: int = 2
    temperature: float = 1.0
    min_expert_weight: float = 0.1
    max_experts_per_layer: int = 3


# ---------------------------------------------------------------------------
# Keyword tables for task/domain detection
# ---------------------------------------------------------------------------

_TASK_KEYWORDS: dict[str, list[str]] = {
    "summarization": ["summarize", "summary", "abstract", "tldr", "shorten"],
    "classification": ["classify", "label", "categorize", "detect", "identify"],
    "generation": ["generate", "write", "compose", "create", "produce"],
    "qa": ["what", "why", "how", "question", "answer", "explain"],
    "translation": ["translate", "language", "french", "spanish", "german", "arabic"],
    "extraction": ["extract", "parse", "find", "retrieve", "list all"],
    "reasoning": ["reason", "solve", "prove", "logic", "deduce", "math"],
    "coding": ["code", "function", "program", "debug", "implement", "script"],
    "dialogue": ["chat", "conversation", "respond", "reply", "roleplay"],
}

_DOMAIN_KEYWORDS: dict[str, list[str]] = {
    "biblical": ["scripture", "bible", "kjv", "verse", "chapter", "gospel",
                 "psalm", "proverb", "genesis", "revelation", "jesus", "god",
                 "lord", "holy", "covenant", "apostle", "prophet"],
    "medical": ["patient", "diagnosis", "treatment", "clinical", "symptom",
                "medicine", "drug", "disease", "health", "therapy"],
    "legal": ["law", "statute", "contract", "court", "legal", "plaintiff",
              "defendant", "jurisdiction", "liability"],
    "technical": ["algorithm", "architecture", "system", "api", "software",
                  "hardware", "protocol", "database", "network"],
    "creative": ["story", "poem", "fiction", "narrative", "character",
                 "plot", "creative", "novel", "write a"],
    "academic": ["research", "study", "hypothesis", "methodology", "paper",
                 "academic", "literature", "citation"],
}


# ---------------------------------------------------------------------------
# Hierarchical router
# ---------------------------------------------------------------------------

class HierarchicalRouter:
    """
    Routes an input text through the adapter registry to produce a RoutePlan.

    The routing pipeline:
      1. Detect task types from input text (keyword match)
      2. Detect domain from input text (keyword match)
      3. Query registry for adapters matching detected domains
      4. Score each adapter by overlap with detected tasks/domains
      5. Select top_k by score
      6. Apply conflict resolver
      7. Enforce budget cap
    """

    def __init__(
        self,
        registry: "AdapterGenomeRegistry",  # type: ignore[name-defined]
        conflict_resolver: "ConflictResolver",  # type: ignore[name-defined]
        config: RouterConfig | None = None,
    ) -> None:
        # Lazy imports to avoid circular deps at module load time
        from .registry import AdapterGenomeRegistry  # noqa: F401
        from .conflict import ConflictResolver        # noqa: F401

        self.registry = registry
        self.conflict_resolver = conflict_resolver
        self.config = config or RouterConfig()

    def route(
        self,
        input_text: str,
        task_spec: dict,
        budget: HardwareBudget,
    ) -> RoutePlan:
        """
        Full routing pipeline from raw text to a conflict-free, budget-safe RoutePlan.
        """
        # Step 1 & 2: Detect tasks and domains
        detected_tasks = self._detect_task(input_text)
        detected_domains = self._detect_domain(input_text)

        # Also pull from task_spec if provided
        spec_domains = task_spec.get("domains", [])
        spec_tasks = task_spec.get("tasks", [])
        all_domains = list(set(detected_domains + spec_domains))
        all_tasks = list(set(detected_tasks + spec_tasks))

        # Step 3: Query registry
        candidates = self.registry.query(domains=all_domains or None, tasks=all_tasks or None)

        # If no domain-specific hits, fall back to all non-quarantined adapters
        if not candidates:
            candidates = [
                e for e in self.registry.entries.values()
                if e.status != "quarantined"
            ]

        # Step 4: Score candidates
        scored = [
            (entry, self._score_adapter(entry.genome, all_domains, all_tasks))
            for entry in candidates
        ]
        scored.sort(key=lambda x: x[1], reverse=True)

        # Step 5: Select top_k
        top_k = scored[: self.config.top_k_experts]

        # Build raw route plan
        total_score = sum(s for _, s in top_k) or 1.0
        active_experts: list[ActiveExpert] = []
        for entry, score in top_k:
            weight = score / total_score
            if weight >= self.config.min_expert_weight:
                active_experts.append(ActiveExpert(
                    expert_id=entry.genome.name,
                    weight=weight,
                    layer_idx=None,
                ))

        raw_plan = RoutePlan(
            active_experts=active_experts,
            budget_vram_mb=float(budget.infer_vram_mb),
            safety_pass=True,
            conflict_free=True,
        )

        # Step 6: Conflict resolution
        report = self.conflict_resolver.prune(raw_plan, self.registry, budget)

        # Step 7: Budget enforcement is already done inside prune()
        return report.final_plan

    # ------------------------------------------------------------------
    # Keyword detectors
    # ------------------------------------------------------------------

    def _detect_task(self, text: str) -> list[str]:
        lower = text.lower()
        return [task for task, kws in _TASK_KEYWORDS.items() if any(kw in lower for kw in kws)]

    def _detect_domain(self, text: str) -> list[str]:
        lower = text.lower()
        return [domain for domain, kws in _DOMAIN_KEYWORDS.items() if any(kw in lower for kw in kws)]

    # ------------------------------------------------------------------
    # Scoring
    # ------------------------------------------------------------------

    def _score_adapter(
        self,
        genome: "AdapterGenomeRecord",  # type: ignore[name-defined]
        domains: list[str],
        tasks: list[str],
    ) -> float:
        """
        Compute overlap score between genome and detected context.

        Score = domain_hits + task_hits + activation_keyword_hits
        """
        score = 0.0
        genome_domains = set(genome.purpose_domains)
        genome_tasks = set(genome.purpose_tasks)
        activate_when = set(genome.routing_activate_when)

        score += len(genome_domains & set(domains)) * 2.0   # domain match is worth more
        score += len(genome_tasks & set(tasks)) * 1.0

        # Partial keyword overlap in activation hints
        all_context = set(domains + tasks)
        score += len(activate_when & all_context) * 0.5

        return score
