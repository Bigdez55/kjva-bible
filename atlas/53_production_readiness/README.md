# 53 — Production-Readiness Corpus & Audit Framework

A canonical, reusable **accountability / verification / validation / audit layer** that sits
alongside the development skills. It answers one recurring need: *when we audit any project,
nothing gets missed, gaps surface explicitly, and "platinum grade production ready" is a
measurable bar* — for our own projects and for consulting engagements in any domain or industry.

## What this is

- A **corpus**: 68 categories → sections → **3,378 verbatim checklist items** (the Platinum Dev Checklist).
- A **scoring rubric**: Bronze → Silver → Gold → Platinum, computed deterministically.
- **Profiles**: project archetypes (repo blueprints) + industry overlays that scope the corpus per engagement.
- An **audit skill**: `SKILL_PRODUCTION_READINESS_AUDIT_001` runs a scoped, scored, evidence-backed audit.
- A **gap engine**: every category links the skill(s) that own it; categories with no skill are flagged `NO-SKILL GAP`.

## Source of truth

`corpus/source/dev-checklist-v2.jsx` is the **only authored content** (and doubles as an interactive
viewer). Everything else is **generated**:

```
corpus/source/dev-checklist-v2.jsx   # SOURCE OF TRUTH (hand-authored checklist)
corpus/overlay.yaml                  # HAND-MAINTAINED audit metadata (coverage_status, skill_refs, severity) — merged, never clobbered
corpus/taxonomy.yaml                 # GENERATED index of all categories
corpus/categories/PRC-*.yaml         # GENERATED per-category files (sections -> items, verbatim)
generated/corpus.json                # GENERATED machine artifact (ATLAS / TypeScript)
rubric/scoring_rubric.yaml           # tier thresholds
schema/                              # shape contracts (corpus + profiles)
profiles/industry_overlays/          # consulting domain overlays
tools/build_corpus.py                # regenerate the corpus from the JSX
tools/score_audit.py                 # score an audit_state.yaml -> gap_report.yaml + summary.md
```

### Regenerate after editing the checklist

```bash
python3 tools/build_corpus.py          # asserts zero item loss vs the JSX
python3 tools/build_corpus.py --check  # dry-run count assertion, no writes
```

Edit **item text/structure in the JSX**, then regenerate. Edit **audit metadata in `overlay.yaml`**.
Never hand-edit the generated files — they are overwritten on every build.

## Running an audit

```bash
# 1. author a verdict file (audit_state.yaml) — see tools/score_audit.py for the schema
# 2. score it:
python3 tools/score_audit.py path/to/audit_state.yaml
# -> writes gap_report.yaml + summary.md next to it
```

Audit runs are stored under `platform/systems/23_evidence/production_readiness_runs/<target>-<date>/`.

## ID scheme

`PRC.<CATEGORY_SLUG>.<SECTION_SLUG>.<NNN>` — slugs are uppercase underscore forms of the verbatim
names (stable, unique). `NNN` is the 1-based item index within its section. Items are **append-only**
for ID stability.

## Distribution & integrity

- Synced to the fleet via `infrastructure/scripts/sync_scripts/sync_to_child_repo.py` (allowlist).
- The corpus lives in `platform/systems/` and is therefore **outside** `skill_drift_detect.py`'s scope
  (which tracks only `13_skills/active/`). Only the audit skill + the 11 gap skills are drift-tracked.
- Pairs with `SKILL_AUDIT_ASSESS_ANALYZE_001` (forensic rigor), `SKILL_EXISTING_REPO_AUDIT_001`
  (truth map), `SKILL_PROOF_MATRIX_001` (evidence), and `SKILL_UI_LIVE_VERIFICATION_BEFORE_DONE_001`
  (tool-success ≠ done).

## Coverage baseline (2026-05-31)

Of 68 categories: most are FULL or PARTIAL covered by existing skills; **11 are zero-coverage gaps**
(Mobile, i18n/L10n, Search, OSS Licensing, CMS/Content, Browser Extension, Go-To-Market, Trust &
Safety, Fraud & Abuse, Sustainability, File Upload/Media) — each filled by a new `SKILL_*` and tracked
in `corpus/overlay.yaml`.
