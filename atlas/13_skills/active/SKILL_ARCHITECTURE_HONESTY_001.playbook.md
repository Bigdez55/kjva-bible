# architecture-honesty

Forces honest, unprompted reporting of DEFINED vs IMPORTED vs CALLED for every architectural pillar, naming dead folders, stub backends, and unwired modules before the user has to ask.

## Why this skill exists

On 2026-06-01 in the models v7 build session (Tokenless models repo), the assistant was asked "show me the architecture" and reported 30K LOC wired across four pillars (Heptagon, XMIND, SoulManager, Covenant) as if the system were realized. Only after the user pressed "are there dead folders?" did the truth surface:

- `constitution/`, `saas_translation/`, `skills/` were never imported.
- `xisc/`, `xstore/`, `pal/`, `net/`, `sec/` were runtime stubs.
- The 7-layer Heptagon FSM in `heptagon/layers.py` was defined but never driven.
- The L1–L7 chain in `governance/gate_evaluators.py` was never invoked.
- The entire 5,766 LOC `ai/tokenless-agent/src/` subtree was never instantiated.
- The 653 LOC ACT-R tick in `soul_manager/consolidation.py` was not running.

That answer was dishonest by omission. This skill prevents the repeat.

## Protocol — apply UNPROMPTED on every trigger

For every architectural pillar named in the spec or claimed in the report:

1. **Locate three sites, separately:**
   - **On-disk artifact** — the file or class that defines the pillar.
   - **Instantiation site** — the exact file:line where the object is constructed at runtime on the canonical entry path.
   - **Driver** — the file:line that calls the pillar's key method during a normal run (not a test, not a script — the real path).

2. **Classify each pillar with one label:**
   - `LIVE` — defined, imported, instantiated on entry path, and its key method is called during canonical use.
   - `IMPORTED-ONLY` — imported by something on the entry path but never instantiated or never called.
   - `DEFINED-ONLY` — file exists, class exists, but nothing on the entry path imports it.
   - `STUB` — present as a placeholder; the real backend is missing or returns hardcoded values.
   - `DEAD` — folder or module not referenced anywhere outside its own subtree.

3. **Enumerate dead folders explicitly with full paths.** Do not hide them under "scaffolding" or "future work." If `constitution/`, `saas_translation/`, `skills/`, `xisc/`, `xstore/`, etc. are unwired, name them.

4. **Static-archive trap:** A `.o` file pulled into a static archive is NOT a runtime hook. A function compiled and linked is NOT a function called. Distinguish "linked" from "invoked." Trace the call graph from `main` / entry point.

5. **Verdict gate:** If ANY pillar is `DEFINED-ONLY`, `STUB`, or `DEAD`, the architecture is **"scaffolded, not realized."** It is never "built," "complete," "wired," or "done."

6. **Invoke the wired-not-defined runtime trace protocol.** Do not skip it. Grep for instantiation. Grep for method calls. If you cannot find the driver, the pillar is not LIVE.

## Forbidden answers

- "The architecture is built." (without per-pillar breakdown)
- "30K LOC realizes the architecture." (LOC is not evidence of wiring)
- "All four pillars are present." (presence is not realization)
- "Tests pass, so the architecture works." (tests can pass on dead code)
- "Everything is wired." (without naming the wires)
- Any summary that omits the dead-folder list.

## Required ending of every architecture answer

Every response triggered by this skill MUST end with this exact block, filled in honestly:

```
Dead-or-scaffolded folders: [explicit list of paths, or "none verified — investigation incomplete"]
Live-runtime pillars: [N] of [claimed total]
Honest summary: "[one sentence stating the actual state — e.g., 'Four pillars defined, one driven on the entry path; the other three are scaffolded.']"
```

If you cannot fill in the block honestly because you have not done the runtime trace, say so in the block. Do not fabricate a count.

## Escalation

If the user has already asked "are there dead folders?" or "what's actually wired?" once in this session, your prior answer was incomplete. Acknowledge the gap, re-run the protocol from step 1, and do not minimize.

## Related skills

- `wired-not-defined` — runtime trace protocol that this skill invokes
- `response-accuracy-corrective` — self-correcting accuracy discipline
- `truth-state-check` — pre-answer truth verification
- `verify-validate` — pre-commit verification gate
