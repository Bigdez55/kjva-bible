# git-remote-discipline

<!-- Source: migrated from ~/.claude/skills/git-remote-discipline/SKILL.md on 2026-05-26 -->
<!-- Runtime alias: git-remote-discipline -->

**Summary.** Pre-push remote verification discipline. MANDATORY before every git push. Triggers on: any git push command, "push to remote", "push branch", "push tags", "--follow-tags", "git push origin", or any push to a GitHub URL. NEVER push without running STEP 1 of this skill first. Prevents cross-repo contamination — branches, tags, and commits pushed to the wrong repo are destructive, public, and hard to recover from.

# Git Remote Discipline — Pre-Push Verification Gate

**ABSOLUTE RULE: Run `git remote -v` and cross-check against the canonical map BEFORE every push. No exceptions.**

---

## ROOT CAUSE OF THIS SKILL

2026-05-26: SUPER C compiler (`superc-v1/`) had `origin` misconfigured to
`Storbits.git` (a separate product repo). Running `git push origin super-c-1-lang
--follow-tags` pushed the entire branch + 78 SUPER C tags into Storbits. Required
manual deletion of 79 refs. Storbits `main` was unaffected only by luck — the
branch diverged early. One mistake, one command, one wrong remote = cross-product
contamination at the remote level.

---

## STEP 1 — VERIFY REMOTE BEFORE ANY PUSH (MANDATORY)

```bash
git remote -v
```

Read every URL. Cross-check against the canonical map below. If `origin` does not
match the expected URL for the current working directory, **STOP — do not push**.
Fix the remote first (STEP 3), then re-verify, then push.

---

## STEP 2 — CANONICAL REMOTE MAP

| Working directory (local) | Expected `origin` URL | Correct push remote |
|---|---|---|
| `desmond-super-c/superc-v1/` | `https://github.com/Bigdez55/SUPER-C-PGLANG.git` | `origin` or `pglang` |
| `Storbits/` | `https://github.com/Bigdez55/Storbits.git` | `origin` |
| `GENESYS/GENESYS/` | (verify before each push) | `origin` |
| `kjva-bible/` | (verify before each push) | `origin` |
| `ATLAS/` | (verify before each push) | `origin` |

**Add new entries to this map whenever a new repo is cloned or a new project is started.**

If `origin` is WRONG but a correctly-named remote exists (e.g., `pglang`),
use the named remote AND fix `origin` before pushing again (STEP 3).

---

## STEP 3 — FIXING A MISCONFIGURED REMOTE

```bash
git remote set-url origin https://github.com/<user>/<correct-repo>.git
git remote -v   # re-verify before proceeding
```

---

## STEP 4 — EXTRA CAUTION FOR `--follow-tags`

`--follow-tags` pushes ALL reachable annotated tags to the remote — not just the
branch. On a misconfigured remote this contaminates the wrong repo with every tag
ever created on the branch.

**Before any push with `--follow-tags`:**
1. Run `git remote -v` and confirm URL (STEP 1).
2. Run `git tag --list | wc -l` — know how many tags will transfer.
3. If tag count is unexpectedly high (>10), explicitly name only the tags you
   intend to push rather than using `--follow-tags`.

---

## STEP 5 — POST-PUSH VERIFICATION

After every push, immediately verify the target repo contains only what you intended:

```bash
# Confirm the correct repo received the push
git ls-remote <expected-url> refs/heads/<branch> refs/tags/<tag>

# Confirm the wrong repo was NOT touched
git ls-remote <other-repo-url> refs/heads/<branch> | wc -l  # expect 0
```

If contamination is detected, immediately delete from the wrong remote:
```bash
git push <wrong-remote-url> --delete <branch>
git push <wrong-remote-url> --delete <tag1> <tag2> ...
```

---

## STEP 6 — RECOVERY PROTOCOL (IF WRONG REPO WAS PUSHED)

1. **Do NOT panic and force-push main** — the wrong repo's main is almost certainly
   unaffected; the contamination is a branch and/or tags, not main.
2. `git ls-remote <wrong-url>` — enumerate ALL contaminating refs.
3. Filter: everything that does not belong to the wrong repo's project is
   contamination. Every tag that was pushed is suspect.
4. Delete branch first, then all contaminating tags in one batch push --delete.
5. Verify with a final `git ls-remote <wrong-url>` that only legitimate refs remain.
6. Confirm the correct repo (`git ls-remote <right-url>`) has all intended refs.

---

## ANTI-PATTERNS THAT CAUSE CROSS-REPO CONTAMINATION

| Anti-pattern | Consequence | Prevention |
|---|---|---|
| `git push origin` without checking `git remote -v` first | Pushes to whatever `origin` happens to resolve to | STEP 1: always verify first |
| `--follow-tags` to an unverified remote | All tags contaminate wrong repo | STEP 4: verify URL + count tags before using |
| Assuming `origin` = correct repo without checking | Wrong repo gets branch + all history | Remote map (STEP 2) |
| Cloning then never updating remote map entry | Map drifts from reality | Update map on every new clone |
| Using `origin` when a more explicit named remote exists | `pglang` exists but `origin` was wrong — `origin` was used anyway | Prefer named remotes when multiple exist; fix `origin` immediately |

---

## INTEGRATION WITH VERIFY-VALIDATE

This skill is a pre-push extension of `verify-validate`. It runs AFTER Gate 7B
(repo status clean) and BEFORE the push command. The verify-validate Gate 7E
references this skill for the full protocol.

---

## CONTINUOUS IMPROVEMENT

After any push incident — whether caught before or after — add the anti-pattern
to the table in STEP 6 and update the canonical map in STEP 2.

Current version: 1.0.0
Last updated: 2026-05-26

**Changelog:**
- v1.0.0 (2026-05-26): Initial. Sourced from SUPER C cross-repo contamination
  incident where `superc-v1/` had `origin` pointing to `Storbits.git`. Push of
  `super-c-1-lang --follow-tags` contaminated Storbits with 78 SUPER C tags + 1
  branch. Full recovery: delete branch + 78 tags from Storbits, fix origin,
  re-push to SUPER-C-PGLANG via `pglang` remote. Root cause: no pre-push remote
  verification step existed.
