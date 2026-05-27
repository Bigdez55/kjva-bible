#!/usr/bin/env python3
"""Validate repo-local .codex health and Codex registration state."""
from __future__ import annotations

import json
import tomllib
from pathlib import Path

from agent_surface_health import (
    canonical_root_status,
    command_drift_report,
    count_files,
    drift_warnings,
)


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    codex_root = repo_root / '.codex'
    dev_skills = repo_root / 'development_skills'
    config_path = Path.home() / '.codex' / 'config.toml'
    bridge_skill = Path.home() / '.codex' / 'skills' / 'kjva-codex-bundle' / 'SKILL.md'

    trusted_project = False
    if config_path.exists():
        with config_path.open('rb') as fh:
            config = tomllib.load(fh)
        trusted_project = (
            config.get('projects', {})
            .get(str(repo_root), {})
            .get('trust_level') == 'trusted'
        )

    canonical = canonical_root_status(repo_root)
    drift = command_drift_report(repo_root)
    warnings: list[str] = []
    critical: list[str] = []

    if not codex_root.exists():
        critical.append('repo .codex folder is missing')
    if not bridge_skill.exists():
        critical.append('global Codex bridge skill is not registered')
    if not trusted_project:
        critical.append('project is not trusted in ~/.codex/config.toml')

    if not (dev_skills / '37_command_protocol' / 'slash_commands').exists():
        warnings.append('development_skills slash command sources are missing')
    if not (dev_skills / '37_command_protocol' / 'command_playbooks').exists():
        warnings.append('development_skills command playbooks are missing')
    warnings.extend(
        f"canonical root missing: {name} -> {entry['path']}"
        for name, entry in canonical.items()
        if not entry['exists']
    )
    warnings.extend(drift_warnings(drift))

    status = {
        'repo_root': str(repo_root),
        'codex_root': str(codex_root),
        'trusted_project': trusted_project,
        'bridge_skill_registered': bridge_skill.exists(),
        'inventory': {
            'commands': count_files(codex_root / 'commands', '*.md'),
            'universal_skills': count_files(codex_root / 'universal' / 'skills', '*.md'),
            'universal_agents': count_files(codex_root / 'universal' / 'agents', '*.md'),
            'universal_tools': count_files(codex_root / 'universal' / 'tools', '*.md'),
            'slash_commands': count_files(
                dev_skills / '37_command_protocol' / 'slash_commands', '*.md'
            ),
            'command_playbooks': count_files(
                dev_skills / '37_command_protocol' / 'command_playbooks', '*.md'
            ),
        },
        'canonical_roots': canonical,
        'command_drift': drift,
        'critical': critical,
        'warnings': warnings,
        'ok': not critical,
    }
    print(json.dumps(status, indent=2))
    return 0 if not critical else 1


if __name__ == '__main__':
    raise SystemExit(main())
