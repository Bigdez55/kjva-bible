# gate-contention-isolation

<!-- Source: migrated from ~/.claude/skills/gate-contention-isolation/SKILL.md on 2026-05-26 -->
<!-- Runtime alias: gate-contention-isolation -->

**Summary.** Triage discipline for test/gate failures that present as "flaky" but are actually rooted in timing-sensitive assertions, shared mutable state, or resource exhaustion under parallel execution and system contention. Forces a mandatory three-tier reproduction protocol (standalone → serial-in-batch → parallel) BEFORE any failure can be classified as flake. Triggers on phrases like "passes alone fails in batch", "CI-only failure", "flaky under load", "intermittent test", "parallel test failure", "timing-sensitive", "works on my machine", and "test fails only in suite". Anchored by the SUPER C v31.5.I `sco_validate_digest_gate` 12/0 → 11/1 contention episode, where orphan `scc` processes from prior gold_gate runs polluted the gate's shared state. Cross-references `gate-harness-process-isolation`, `sc-empirical-surface-probe`, `verify-validate`, and `test-harness`.

# Gate Contention Isolation

## When to invoke
Triggers: "passes alone fails in batch", "CI-only failure", "flaky under load", "intermittent test", "parallel test failure", "timing-sensitive", "works on my machine", "test fails only in suite".

## Core directive
**Tests passing standalone but failing under parallel execution or system contention indicate timing-sensitive assertions, shared mutable state, or resource exhaustion — NOT flake.** MANDATORY three-tier reproduction protocol before declaring "flake":

1. **Standalone** — Run the failing test alone in a clean process state.
2. **Serial-in-batch** — Run the suite serially (NO concurrent processes from other tests).
3. **Parallel** — Run with at least 2 concurrent instances of the same test or related tests.

Report which condition flips RC. Forbidden: declaring "flake" without all three runs documented.

## Contention-source taxonomy
1. **CPU contention** — Test relies on wall-clock timeout that's exceeded only under load.
2. **FD limit** — Each test opens many files; ulimit-bound under parallel.
3. **Port collision** — Test binds to fixed port; second instance fails.
4. **Filesystem collision** — `/tmp/<gate>.log` shared between concurrent runs; race overwrites.
5. **Build cache** — Test modifies build artifacts that other tests depend on.
6. **Process-group orphan compounding** — See cross-ref `gate-harness-process-isolation`.

## Resolution patterns
- **Resource fences**: each test gets a unique tmpdir (`mktemp -d`).
- **Port pool**: allocate from a range; test gets next-free.
- **Build serialization**: tests that mutate build artifacts gated by a lockfile.
- **Independent process groups**: see `gate-harness-process-isolation`.
- **Hard timeouts with slack**: per-test budget = 3-5x measured standalone time.

## When to mark environmental vs source defect
- Three-tier protocol consistent across runs → source defect (race, shared state).
- Variable under load only (PASS at low load, FAIL at high load) → environmental + harness fragility.
- PASS standalone, PASS in batch, FAIL in parallel → genuine concurrent-safety bug.

## Empirical anchor
SUPER C v31.5.I session — `sco_validate_digest_gate` PASSED 12/0 standalone, then 11/1 minutes later. Investigation revealed leftover orphaned `scc` processes from prior gold_gate runs (harness retry-storm). After applying `gate-harness-process-isolation` fix, standalone gate became deterministic. The three-tier protocol caught the contention source as harness, not source.

## Tooling guidance
- `pgrep -f <pattern> | wc -l` — count concurrent instances
- `ps -eo pid,pgid,etime,command | grep <pattern>` — process tree audit
- `uptime` — load average reading
- Per-test timing — capture with `time` to detect timing drift under load

## Cross-references
- `gate-harness-process-isolation` — when contention IS the harness
- `sc-empirical-surface-probe` — A/B reproduction methodology
- `verify-validate` — pre-commit gate discipline
- `test-harness` — test runner architecture

## Anti-patterns
- Quietly retrying failed tests in CI without investigation
- Marking "flake" → silencing → real defect masked
- Increasing timeouts as the universal fix
- Assuming gate output is authoritative when contention may have polluted shared paths
