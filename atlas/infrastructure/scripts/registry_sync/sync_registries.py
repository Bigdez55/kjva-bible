#!/usr/bin/env python3
"""Derive every *.registry.yaml from disk. --check fails on drift, --write rewrites."""
import argparse, sys, yaml
from pathlib import Path
from datetime import date

ROOT = Path(__file__).resolve().parents[3]
TODAY = date.today().isoformat()

# (registry_path, scan_dir, glob, key_extractor)
RULES = [
    ("platform/sdlc/13_skills/skills.registry.yaml",       "platform/sdlc/13_skills/active",        "*.yaml",          "skill"),
    ("platform/sdlc/14_templates/templates.registry.yaml", "platform/sdlc/14_templates",            "*/*.template.*",  "template"),
    ("schemas/schemas.registry.yaml",     "schemas",              "*/*.schema.json", "schema"),
    ("infrastructure/scripts/automation.registry.yaml","infrastructure/scripts",          "**/*.py",         "automation"),
    ("platform/systems/39_repo_twins/repo_twins.registry.yaml","platform/systems/39_repo_twins/twins",    "*",               "twin"),
    ("platform/sdlc/04_architecture/diagrams/diagrams.registry.yaml","platform/sdlc/04_architecture/diagrams/source","**/*.mmd","diagram"),
    ("platform/sdlc/16_knowledge/knowledge.registry.yaml", "platform/sdlc/16_knowledge",            "**/*.md",         "knowledge"),
    ("platform/systems/24_prompt_library/prompts.registry.yaml","platform/systems/24_prompt_library",     "**/*.md",         "prompt"),
    ("platform/sdlc/12_agents/agents.registry.yaml",       "platform/sdlc/12_agents/personas",      "*.yaml",          "agent"),
    ("platform/sdlc/03_specs/specs.registry.yaml",         "platform/sdlc/03_specs",                "**/*.yaml",       "spec"),
    ("platform/sdlc/05_workflows/workflows.registry.yaml", "platform/sdlc/05_workflows",            "*.workflow.yaml", "workflow"),
    ("platform/sdlc/06_planning/plans.registry.yaml",      "platform/sdlc/06_planning/plans",       "*.md",            "plan"),
    ("platform/sdlc/08_verification/verification_ledger.yaml","platform/sdlc/08_verification/skill_tests","*.yaml",    "test"),
    ("platform/sdlc/09_release/releases.registry.yaml",    "platform/sdlc/09_release",              "RELEASE-*.yaml",  "release"),
    ("platform/sdlc/17_retrospectives/retros.registry.yaml","platform/sdlc/17_retrospectives",      "RETRO-*.md",      "retro"),
    ("platform/systems/20_drift_detection/drift.registry.yaml","platform/systems/20_drift_detection/drift_reports","*.json","drift"),
    ("platform/systems/22_vertical_slices/slices.registry.yaml","platform/systems/22_vertical_slices",    "SLICE-*.yaml",    "slice"),
    ("platform/systems/23_evidence/evidence.registry.yaml",   "platform/systems/23_evidence/evidence_packets","*.yaml",      "evidence"),
    ("platform/systems/31_architecture_digital_twin/twin.registry.yaml","platform/systems/31_architecture_digital_twin/twins","*","digital_twin"),
    ("platform/systems/32_execution_cinema/cinema.registry.yaml","platform/systems/32_execution_cinema/recordings","*.yaml", "recording"),
    ("platform/systems/33_preview_deployment_factory/preview.registry.yaml","platform/systems/33_preview_deployment_factory/preview_plans","*.yaml","preview"),
    ("platform/systems/34_environment_passport/passport.registry.yaml","platform/systems/34_environment_passport/passports","*.yaml","passport"),
    ("platform/systems/35_synthetic_reality_lab/synth.registry.yaml","platform/systems/35_synthetic_reality_lab/scenarios","*.yaml","scenario"),
    ("platform/systems/36_proof_matrix/proof.registry.yaml",  "platform/systems/36_proof_matrix",         "*.yaml",          "proof"),
    ("platform/systems/21_repo_sync/repo_sync.registry.yaml", "platform/systems/21_repo_sync/sync_packets","*.yaml",         "sync_packet"),
    ("platform/systems/40_citadel_bridge/bridge.registry.yaml","platform/systems/40_citadel_bridge/messages","*.yaml",       "bridge_msg"),
    ("platform/systems/41_storbits_memory_layer/memory.registry.yaml","platform/systems/41_storbits_memory_layer/memory_records","*.yaml","memory"),
    ("platform/systems/42_context_compiler/compiler.registry.yaml","platform/systems/42_context_compiler/output/generated","*.yaml","context_pkt"),
    ("platform/systems/47_project_consolidation/consolidation.registry.yaml","platform/systems/47_project_consolidation/consolidation_packets","*.yaml","consolidation"),
    ("platform/sdlc/01_vision/vision.registry.yaml",       "platform/sdlc/01_vision",               "VISION-*.md",     "vision"),
    ("platform/sdlc/02_discovery/discovery.registry.yaml", "platform/sdlc/02_discovery/research_notes","*.md",         "discovery"),
    ("platform/sdlc/00_intake/intake.registry.yaml",       "platform/sdlc/00_intake/intake_packets", "*.yaml",         "intake"),
    ("platform/sdlc/15_governance/governance.registry.yaml","platform/sdlc/15_governance/policies",  "*.md",           "policy"),
    ("platform/systems/28_archive/archive.registry.yaml",     "platform/systems/28_archive",              "**/*",            "archive"),
    ("platform/systems/29_intent_compiler/intents.registry.yaml","platform/systems/29_intent_compiler/compiled","*.yaml",    "intent"),
    ("platform/systems/30_repo_starter/starter.registry.yaml","platform/systems/30_repo_starter/starter_packets","*.yaml",   "starter"),
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
    if reg == "platform/sdlc/12_agents/agents.registry.yaml":
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

    definitions_path = ROOT / "platform/sdlc/12_agents/imported_claude_agents/claude_agents.registry.yaml"
    surfaces_path = ROOT / "platform/sdlc/12_agents/imported_claude_agent_surfaces/claude_agent_surfaces.registry.yaml"
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
