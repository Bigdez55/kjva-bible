#!/usr/bin/env python3
"""Validate Skills Stack v7 repo-native integration artifacts."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]


REQUIRED_PATHS = [
    "16_knowledge/external_collateral/skills_stack_2026-05-17/source_index.yaml",
    "16_knowledge/external_collateral/skills_stack_2026-05-17/native_mapping_report.md",
    "platform/systems/37_command_protocol/trigger_router.yaml",
    "platform/sdlc/13_skills/skill_refinery/trigger_router.md",
    "platform/sdlc/13_skills/skill_refinery/trigger_router.yaml",
    "24_prompt_library/reusable_prompts/trigger_router_instructions.md",
    "schemas/trigger_router/trigger_router.schema.yaml",
    "platform/systems/43_atlas_graph_engine/graphs/trigger_skill.graph.json",
    "44_atlas_knowledge_vault/07_skills/Trigger_Router.md",
    "platform/systems/37_command_protocol/atlas_intelligence_routing.yaml",
    "platform/systems/37_command_protocol/platform_build_routing.yaml",
    "platform/systems/37_command_protocol/existing_repo_audit_routing.yaml",
    "platform/systems/37_command_protocol/ui_wiring_audit_routing.yaml",
    "platform/systems/37_command_protocol/source_truth_drift_routing.yaml",
    "platform/sdlc/13_skills/skill_refinery/master_ledger.yaml",
    "platform/sdlc/13_skills/skill_refinery/recurrence_escalation.yaml",
    "14_templates/platform_build/platform_artifact_manifest.yaml",
    "14_templates/final_reports/skills_stack_v7_final_report.md",
]

REQUIRED_COMMANDS = [
    "route",
    "platform_build",
    "repo_audit",
    "ui_wiring",
    "dataflow_map",
    "refactor_plan",
    "runtime_verify",
]

REQUIRED_ATLAS_COMMANDS = [
    "ingest",
    "graph",
    "knowledge_vault",
    "status",
    "validate",
    "compile_context",
    "report",
    "flow",
]

ROUTER_TESTS = {
    "I want to build LMOS.": {"platform_build", "lmos_platform"},
    "The UI is just a shell.": {"visual_to_system_backbone"},
    "Audit this existing repo.": {"existing_repo_audit"},
    "Buttons and toggles do not work.": {"ui_feature_wiring_audit"},
    "Docs are stale.": {"source_truth_drift"},
    "How is the data coming in and going out?": {"data_reporting_platform"},
    "I want this repo linked to a domain.": {"deployment_domain_repo"},
    "I need an Atlas ingest snapshot.": {"atlas_ingest"},
    "Build the Atlas graph for this repo.": {"atlas_graph_engine"},
    "Export Atlas Knowledge Vault notes now.": {"atlas_knowledge_vault"},
    "What is Atlas status right now?": {"atlas_status"},
    "Run Atlas validate blockers.": {"atlas_validate"},
    "Compile Atlas context for handoff.": {"atlas_compile_context"},
    "Create an Atlas report package.": {"atlas_report"},
    "Run atlas:flow with all convergence steps.": {"atlas_flow"},
}

LAYER_ROUTER_TESTS = {
    "build a platform": {
        "selected_root": "build",
        "selected_noun": "platform",
        "expected_intents": {"platform_build"},
    },
    "build dashboard DeepThink proof one-shot": {
        "selected_root": "build",
        "selected_noun": "dashboard",
        "proof_required": True,
        "output_modifier": "one_shot",
    },
    "research on X, Y, and Z with verify evidence": {
        "selected_root": "research",
        "selected_noun": "research",
        "proof_required": True,
    },
    "reconcile contract": {
        "selected_root": "reconcile",
        "selected_noun": "contract",
    },
    "/atlas:graph": {
        "selected_noun": "atlas",
        "selected_target": "atlas_graph_engine",
        "expected_intents": {"atlas_graph_engine"},
    },
    "/atlas:knowledge_vault": {
        "selected_noun": "atlas",
        "selected_target": "atlas_knowledge_vault",
        "expected_intents": {"atlas_knowledge_vault"},
    },
    "wrong target re-read missed it": {
        "corrective": "wrong_target",
    },
}


def check_path(rel: str) -> list[str]:
    return [] if (ROOT / rel).exists() else [f"missing {rel}"]


def run(cmd: list[str]) -> tuple[int, str]:
    proc = subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True)
    return proc.returncode, (proc.stdout + proc.stderr).strip()


def validate_json(path: Path) -> list[str]:
    try:
        json.loads(path.read_text())
        return []
    except Exception as exc:
        return [f"{path.relative_to(ROOT)} invalid JSON: {exc}"]


def main() -> int:
    failures: list[str] = []

    for rel in REQUIRED_PATHS:
        failures.extend(check_path(rel))
    for slug in REQUIRED_COMMANDS:
        failures.extend(check_path(f"platform/systems/37_command_protocol/slash_commands/apex_{slug}.md"))
        failures.extend(check_path(f"platform/systems/37_command_protocol/command_playbooks/apex_{slug}.playbook.md"))
    for slug in REQUIRED_ATLAS_COMMANDS:
        failures.extend(check_path(f"platform/systems/37_command_protocol/slash_commands/atlas_{slug}.md"))
        failures.extend(check_path(f"platform/systems/37_command_protocol/command_playbooks/atlas_{slug}.playbook.md"))
    for tid in ["REG-006", "REG-007", "REG-008", "REG-009", "REG-010"]:
        failures.extend(check_path(f"08_verification/regression_cases/{tid}.yaml"))

    for rel in [
        "schemas/skill/skill.schema.json",
        "schemas/correction_ledger/correction_ledger.schema.json",
        "schemas/trigger_router/trigger_router.schema.json",
        "schemas/regression_case/regression_case.schema.json",
        "schemas/skill_matrix/skill_matrix.schema.json",
        "schemas/source_import_manifest/source_import_manifest.schema.json",
        "schemas/platform_artifact_manifest/platform_artifact_manifest.schema.json",
    ]:
        failures.extend(validate_json(ROOT / rel))

    source_index = yaml.safe_load((ROOT / "16_knowledge/external_collateral/skills_stack_2026-05-17/source_index.yaml").read_text())
    if len(source_index.get("sources", []) or []) < 11:
        failures.append("source_index.yaml must list all 11 source files")

    sys.path.insert(0, str(ROOT / "infrastructure/scripts"))
    from route_intent import route_text

    for text, expected in ROUTER_TESTS.items():
        actual = set(route_text(text).get("matched_intents", []) or [])
        missing = expected - actual
        if missing:
            failures.append(f"router miss for {text!r}: missing {sorted(missing)}, actual={sorted(actual)}")

    for text, expected in LAYER_ROUTER_TESTS.items():
        routed = route_text(text)
        if expected.get("selected_root") and routed.get("selected_root") != expected["selected_root"]:
            failures.append(f"router root miss for {text!r}: expected={expected['selected_root']}, actual={routed.get('selected_root')}")
        if expected.get("selected_noun") and routed.get("selected_noun") != expected["selected_noun"]:
            failures.append(f"router noun miss for {text!r}: expected={expected['selected_noun']}, actual={routed.get('selected_noun')}")
        if expected.get("selected_target") and routed.get("selected_target") != expected["selected_target"]:
            failures.append(f"router target miss for {text!r}: expected={expected['selected_target']}, actual={routed.get('selected_target')}")
        if expected.get("proof_required") is not None and routed.get("proof_requirements", {}).get("required") != expected["proof_required"]:
            failures.append(f"router proof miss for {text!r}: expected={expected['proof_required']}, actual={routed.get('proof_requirements')}")
        if expected.get("output_modifier") and expected["output_modifier"] not in routed.get("active_output_contract", {}).get("modifiers", []):
            failures.append(f"router output modifier miss for {text!r}: expected={expected['output_modifier']}, actual={routed.get('active_output_contract')}")
        if expected.get("corrective") and routed.get("corrective_override", {}).get("trigger") != expected["corrective"]:
            failures.append(f"router corrective miss for {text!r}: expected={expected['corrective']}, actual={routed.get('corrective_override')}")
        if expected.get("expected_intents"):
            actual = set(routed.get("matched_intents", []) or [])
            missing = expected["expected_intents"] - actual
            if missing:
                failures.append(f"router layered intent miss for {text!r}: missing {sorted(missing)}, actual={sorted(actual)}")

    code, out = run(["python3", "infrastructure/scripts/regression_runner.py"])
    if code != 0:
        failures.append(out)

    code, out = run(["python3", "infrastructure/scripts/validate_trigger_determinism.py"])
    if code != 0:
        failures.append(out)

    code, out = run(["python3", "infrastructure/scripts/validate_skill_router_integration.py"])
    if code != 0:
        failures.append(out)

    if failures:
        print("FAIL: Skills Stack v7 validation")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print("PASS: Skills Stack v7 validation")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
