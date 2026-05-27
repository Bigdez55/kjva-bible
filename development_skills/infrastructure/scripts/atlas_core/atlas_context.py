"""Context packet generation for Atlas Platform Core."""

from __future__ import annotations

from typing import Any

from atlas_models import write_yaml
from atlas_paths import CONTEXT_PACKET


def build_context_packet(
    status: dict[str, Any],
    gate_payload: dict[str, Any] | None = None,
    ingest_snapshot: dict[str, Any] | None = None,
    graph_payload: dict[str, Any] | None = None,
    vault_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    atlas = status["atlas_status"]
    gates = gate_payload or {"safe_gates": atlas["subsystems"]["validation"].get("safe_gates", []), "overall_verdict": "not_run"}
    flow_refs = {
        "ingest": ingest_snapshot.get("run_id", "not_run") if isinstance(ingest_snapshot, dict) else "not_run",
        "graph": graph_payload.get("graph_id", "not_run") if isinstance(graph_payload, dict) else "not_run",
        "vault": vault_payload.get("vault_id", "not_run") if isinstance(vault_payload, dict) else "not_run",
    }
    return {
        "context_packet_id": "CP-super-c-atlas-platform-core",
        "mission": "Atlas Intelligence Core convergence packet for ingest, Atlas Graph Engine, Atlas Knowledge Vault, status, validation, and report synthesis.",
        "system_name": atlas["system_name"],
        "repository_lineage": atlas["repository_lineage"],
        "branch": atlas["branch"],
        "commit": atlas["commit"],
        "truth_state": atlas["truth_state"],
        "intelligence_flow": flow_refs,
        "subsystem_status": {
            name: value.get("status", "unknown") for name, value in atlas["subsystems"].items() if isinstance(value, dict)
        },
        "safe_gates": gates.get("safe_gates", []),
        "active_caveats": atlas["caveats"],
        "evidence": {
            "ingest_source_count": len((ingest_snapshot or {}).get("source", {}).get("registries", [])),
            "graph_node_count": len((graph_payload or {}).get("nodes", [])),
            "knowledge_vault_notes": len((vault_payload or {}).get("notes", [])),
        },
        "next_implementation_unit": "Atlas Intelligence Core v0.2: convergence command surface + next flow hardening.",
    }


def write_context_packet(packet: dict[str, Any]) -> None:
    CONTEXT_PACKET.parent.mkdir(parents=True, exist_ok=True)
    write_yaml(CONTEXT_PACKET, packet)
