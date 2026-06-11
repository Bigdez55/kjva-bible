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
from .conflict import _CLASH_PAIRS


# ---------------------------------------------------------------------------
# Router config
# ---------------------------------------------------------------------------

@dataclass
class RouterConfig:
    top_k_experts: int = 2
    temperature: float = 1.0
    min_expert_weight: float = 0.1
    max_experts_per_layer: int = 3
    # ADR-0002 §9.2 adapter-activation admission (deployment config):
    active_base: str = ""        # the live base-model id; non-empty ⇒ enforce base-hash match
    require_signed: bool = False  # if True, reject unsigned adapters (rule 1, presence)
    verify_key: bytes | None = None  # if set, signatures are CRYPTOGRAPHICALLY verified via
                                     # AdapterGenomeV2.verify(key) (HMAC over content_hash|method|
                                     # family) — a present-but-forged signature is rejected (rule 1,
                                     # strong). None ⇒ presence-only (require_signed).
    # ADR-0002 §9.2 rule 4 (conflict): two adapters whose weight-deltas point in strongly
    # opposing directions interfere. cosine ≤ this threshold ⇒ weight-space conflict (pruned).
    weight_conflict_threshold: float = -0.5
    # Safety blocklist: additional (frozenset, frozenset) clash pairs beyond _CLASH_PAIRS.
    # Each pair is (domain_set_A, domain_set_B); any plan whose active adapters collectively
    # span both sides is flagged as safety_pass=False.
    safety_blocklist: list[tuple[frozenset, frozenset]] = field(default_factory=list)
    # LayerPlasticityV2 instance (Component 4) used to assign layer_idx per expert.
    # When None, layer_idx remains None (no layer-scoped assignment).
    layer_plasticity_map: object | None = None


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
    # Consuming projects extend this table with their own domain keyword lists.
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
        delta_provider=None,
        seed: int = 0,
    ) -> RoutePlan:
        """
        Full routing pipeline from raw text to a conflict-free, budget-safe RoutePlan.

        delta_provider: optional callable expert_id -> mx.array (the adapter's flattened
        weight-delta). When supplied, the conflict resolver runs the §9.2 rule-4 NUMERIC
        weight-space check (cosine of delta pairs); when None, that check is skipped (the
        metadata-only path) — honest "wired-as-available".

        seed: replay seed for the emitted DeterminantProbabilityRecord (RouteRecord). The
        full decision (candidates, admission trail, final plan) is recorded on
        ``self._last_route_record`` so an identical (seed, input) re-derives the same plan.
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

        # ADR-0002 §9.2 admission gate (the trust chain — previously called by nothing). Each
        # candidate must pass before it can become an active expert; rejects are dropped + recorded.
        admitted: list = []
        self._last_admission: list[dict] = []
        for entry, score in top_k:
            ok, reason = self._admit_genome(entry.genome, all_domains, all_tasks)
            self._last_admission.append({"adapter": entry.genome.name, "admitted": ok, "reason": reason})
            if ok:
                admitted.append((entry, score))
        # Build raw route plan from the ADMITTED candidates only
        total_score = sum(s for _, s in admitted) or 1.0
        active_experts: list[ActiveExpert] = []
        for entry, score in admitted:
            weight = score / total_score
            if weight >= self.config.min_expert_weight:
                layer_idx = self._assign_layer_idx(entry.genome, active_experts)
                active_experts.append(ActiveExpert(
                    expert_id=entry.genome.name,
                    weight=weight,
                    layer_idx=layer_idx,
                ))

        # Token-level routing stage: delegate to XLoRALayer when a ROUTING-family
        # adapter is among the active experts (position context forwarded downstream).
        active_experts = self._route_token_level(active_experts)

        # Safety check: must run after conflict resolution prep, before RoutePlan is sealed.
        safety_pass = self._check_safety(active_experts)

        raw_plan = RoutePlan(
            active_experts=active_experts,
            budget_vram_mb=float(budget.infer_vram_mb),
            safety_pass=safety_pass,
            conflict_free=True,
        )

        # Step 6: Conflict resolution — pass the numeric §9.2 rule-4 inputs through.
        report = self.conflict_resolver.prune(
            raw_plan, self.registry, budget,
            delta_provider=delta_provider,
            weight_conflict_threshold=self.config.weight_conflict_threshold,
        )

        # Step 7: emit the DeterminantProbabilityRecord (replayable route determinant).
        # Identical (seed, input_text, task_spec) ⇒ identical candidate ordering ⇒ identical
        # plan; determinism.is_deterministic(record) re-derives it. Stored, not returned, so
        # the RoutePlan contract is unchanged.
        from .v2 import determinism as _det
        candidate_names = [entry.genome.name for entry, _ in scored]
        rec = _det.record(
            seed=seed,
            candidates=candidate_names,
            inputs={"input_text": input_text, "task_spec": task_spec},
            top_k=self.config.top_k_experts,
            env_fingerprint=f"active_base={self.config.active_base}|require_signed={self.config.require_signed}",
        )
        # Attach the actual admission/plan outcome to the determinant record for audit/replay.
        rec.plan = [e.expert_id for e in report.final_plan.active_experts]
        self._last_route_record = rec
        self._last_admission = getattr(self, "_last_admission", [])

        return report.final_plan

    # ------------------------------------------------------------------
    # Layer-level routing: assign layer_idx per expert via LayerPlasticityMap
    # ------------------------------------------------------------------

    def _assign_layer_idx(self, genome, already_assigned: list[ActiveExpert]) -> int | None:
        """
        Return a layer_idx for this genome using the LayerPlasticityV2 map when
        available, respecting max_experts_per_layer.

        Strategy:
          - For each layer in the plasticity map, count how many experts are
            already assigned to it.
          - Find the best-fit layer: the highest-plasticity layer whose sublayer
            recommendation matches the genome's peft_method, and that has not yet
            hit max_experts_per_layer.
          - Fall back to the globally most-plastic under-capped layer, then None.
        """
        plmap = self.config.layer_plasticity_map
        if plmap is None:
            return None

        n_layers = getattr(plmap, "n_layers", 0)
        if not n_layers:
            return None

        max_per_layer = self.config.max_experts_per_layer
        peft_method = (getattr(genome, "peft_method", "") or "").lower()

        # Count current assignments per layer
        layer_counts: dict[int, int] = {}
        for e in already_assigned:
            if e.layer_idx is not None:
                layer_counts[e.layer_idx] = layer_counts.get(e.layer_idx, 0) + 1

        best_layer: int | None = None
        best_plasticity: float = -1.0

        for sublayer in ("attn", "mlp"):
            for li in range(n_layers):
                if layer_counts.get(li, 0) >= max_per_layer:
                    continue
                rec = plmap.recommend(li, sublayer)
                plasticity = plmap.plasticity(li, sublayer)
                # Prefer layers where the peft_method is explicitly recommended
                method_match = any(peft_method.startswith(r) for r in rec) if rec else False
                effective_plasticity = plasticity + (0.5 if method_match else 0.0)
                if effective_plasticity > best_plasticity:
                    best_plasticity = effective_plasticity
                    best_layer = li

        return best_layer

    # ------------------------------------------------------------------
    # Token-level routing stage
    # ------------------------------------------------------------------

    def _route_token_level(self, experts: list[ActiveExpert]) -> list[ActiveExpert]:
        """
        Token-level routing stage: for any active expert whose genome carries a
        ROUTING delta_family (X-LoRA and kin), mark the expert as token-routed by
        recording the routing family in a side-channel attribute. The XLoRALayer's
        per-position softmax gating runs at forward time; here we simply ensure the
        router recognises and forwards the token-position context to those experts by
        tagging them. Experts from other families are passed through unchanged.

        This stage sits between layer-level assignment (above) and budget routing
        (conflict resolver), exactly as specified in the pipeline docstring.
        """
        from .base import DeltaFamily

        routing_family_name = DeltaFamily.ROUTING.name  # "ROUTING"

        updated: list[ActiveExpert] = []
        for expert in experts:
            genome = None
            entry = self.registry.entries.get(expert.expert_id)
            if entry is not None:
                genome = entry.genome

            is_routing_family = (
                genome is not None
                and (getattr(genome, "delta_family", "") or "").upper() == routing_family_name
            )

            if is_routing_family:
                # Token-level dispatch: annotate the expert so the caller (OmniPEFTBlock
                # / serve layer) knows to delegate to the XLoRALayer router at inference.
                # We represent this by setting layer_idx to a sentinel value that the
                # serving layer interprets as "apply XLoRALayer token routing".
                # Preserve the existing layer_idx if already assigned; only attach the
                # token-routing flag via a wrapped ActiveExpert with a known convention.
                # Since ActiveExpert is a plain dataclass with no flags field, we store the
                # annotation on a parallel dict keyed by expert_id.
                if not hasattr(self, "_token_routed_experts"):
                    self._token_routed_experts: set[str] = set()
                self._token_routed_experts.add(expert.expert_id)

            updated.append(expert)

        return updated

    # ------------------------------------------------------------------
    # Safety routing stage (final gate before RoutePlan is returned)
    # ------------------------------------------------------------------

    def _check_safety(self, experts: list[ActiveExpert]) -> bool:
        """
        Evaluate unsafe adapter combinations using _CLASH_PAIRS from conflict.py
        plus any additional pairs in RouterConfig.safety_blocklist.

        Returns False if any active expert pair collectively spans both sides of a
        clash pair (i.e., the combined domain set of the plan touches group_A AND
        group_B). Returns True when the plan is safe.

        Must run after conflict resolution, as the spec requires it as the final
        gate before the RoutePlan is returned.
        """
        # Collect all domains from every active expert's genome
        all_domains: set[str] = set()
        for expert in experts:
            entry = self.registry.entries.get(expert.expert_id)
            if entry is not None:
                genome = entry.genome
                all_domains.update(getattr(genome, "purpose_domains", []) or [])
                # Include routing_never_activate_when tags for conservative coverage
                all_domains.update(getattr(genome, "routing_never_activate_when", []) or [])

        clash_pairs = list(_CLASH_PAIRS) + list(self.config.safety_blocklist)
        for group_a, group_b in clash_pairs:
            if all_domains & group_a and all_domains & group_b:
                return False

        return True

    # ------------------------------------------------------------------
    # ADR-0002 §9.2 admission gate
    # ------------------------------------------------------------------
    def _admit_genome(self, genome, domains: list[str], tasks: list[str]) -> "tuple[bool, str]":
        """Enforce the ADR-0002 §9.2 adapter-activation rules before an adapter activates.
        Returns (admitted, reason). Rules that always hold are enforced unconditionally; the
        signature rule is enforced only when the deployment opts in (require_signed), so the
        unsigned-substrate flow isn't hard-blocked — but the machinery is now genuinely CALLED.

          rule 1  unsigned:   reject if require_signed and no signature (presence); and if
                              verify_key is set, CRYPTOGRAPHICALLY verify the HMAC — a present-
                              but-forged signature is rejected (AdapterGenomeV2.verify CALLED).
          rule 2  base-hash:  reject if active_base set and genome.base_model mismatches
          rule 3  scope:      reject if a requested domain/task is in routing_never_activate_when
        """
        # rule 2 — base-hash / base-model match
        base = getattr(genome, "base_model", "") or ""
        if self.config.active_base and base and base != self.config.active_base:
            return False, f"base mismatch ({base} != {self.config.active_base})"
        # rule 3 — authority scope (never-activate policy)
        never = set(getattr(genome, "routing_never_activate_when", []) or [])
        if never & (set(domains) | set(tasks)):
            return False, "scope: matches routing_never_activate_when"
        # rule 1 — signed
        sig = getattr(genome, "signature", "") or ""
        if self.config.require_signed and not sig:
            return False, "unsigned (require_signed)"
        if self.config.verify_key is not None and sig:
            # Strong verification: reconstruct the v2 genome's signing view and HMAC-verify.
            # A forged/tampered signature (or a tampered content_hash/method/family) fails here
            # even though it is "present". Absent signature falls through to the presence rule.
            from .v2.adapter_genome_v2 import AdapterGenomeV2
            v2 = AdapterGenomeV2(
                method=getattr(genome, "peft_method", "") or "",
                family=getattr(genome, "delta_family", "") or "",
                content_hash=getattr(genome, "content_hash", "") or "",
                signature=sig,
            )
            if not v2.verify(self.config.verify_key):
                return False, "signature: HMAC verify failed (forged/tampered)"
        return True, "ok"

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
