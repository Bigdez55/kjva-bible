# Definition-of-Done Gate — probes write verdicts, not the agent

> The structural cure for false-completion ("done/wired/verified" claimed when it
> isn't). Completion is decided by **evidence probes** — scripts that inspect real
> state — enforced at pre-commit and CI, with release state DERIVED from probe
> output. Born from MISS-001 (2026-06-01): ATLAS declared production-ready while a
> read-only demo.

## The principle
A skill DESCRIBES; a probe DECIDES. The agent may build and reason, but it does **not**
get to declare "done." A claim of done/proven/ready is valid only if its backing
probes pass. Unknown is never a pass.

## Components (this repo)
| Part | Path | Role |
|---|---|---|
| Probe runner | `platform/systems/53_production_readiness/probes/probe_runner.py` | Inspects real state → pass/fail/unknown per check |
| Derive state | `infrastructure/scripts/production_readiness/derive_gate_state.py` | Computes `releaseRecommendation` from probes; `--check` blocks hand-typed claims |
| Claim guard | `infrastructure/scripts/production_readiness/completion_claim_guard.py` | Pre-commit: a staged done/ready claim must be probe-backed |
| Pre-commit hook | `.git/hooks/pre-commit` | Runs the guard; bypass only via `--no-verify` (logged) |
| CI floor | `.github/workflows/atlas-release-gate.yml` → `dod-gate` job | The non-bypassable floor |
| Miss log | `platform/systems/53_production_readiness/ATLAS_MISS_LOG.md` | A caught miss → regression probe required before next done |
| Capability registry | `platform/systems/53_production_readiness/capabilities/registry.yaml` | CAP_* executables (see SKILL_CAPABILITY_CREATION_001) |

## When to use
Any time you're about to say done/wired/complete/production-ready/proven; any time you
edit a file that asserts release readiness; when setting up completion enforcement on a
new project; after a false-completion is caught.

## Workflow
1. **Define the probe before the claim.** For each thing that must be true, write/extend
   a probe that inspects REAL state (file exists + is CALLED at runtime, route persists,
   app installed, capability WIRED). Tie it to a corpus item id and/or a CAP_*.
2. **unknown == not pass.** A probe that can't determine state returns `unknown`; the
   gate treats that as not-pass. Never let unassessed read as done.
3. **Derive, don't declare.** Release/readiness state in code is generated from probe
   output (`derive_gate_state.py --write`); `--check` fails CI if a human hand-types a
   claim that disagrees.
4. **Block at the edges.** Pre-commit claim-guard blocks a false done locally; the CI
   `dod-gate` job is the real floor.
5. **Self-test the probes.** Run `probe_runner.py --self-test` against the known-bad
   state — a probe that passes on a broken state is a bug; catch it here.
6. **Verify real behavior.** HTTP 200 + build green ≠ done. Compose
   `SKILL_WIRED_NOT_DEFINED_001` (DEFINED/IMPORTED/CALLED) and
   `SKILL_UI_LIVE_VERIFICATION_BEFORE_DONE_001`.
7. **Log + force-regression.** A caught miss → append to the fleet miss log with a named
   regression probe; the gate refuses a future done in that domain until the probe passes.

## Applying to a NEW project
- Add probes for that project's must-be-true facts (start with the critical ones).
- Add a `derive_gate_state`-style derived state if it has a release/readiness file.
- Install the pre-commit hook + add the `dod-gate` checks to its CI.
- Register its executable capabilities (SKILL_CAPABILITY_CREATION_001).

## Anti-patterns
| Anti-pattern | Correct move |
|---|---|
| "I verified it, it's done" | A probe verifies it; paste the probe verdict |
| Hand-typing `releaseRecommendation: READY` | Derive it from probes; `--check` enforces |
| Probe returns unknown → treated as pass | unknown == not pass, always |
| Lenient probe that passes on broken state | Self-test probes against the known-bad oracle |
| Pre-commit only | CI is the floor; pre-commit is `--no-verify`-bypassable |

## Related
`SKILL_PRODUCTION_READINESS_AUDIT_001`, `SKILL_CAPABILITY_CREATION_001`,
`SKILL_WIRED_NOT_DEFINED_001`, `SKILL_ARCHITECTURE_HONESTY_001`,
`SKILL_UI_LIVE_VERIFICATION_BEFORE_DONE_001`, `SKILL_IMPROVEMENT_LOOP_001`.
