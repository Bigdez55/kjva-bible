# skill-continuous-improvement-loop

<!-- Source: migrated from ~/.claude/skills/skill-continuous-improvement-loop/SKILL.md on 2026-05-26 -->
<!-- Runtime alias: skill-continuous-improvement-loop -->

**Summary.** Meta-skill that codifies the practice of authoring and refining skills after every session. Invoke at session-close, post-milestone-PR, pre-release-tag, after any reverted change, during post-mortems, or at end-of-loop in autonomous /loop runs. Also triggers on phrases: "wrap up", "what did we learn", "session close", "milestone complete", "before tagging release", "post-mortem". Every non-trivial session closes with a Session Learnings Review producing two written artifacts (session_learnings.md + candidate_skill_updates.md) so observed patterns become durable skill refinements instead of evaporating into chat history.

# Skill Continuous Improvement Loop

## When to invoke

Session-close, post-milestone-PR, pre-release-tag, after any reverted change, post-mortem, or end-of-loop in autonomous /loop runs. Also trigger on phrases: "wrap up", "what did we learn", "session close", "milestone complete", "before tagging release", "post-mortem".

## Core directive

Every session that touches non-trivial production code MUST close with a Session Learnings Review producing two written artifacts:

1. `session_learnings.md` — concrete patterns observed this session, with file:line citations, empirical anchors, and failure modes encountered.
2. `candidate_skill_updates.md` — proposed skill refinements or new skills, each with:
   - Target skill name (or NEW)
   - Concrete addition text (paste-ready)
   - Trigger phrases (when the skill should auto-activate)
   - Empirical anchor (this session's evidence)
   - Project-agnostic framing
   - Cross-references to related skills

Both artifacts attached to session close; reviewed BEFORE next session's open.

## Candidate-vs-Refinement Decision Tree

- Directive collapses without a SPECIFIC anchor → REFINEMENT to existing skill (deepen)
- Directive stands alone with agnostic framing → NEW skill
- Multiple sessions surfaced the same lesson → NEW skill (graduate from refinement)

## Author-Review-Merge Workflow

1. Author draft `candidate_skill_updates.md` at session close.
2. advisor() review of candidates BEFORE editing any SKILL.md.
3. Apply approved edits one-at-a-time (advisor before each).
4. Quarterly skill audit — re-read every SKILL.md, mark stale anchors, prune obsolete sections.

## Empirical anchor (from v31.5.I.F1 closeout)

Session surfaced 7 candidate skill updates organically (harness process leak, A/B verification, STORE width promotion guard, state-dependent transient FLAG-don't-dismiss, helper extraction mandate, contention isolation, pipeline connection map). Without a closing loop, these would have evaporated into chat history. The skill ensures durable capture.

## Cross-references

- ALL skills (this is the meta-loop that grows them)
- `audit-assess-analyze` (depth standard for learnings review)
- `one-shot-execution-planning` (mirror artifact-as-proof pattern)
- `verify-validate` (gate before closing the session)

## Anti-patterns

- "Just remember it" → skill not authored → lesson lost
- Refinement without empirical anchor → bloats skill body without sharpening
- New skill duplicating existing skill's scope → cross-reference instead
