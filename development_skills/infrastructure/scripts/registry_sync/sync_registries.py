#!/usr/bin/env python3
"""Derive every *.registry.yaml from disk. --check fails on drift, --write rewrites."""
import argparse, sys, yaml
from pathlib import Path
from datetime import date

ROOT = Path(__file__).resolve().parents[2]
TODAY = date.today().isoformat()

# (registry_path, scan_dir, glob, key_extractor)
RULES = [
    ("platform/sdlc/13_skills/skills.registry.yaml",       "platform/sdlc/13_skills/active",        "*.yaml",          "skill"),
    ("14_templates/templates.registry.yaml", "14_templates",            "*/*.template.*",  "template"),
    ("schemas/schemas.registry.yaml",     "26_schemas",              "*/*.schema.json", "schema"),
    ("infrastructure/scripts/automation.registry.yaml","infrastructure/scripts",          "**/*.py",         "automation"),
    ("39_repo_twins/repo_twins.registry.yaml","39_repo_twins/twins",    "*",               "twin"),
    ("04_architecture/diagrams/diagrams.registry.yaml","04_architecture/diagrams/source","**/*.mmd","diagram"),
    ("16_knowledge/knowledge.registry.yaml", "16_knowledge",            "**/*.md",         "knowledge"),
    ("24_prompt_library/prompts.registry.yaml","24_prompt_library",     "**/*.md",         "prompt"),
    ("12_agents/agents.registry.yaml",       "12_agents/personas",      "*.yaml",          "agent"),
    ("03_specs/specs.registry.yaml",         "03_specs",                "**/*.yaml",       "spec"),
    ("05_workflows/workflows.registry.yaml", "05_workflows",            "*.workflow.yaml", "workflow"),
    ("06_planning/plans.registry.yaml",      "06_planning/plans",       "*.md",            "plan"),
    ("08_verification/verification_ledger.yaml","08_verification/skill_tests","*.yaml",    "test"),
    ("09_release/releases.registry.yaml",    "09_release",              "RELEASE-*.yaml",  "release"),
    ("17_retrospectives/retros.registry.yaml","17_retrospectives",      "RETRO-*.md",      "retro"),
    ("20_drift_detection/drift.registry.yaml","20_drift_detection/drift_reports","*.json","drift"),
    ("22_vertical_slices/slices.registry.yaml","22_vertical_slices",    "SLICE-*.yaml",    "slice"),
    ("23_evidence/evidence.registry.yaml",   "23_evidence/evidence_packets","*.yaml",      "evidence"),
    ("31_architecture_digital_twin/twin.registry.yaml","31_architecture_digital_twin/twins","*","digital_twin"),
    ("32_execution_cinema/cinema.registry.yaml","32_execution_cinema/recordings","*.yaml", "recording"),
    ("33_preview_deployment_factory/preview.registry.yaml","33_preview_deployment_factory/preview_plans","*.yaml","preview"),
    ("34_environment_passport/passport.registry.yaml","34_environment_passport/passports","*.yaml","passport"),
    ("35_synthetic_reality_lab/synth.registry.yaml","35_synthetic_reality_lab/scenarios","*.yaml","scenario"),
    ("36_proof_matrix/proof.registry.yaml",  "36_proof_matrix",         "*.yaml",          "proof"),
    ("21_repo_sync/repo_sync.registry.yaml", "21_repo_sync/sync_packets","*.yaml",         "sync_packet"),
    ("40_citadel_bridge/bridge.registry.yaml","40_citadel_bridge/messages","*.yaml",       "bridge_msg"),
    ("41_storbits_memory_layer/memory.registry.yaml","41_storbits_memory_layer/memory_records","*.yaml","memory"),
    ("42_context_compiler/compiler.registry.yaml","42_context_compiler/output/generated","*.yaml","context_pkt"),
    ("43_project_consolidation/consolidation.registry.yaml","43_project_consolidation/consolidation_packets","*.yaml","consolidation"),
    ("01_vision/vision.registry.yaml",       "01_vision",               "VISION-*.md",     "vision"),
    ("02_discovery/discovery.registry.yaml", "02_discovery/research_notes","*.md",         "discovery"),
    ("00_intake/intake.registry.yaml",       "00_intake/intake_packets", "*.yaml",         "intake"),
    ("15_governance/governance.registry.yaml","15_governance/policies",  "*.md",           "policy"),
    ("28_archive/archive.registry.yaml",     "28_archive",              "**/*",            "archive"),
    ("29_intent_compiler/intents.registry.yaml","29_intent_compiler/compiled","*.yaml",    "intent"),
    ("30_repo_starter/starter.registry.yaml","30_repo_starter/starter_packets","*.yaml",   "starter"),
    ("platform/systems/38_bookworm_engine/bookworm.registry.yaml","platform/systems/38_bookworm_engine/indexing","*.yaml",   "bw_index"),
]

def scan(scan_dir, glob):
    base = ROOT / scan_dir
    if not base.exists():
        return []
    items = []
    for p in sorted(base.glob(glob)):
        if p.name.startswith('.') or p.name == 'README.md':
            continue
        rel = p.relative_to(ROOT).as_posix()
        items.append({"name": p.stem if p.is_file() else p.name, "path": rel})
    return items

def build(rule):
    reg, scan_dir, glob, key = rule
    if reg == "12_agents/agents.registry.yaml":
        return build_agents_registry(rule)
    items = scan(scan_dir, glob)
    reg_path = ROOT / reg
    last_updated = TODAY
    if reg_path.exists():
        try:
            old = yaml.safe_load(reg_path.read_text()) or {}
            old_items = old.get(f"{key}s", [])
            if old_items == items:
                last_updated = old.get("last_updated", TODAY)
        except Exception:
            pass
    return {
        "last_updated": last_updated,
        "scan_dir": scan_dir,
        "total": len(items),
        f"{key}s": items,
    }

def _safe_yaml(path):
    if not path.exists():
        return {}
    try:
        return yaml.safe_load(path.read_text()) or {}
    except Exception:
        return {}

def build_agents_registry(rule):
    reg, scan_dir, glob, key = rule
    items = scan(scan_dir, glob)

    definitions_path = ROOT / "12_agents/imported_claude_agents/claude_agents.registry.yaml"
    surfaces_path = ROOT / "12_agents/imported_claude_agent_surfaces/claude_agent_surfaces.registry.yaml"
    definitions = _safe_yaml(definitions_path)
    surfaces = _safe_yaml(surfaces_path)

    if definitions_path.exists():
        items.append(
            {
                "name": "imported_claude_agent_definitions",
                "path": definitions_path.relative_to(ROOT).as_posix(),
                "source": "claude_agent_surface_registry",
                "type": "agent_definition_registry",
                "count": len(definitions.get("agents", []) or []),
            }
        )
    if surfaces_path.exists():
        items.append(
            {
                "name": "imported_claude_agent_surfaces",
                "path": surfaces_path.relative_to(ROOT).as_posix(),
                "source": "claude_agent_surface_registry",
                "type": "agent_surface_registry",
                "count": surfaces.get("unique_category_hash_entries", 0),
                "source_file_count": surfaces.get("total_source_files", 0),
                "categories": surfaces.get("unique_counts_by_category", {}) or {},
            }
        )

    reg_path = ROOT / reg
    last_updated = TODAY
    if reg_path.exists():
        try:
            old = yaml.safe_load(reg_path.read_text()) or {}
            old_items = old.get(f"{key}s", [])
            if old_items == items:
                last_updated = old.get("last_updated", TODAY)
        except Exception:
            pass

    return {
        "last_updated": last_updated,
        "scan_dir": f"{scan_dir} + imported Claude agent registries",
        "total": len(items),
        f"{key}s": items,
        "import_summary": {
            "claude_agent_definitions": len(definitions.get("agents", []) or []),
            "claude_agent_surface_source_files": surfaces.get("total_source_files", 0),
            "claude_agent_surface_unique_entries": surfaces.get("unique_category_hash_entries", 0),
            "claude_agent_surface_categories": surfaces.get("unique_counts_by_category", {}) or {},
        },
    }

def write_or_check(check_only):
    drift = []
    for rule in RULES:
        reg_path = ROOT / rule[0]
        new = build(rule)
        new_text = yaml.safe_dump(new, sort_keys=False)
        if reg_path.exists():
            old_text = reg_path.read_text()
            if old_text.strip() == new_text.strip():
                continue
        if check_only:
            drift.append(rule[0])
        else:
            reg_path.parent.mkdir(parents=True, exist_ok=True)
            reg_path.write_text(new_text)
    return drift

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args()
    if not (args.check or args.write):
        args.write = True
    drift = write_or_check(check_only=args.check)
    if args.check and drift:
        print("DRIFT in registries:")
        for d in drift:
            print(f"  {d}")
        sys.exit(1)
    if args.write:
        print(f"Synced {len(RULES)} registries.")
    else:
        print("No drift.")

if __name__ == "__main__":
    main()
