# ATLAS Thin Tether — Agent Instructions

This repo is tethered to ATLAS via `atlas_tether.py`. All skill resolution,
routing, and context compilation go through the Bookworm ABI at
`$ATLAS_HOME/infrastructure/scripts/atlas_tether.py` — **in-process, no HTTP**.

## Thin Tether Contract

- **ATLAS_HOME**: `/Users/desmondearly/Developer/ATLAS` (see `.atlas/tether.yaml`)
- **Tether CLI**: `python3 /Users/desmondearly/Developer/ATLAS/infrastructure/scripts/atlas_tether.py <subcommand>`
- The vendored `atlas/`, `.claude/universal/`, `.codex/universal/` corpus has been
  purged or was never present. All knowledge is resolved live from ATLAS_HOME.

## Skill Resolution

```bash
python3 /Users/desmondearly/Developer/ATLAS/infrastructure/scripts/atlas_tether.py resolve-skill REFACTOR
python3 /Users/desmondearly/Developer/ATLAS/infrastructure/scripts/atlas_tether.py resolve-skill ADR --full
```

## Routing

```bash
python3 /Users/desmondearly/Developer/ATLAS/infrastructure/scripts/atlas_tether.py route "audit the repo"
```

## Context Compilation

```bash
python3 /Users/desmondearly/Developer/ATLAS/infrastructure/scripts/atlas_tether.py compile-context --scope full --task "implement feature X"
```

## Knowledge Search

```bash
python3 /Users/desmondearly/Developer/ATLAS/infrastructure/scripts/atlas_tether.py ask "skill routing strategies"
```

## Cross-Runtime Skill Invocation

When the user says `invoke all skills`, `use all skills`, or `activate all skills`,
route through `atlas_tether.py route` which binds the canonical trigger router
at `$ATLAS_HOME/platform/systems/37_command_protocol/trigger_router.yaml`.

Required behavior:
- Use `atlas_tether.py resolve-skill` for all skill lookups (resolves from ABI)
- Treat resolved `SKILL_*.yaml` + `.playbook.md` files as applicable disciplines
- Suppress project-specific skills unless explicitly target-bound

Forbidden behavior:
- Do not reference paths under `atlas/`, `.claude/universal/`, `.codex/universal/`
  (the vendored corpus has been purged; those paths are dead references)
- Do not hardcode ATLAS internal paths — use the tether CLI exclusively

## Health Check

```bash
python3 /Users/desmondearly/Developer/ATLAS/infrastructure/scripts/atlas_tether.py doctor
```

## Tether Configuration

See `.atlas/tether.yaml` for `atlas_home`, `pinned_ref`, and `abi_version`.
