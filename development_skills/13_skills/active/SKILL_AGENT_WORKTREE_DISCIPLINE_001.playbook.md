# agent-worktree-discipline

<!-- Source: migrated from ~/.claude/skills/agent-worktree-discipline/SKILL.md on 2026-05-26 -->
<!-- Runtime alias: agent-worktree-discipline -->

**Summary.** Pre-flight + post-flight discipline for ANY agent that creates a git worktree, writes files, and commits. Triggers on requests to "create worktree", "git worktree add", agent prompts that include `git worktree add /tmp/...`, or any multi-agent dispatch in nested-project repos. Prevents orphan-path commits, sync-rewind silent loss, and accumulated worktree debt. CRITICAL for repos where the project tree is nested inside the git root (e.g. `repo-root/project-name/...`).

# Agent Worktree Discipline

## Trigger

Use this skill BEFORE any agent dispatched with `git worktree add /tmp/<name>` instructions, AND BEFORE merging any agent's commit, AND AFTER cleanup of finished worktrees.

Triggers on:
- "create a worktree"
- "git worktree add"
- Multi-agent dispatch (parallel waves) where 2+ agents touch the repo
- Any commit message authored from a worktree at `/tmp/`, `/private/tmp/`, or sibling-of-repo path
- Repo introspection that reveals `<repo-root>/<project-subdir>/...` nesting

## The failure mode this prevents

**Orphan-path commits.** When a git worktree is created at `/tmp/scc-foo/`, that path becomes the worktree root from git's perspective. Files written at `/tmp/scc-foo/os/crypto/file.sc` commit as `os/crypto/file.sc` (no prefix). But if the canonical project tree on `main` is at `superc-v1/os/crypto/file.sc` (nested inside git root), the merge to main creates a PARALLEL ORPHAN TREE — `os/crypto/file.sc` AND `superc-v1/os/crypto/file.sc` both exist on main.

Documented incident: SUPER C project, sessions 11-16. **31 orphan-path files** + **5 branches with unmerged work** + **168 accumulated worktrees** + **9K–18K-line phantom diffs** when merging branches branched pre-consolidation. Fix cost: ~3 hours of cleanup + recovery commits + branch deletion. Loss-if-not-caught: ~1,250 LOC of agent work + Stage IV/V scaffolds.

---

## PHASE A — Pre-dispatch (BEFORE creating worktree)

### A.1 Identify canonical project root

Run from intended repo location:
```bash
git rev-parse --show-toplevel        # → e.g. /Users/x/myrepo
git rev-parse --show-prefix          # → e.g. project-name/  (or empty if at root)
```

If `--show-prefix` returns non-empty, **the canonical project is NESTED inside git root.** Record the prefix. Every file the agent commits must include this prefix.

### A.2 Mandatory agent-prompt template

Every agent prompt that includes `git worktree add` MUST include:

```
CRITICAL DIRECTORY DISCIPLINE: This repo's git root is at `<git-root>`.
The canonical project tree is at `<git-root>/<project-prefix>/`.

ALL FILES YOU WRITE MUST BE AT PATHS UNDER `<project-prefix>/...`.

Worktree root will be `/tmp/scc-<slice>/`. From the worktree, files belong at:
  /tmp/scc-<slice>/<project-prefix>/<remaining-path>
NOT at:
  /tmp/scc-<slice>/<remaining-path>     ← THIS IS THE ORPHAN-PATH BUG

Verify before commit: `git diff --name-only --staged | grep -v "^<project-prefix>/"`
must return EMPTY. Any path without the prefix is an orphan-path violation.
```

### A.3 Worktree base discipline

- Default: `/tmp/scc-<slice-id>/` (outside OneDrive/cloud-synced volumes — see C.3)
- Branch from current `main` (NOT pre-consolidation snapshots)
- Always `--force` is OK; `git worktree add /tmp/scc-foo -b experiment/foo main`

---

## PHASE B — Pre-merge (BEFORE merging an agent's commit to main)

### B.1 Path-prefix verification gate

```bash
# For each commit on the experiment branch:
git diff --name-only main..experiment/foo | grep -v "^<project-prefix>/" | head
```

If output is non-empty, **STOP**. The branch contains orphan-path commits. Either:
- (a) ABORT the merge and ask the agent to redo at canonical paths, OR
- (b) RESCUE the unique additions via direct file copy to canonical paths (see Phase D)

### B.2 Pre-consolidation diff check

```bash
git diff --stat main..experiment/foo | tail -1
```

If the diff shows MASSIVE deletions (>1000 lines deleted vs <500 added), the branch likely branched pre-consolidation. Merging would re-introduce orphan paths AND delete legitimate work. **STOP** and pursue Phase D rescue instead.

### B.3 OneDrive sync rewind verification

After merge, verify the merge persists:
```bash
git log --oneline main -3
git ls-tree HEAD <key-file-from-merge>
```

If the merge commit disappears from history within 30 seconds, OneDrive sync rewound it. **Re-merge.** Document in audit log per memory `feedback_no_destructive_git_on_shared_main`.

---

## PHASE C — Post-execution (AFTER agent commits)

### C.1 Worktree pruning discipline

After EVERY agent completes (success OR abort):
```bash
git worktree remove --force /tmp/scc-<slice>
```

Never leave worktrees lying around. They accumulate.

### C.2 Periodic prune

Every 5 dispatched waves:
```bash
git worktree list | grep "/private/tmp/" | wc -l        # alert if >10
git worktree prune                                       # remove dangling
```

### C.3 Filesystem zone discipline

| Zone | Use? | Why |
|---|---|---|
| `/tmp/scc-*` | ✅ recommended | outside cloud sync, fast, ephemeral |
| `/private/tmp/scc-*` | ✅ macOS canonical | symlink target of /tmp |
| `<repo-root>/superc-v1-*` | ❌ FORBIDDEN | sibling of canonical = orphan-zone |
| `<repo-root>/superc-v1/experiment/*` | ❌ FORBIDDEN | nested inside canonical = pollutes tree |
| `<repo-root>/.claude/worktrees/*` | ❌ AVOID | inside cloud-synced volume |

---

## PHASE D — Rescue (when orphan-path commits ALREADY exist)

### D.1 Triage unmerged branches

```bash
# List branches NOT on main
git branch | while read b; do
  git merge-base --is-ancestor $b main 2>/dev/null || echo "UNMERGED $b"
done
```

For each unmerged branch:
```bash
# Check what files it ADDS (not deletions)
git diff --name-status main..<branch> | grep "^A"
```

### D.2 Direct file copy (NOT cherry-pick)

Cherry-picking a pre-consolidation branch will DELETE the consolidation work. Instead:

```bash
# For each unique file the branch added:
cp <worktree-path>/<orphan-relative-path> <canonical-prefix>/<canonical-path>
git add <canonical-prefix>/<canonical-path>
```

Commit as a single `chore: recover orphan-worktree unique work` commit.

### D.3 Then remove worktree

```bash
git worktree remove --force <worktree-path>
git branch -D <branch>
```

### D.4 Mass-cleanup script

```bash
# Audit all worktrees for merge status:
git worktree list --porcelain | awk '/^worktree/{p=$2} /^branch/{print p, $2}' > /tmp/wt.txt
while read path branch; do
  case "$path" in /tmp/*|/private/tmp/*) ;; *) continue;; esac
  if git merge-base --is-ancestor $branch main 2>/dev/null; then
    echo "MERGED $path"; git worktree remove --force "$path"
  else
    added=$(git diff --name-status main..$branch | grep -c '^A')
    echo "UNMERGED($added) $path"
  fi
done < /tmp/wt.txt
```

---

## QUICK REFERENCE

| Situation | Action |
|---|---|
| About to dispatch agent with `git worktree add` | Phase A (set canonical-prefix in prompt) |
| About to `git merge --no-ff experiment/foo` | Phase B (path-prefix gate + rewind check) |
| Agent finished | Phase C.1 (`git worktree remove --force`) |
| Every 5 waves | Phase C.2 (prune audit) |
| Discovered orphan paths on main | Phase D (rescue + relocate) |
| > 30 worktrees accumulated | Phase D.4 (mass cleanup) |

## Failure-pattern signatures

If you see ANY of these, this skill applies:

- `git ls-tree HEAD --name-only` shows BOTH `os/crypto/...` AND `superc-v1/os/crypto/...`
- `git diff --stat main..<branch>` shows >1000-line deletions for a "feature" commit
- `git worktree list | wc -l` returns > 30
- Merge commit reports +N insertions but `git ls-tree HEAD <added-file>` returns empty
- Filesystem has `<repo>/superc-v1-*` siblings or `<repo>/superc-v1/experiment/*` subdirs
- An agent reports "smoke 31/31 PASS" from worktree but smoke fails on main

## Continuous refinement

Update version below every time a NEW failure pattern is observed:

- 1.0.0 (2026-05-07): initial — based on SUPER C orphan-worktree disaster (sessions 11-16). 31 orphan files, 168 accumulated worktrees, 5 unmerged branches with unique work, OneDrive sync rewind hazard documented.

## Domain notes

- **Nested projects** (repo-root/project-name/) are most vulnerable. If you can choose, put `.git/` inside the project (eliminates the prefix issue). If you can't, this skill is mandatory.
- **Cloud-synced volumes** (OneDrive, iCloud, Dropbox) holding `.git/` directories are fragile. Verify merge persistence post-commit.
- **Multi-agent dispatch** amplifies the failure mode N× — each agent is one chance for a path-prefix violation.

## Recursion

This skill applies to itself: when adding new domain examples, audit which repo structure they target; ensure path-prefix examples are concrete (not pseudocode).
