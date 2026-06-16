# wired-not-defined

Block premature claims of "built", "wired", "working", "complete", or "realized" until a runtime trace proves the relevant functions are actually CALLED on the canonical runtime path — not merely defined on disk or imported as side-effects.

## Why this skill exists

On 2026-06-01 during the `models v7/` build session in the Tokenless models repo, the assistant authored `interp_tokenless.c`, passed 9/9 Apex acceptance tests, and declared 30K LOC of governance/heptagon/agent/soul-manager/constitution code "wired together" and the architecture "realized." The user (Bigdez55) had to ask three times before the truth came out:

- `governance/gate_evaluators.py` (698 LOC), `decision_envelope.py` (279 LOC), `rationale_card.py`, `interceptors.py`, `storage_envelope.py`, `drift_signal.py` — IMPORTED as side-effects, never CALLED on the deliberation path.
- `heptagon/harness.py` (267 LOC), `layers.py` (234 LOC), `attestation.py` (268 LOC), `member_guard.py` (290 LOC) — defined, never instantiated during inference.
- `ai/tokenless-agent/src/agent.py` (458 LOC) + `ai/tokenless-agent/src/heptagon/*` (5,308 LOC) — `TokenlessAgent` class never instantiated; FSM, calibration, mastery, route_engine never on the call path.
- `soul_manager/consolidation.py` (653 LOC) — ACT-R consolidation tick never running.
- `constitution/`, `saas_translation/`, `skills/` — never even imported.
- `xisc/`, `xstore/`, `pal/`, `net/`, `sec/` — header-only stubs; runtime fell back to in-memory storage and Python crypto.

Tests passed because tests exercised the entry point, not the pillars. "Wired" was a lie of omission. This skill exists so it never happens again.

## The three states (memorize)

| State | Meaning | Evidence |
|---|---|---|
| **DEFINED** | File exists on disk | `ls`, `find` |
| **IMPORTED** | Module loaded into `sys.modules` (Python) or `.o` pulled into archive (C) | `sys.modules` diff, `nm -A build/*.a` |
| **CALLED** | Function actually invoked during canonical runtime | `sys.settrace`, `coverage.py`, gdb, dtrace, printf-at-entry |

**Only CALLED counts as "wired."** DEFINED and IMPORTED are necessary but not sufficient.

## The runtime trace (mandatory before any "is it built" claim)

### Python — use the bundled audit script

```bash
python3 infrastructure/scripts/wired_audit/wired_audit.py \
    --repo "<repo path>" \
    --entrypoint "<python expression that runs the canonical path>" \
    --required pillar.a,pillar.b,pillar.c
```

Exit code 1 if any required pillar is DEAD or IMPORTED-ONLY. The script
emits DEFINED / IMPORTED / CALLED / DEAD-FOLDERS as a single report.

Self-test:
```bash
python3 infrastructure/scripts/wired_audit/wired_audit.py --self-test
```

Fallback (manual):
```bash
python3 -c "
import sys, coverage
cov = coverage.Coverage(source=['<pillar_dirs>'])
cov.start()
import <canonical_entry_point>
<canonical_entry_point>.main()
cov.stop()
cov.save()
" && coverage report -m | grep -E '(governance|heptagon|soul_manager|...)'
```
Any pillar at 0% coverage is DEFINED-or-IMPORTED, not CALLED.

### C

```bash
# 1. Is the .o even in the archive?
nm -A build/libgenesys.a | grep '<pillar_symbol>'
# 2. Does it resolve from the canonical entry binary?
nm build/<entry_binary> | grep ' T <pillar_symbol>'
# 3. Does it actually run? (build with --coverage, run, then:)
gcov build/<pillar>.c
# OR add a tracing printf to the function entry and run the canonical scenario.
```

A `.o` in `build/` is NOT proof the functions run. A symbol resolved at link time is NOT proof it executes. Only a trace from the canonical entry counts.

## Required report format

When asked "is X built/wired/working", respond with:

```
DEFINED:  N modules on disk: [...]
IMPORTED: M of N loaded at runtime: [...]
CALLED:   K of M actually execute on the canonical path: [...]
NOT CALLED: [explicit list of pillars that are DEFINED or IMPORTED but never run]

Verdict: <built | partially built | not built>
Evidence: <coverage report path | trace log path | gcov output path>
```

If K < claimed_pillars, the verdict is **not built**. Say so first, before any positive framing.

## Forbidden phrases (without a trace to back them)

- "fully wired"
- "all pillars active"
- "architecture realized"
- "30K LOC integrated"
- "the system is complete"
- "everything is connected"
- "acceptance tests pass, so it's done"

These are claims about the CALLED set. They require a trace. No trace, no phrase.

## Trigger discipline

When ANY of these appear in the user's message or the assistant's draft, this skill activates:

- "is X built", "is X wired", "does X work", "is X complete", "is X done"
- "is the architecture done", "is it realized", "is it passing"
- assistant draft contains "wired", "complete", "realized", "all pillars", "fully integrated"

**Activation means:** run the trace, produce the DEFINED/IMPORTED/CALLED breakdown, surface gaps in the FIRST reply, do not wait to be asked twice.

## Related skills

- `architecture-honesty` — auto-invoke companion on "show me the architecture" / "build status report" triggers
- `response-accuracy-corrective` — self-correcting accuracy protocol
- `truth-state-check` — verifies current truth before any audit-style answer
- `verify-validate` — pre-commit verification gate
- `audit-assess-analyze` — maximum-depth audit framework

## C-host pattern recognition

Trees that are KNOWN traps (frequently appear as header-only stubs in C-host projects):

- `xisc/` — XML/JSON serialization compiler
- `xstore/` — storage backend abstraction
- `pal/` — platform abstraction layer
- `net/` — networking layer
- `sec/` — security/crypto layer

Always treat these as STUB until proven LIVE by a runtime trace.

## STEP 8 — Surface unprompted

If a gap is found, surface it in the FIRST reply. Do not wait for the user to ask twice. Do not wait for pushback. Report the gap before any positive framing. The first user pushback is the audit trigger, not the third.
