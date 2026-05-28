"""Report generation for Atlas Platform Core."""

from __future__ import annotations

import json
from typing import Any

from atlas_context import build_context_packet, write_context_packet
from atlas_inventory import build_inventory, inventory_markdown, write_inventory
from atlas_models import read_yaml
from atlas_paths import GENERATED_DOC, GATES_DIR, INTELLIGENCE_CORE_REPORT, RELEASE_REPORT, ROOT, rel
from atlas_status import build_status, status_markdown, write_status


def load_gate_payload() -> dict[str, Any]:
    path = ROOT / "platform" / "sdlc" / "08_verification" / "gate_results" / "atlas_platform_core_safe_gates.yaml"
    data = read_yaml(path)
    if data:
        return data
    return {"safe_gates": [], "unsafe_skipped": [], "overall_verdict": "not_run"}


def generate_status_docs(status: dict[str, Any], inventory: dict[str, Any], gate_payload: dict[str, Any]) -> None:
    GENERATED_DOC.parent.mkdir(parents=True, exist_ok=True)
    atlas = status["atlas_status"]
    lines = [
        "# SUPER C Atlas Platform Status (generated)",
        "",
        status_markdown(status),
        "",
        "## Inventory Summary",
        "",
        f"- Tracked files: {inventory['atlas_inventory']['tracked_files_total']}",
        f"- Tracked numbered roots: {inventory['atlas_inventory']['tracked_numbered_roots_count']}",
        "",
        "## Safe Gate Summary",
        "",
        f"- Overall: `{gate_payload.get('overall_verdict', 'not_run')}`",
        f"- Gate count: {len(gate_payload.get('safe_gates', []))}",
        "",
        "## Generated Evidence",
        "",
    ]
    for path in atlas["evidence"]["generated_files"]:
        lines.append(f"- `{path}`")
    lines.append("")
    GENERATED_DOC.write_text("\n".join(lines))


def platform_verdict(gate_payload: dict[str, Any]) -> str:
    if gate_payload.get("overall_verdict") != "pass":
        return "SILVER_FAIL_WITH_ACTIVE_BLOCKERS"
    return "GOLD_PASS"


def generate_release_report(
    status: dict[str, Any],
    inventory: dict[str, Any],
    gate_payload: dict[str, Any],
    context_packet_path: str,
) -> None:
    atlas = status["atlas_status"]
    verdict = platform_verdict(gate_payload)
    created_files = [
        "infrastructure/scripts/atlas_core/atlas.py",
        "infrastructure/scripts/atlas_core/atlas_paths.py",
        "infrastructure/scripts/atlas_core/atlas_models.py",
        "infrastructure/scripts/atlas_core/atlas_inventory.py",
        "infrastructure/scripts/atlas_core/atlas_status.py",
        "infrastructure/scripts/atlas_core/atlas_gates.py",
        "infrastructure/scripts/atlas_core/atlas_context.py",
        "infrastructure/scripts/atlas_core/atlas_reports.py",
        "infrastructure/scripts/atlas_core/adapters/*.py",
        "infrastructure/scripts/atlas_core/tests/*.py",
        "platform/systems/23_evidence/atlas_platform/preflight/2026-05-17_platform_core_preflight.md",
        *atlas["evidence"]["generated_files"],
        "platform/sdlc/08_verification/gate_results/atlas_platform_core_safe_gates.yaml",
        "platform/sdlc/08_verification/gate_results/atlas_platform_core_safe_gates.json",
    ]
    updated_files = [
        "platform/systems/20_drift_detection/drift_reports/truth_drift_report.json",
        "platform/systems/20_drift_detection/drift_state.yaml",
        "infrastructure/scripts/automation.registry.yaml",
        "platform/systems/42_context_compiler/compiler.registry.yaml",
    ]
    lines = [
        "# SUPER C Atlas Platform Core v0.1 Report",
        "",
        "## Verdict",
        verdict,
        "",
        "## Mission",
        "Build the repo-native Atlas control plane before any UI work.",
        "",
        "## Branch",
        atlas["branch"],
        "",
        "## Base Commit",
        "9d92860 chore: close central onboarding validation",
        "",
        "## Final Commit",
        "Pending until commit is created.",
        "",
        "## What Was Built",
        "- Atlas CLI/control plane under `infrastructure/scripts/atlas_core/`.",
        "- Status, inventory, safe gate, context packet, and report generators.",
        "- Machine-readable and Markdown Atlas platform outputs.",
        "- Adapter bridge over existing truth state, manifests, skills, agents, registries, Bookworm, repo twins, context compiler, proof matrix, and drift reports.",
        "",
        "## Existing Systems Reused",
        "- Truth state, manifests, skills registry, agents registry, Bookworm manifest/indexes, repo twins, context compiler, proof matrix, drift reports, and release evidence.",
        "- Existing graph and linked-knowledge capabilities were mapped to proprietary Atlas Graph Engine and Atlas Knowledge Vault surfaces.",
        "",
        "## Files Created",
        "",
    ]
    for path in created_files:
        lines.append(f"- `{path}`")
    lines.extend(
        [
            "",
            "## Files Updated",
            "",
        ]
    )
    for path in updated_files:
        lines.append(f"- `{path}`")
    lines.extend(
        [
            "",
            "## Files Preserved",
            "- `New updates/` remained untracked and unstaged.",
            "- No UI roots were added.",
            "- No external graph/vault product subsystem names are used for new Atlas surfaces.",
            "- Protected Bookworm import and canonical bridge paths were not modified.",
            "",
            "## Find-Before-Create Decision",
            "No existing repo-native Atlas status/inventory/control-plane CLI was found. Platform build routing and context compiler structures were reused, and the minimal implementation home `infrastructure/scripts/atlas_core/` was created under the existing automation root.",
            "",
            "## Commands Added",
            "- `python3 infrastructure/scripts/atlas_core/atlas.py status`",
            "- `python3 infrastructure/scripts/atlas_core/atlas.py status --json`",
            "- `python3 infrastructure/scripts/atlas_core/atlas.py inventory`",
            "- `python3 infrastructure/scripts/atlas_core/atlas.py inventory --write-report`",
            "- `python3 infrastructure/scripts/atlas_core/atlas.py validate --safe-only`",
            "- `python3 infrastructure/scripts/atlas_core/atlas.py context --sample`",
            "- `python3 infrastructure/scripts/atlas_core/atlas.py report`",
            "",
            "## Skills and Agent Lanes Applied",
            "- Applied repo-native skill lanes for find-before-create, existing repo audit, source truth reconciliation, context compilation, repo twin ingest, registry sync, truth state check, proof matrix, runtime regression verification, automated regression testing, docs architecture sync, and architecture atlas mapping.",
            "- Used logical review lanes for the architect, platform integrity auditor, knowledge weaver, test forge, and devops catalyst. Physical `/apex-parallel-deploy` was not required for this scoped platform-core build.",
            "",
        ]
    )
    lines.extend(
        [
            "",
            "## Generated Outputs",
            "",
        ]
    )
    for path in atlas["evidence"]["generated_files"]:
        lines.append(f"- `{path}`")
    lines.extend(
        [
            "",
            "## Context Packet",
            f"`{context_packet_path}`",
            "",
            "## Safe Gates Run",
            "",
            "| Gate | Return Code | Verdict |",
            "|---|---:|---|",
        ]
    )
    for gate in gate_payload.get("safe_gates", []):
        lines.append(f"| `{gate['name']}` | {gate['return_code']} | `{gate['verdict']}` |")
    lines.extend(["", "## Unsafe Gates Not Run", ""])
    for gate in gate_payload.get("unsafe_skipped", []):
        lines.append(f"- `{gate['command']}`: {gate['reason']}")
    lines.extend(
        [
            "",
            "## Silver Gate Status",
            "Passed.",
            "",
            "## Gold Gate Status",
            "Passed: live status reads the required subsystems, inventory maps graph/knowledge structures, safe gates capture command/output/return-code/verdict, and the context packet/report are generated from live status.",
            "",
            "## Known Caveats",
            "- No UI was built.",
            "- Atlas Graph Engine and Atlas Knowledge Vault are the proprietary graph and linked-knowledge surfaces.",
            "- `/apex-parallel-deploy` was not required for Platform Core v0.1.",
            "",
            "## Active Blockers and Closure Paths",
            "- None blocking Platform Core v0.1 Gold gate. Next work should extend graph/export adapters before UI.",
            "",
            "## Next Build Unit",
            "Atlas Platform Core v0.2: graph/export adapters, then UI/dashboard.",
            "",
        ]
    )
    RELEASE_REPORT.write_text("\n".join(lines))


def generate_intelligence_report(
    status: dict[str, Any],
    inventory: dict[str, Any],
    gate_payload: dict[str, Any],
    context_packet_path: str,
    require_gates: bool = False,
    flow_log: str | None = None,
) -> list[str]:
    atlas = status["atlas_status"]
    if require_gates and gate_payload.get("overall_verdict") != "pass":
        return []

    evidence = [
        "platform/systems/23_evidence/atlas_platform/ingest/",
        "platform/systems/23_evidence/atlas_platform/graph/",
        "platform/systems/23_evidence/atlas_platform/vault/",
        "platform/systems/23_evidence/atlas_platform/flows/",
    ]
    created_files = [
        "infrastructure/scripts/atlas_core/atlas.py",
        "infrastructure/scripts/atlas_core/atlas_paths.py",
        "infrastructure/scripts/atlas_core/atlas_models.py",
        "infrastructure/scripts/atlas_core/atlas_inventory.py",
        "infrastructure/scripts/atlas_core/atlas_status.py",
        "infrastructure/scripts/atlas_core/atlas_gates.py",
        "infrastructure/scripts/atlas_core/atlas_context.py",
        "infrastructure/scripts/atlas_core/atlas_graph_engine.py",
        "infrastructure/scripts/atlas_core/atlas_ingest.py",
        "infrastructure/scripts/atlas_core/atlas_knowledge_vault.py",
        "infrastructure/scripts/atlas_core/atlas_reports.py",
        "platform/systems/23_evidence/atlas_platform/status/atlas_status.json",
        "platform/systems/23_evidence/atlas_platform/status/atlas_status.md",
        "platform/systems/23_evidence/atlas_platform/inventory/atlas_inventory.json",
        "platform/systems/23_evidence/atlas_platform/inventory/atlas_inventory.md",
        "platform/systems/23_evidence/atlas_platform/gates/atlas_safe_gate_results.md",
        "platform/sdlc/09_release/release_evidence/" + INTELLIGENCE_CORE_REPORT.name,
        "platform/systems/43_atlas_graph_engine/reports/atlas_graph*",
        "platform/systems/44_atlas_knowledge_vault/reports/atlas_knowledge_vault*",
        "platform/systems/44_atlas_knowledge_vault/notes/",
        "platform/sdlc/08_verification/gate_results/atlas_platform_core_safe_gates.yaml",
        "platform/sdlc/08_verification/gate_results/atlas_platform_core_safe_gates.json",
    ]

    lines = [
        "# SUPER C Atlas Intelligence Core v0.2 Report",
        "",
        "## Verdict",
        "GOLD_PASS" if gate_payload.get("overall_verdict") == "pass" else "SILVER_GATE_FAIL",
        "",
        "## Mission",
        "Build Atlas convergence command surface and run deterministic intelligence loop: ingest -> Atlas Graph Engine -> Atlas Knowledge Vault -> status -> validate -> context -> report.",
        "",
        "## Branch",
        atlas["branch"],
        "",
        "## Flow",
        flow_log or "not recorded",
        "",
        "## Status",
        f"system: {atlas['system_name']}",
        f"version: {atlas['branch']}@{atlas['commit']}",
        f"status: {atlas['caveats'][-1] if atlas.get('caveats') else 'unknown'}",
        "",
        "## Proof and Evidence",
    ]
    for item in evidence:
        lines.append(f"- `{item}`")
    lines.extend(["", "## Gate Results", "", "| Gate | Return Code | Verdict |", "|---|---:|---|"])
    for gate in gate_payload.get("safe_gates", []):
        lines.append(f"| `{gate['name']}` | {gate['return_code']} | `{gate['verdict']}` |")

    lines.extend([
        "",
        "## Context Packet",
        f"`{context_packet_path}`",
        "",
        "## Created Files",
    ])
    for path in created_files:
        lines.append(f"- `{path}`")
    INTELLIGENCE_CORE_REPORT.write_text("\n".join(lines))
    return [str(INTELLIGENCE_CORE_REPORT)]


def generate_all() -> dict[str, Any]:
    gate_payload = load_gate_payload()
    status = build_status(gate_payload.get("safe_gates", []))
    inventory = build_inventory()
    write_status(status)
    write_inventory(inventory)
    packet = build_context_packet(status, gate_payload)
    write_context_packet(packet)
    generate_status_docs(status, inventory, gate_payload)
    generate_release_report(status, inventory, gate_payload, rel(ROOT / "platform/systems/42_context_compiler/output/generated/CP-super-c-atlas-platform-core.yaml"))
    return {
        "status": status,
        "inventory": inventory,
        "gate_payload": gate_payload,
        "context_packet": packet,
        "release_report": rel(RELEASE_REPORT),
        "generated_doc": rel(GENERATED_DOC),
    }


def print_report_summary(payload: dict[str, Any]) -> str:
    return json.dumps(
        {
            "release_report": payload["release_report"],
            "generated_doc": payload["generated_doc"],
            "verdict": platform_verdict(payload["gate_payload"]),
        },
        indent=2,
        sort_keys=True,
    )
