# OneDrive + .git Hazard Discipline

> Promoted from the 2026-05-30 incident. The repo lives under
> `OneDrive-Personal/`; OneDrive synced another machine's `.git` mid-session and
> moved `main` to an unrelated history. This playbook is how to work safely in a
> cloud-synced git repo until the repo is moved out of cloud sync.

## Why This Is Dangerous

`.git/` is a live database of small files (refs, objects, index, HEAD). Cloud
sync clients (OneDrive, Dropbox, iCloud, Google Drive) treat them as ordinary
files and will:
- Overwrite `.git/refs/heads/main` with another machine's version → your `main`
  silently jumps to a different commit.
- Replace working-tree files between the moment you read a file and the moment
  you edit it → the `Edit` tool's `old_string` no longer matches and the change
  **silently no-ops**.
- Leave refs and objects partially out of sync → dangling objects, confusing
  `fsck`, rejected fast-forwards.

**The 2026-05-30 failure chain:** OneDrive pulled in another machine's
`atlas-rename` history (moved `main`). The working tree still held this session's
edits. A routine `git add . && git commit` swept the unrelated rename under a
"skills" message (mislabeled mega-commit). Separately, three `Edit` calls
silently failed because the target files had been replaced by the synced
versions, and several `Write` calls in a cancelled parallel batch never reached
disk while I believed they had.

## Pre-Flight (before any git work in a cloud-synced repo)

```bash
git branch "safety/$(git rev-parse --short HEAD)-preflight" 2>/dev/null || true
git rev-parse HEAD > /tmp/expected-head.txt
# Best effort: pause cloud sync on .git during heavy work (OneDrive menu → Pause).
```

## In-Flight Detection

```bash
test "$(git rev-parse HEAD)" = "$(cat /tmp/expected-head.txt)" \
  && echo "HEAD stable" \
  || echo "!! HEAD MOVED — external sync suspected, STOP and run recovery"
```

If an `Edit` reports "String to replace not found" on a file you just read, or a
file you just `Write`-created reads as MISSING: **suspect a cloud-replace or a
cancelled write.** Re-read / re-write and grep-verify before continuing — never
assume the tool succeeded.

## Recovery Protocol (HEAD unexpectedly moved)

**NEVER `git reset --hard` first.** Both lines are probably still in the object
store — preserve both before choosing.

```bash
git branch onedrive-incoming HEAD                 # 1. never lose the incoming line
git reflog -30                                    # 2. find YOUR last real commit
git cat-file -t <your-sha>                         # 3. confirm reachable (prints: commit)
git cat-file -t <incoming-sha>
git merge-base --is-ancestor <origin/main> <your-sha> && echo "FF-able"   # 4. relationship
git merge-base --is-ancestor <incoming-sha> <your-sha> && echo "your line contains incoming"
git update-ref refs/heads/main <chosen-tip>        # 5. set canonical tip
git status --short && git push origin main         # 6. verify tree + push
```

## Safe-Commit Rule

```bash
# WRONG in a cloud-synced repo mid-incident — sweeps synced noise
git add -A && git commit -m "..."

# RIGHT — name exactly your files; inspect the staged diff first
git add path/to/file1 path/to/file2
git diff --cached --stat        # confirm ONLY your files
git commit -m "..."
```

## Verify-After-Write/Edit Rule

After writing or editing any file in a cloud-synced repo, confirm it is actually
on disk with the intended content before moving on:

```bash
test -f <file> && grep -c "<sentinel string>" <file>   # expect file present + >=1
```

A tool returning "success" is not proof the bytes are on disk — cloud-replace,
cancelled parallel batches, and silent no-ops all defeat that assumption. This is
the same principle as `SKILL_UI_LIVE_VERIFICATION_BEFORE_DONE_001`.

## Anti-Patterns

| Anti-pattern | Consequence | Correct move |
|---|---|---|
| `git reset --hard` on unexpected HEAD | Destroys in-progress work permanently | Branch incoming first, verify via reflog |
| `git add .` mid-incident | Mislabeled mega-commit sweeps synced noise | Stage explicit paths; inspect `--cached --stat` |
| Trusting Write/Edit "success" on a synced file | Silent no-op / never-written; change lost | Grep-verify the sentinel after every write |
| Assuming unexpected commits are your own error | Wrong recovery; real cause missed | Treat as external clobber until proven otherwise |
| Heavy git work with cloud sync active on .git | Repeated mid-op clobbers | Pause sync or use a non-synced clone |

## The Real Fix (deferred)

Git repos should not live under cloud sync. The durable solution is to move them
to a non-synced path (e.g. `~/dev/`) and rely on GitHub as the cross-machine sync
mechanism. Deferred here because the workspace depends on OneDrive for
cross-machine file access (pending GEN.X). Until then, this discipline is the
guard. When ready: clone from GitHub into `~/dev/`, delete the OneDrive working
copy.

## Incident Record

| Date | Project | Symptom | Root cause | Fix |
|---|---|---|---|---|
| 2026-05-30 | Development_Skills | `main` jumped to unrelated atlas-rename history; 3 Edits silently no-opped; some Writes never hit disk; a routine commit became a mislabeled mega-commit | OneDrive synced another machine's `.git` refs + working tree mid-session | Branched incoming (archived as tag), verified via reflog, fast-forwarded main to intended tip; rebuilt silently-failed edits/writes with grep-verification |

## Related Skills

- `SKILL_GIT_REMOTE_DISCIPLINE_001` — pre-push remote + SSH discipline
- `SKILL_NETWORK_CONNECTIVITY_DISCIPLINE_001` — connectivity faults from the same session
- `SKILL_UI_LIVE_VERIFICATION_BEFORE_DONE_001` — "tool success ≠ change landed" sibling rule
