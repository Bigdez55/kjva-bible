#!/usr/bin/env python3
"""Generate a context packet for a target agent persona."""
import argparse, yaml
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--persona", required=True)
    ap.add_argument("--task", default="general")
    args = ap.parse_args()
    persona_path = ROOT / "12_agents" / "personas" / f"{args.persona}.yaml"
    persona = yaml.safe_load(persona_path.read_text())
    truth = yaml.safe_load((ROOT/"19_truth_state/current.truth.yaml").read_text())
    packet = {
        "id": f"CP-{args.persona}-{args.task}",
        "target_agent": args.persona,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "sections": [
            {"name":"persona","data":persona},
            {"name":"truth_state","data":truth},
            {"name":"source_ranking","ref":"19_truth_state/source_of_truth_ranking.yaml"},
            {"name":"task","data":{"task":args.task}},
            {"name":"relevant_skills","ref":"13_skills/skills.registry.yaml"},
            {"name":"playbook_index","ref":"37_command_protocol/commands.registry.yaml"},
        ],
    }
    out = ROOT / "42_context_compiler" / "output" / "generated" / f"{packet['id']}.yaml"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(yaml.safe_dump(packet, sort_keys=False))
    print(f"Wrote {out}")

if __name__ == "__main__":
    main()
