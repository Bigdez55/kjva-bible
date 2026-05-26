"""ai/tokenless-agent/src/heptagon/node_registry.py
Heptagon Node Registry - catalogs Tokenless AI nodes across the 7-layer cognitive
architecture defined in the Heptagon Unified Model Spec.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger("tokenless.heptagon.node_registry")

# ── Layer catalogue ───────────────────────────────────────────────────────────
LAYERS: Dict[int, str] = {
    1: "Ontology",
    2: "Schema",
    3: "Kernel",
    4: "Instrumentation",
    5: "Evaluation",
    6: "Calibration",
    7: "Enforcement",
}

# ── HeptagonNode ──────────────────────────────────────────────────────────────

@dataclass
class HeptagonNode:
    """
    A single node in the Heptagon 7-layer architecture.

    Attributes
    ----------
    node_id      : unique identifier (e.g. "ontology.core", "eval.verifier")
    name         : human-readable display name
    capabilities : list of capability tags (e.g. ["reasoning", "search"])
    layer        : Heptagon layer number 1-7
    metadata     : arbitrary extension fields
    active       : whether the node is currently online
    """
    node_id: str
    name: str
    capabilities: List[str]
    layer: int
    metadata: Dict[str, Any] = field(default_factory=dict)
    active: bool = True

    def layer_name(self) -> str:
        return LAYERS.get(self.layer, f"Unknown({self.layer})")

    def has_capability(self, cap: str) -> bool:
        return cap.lower() in [c.lower() for c in self.capabilities]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "node_id": self.node_id,
            "name": self.name,
            "capabilities": self.capabilities,
            "layer": self.layer,
            "layer_name": self.layer_name(),
            "metadata": self.metadata,
            "active": self.active,
        }


# ── NodeRegistry ──────────────────────────────────────────────────────────────

class NodeRegistry:
    """
    Central registry for all Heptagon nodes.

    Provides O(1) lookup by node_id and O(n) filtering by capability or layer.
    Pre-populated with the canonical 7-layer baseline nodes on construction.
    """

    def __init__(self) -> None:
        self._nodes: Dict[str, HeptagonNode] = {}
        self._populate_defaults()

    # ── Default population ────────────────────────────────────────────────────

    def _populate_defaults(self) -> None:
        """Register the canonical baseline nodes for all 7 Heptagon layers."""
        defaults: List[HeptagonNode] = [
            # Layer 1 — Ontology
            HeptagonNode(
                node_id="l1.ontology.core",
                name="Core Ontology Engine",
                capabilities=["ontology", "concept_mapping", "taxonomy"],
                layer=1,
                metadata={"description": "Defines the conceptual vocabulary and entity relationships"},
            ),
            HeptagonNode(
                node_id="l1.ontology.relation",
                name="Relation Mapper",
                capabilities=["ontology", "relation_extraction", "graph"],
                layer=1,
            ),
            # Layer 2 — Schema
            HeptagonNode(
                node_id="l2.schema.validator",
                name="Schema Validator",
                capabilities=["schema", "validation", "pydantic"],
                layer=2,
                metadata={"description": "Validates structured inputs/outputs against Pydantic v2 schemas"},
            ),
            HeptagonNode(
                node_id="l2.schema.encoder",
                name="Schema Encoder",
                capabilities=["schema", "encoding", "serialization"],
                layer=2,
            ),
            # Layer 3 — Kernel
            HeptagonNode(
                node_id="l3.kernel.inference",
                name="XMIND Inference Kernel",
                capabilities=["inference", "generation", "xmind", "llm"],
                layer=3,
                metadata={"model": "llama3.2-3b-q4_0", "backend": "xmind"},
            ),
            HeptagonNode(
                node_id="l3.kernel.tokenizer",
                name="BPE Tokenizer",
                capabilities=["tokenization", "bpe", "vocab"],
                layer=3,
                metadata={"vocab_size": 128256},
            ),
            HeptagonNode(
                node_id="l3.kernel.sampler",
                name="Token Sampler",
                capabilities=["sampling", "temperature", "top_p"],
                layer=3,
            ),
            # Layer 4 — Instrumentation
            HeptagonNode(
                node_id="l4.instr.tracer",
                name="Request Tracer",
                capabilities=["tracing", "observability", "telemetry"],
                layer=4,
            ),
            HeptagonNode(
                node_id="l4.instr.metrics",
                name="Metrics Collector",
                capabilities=["metrics", "latency", "throughput", "observability"],
                layer=4,
            ),
            HeptagonNode(
                node_id="l4.instr.journal",
                name="Event Journal",
                capabilities=["logging", "audit", "journal"],
                layer=4,
            ),
            # Layer 5 — Evaluation
            HeptagonNode(
                node_id="l5.eval.verifier",
                name="Response Verifier",
                capabilities=["verification", "quality", "coherence", "safety"],
                layer=5,
            ),
            HeptagonNode(
                node_id="l5.eval.scorer",
                name="Quality Scorer",
                capabilities=["scoring", "relevance", "completeness"],
                layer=5,
            ),
            # Layer 6 — Calibration
            HeptagonNode(
                node_id="l6.calib.budget",
                name="Budget Governor",
                capabilities=["budget", "token_limit", "step_limit", "governance"],
                layer=6,
            ),
            HeptagonNode(
                node_id="l6.calib.consolidator",
                name="Memory Consolidator",
                capabilities=["consolidation", "actr", "decay", "memory"],
                layer=6,
            ),
            # Layer 7 — Enforcement
            HeptagonNode(
                node_id="l7.enforce.safety",
                name="Safety Enforcer",
                capabilities=["safety", "pii", "content_policy", "redaction"],
                layer=7,
            ),
            HeptagonNode(
                node_id="l7.enforce.invariants",
                name="Invariant Engine",
                capabilities=["invariants", "halt", "governance", "enforcement"],
                layer=7,
            ),
        ]
        for node in defaults:
            self._nodes[node.node_id] = node
        logger.debug("NodeRegistry: populated %d default nodes", len(defaults))

    # ── CRUD ──────────────────────────────────────────────────────────────────

    def register(self, node: HeptagonNode) -> None:
        """Register or replace a node. Logs a warning on overwrite."""
        if node.node_id in self._nodes:
            logger.warning(
                "NodeRegistry: overwriting existing node %s", node.node_id
            )
        if node.layer not in LAYERS:
            raise ValueError(
                f"Invalid Heptagon layer {node.layer} — must be 1-7"
            )
        self._nodes[node.node_id] = node
        logger.debug("NodeRegistry: registered %s (layer %d)", node.node_id, node.layer)

    def get(self, node_id: str) -> Optional[HeptagonNode]:
        """Return node by ID or None."""
        return self._nodes.get(node_id)

    def deregister(self, node_id: str) -> bool:
        """Remove a node by ID. Returns True if it existed."""
        node = self._nodes.pop(node_id, None)
        if node:
            logger.debug("NodeRegistry: deregistered %s", node_id)
        return node is not None

    def set_active(self, node_id: str, active: bool) -> bool:
        """Toggle the active flag. Returns False if node not found."""
        node = self._nodes.get(node_id)
        if node is None:
            return False
        node.active = active
        return True

    # ── Query ─────────────────────────────────────────────────────────────────

    def find_by_capability(
        self, capability: str, active_only: bool = True
    ) -> List[HeptagonNode]:
        """Return all nodes with the given capability tag."""
        cap = capability.lower()
        return [
            n for n in self._nodes.values()
            if n.has_capability(cap) and (not active_only or n.active)
        ]

    def find_by_layer(
        self, layer: int, active_only: bool = True
    ) -> List[HeptagonNode]:
        """Return all nodes in a specific Heptagon layer."""
        return [
            n for n in self._nodes.values()
            if n.layer == layer and (not active_only or n.active)
        ]

    def all_nodes(self, active_only: bool = False) -> List[HeptagonNode]:
        """Return all registered nodes, optionally filtered to active only."""
        nodes = list(self._nodes.values())
        if active_only:
            nodes = [n for n in nodes if n.active]
        return nodes

    def node_count(self) -> int:
        return len(self._nodes)

    def layer_summary(self) -> Dict[int, int]:
        """Return count of nodes per layer."""
        summary: Dict[int, int] = {i: 0 for i in range(1, 8)}
        for node in self._nodes.values():
            if node.layer in summary:
                summary[node.layer] += 1
        return summary

    def __repr__(self) -> str:
        return f"NodeRegistry(nodes={len(self._nodes)}, layers={list(LAYERS.values())})"
