#!/usr/bin/env python3
"""Validate Repo Onboarding tiers (T1-T4) for any repo containing atlas/."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Iterable

try:
    import yaml
except Exception:  # pragma: no cover
    yaml = None


@dataclass
class Check:
    id: str
    ok: bool
    detail: str


def parse_tiers(raw: str) -> list[int]:
    text = raw.strip().lower()
    if text in {"all", "1-4", "t1-t4"}:
        return [1, 2, 3, 4]
    out: list[int] = []
    for part in text.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            a, b = part.split("-", 1)
            out.extend(range(int(a), int(b) + 1))
        else:
            out.append(int(part))
    out = sorted(set(out))
    for t in out:
        if t < 1 or t > 4:
            raise ValueError(f"invalid tier: {t}")
    return out


def resolve_target_repo(target: Path) -> tuple[Path, Path]:
    target = target.resolve()
    if (target / "atlas").exists():
        return target, (target / "atlas")
    if target.name.lower() == "atlas" and target.exists():
        return target, target
    if (
        target.exists()
        and (target / "atlas.manifest.yaml").exists()
        and (target / "13_skills").exists()
        and (target / "19_truth_state").exists()
    ):
        return target, target
    raise FileNotFoundError(
        f"target must be a repo root with atlas/ or a atlas dir: {target}"
    )


def read_yaml(p: Path):
    if not p.exists() or yaml is None:
        return None
    try:
        return yaml.safe_load(p.read_text())
    except Exception:
        return None


def run_cmd(cmd: list[str], cwd: Path) -> tuple[int, str]:
    r = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True)
    txt = (r.stdout or "") + ("\n" + r.stderr if r.stderr else "")
    return r.returncode, txt.strip()


def find_files(base: Path, pattern: str) -> list[Path]:
    if not base.exists():
        return []
    return sorted(base.rglob(pattern))


def non_placeholder_file(p: Path) -> bool:
    if not p.exists():
        return False
    text = p.read_text(errors="ignore").strip()
    if not text:
        return False
    bad_fragments = ["components: []", "relationships: []", "dependencies: []", "diagrams: []", "pending_ingestion"]
    return not any(frag in text for frag in bad_fragments)


def has_nonempty_markdown(p: Path) -> bool:
    if not p.exists():
        return False
    lines = [ln.strip() for ln in p.read_text(errors="ignore").splitlines() if ln.strip()]
    content_lines = [ln for ln in lines if not ln.startswith("#")]
    return len(content_lines) > 0


def pick_twin_root(repo_name: str, preferred_central: Path, ds: Path) -> Path:
    """Resolve where repo twins are tracked.

    Priority:
    1) Explicit/derived central ATLAS checkout (preferred_central)
    2) The target repo's local atlas copy (ds)
    """
    roots = [preferred_central, ds]
    for root in roots:
        twin = find_twin_dir(root, repo_name)
        if twin.exists():
            return root
    return preferred_central


def normalize_token(raw: str) -> str:
    return raw.lower().replace("-", "_")


def find_twin_dir(root: Path, repo_name: str) -> Path:
    base = root / "39_repo_twins" / "twins"
    exact = base / repo_name
    if exact.exists():
        return exact
    target = normalize_token(repo_name)
    if base.exists():
        for child in base.iterdir():
            if child.is_dir() and normalize_token(child.name) == target:
                return child
    return exact


def matches_repo(path: Path, repo_name: str) -> bool:
    target = normalize_token(repo_name)
    if target in normalize_token(path.stem):
        return True
    body = read_yaml(path) or {}
    candidates = [
        body.get("repo_name"),
        body.get("repo"),
        body.get("repository"),
        body.get("repository_full_name"),
    ]
    return any(value and normalize_token(str(value).split("/")[-1]) == target for value in candidates)


def tier1(repo_root: Path, ds: Path, central: Path, repo_name: str) -> list[Check]:
    checks: list[Check] = []

    truth = ds / "19_truth_state" / "current.truth.yaml"
    checks.append(Check("T1.truth_file", truth.exists(), str(truth)))

    diagram_root = ds / "04_architecture" / "diagrams" / "source"
    mmd = [p.as_posix().lower() for p in find_files(diagram_root, "*.mmd")]
    required = [
        "system_context",
        "component_map",
        "data_flow",
        "execution_sequence",
        "dependency_impact",
        "test_coverage",
        "deployment_impact",
    ]
    missing = [k for k in required if not any(k in p for p in mmd)]
    checks.append(Check("T1.mandated_diagrams", len(missing) == 0, f"missing={missing}" if missing else "all present"))

    sync_script = ds / "infrastructure/scripts" / "registry_sync" / "sync_registries.py"
    if sync_script.exists():
        code, out = run_cmd(["python3", str(sync_script), "--check"], cwd=ds)
        checks.append(Check("T1.registry_sync_check", code == 0, out[:400]))
    else:
        checks.append(Check("T1.registry_sync_check", False, f"missing {sync_script}"))

    ep_dir = ds / "23_evidence" / "evidence_packets"
    tier1_eps = [p for p in find_files(ep_dir, "*.yaml") if "tier1" in p.name.lower() or "onboarding-tier1" in p.name.lower()]
    checks.append(Check("T1.drift_evidence_packet", len(tier1_eps) > 0, ", ".join(p.name for p in tier1_eps) or "none"))

    twin_root = pick_twin_root(repo_name, central, ds)
    twin = find_twin_dir(twin_root, repo_name)
    twin_files = [
        twin / "current.truth.yaml",
        twin / "architecture.snapshot.yaml",
        twin / "component.graph.yaml",
        twin / "dependency.graph.yaml",
        twin / "diagram.registry.yaml",
        twin / "sync_status.yaml",
    ]
    twin_ok = twin.exists() and all(p.exists() for p in twin_files)
    populated = all(non_placeholder_file(p) for p in twin_files[1:]) if twin_ok else False
    checks.append(Check("T1.repo_twin_populated", twin_ok and populated, f"{twin} (root={twin_root})"))

    if truth.exists() and (repo_root / ".git").exists():
        _, remotes = run_cmd(["git", "remote", "-v"], cwd=repo_root)
        t = read_yaml(truth) or {}
        local_only = str(t.get("local_only", "")).lower() == "true"
        stale = bool(remotes.strip()) and local_only
        checks.append(Check("T1.truth_not_stale_local_only", not stale, "local_only=true but git remote exists" if stale else "ok"))

    return checks


def tier2(ds: Path, repo_name: str) -> list[Check]:
    checks: list[Check] = []

    intake_dir = ds / "00_intake" / "intake_packets"
    intake = [p for p in find_files(intake_dir, "IDEA-*.yaml") if repo_name in p.name.lower()]
    valid_intake = False
    if intake:
        body = read_yaml(intake[0]) or {}
        raw = str(body.get("raw_idea", ""))
        valid_intake = bool(raw.strip()) and "placeholder" not in raw.lower() and "gitkeep" not in raw.lower()
    checks.append(Check("T2.intake_packet", valid_intake, intake[0].as_posix() if intake else "none"))

    starter_dir = ds / "30_repo_starter" / "starter_packets"
    starter = [p for p in find_files(starter_dir, "*.yaml") if matches_repo(p, repo_name)]
    checks.append(Check("T2.starter_packet", len(starter) > 0, starter[0].name if starter else "none"))

    slice_dir = ds / "22_vertical_slices"
    slice1 = [p for p in find_files(slice_dir, "SLICE-0001*.yaml")]
    checks.append(Check("T2.first_slice", len(slice1) > 0, slice1[0].name if slice1 else "none"))

    spec_dir = ds / "03_specs" / "functional_requirements"
    specs = find_files(spec_dir, "*.md") + find_files(spec_dir, "*.yaml")
    checks.append(Check("T2.functional_specs", len(specs) > 0, f"count={len(specs)}"))

    adr_dir = ds / "04_architecture" / "adrs"
    adrs = find_files(adr_dir, "ADR-*.md")
    checks.append(Check("T2.baseline_adrs", len(adrs) > 0, f"count={len(adrs)}"))

    ep_dir = ds / "23_evidence" / "evidence_packets"
    tier2_eps = [p for p in find_files(ep_dir, "*.yaml") if "tier2" in p.name.lower() or "onboarding-tier2" in p.name.lower()]
    checks.append(Check("T2.evidence_packet", len(tier2_eps) > 0, ", ".join(p.name for p in tier2_eps) or "none"))

    return checks


def tier3(ds: Path) -> list[Check]:
    checks: list[Check] = []
    slice_dir = ds / "22_vertical_slices"
    slices = [p for p in find_files(slice_dir, "SLICE-*.yaml") if "SLICE-0001" not in p.name]
    checks.append(Check("T3.slice_beyond_0001", len(slices) > 0, f"count={len(slices)}"))

    ep_dir = ds / "23_evidence" / "evidence_packets"
    eps = [p for p in find_files(ep_dir, "*.yaml") if "slice" in p.name.lower() or "tier3" in p.name.lower()]
    checks.append(Check("T3.slice_evidence", len(eps) > 0, f"count={len(eps)}"))

    drift_dir = ds / "20_drift_detection" / "drift_reports"
    drifts = find_files(drift_dir, "*.json") + find_files(drift_dir, "*.yaml")
    checks.append(Check("T3.drift_reports", len(drifts) > 0, f"count={len(drifts)}"))

    preview_dir = ds / "33_preview_deployment_factory" / "preview_plans"
    previews = find_files(preview_dir, "*.yaml")
    checks.append(Check("T3.preview_plans", len(previews) > 0, f"count={len(previews)}"))

    return checks


def tier4(ds: Path) -> list[Check]:
    checks: list[Check] = []

    drift_dir = ds / "20_drift_detection" / "drift_reports"
    drifts = find_files(drift_dir, "*.json") + find_files(drift_dir, "*.yaml")
    checks.append(Check("T4.session_drift_report", len(drifts) > 0, f"count={len(drifts)}"))

    ledger_dir = ds / "platform" / "sdlc" / "13_skills" / "skill_refinery" / "mistake_ledgers"
    ledgers = [p for p in find_files(ledger_dir, "*.md") if has_nonempty_markdown(p)]
    checks.append(Check("T4.mistake_ledger_entry", len(ledgers) > 0, f"count={len(ledgers)}"))

    imp_dir = ds / "platform" / "sdlc" / "13_skills" / "skill_refinery" / "improvement_proposals"
    improvements = find_files(imp_dir, "*.yaml")
    checks.append(Check("T4.skill_improvement_proposal", len(improvements) > 0, f"count={len(improvements)}"))

    return checks


def print_report(tier_checks: dict[int, list[Check]]) -> int:
    failed = 0
    for tier in sorted(tier_checks):
        checks = tier_checks[tier]
        ok = all(c.ok for c in checks)
        print(f"Tier {tier}: {'PASS' if ok else 'FAIL'}")
        for c in checks:
            status = "PASS" if c.ok else "FAIL"
            print(f"  - {status} {c.id}: {c.detail}")
            if not c.ok:
                failed += 1
    return failed


def main() -> int:
    ap = argparse.ArgumentParser(description="Validate onboarding tiers (T1-T4) for a target repo")
    ap.add_argument("--target", required=True, help="repo root path or atlas path")
    ap.add_argument("--tiers", default="1-4", help="tier set: 1,2,3,4 or 1-4 or all")
    ap.add_argument("--central-root", default=None, help="central ATLAS root; default resolves from this script")
    ap.add_argument("--json", dest="json_out", action="store_true", help="emit json report")
    args = ap.parse_args()

    tiers = parse_tiers(args.tiers)
    repo_root, ds = resolve_target_repo(Path(args.target))

    # This script lives at <atlas>/25_automation/onboarding_validate_tiers.py
    # so the ATLAS root is parents[1].
    script_root = Path(__file__).resolve().parents[2]
    central = Path(args.central_root).resolve() if args.central_root else script_root
    repo_name = repo_root.name.lower()

    tier_checks: dict[int, list[Check]] = {}
    for tier in tiers:
        if tier == 1:
            tier_checks[tier] = tier1(repo_root, ds, central, repo_name)
        elif tier == 2:
            tier_checks[tier] = tier2(ds, repo_name)
        elif tier == 3:
            tier_checks[tier] = tier3(ds)
        elif tier == 4:
            tier_checks[tier] = tier4(ds)

    if args.json_out:
        payload = {
            "target": str(repo_root),
            "atlas": str(ds),
            "central_root": str(central),
            "tiers": {str(k): [asdict(c) for c in v] for k, v in tier_checks.items()},
        }
        print(json.dumps(payload, indent=2))
        failures = sum(0 if c.ok else 1 for checks in tier_checks.values() for c in checks)
        return 1 if failures else 0

    failures = print_report(tier_checks)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
