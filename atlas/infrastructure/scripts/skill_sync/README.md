# Bidirectional Skill Sync — Drift Detect + Vet Queue

The operational answer to: *"how do we stop child-repo skill improvements from
being silently overwritten by a canonical→child copy?"* (the 2026-05-30 incident
where the other agent's SSH fix, made in Tokenless, would have been clobbered by
a blind fleet sync).

## Model: canonical authority + inbound review

```
Development_Skills/platform/sdlc/13_skills/active/   <- CANONICAL (source of truth)
        |  re-sync DOWN (canonical -> child)  for CANON_ONLY
        v
each child repo: atlas/13_skills/active/
        |  PROMOTE UP (child -> canonical, reviewed)  for DIFF / CHILD_ONLY
        v
   inbound_queue/  <- staged for human/approved-agent vetting; nothing auto-applies
```

Canonical stays the single source of truth, but child-side edits are never lost
to a blind overwrite — they surface in the queue for a deliberate promote/reject.

## Workflow

1. **Detect** (read-only):
   ```bash
   python3 infrastructure/scripts/skill_sync/skill_drift_detect.py
   ```
   Classifies every child skill: `IN_SYNC`, `DIFF`, `CANON_ONLY`, `CHILD_ONLY`,
   `NO_DEV_SKILLS`.

2. **Queue** the cases that must not be blind-overwritten:
   ```bash
   python3 infrastructure/scripts/skill_sync/skill_drift_detect.py --queue
   ```
   Copies each `DIFF` / `CHILD_ONLY` child file to
   `platform/sdlc/13_skills/skill_refinery/inbound_queue/<repo>__<skill>`.

3. **Vet each queued file** — decide:
   - **PROMOTE**: the child version is an improvement → copy into canonical
     `active/`, bump the skill version + changelog, `git commit`, then re-sync
     down to the whole fleet.
   - **REJECT**: stale/wrong → delete from queue; the next down-sync overwrites
     the child with canonical.

4. **Re-sync down** only after the queue is empty, so a sync never destroys an
   un-reviewed child improvement.

## Why not auto-merge

Auto-merge trusts a validator to tell an improvement from a regression. A YAML
that parses can still be semantically wrong. The queue costs one human glance per
drifted file and makes silent loss structurally impossible — the property that
actually failed on 2026-05-30.

## Guardrails

- Canonical → child copies should not run while the queue is non-empty for a skill.
- Every promotion bumps version + changelog (audit trail).
- `DIFF` always stops for review; the detector never guesses ahead-vs-behind.
- Pairs with `SKILL_ONEDRIVE_GIT_HAZARD_DISCIPLINE_001` (verify-after-write) and
  `SKILL_GIT_REMOTE_DISCIPLINE_001` (pre-push remote/SSH discipline).
