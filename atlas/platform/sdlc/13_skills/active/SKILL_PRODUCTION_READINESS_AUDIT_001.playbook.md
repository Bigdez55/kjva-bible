# Production-Readiness Audit

> Operationalizes the **Production-Readiness Corpus** at
> `platform/systems/53_production_readiness/` (68 categories / 3,378 verbatim items,
> generated from the source-of-truth `dev-checklist-v2.jsx`). Produces a scoped,
> scored, evidence-backed audit with an explicit gap list and a Bronze/Silver/Gold/
> Platinum tier — for our own repos and for consulting/infrastructure assessments in
> any domain or industry.

## When to use

Whenever someone asks "is X production ready / platinum grade / fully built?", "what
are the gaps / what's left?", "audit this against our standards", "what's the
completion % / scope / milestone status?", or requests a client infrastructure
assessment.

## Slash command

```
/apex:production_audit --target <repo-or-path> --profile <archetype> [--tier <platinum>] [--overlay <industry>]
```

`--profile` is a repo blueprint archetype (web_app, dashboard, mobile, cli_tool,
ml_training, saas_multitenant, desktop_electron, consulting_infra_assessment).
`--overlay` (optional) layers an industry overlay (healthcare, fintech, …).

## Composition (do not duplicate these)

- `SKILL_AUDIT_ASSESS_ANALYZE_001` — forensic rigor, citation discipline.
- `SKILL_EXISTING_REPO_AUDIT_001` — truth map / feature inventory of the target.
- `SKILL_PROOF_MATRIX_001` — evidence-packet format.
- `SKILL_UI_LIVE_VERIFICATION_BEFORE_DONE_001` — "HTTP 200 + build ≠ done."

## Phases

### 1. Scope
- Resolve the **profile**: read `platform/systems/30_repo_starter/repo_blueprints/BLUEPRINT-<archetype>.yaml` →
  `production_readiness_profile`. `in_scope = all corpus categories − na_categories`
  (or the explicit `in_scope_categories`).
- If an **overlay** is given, read `…/profiles/industry_overlays/OVERLAY-<industry>.yaml`
  and union `add_required_categories` into scope; apply `severity_bumps` and
  `min_tier_override`.
- State the scope explicitly to the user: in-scope categories, N/A categories (+why),
  required tier.

### 2. Truth-map
- Run the `EXISTING_REPO_AUDIT` discipline on the target: what actually exists, what
  runs, what's stubbed. This is the ground truth the verdicts rest on. **Never** judge
  from docs alone.

### 3. Evidence (per item — evidence before pass)
- Load the corpus: `generated/corpus.json` (or per-category YAMLs).
- For each in-scope item, assign a verdict in `audit_state.yaml`:
  - `pass` — only with evidence (a file path, a command + its result, a cited artifact).
  - `fail` — a real, named deficiency.
  - `na` — out of scope for this profile (the reason is the profile/overlay).
  - `unknown` — not yet audited. **This is honest and expected** for a breadth pass.
- **HTTP 200 / green build is not evidence of behavior.** For UI/feature items, verify
  the rendered surface or the real path (Playwright, a real request, a screenshot).
- Resolve effective severity: item override → section/category `default_severity`.

### 4. Score (deterministic — never by hand)
```bash
python3 platform/systems/53_production_readiness/tools/score_audit.py <runs_dir>/<target>-<date>/audit_state.yaml
```
This writes `gap_report.yaml` + `summary.md`. The tier comes from
`rubric/scoring_rubric.yaml`. `unknown` counts as not-passed; `na` is excluded from the
denominator.

### 5. Gap report
For every failed (or sub-Gold) category, the report links the owning/fixing skill from
the corpus `skill_refs`. Categories with `coverage_status: NONE` raise a
**`NO-SKILL GAP`** pointing at the new skill that fills it. This is the engine for
"find the gaps and fill them."

### 6. Evidence packet
Emit a proof-matrix-compatible `evidence_packet.yaml` (command, timestamp, cwd, result,
output summary) alongside the run. The audit is only as real as its evidence.

### 7. Verify-before-done gate
Before declaring any tier or "done": confirm the claims with live behavior, not just
build/HTTP status. Re-state unknowns honestly. A high `unknown` count is a *true* result,
not a failure to hide.

## Run artifacts

Written to `platform/systems/23_evidence/production_readiness_runs/<target>-<YYYY-MM-DD>/`:
- `audit_state.yaml` — the verdicts (scoring INPUT).
- `gap_report.yaml` — per-category tier, counts, failed items, linked skills / NO-SKILL gaps.
- `summary.md` — scannable completion % + tier (the milestone/scope visual).
- `evidence_packet.yaml` — proof of the commands/paths behind the verdicts.

## audit_state.yaml shape

```yaml
target: ATLAS
profile: desktop_electron
required_tier: gold
na_categories: [ ... ]              # from the profile
severity_overrides: { <item_id>: critical }
verdicts:
  PRC.SECURITY_AND_AUTHENTICATION.AUTHENTICATION.001: pass
  PRC.SECURITY_AND_AUTHENTICATION.AUTHENTICATION.002: fail
  # unlisted items default to unknown
```

## Honest-scope rule (anti-theater)

A breadth audit across thousands of items cannot truthfully verdict every item. Declare
the scope you actually evidenced:
- **category/section maturity** + **critical-severity items** judged item-by-item, and
- everything else recorded as `unknown` (pending deeper per-item audit).

Never present `unknown` as `pass`. Full per-item audits are a repeatable follow-on, run
per category on demand — the framework makes them repeatable, it does not fake them.

## Anti-patterns

| Anti-pattern | Correct move |
|---|---|
| Marking items pass because the build is green | Verify real behavior (rendered UI, real request) |
| Paraphrasing a corpus item | Quote it verbatim; the JSX is source of truth |
| Skipping a category silently | Record `na` + the profile reason, or `unknown` |
| Declaring a tier from intuition | Run `score_audit.py`; report its tier |
| Presenting 33k unverified verdicts as audited | Honest-scope: maturity + critical items; rest `unknown` |

## Related

- Corpus + tooling: `platform/systems/53_production_readiness/README.md`
- `SKILL_AUDIT_ASSESS_ANALYZE_001`, `SKILL_EXISTING_REPO_AUDIT_001`,
  `SKILL_PROOF_MATRIX_001`, `SKILL_UI_LIVE_VERIFICATION_BEFORE_DONE_001`
