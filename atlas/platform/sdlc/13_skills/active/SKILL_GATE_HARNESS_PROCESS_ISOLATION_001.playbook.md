# Gate Harness Process Isolation

<!-- Source: migrated from ~/.claude/skills/gate-harness-process-isolation/SKILL.md on 2026-05-26 -->
<!-- Runtime alias: gate-harness-process-isolation -->

# Gate Harness Process Isolation

## When to invoke
Triggers: "harness timeout", "retry storm", "test runner hang", "perl alarm", "bash timeout", "process leak", "orphan PID", "CI gate hanging", "macOS test runner", any CI/gate runner on macOS/BSD that uses shell timeouts (perl alarm, `timeout` wrapped in `bash -c`, `kill $!`).

## Core directive
**Shell-based timeouts do NOT terminate descendant process groups on non-Linux POSIX systems.** When a harness times out a wrapped command, child processes orphan to launchd (macOS) or init, accumulate, and cause retry-storms. MANDATORY: ensure the timeout wrapper kills the entire process group.

## Detection symptoms
1. `ps -eo pid,pgid,command` shows orphaned children of the harness after timeout fires.
2. Subsequent gate runs slower than first (CPU/memory contention from leaked children).
3. Gate retry pattern compounds: 3 retries × N sub-gates × M tiers → up to 3*N*M orphan processes.
4. Tests that pass standalone fail under aggregator orchestration.

## Platform matrix
- **Linux GNU**: `timeout --kill-after=5s $T $cmd` available; correctly kills process group when using `--foreground` or via `setsid` wrapping.
- **macOS BSD**: NO GNU `timeout`. `gtimeout` via `brew install coreutils` exists but is not standard. `setsid` binary may not be available. Must use `perl POSIX::setpgid` or `bash -m` job-control.
- **WSL**: Linux semantics apply.

## Remediation patterns

### Pattern A — Perl POSIX::setpgid fork+exec (macOS-friendly)
```bash
out=$(perl -e 'use POSIX;
my $t=shift; my $pid=fork();
if(!defined $pid){die "fork: $!\n";}
if($pid==0){POSIX::setpgid(0,0); exec @ARGV; exit 127;}
POSIX::setpgid($pid,$pid);
$SIG{ALRM}=sub{kill("TERM",-$pid); sleep 2; kill("KILL",-$pid);};
alarm $t; waitpid($pid,0); my $rc=$?; alarm 0;
exit($rc>>8);' "$timeout_s" bash -c "$cmd" 2>&1)
```

### Pattern B — setsid + kill -PG
```bash
setsid bash -c "$cmd" &
PGID=$!
(sleep "$timeout_s"; kill -TERM -"$PGID" 2>/dev/null; sleep 2; kill -KILL -"$PGID" 2>/dev/null) &
KILLER=$!
wait "$PGID"; rc=$?
kill "$KILLER" 2>/dev/null
```

### Pattern C — Drop the retry (preferred when feasible)
3-attempt retry magnifies the leak 3x. If the underlying flake is harness, not SUT, fix the harness instead of papering with retries.

## Empirical anchor
SUPER C v31.5.I.HARNESS (commit 23a85d6f) — `scripts/gates/lib/check_gate.sh` used `perl -e 'alarm N; exec @ARGV' bash -c "$cmd"`. On SIGALRM perl was already replaced by bash (via exec); bash inherited the alarm and died, but bash's `scc` children orphaned. 3-retry × 7-subgate × 3-tier produced 4+ simultaneous tier2_validator processes, ~30x normal runtime. Replaced with Pattern A — `harness_no_orphan_gate.sh` (3/0 PASS) witnesses zero post-timeout orphan accumulation.

## Verification gate (mandatory after any harness fix)
1. Spawn a known-stuck fixture (`sleep 200` with unique marker).
2. Apply the harness wrapper with short timeout (3-5s).
3. Sleep past timeout + grace.
4. Assert `pgrep -f <marker>` count returns to baseline (0).
5. Run normal regression suite (scc_smoke equivalent) to verify no SUT change.

## Cross-references
- `verify-validate` — pre-commit gate discipline
- `sentinel` / `test-harness` — test runner architecture
- `compiler-discipline` — SCC gate semantics

## Anti-patterns
- Increasing per-attempt timeout instead of fixing process management
- Adding `killall` to gate cleanup (collateral damage on other agent processes)
- Assuming "if scc_smoke passes the harness is fine" (smoke ≠ orphan check)
