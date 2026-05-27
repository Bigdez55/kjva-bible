from __future__ import annotations

from pathlib import Path


CANONICAL_ROOTS = {
    "04_architecture": "development_skills/04_architecture",
    "13_skills": "development_skills/13_skills",
    "19_truth_state": "development_skills/19_truth_state",
    "37_command_protocol": "development_skills/37_command_protocol",
    "12_agents": "development_skills/12_agents",
    "42_context_compiler": "development_skills/42_context_compiler",
}


def count_files(base: Path, pattern: str) -> int:
    if not base.exists():
        return 0
    return sum(1 for _ in base.glob(pattern))


def canonical_roots(repo_root: Path) -> dict[str, Path]:
    roots: dict[str, Path] = {}
    for name, target in CANONICAL_ROOTS.items():
        target_path = Path(target)
        roots[name] = target_path if target_path.is_absolute() else repo_root / target_path
    return roots


def canonical_root_status(repo_root: Path) -> dict[str, dict[str, object]]:
    status: dict[str, dict[str, object]] = {}
    for name, path in canonical_roots(repo_root).items():
        status[name] = {
            "path": str(path),
            "exists": path.exists(),
        }
    return status


def normalize_command_name(name: str) -> str:
    return name.replace(":", "_")


def command_inventory(base: Path) -> dict[str, str]:
    if not base.exists():
        return {}
    inventory: dict[str, str] = {}
    for path in sorted(base.glob('*.md')):
        inventory[normalize_command_name(path.stem)] = path.name
    return inventory


def command_drift_report(repo_root: Path) -> dict[str, object]:
    canonical_dir = repo_root / 'development_skills/37_command_protocol/slash_commands'
    codex_dir = repo_root / '.codex/commands'
    claude_dir = repo_root / '.claude/commands'

    canonical = command_inventory(canonical_dir)
    codex = command_inventory(codex_dir)
    claude = command_inventory(claude_dir)

    canonical_keys = set(canonical)
    codex_keys = set(codex)
    claude_keys = set(claude)

    return {
        'canonical_count': len(canonical),
        'codex_count': len(codex),
        'claude_count': len(claude),
        'canonical_files': sorted(canonical.values()),
        'codex_files': sorted(codex.values()),
        'claude_files': sorted(claude.values()),
        'codex_missing': sorted(canonical_keys - codex_keys),
        'codex_extra': sorted(codex_keys - canonical_keys),
        'claude_missing': sorted(canonical_keys - claude_keys),
        'claude_extra': sorted(claude_keys - canonical_keys),
        'codex_claude_only': sorted(codex_keys - claude_keys),
        'claude_codex_only': sorted(claude_keys - codex_keys),
        'ok': codex_keys == canonical_keys == claude_keys,
    }


def drift_warnings(drift: dict[str, object]) -> list[str]:
    warnings: list[str] = []
    for key in (
        'codex_missing',
        'codex_extra',
        'claude_missing',
        'claude_extra',
        'codex_claude_only',
        'claude_codex_only',
    ):
        values = drift.get(key, [])
        if isinstance(values, list) and values:
            warnings.append(f"{key}: {', '.join(values)}")
    return warnings
