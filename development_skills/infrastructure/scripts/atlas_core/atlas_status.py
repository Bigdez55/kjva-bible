"""Atlas status model builder."""

from __future__ import annotations

import subprocess
from typing import Any

from adapters import (
    agents_adapter,
    architecture_adapter,
    bookworm_adapter,
    context_compiler_adapter,
    drift_adapter,
    manifest_adapter,
    proof_matrix_adapter,
    registry_adapter,
    repo_twins_adapter,
    skills_adapter,
    truth_state_adapter,
)
from atlas_models import write_json
from atlas_paths import ROOT, STATUS_DIR, rel


def run_git(args: list[str]) -> str:
    proc = subprocess.run(["git", *args], cwd=ROOT, text=True, capture_output=True)
    return proc.stdout.strip() if proc.returncode == 0 else ""


def protected_untracked() -> list[str]:
    untracked = run_git(["ls-files", "--others", "--exclude-standard"]).splitlines()
    protected = []
    if any(p == "New updates" or p.startswith("New updates/") for p in untracked):
        protected.append("New updates/")
    return protected


def dirty_state() -> str:
    status = run_git(["status", "--short"]).splitlines()
    if not status:
        return "clean"
    non_protected = [line for line in status if "New updates/" not in line and '"New updates/"' not in line]
    if not non_protected:
        return "clean_except_protected_untracked"
    return "dirty"


def build_status(gate_results: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    truth = truth_state_adapter.load()
    manifests = manifest_adapter.load()
    architecture = architecture_adapter.load()
    bookworm = bookworm_adapter.load()
    repo_twins = repo_twins_adapter.load()
    context = context_compiler_adapter.load()
    skills = skills_adapter.load()
    agents = agents_adapter.load()
    proof = proof_matrix_adapter.load()
    drift = drift_adapter.load()
    registries = registry_adapter.load()
    gates = gate_results or []
    validation_status = "pass" if gates and all(g.get("verdict") == "pass" for g in gates) else "not_run"
    caveats = [
        "No UI was built in Platform Core v0.1.",
        "Atlas Graph Engine and Atlas Knowledge Vault are the proprietary graph and linked-knowledge roots.",
        "Protected New updates/ source intake remains untracked.",
    ]
    if not gates:
        caveats.append("Safe gates have not been run for this status snapshot.")

    status = {
        "atlas_status": {
            "system_name": "SUPER C Atlas",
            "repository_lineage": "Development_Skills",
            "branch": run_git(["branch", "--show-current"]),
            "commit": run_git(["rev-parse", "HEAD"]),
            "dirty_state": dirty_state(),
            "protected_untracked": protected_untracked(),
            "truth_state": truth,
            "manifests": {
                "development_skills_manifest": manifests["development_skills_manifest"],
                "project_manifest": manifests["project_manifest"],
                "apex_version": manifests["apex_version"],
                "bookworm_manifest": manifests["bookworm_manifest"],
            },
            "subsystems": {
                "bookworm": {
                    "status": bookworm["status"],
                    "paths": bookworm["paths"],
                    "index_count": bookworm["index_count"],
                },
                "graph_layer": architecture["graph_layer"],
                "knowledge_mesh": architecture["knowledge_mesh"],
                "repo_twins": repo_twins,
                "context_compiler": context,
                "skills": skills,
                "agents": agents,
                "proof_matrix": proof,
                "drift_detection": drift,
                "registries": registries,
                "validation": {
                    "status": validation_status,
                    "safe_gates": gates,
                },
            },
            "evidence": {
                "generated_files": [
                    "23_evidence/atlas_platform/status/atlas_status.json",
                    "23_evidence/atlas_platform/status/atlas_status.md",
                    "23_evidence/atlas_platform/inventory/atlas_inventory.json",
                    "23_evidence/atlas_platform/inventory/atlas_inventory.md",
                    "23_evidence/atlas_platform/gates/atlas_safe_gate_results.md",
                    "11_documentation/generated/ATLAS_PLATFORM_STATUS.generated.md",
                    "42_context_compiler/output/generated/CP-super-c-atlas-platform-core.yaml",
                    "09_release/release_evidence/2026-05-17_super_c_atlas_platform_core_v0_1_report.md",
                ],
                "validation_outputs": [g.get("stdout_path", "") for g in gates],
            },
            "caveats": caveats,
        }
    }
    return status


def status_markdown(status: dict[str, Any]) -> str:
    atlas = status["atlas_status"]
    lines = [
        "# SUPER C Atlas Platform Status",
        "",
        f"- System: {atlas['system_name']}",
        f"- Repository lineage: {atlas['repository_lineage']}",
        f"- Branch: `{atlas['branch']}`",
        f"- Commit: `{atlas['commit']}`",
        f"- Dirty state: `{atlas['dirty_state']}`",
        "",
        "## Subsystems",
        "",
        "| Subsystem | Status | Evidence |",
        "|---|---|---|",
    ]
    subsystems = atlas["subsystems"]
    for name in [
        "bookworm",
        "graph_layer",
        "knowledge_mesh",
        "repo_twins",
        "context_compiler",
        "skills",
        "agents",
        "proof_matrix",
        "drift_detection",
        "validation",
    ]:
        item = subsystems[name]
        evidence = item.get("registry") or ", ".join(item.get("paths", [])[:3]) or str(item.get("count", ""))
        lines.append(f"| `{name}` | `{item.get('status', 'unknown')}` | {evidence} |")
    lines.extend(["", "## Caveats", ""])
    for caveat in atlas["caveats"]:
        lines.append(f"- {caveat}")
    lines.append("")
    return "\n".join(lines)


def write_status(status: dict[str, Any]) -> None:
    STATUS_DIR.mkdir(parents=True, exist_ok=True)
    write_json(STATUS_DIR / "atlas_status.json", status)
    (STATUS_DIR / "atlas_status.md").write_text(status_markdown(status))


def load_gate_results_if_present() -> list[dict[str, Any]]:
    from atlas_models import read_yaml

    path = ROOT / "08_verification" / "gate_results" / "atlas_platform_core_safe_gates.yaml"
    data = read_yaml(path)
    return data.get("safe_gates", []) if data else []
