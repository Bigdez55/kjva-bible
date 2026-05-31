# Skill Registry Audit — Everywhere (2026-05-20)

Audit of `13_skills/active/SKILL_*.yaml` files on disk vs `skills.registry.yaml`
entries, across every repo that carries a `atlas/13_skills` tree,
plus router-integration status for the canonical repo.

## Scope — 9 skill-system locations

| Location | disk | registry | gap | status |
|---|---:|---:|---:|---|
| **ATLAS** (CANONICAL) | 177 | 177 | 0 | ✅ IN SYNC |
| desmond-super-c | 156 | 22 | 134 | ❌ DRIFT — registry severely stale |
| GENESYS | 156 | 150 | 6 | ❌ DRIFT |
| IPOS | 156 | 150 | 6 | ❌ DRIFT |
| nexus | 156 | 150 | 6 | ❌ DRIFT |
| Storbits | 156 | 150 | 6 | ❌ DRIFT |
| Apollo16-main/atlas | 156 | 150 | 6 | ❌ DRIFT |
| Apollo16-main/Apollo16 | 14 | 14 | 0 | ✅ IN SYNC (fossil copy) |
| Nexus (uppercase) | 156 | 150 | 6 | ❌ DRIFT |

## Findings

1. **Canonical (ATLAS) is in sync** — 177 active skill files, 177
   registry entries, `total: 177`. `SKILL_APEX_VERIFIED_MACHINE_ENCODING_001`
   is registered. No orphaned entries (every registry name has a file).

2. **6 embedded copies drift identically** — GENESYS, IPOS, nexus, Storbits,
   Apollo16-main/atlas, Nexus each have 156 skill files but only
   150 registered. All six are missing the **same 6** skills from their
   registry: `SKILL_ATLAS_GRAPH_ENGINE_001`, `SKILL_ATLAS_KNOWLEDGE_DEPOT_001`,
   `SKILL_ATLAS_OPERATIONAL_WORKSPACE_001`, `SKILL_ATLAS_ORBITAL_IDENTITY_001`,
   `SKILL_ATLAS_PLANNING_TRACE_001`, `SKILL_ATLAS_REPO_INGESTION_LOOP_001`.
   These six copies are also **stale snapshots** — 156 skills vs the canonical
   177 (21 skills behind).

3. **desmond-super-c registry is severely stale** — 156 skill files on disk but
   only 22 registered (134 unregistered, including all ELSON/GENOS/IPOS/SUPER_C
   project skills and core skills like `SKILL_TRIGGER_ROUTER_001`).

4. **Apollo16-main/Apollo16** is a 14-skill fossil copy — internally consistent
   but far behind canonical; likely a stale duplicate of the bundle.

5. **No orphaned registry entries anywhere** — no registry entry points to a
   missing file in any location.

## Router integration (canonical repo)

`37_command_protocol/trigger_router.yaml` — exact-token recount at audit end:
**all 177 active skills are routed (0 unrouted).** A concurrent process
completed full router integration of the canonical repo *during* this audit
(an earlier mid-audit snapshot showed 161/177 routed and 16 unrouted — that
snapshot is now superseded).

State of the canonical repo: **177 skill files = 177 registry entries = 177
routed.** Fully integrated.

What is still missing: **no enforcement gate.** Neither
`validate_trigger_determinism.py` nor `validate_skills_stack.py` iterates the
active-skill set to assert every skill is registered AND routed. The current
177/177/177 state is therefore not protected — the next skill added by hand
can silently drift. The "at all times" half of the directive
([[full-router-integration-invariant]]) requires a validator gate that does
not yet exist.

## ⚠️ Concurrency warning — writer was live during this audit

An external process (concurrent Codex run and/or OneDrive sync) modified
`37_command_protocol/trigger_router.yaml`, `13_skills/skill_refinery/trigger_router.yaml`,
and `skills.registry.yaml` repeatedly during this audit — APEX entries and the
remaining 16 skill routings appeared mid-audit; dirty count climbed 127 → 138;
`trigger_router.yaml` mtime was observed ~1 second old. The writer runs in
intermittent bursts. **No coordinated remediation edits should be made to the
canonical repo until that process is confirmed finished.**

## Remediation executed (2026-05-20)

**Embedded-copy re-sync — DONE.** Subset re-sync from canonical: for each of the
6 embedded copies, every canonical-derived dir already present was overwritten
with the canonical version via `rsync -a --delete` (repo-unique dirs like
`_miss_log`, `reports` left untouched). Pre-sync backups:
`/tmp/predevsync-{dsc,genesys,ipos,nexus,storbits,apollo16}.tar.gz`.

Post-sync verification — all 6 now match canonical exactly:

| Location | disk | registry | total | routed |
|---|---:|---:|---:|---:|
| ATLAS (canonical) | 177 | 177 | 177 | 177 |
| desmond-super-c | 177 | 177 | 177 | 177 |
| GENESYS | 177 | 177 | 177 | 177 |
| IPOS | 177 | 177 | 177 | 177 |
| Nexus (= nexus) | 177 | 177 | 177 | 177 |
| Storbits | 177 | 177 | 177 | 177 |
| Apollo16-main/atlas | 177 | 177 | 177 | 177 |
| Apollo16-main/Apollo16 (fossil) | 14 | 14 | 14 | — (left untouched, by decision) |

Files re-synced only; **not committed** in any repo (per decision — each repo
already carries 300+ unrelated dirty files for the owner to review).

## Resolved (2026-05-20)

- **Enforcement gate built.** `25_automation/validate_skill_router_integration.py`
  asserts every active skill is registered AND routed (exact-token match);
  wired into `validate_skills_stack.py`. Verified: PASS on current 177-skill
  state; FAIL (exit 1) on an injected unregistered/unrouted skill. The
  `[[full-router-integration-invariant]]` is now continuously enforced in the
  canonical repo.
- **Claude Code surface installed.** `apex-verified-machine-encoding` copied to
  `~/.claude/skills/` (SKILL.md + scripts/encode_oracle.py) — now callable in
  Claude Code, not just Codex. Cross-runtime gap closed.

## Note

The 6 embedded copies were re-synced *before* the enforcement gate was created,
so their `25_automation/` does not yet carry `validate_skill_router_integration.py`.
Re-syncing `25_automation/` would propagate the gate to all embedded copies.
