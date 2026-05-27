#!/usr/bin/env python3
"""Validate repo-local .claude health and Claude registration state."""
from __future__ import annotations

import json
import sys
from pathlib import Path

repo_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(repo_root / '.codex'))

from agent_surface_health import (
    canonical_root_status,
    command_drift_report,
    count_files,
    drift_warnings,
)


def main() -> int:
    claude_root = repo_root / '.claude'
    settings_path = claude_root / 'settings.json'
    bridge_agent = Path.home() / '.claude' / 'agents' / 'kjva-claude-bundle.md'
    canonical = canonical_root_status(repo_root)
    drift = command_drift_report(repo_root)

    critical: list[str] = []
    warnings: list[str] = []

    if not claude_root.exists():
        critical.append('repo .claude folder is missing')
    if not settings_path.exists():
        critical.append('repo .claude/settings.json is missing')
    if not bridge_agent.exists():
        critical.append('home Claude bridge agent is not registered')

    warnings.extend(
        f"canonical root missing: {name} -> {entry['path']}"
        for name, entry in canonical.items()
        if not entry['exists']
    )
    warnings.extend(drift_warnings(drift))

    status = {
        'repo_root': str(repo_root),
        'claude_root': str(claude_root),
        'repo_settings_present': settings_path.exists(),
        'bridge_agent_registered': bridge_agent.exists(),
        'inventory': {
            'commands': count_files(claude_root / 'commands', '*.md'),
            'universal_skills': count_files(claude_root / 'universal' / 'skills', '*.md'),
            'universal_agents': count_files(claude_root / 'universal' / 'agents', '*.md'),
            'universal_tools': count_files(claude_root / 'universal' / 'tools', '*.md'),
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
