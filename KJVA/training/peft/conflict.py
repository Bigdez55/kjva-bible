"""
peft/conflict.py — Conflict Resolver

Detects adapter interference and prunes unsafe adapter combinations.

Conflict types detected:
  - Weight-space conflict: two adapters push same matrix in opposing directions
  - Style conflict: incompatible purpose domains
  - Domain bleed: adapter activates outside its target domain
  - Latency conflict: too many adapters exceed budget
  - Safety conflict: combination degrades safety behavior

Resolution strategies:
  - Prune lowest-weight conflicting expert
  - Reweight conflicting experts to sum to 1.0
  - Quarantine incompatible combinations
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import mlx.core as mx

from .base import AdapterGenomeRecord, ActiveExpert, HardwareBudget, RoutePlan

if TYPE_CHECKING:
    from .registry import AdapterGenomeRegistry


# ---------------------------------------------------------------------------
# Conflict report
# ---------------------------------------------------------------------------

@dataclass
class ConflictReport:
    has_conflicts: bool
    conflicts: list[dict] = field(default_factory=list)
    pruned_experts: list[str] = field(default_factory=list)
    final_plan: RoutePlan = field(default_factory=RoutePlan)


# ---------------------------------------------------------------------------
# Resolver
# ---------------------------------------------------------------------------

class ConflictResolver:
    """
    Inspects a RoutePlan for adapter-level conflicts and returns a pruned,
    safe version via ConflictReport.
    """

    # Latency budget: max adapters that can be active simultaneously
    # before we start pruning the lowest-weight ones.
    _MAX_ACTIVE_ADAPTERS = 4

    def check(
        self,
        genomes: "list[AdapterGenomeRecord]",
    ) -> "ConflictReport":
        """
        Convenience entry-point: given a flat list of AdapterGenomeRecords, run a
        metadata-only pairwise conflict scan and return a ConflictReport.

        No registry or hardware budget is required — this is useful for quick
        pre-registration checks where only the genome metadata is available.
        """
        conflicts: list[dict] = []
        pruned: list[str] = []

        surviving = list(genomes)
        i = 0
        while i < len(surviving):
            j = i + 1
            while j < len(surviving):
                ga = surviving[i]
                gb = surviving[j]
                conflict_type = self._conflict_type(ga, gb)
                if conflict_type is not None:
                    victim = ga if ga.name > gb.name else gb  # deterministic: higher name pruned
                    surviving.remove(victim)
                    pruned.append(victim.name)
                    conflicts.append({
                        "type": conflict_type,
                        "expert_ids": [ga.name, gb.name],
                        "severity": "high",
                        "resolution": f"pruned {victim.name}",
                    })
                    continue
                j += 1
            i += 1

        from .base import RoutePlan
        final_plan = RoutePlan(
            active_experts=[],
            conflict_free=(len(conflicts) == 0),
        )
        return ConflictReport(
            has_conflicts=bool(conflicts),
            conflicts=conflicts,
            pruned_experts=pruned,
            final_plan=final_plan,
        )

    def check_compatibility(
        self,
        genome_a: AdapterGenomeRecord,
        genome_b: AdapterGenomeRecord,
    ) -> bool:
        """
        Return True if genome_a and genome_b can be active simultaneously.

        Incompatible if:
          - either lists the other in conflicts_with
          - they share a domain keyword that is in one's routing_never_activate_when
        """
        return self._conflict_type(genome_a, genome_b) is None

    def prune(
        self,
        route_plan: RoutePlan,
        registry: "AdapterGenomeRegistry",
        budget: HardwareBudget,
        delta_provider=None,
        weight_conflict_threshold: float = -0.5,
    ) -> ConflictReport:
        """
        Check every pair of active experts for conflicts, then enforce the
        latency budget.  Returns a ConflictReport with a NEW (non-mutated)
        RoutePlan.

        delta_provider: optional callable expert_id -> mx.array. When supplied, the
        ADR-0002 §9.2 rule-4 NUMERIC weight-space conflict check runs: a pair whose
        flattened weight-deltas have cosine ≤ weight_conflict_threshold push the shared
        matrix in opposing directions and is pruned (lower-weight victim). When None,
        only the metadata compatibility check runs (honest "wired-as-available").
        """
        conflicts: list[dict] = []
        pruned: list[str] = []

        # Build a mutable list of surviving experts (copy, not reference)
        experts: list[ActiveExpert] = list(route_plan.active_experts)

        # --- Numeric weight-space conflict (§9.2 rule 4) — only when deltas are available ---
        if delta_provider is not None:
            experts, num_conflicts, num_pruned = self._prune_weight_conflicts(
                experts, delta_provider, weight_conflict_threshold
            )
            conflicts.extend(num_conflicts)
            pruned.extend(num_pruned)

        # --- Pairwise compatibility check ---
        i = 0
        while i < len(experts):
            j = i + 1
            while j < len(experts):
                ea = experts[i]
                eb = experts[j]

                genome_a = self._genome(ea.expert_id, registry)
                genome_b = self._genome(eb.expert_id, registry)

                if genome_a is None or genome_b is None:
                    j += 1
                    continue

                conflict_type = self._conflict_type(genome_a, genome_b)
                if conflict_type is not None:
                    # Prune the lower-weight expert
                    victim = ea if ea.weight < eb.weight else eb
                    if victim in experts:
                        experts.remove(victim)
                        pruned.append(victim.expert_id)
                        conflicts.append({
                            "type": conflict_type,
                            "expert_ids": [ea.expert_id, eb.expert_id],
                            "severity": "high",
                            "resolution": f"pruned {victim.expert_id}",
                        })
                    # Don't advance j — list shifted
                    continue
                j += 1
            i += 1

        # --- Merge conflict detection ---
        for idx_a in range(len(experts)):
            for idx_b in range(idx_a + 1, len(experts)):
                ea = experts[idx_a]
                eb = experts[idx_b]
                ga = self._genome(ea.expert_id, registry)
                gb = self._genome(eb.expert_id, registry)
                if ga is None or gb is None:
                    continue
                if (
                    not ga.mergeable
                    and not gb.mergeable
                    and ga.delta_family == gb.delta_family
                    and ga.delta_family is not None
                ):
                    conflicts.append({
                        "type": "merge_conflict",
                        "expert_ids": [ea.expert_id, eb.expert_id],
                        "severity": "high",
                        "delta_family": ga.delta_family,
                        "resolution": "manual intervention required — two non-mergeable adapters share delta_family",
                    })

        # --- Latency / count budget ---
        max_active = self._max_experts_from_budget(budget)
        while len(experts) > max_active:
            # Prune the lowest-weight expert
            victim = min(experts, key=lambda e: e.weight)
            experts.remove(victim)
            pruned.append(victim.expert_id)
            conflicts.append({
                "type": "latency_conflict",
                "expert_ids": [victim.expert_id],
                "severity": "medium",
                "resolution": f"pruned {victim.expert_id} (budget cap {max_active})",
            })

        # --- Renormalize weights ---
        total_w = sum(e.weight for e in experts)
        if total_w > 0 and experts:
            experts = [
                ActiveExpert(e.expert_id, e.weight / total_w, e.layer_idx)
                for e in experts
            ]

        new_plan = RoutePlan(
            active_experts=experts,
            budget_vram_mb=route_plan.budget_vram_mb,
            safety_pass=route_plan.safety_pass,
            conflict_free=(len(conflicts) == 0),
        )

        return ConflictReport(
            has_conflicts=bool(conflicts),
            conflicts=conflicts,
            pruned_experts=pruned,
            final_plan=new_plan,
        )

    def _prune_weight_conflicts(
        self,
        experts: list[ActiveExpert],
        delta_provider,
        threshold: float,
    ) -> "tuple[list[ActiveExpert], list[dict], list[str]]":
        """ADR-0002 §9.2 rule 4 — prune pairs whose weight-deltas oppose.

        For each surviving pair with BOTH deltas available, compute the cosine of the
        flattened deltas (compute_delta_cosine_similarity). cosine ≤ threshold ⇒ the two
        adapters push the shared matrix in opposing directions (weight-space conflict);
        the lower-weight expert is pruned. Deltas absent for an expert ⇒ that pair is
        skipped (cannot assess numerically — never a false positive).
        """
        surviving = list(experts)
        conflicts: list[dict] = []
        pruned: list[str] = []
        i = 0
        while i < len(surviving):
            j = i + 1
            while j < len(surviving):
                ea, eb = surviving[i], surviving[j]
                da = delta_provider(ea.expert_id)
                db = delta_provider(eb.expert_id)
                if da is None or db is None:
                    j += 1
                    continue
                cosine = self.compute_delta_cosine_similarity(da, db)
                if cosine <= threshold:
                    victim = ea if ea.weight < eb.weight else eb
                    if victim in surviving:
                        surviving.remove(victim)
                        pruned.append(victim.expert_id)
                        conflicts.append({
                            "type": "weight_space_conflict",
                            "expert_ids": [ea.expert_id, eb.expert_id],
                            "severity": "high",
                            "cosine": round(cosine, 4),
                            "resolution": f"pruned {victim.expert_id} (cosine {cosine:.3f} ≤ {threshold})",
                        })
                    continue  # list shifted — re-check from same i without advancing j
                j += 1
            i += 1
        return surviving, conflicts, pruned

    def compute_delta_cosine_similarity(
        self,
        delta_a: mx.array,
        delta_b: mx.array,
    ) -> float:
        """
        Flatten both arrays and compute cosine similarity.

        High negative value → weight-space conflict (adapters push in opposite
        directions). Returns a Python float in [-1, 1].
        """
        a_flat = mx.reshape(delta_a, (-1,))
        b_flat = mx.reshape(delta_b, (-1,))

        dot = mx.sum(a_flat * b_flat)
        norm_a = mx.sqrt(mx.sum(a_flat * a_flat))
        norm_b = mx.sqrt(mx.sum(b_flat * b_flat))

        # Guard against zero-norm vectors
        denom = norm_a * norm_b
        # Use mx.where for safe division
        safe_denom = mx.where(denom < 1e-8, mx.array(1.0), denom)
        cosine = mx.where(denom < 1e-8, mx.array(0.0), dot / safe_denom)

        mx.eval(cosine)
        return float(cosine.item())

    def _conflict_type(
        self,
        genome_a: AdapterGenomeRecord,
        genome_b: AdapterGenomeRecord,
    ) -> str | None:
        """Return the conflict type string if the two genomes are incompatible, else None."""
        # Explicit conflict lists
        if genome_b.name in genome_a.conflicts_with or genome_a.name in genome_b.conflicts_with:
            return "explicit_conflict"

        # Domain bleed: routing_never_activate_when
        for forbidden in genome_a.routing_never_activate_when:
            if forbidden in genome_b.purpose_domains or forbidden in genome_b.purpose_tasks:
                return "domain_bleed"
        for forbidden in genome_b.routing_never_activate_when:
            if forbidden in genome_a.purpose_domains or forbidden in genome_a.purpose_tasks:
                return "domain_bleed"

        # Style / safety clash
        a_domains = set(genome_a.purpose_domains)
        b_domains = set(genome_b.purpose_domains)
        if _domain_clash(a_domains, b_domains):
            _SAFETY_KEYWORDS = {"safety", "harmful", "jailbreak"}
            if (a_domains | b_domains) & _SAFETY_KEYWORDS:
                return "safety_conflict"
            return "style_conflict"

        return None

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _genome(
        self,
        expert_id: str,
        registry: "AdapterGenomeRegistry",
    ) -> AdapterGenomeRecord | None:
        entry = registry.entries.get(expert_id)
        return entry.genome if entry else None

    def _max_experts_from_budget(self, budget: HardwareBudget) -> int:
        """Estimate max simultaneous adapters based on latency target."""
        if budget.latency_target_ms < 50:
            return 1
        if budget.latency_target_ms < 100:
            return 2
        if budget.latency_target_ms < 200:
            return self._MAX_ACTIVE_ADAPTERS
        return 8


# ---------------------------------------------------------------------------
# Domain clash heuristic
# ---------------------------------------------------------------------------

# Pairs of domains that are considered semantically incompatible
_CLASH_PAIRS: list[tuple[frozenset[str], frozenset[str]]] = [
    (frozenset({"medical", "clinical"}), frozenset({"fiction", "creative", "roleplay"})),
    (frozenset({"legal"}), frozenset({"casual", "informal"})),
    (frozenset({"safety"}), frozenset({"harmful", "jailbreak"})),
]


def _domain_clash(a_domains: set[str], b_domains: set[str]) -> bool:
    """Return True if domain sets represent a known style/safety clash."""
    for group_a, group_b in _CLASH_PAIRS:
        if a_domains & group_a and b_domains & group_b:
            return True
        if b_domains & group_a and a_domains & group_b:
            return True
    return False
