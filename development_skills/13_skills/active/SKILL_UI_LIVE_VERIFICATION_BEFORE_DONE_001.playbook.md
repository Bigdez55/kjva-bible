# Live UI Verification Before "Done"

> Promoted from ATLAS UI migration failure 2026-05-30. Canonical rule for ALL
> user-facing surfaces. Applies to web, Electron, mobile, CLI TUI.

## The Rule

**Build pipeline green ≠ UI works.** Curl 200, build success, lint clean,
typecheck clean — these are NECESSARY signals that prove the server boots and
the syntax compiles. They are NEVER SUFFICIENT to claim a UI is "done", "ready",
"working", or "verified". The actual rendered surface must be observed.

## Required Verification Steps

For any UI deliverable, before claiming completion:

### 1. Load the rendered surface in its target runtime

| Surface | How to load | How to verify |
|---|---|---|
| Web page | Open dev URL in browser | Inspect rendered DOM, click, scroll |
| Electron window | `npm run electron:dev` + window opens | Same |
| Mobile screen | Open in iOS Simulator / Android Emulator | Tap through |
| CLI TUI | Run the binary, navigate | Type commands |
| Background daemon (UI-less) | N/A — no UI verification needed |

If you cannot load the surface (no browser, no display, no sim), say so
explicitly in the report. **Never claim "verified" when only the build pipeline
was checked.**

### 2. Walk the golden path

For each modified route/screen, perform at least:
- Click the primary CTA
- Submit one form (if present) — verify success state
- Navigate via the main menu / sidebar / tab bar
- Reload the page — verify no hydration error or state loss

### 3. Capture evidence

- Screenshot: `screencapture -i /tmp/<app>-verify-<route>.png` on macOS, or browser DevTools "Capture screenshot"
- Or paste the screenshot into the user-facing report
- Or have the user confirm in writing

### 4. For migrations: side-by-side parity check

Before deleting legacy assets:
- Open legacy URL in tab A, new URL in tab B
- Compare visual layout, colors, spacing, typography
- Compare functional behavior (forms, navigation, dynamic content)
- Document any divergence — user approves before legacy is removed
- **NEVER delete legacy first, then verify** — if the new is broken, regression is irreversible without git revert

### 5. Honest reporting

Report sections:
- **Verified visually:** routes/screens you actually loaded and inspected
- **Verified by user:** routes the user confirmed
- **NOT visually verified:** routes that only have build-pipeline green — list them by name
- **Known issues:** anything you saw but didn't fix

A truthful "build passed but I haven't opened the page" is always better than a
false "verified".

## Anti-Patterns

### Trusting curl + build as proof of correctness

```bash
# WRONG — this only proves the server responds + JS compiles
curl http://localhost:3100/ → 200          # server boots
npm run build → success                    # syntax + reachability
npm run lint → 0 errors                    # style
npm run typecheck → 0 errors               # type contracts
# Therefore: "UI is done!" — NO. None of these touched the rendered page.
```

```bash
# RIGHT — add the visual check before declaring done
curl http://localhost:3100/ → 200          # necessary
npm run build → success                    # necessary
npm run lint → 0 errors                    # necessary
npm run typecheck → 0 errors               # necessary
open http://localhost:3100/                # SUFFICIENT — actually loads it
# Then: screenshot + walk golden path + compare to spec
```

### Trusting sub-agent reports

```
Sub-agent: "✓ Build PASS, ✓ Lint PASS, ✓ All routes 200"
Parent (wrong):   "Migration complete!"
Parent (right):   "Build green per agent report. Visual verification still pending —
                   I haven't loaded the pages. Let me open the Electron window now."
```

The sub-agent ran the same checks the parent could run. It did NOT open the
rendered surface either. The visual verification is still owed.

### Deleting legacy before verifying new

```bash
# WRONG — irreversible if new is broken
git rm public/atlas-ui/*.html
git commit -m "delete legacy, new TSX renders"
# (... user opens app, new TSX is regressed, legacy is gone)
```

```bash
# RIGHT — verify new in parallel, then remove legacy
# 1. Hybrid redirects: /atlas-ui/* still serves legacy AND /new-route serves new
# 2. User confirms new looks/works right
# 3. Then delete legacy
git rm public/atlas-ui/*.html
git commit -m "delete legacy after user-confirmed parity"
```

### Hiding behind isolation

```
"The 4 parallel sub-agents each reported their builds passed."
```

That sentence says nothing about whether the UI works. It proves 4 builds
compiled. The visual check is owed by SOMEONE — usually the parent who
declared the phase done.

## Validation Gates

Before any "done" claim on UI work, all of these must be true:

| Gate | Pass condition |
|---|---|
| Server boot | curl /api/health → 200 |
| Build | `npm run build` exits 0 |
| Lint | `npm run lint` exits 0 (or within agreed warning budget) |
| Typecheck | `npm run typecheck` exits 0 |
| **Rendered output observed** | Screenshot OR user confirmation OR Playwright capture |
| **Golden path walked** | At least 1 interactive flow per modified route |
| **Migration parity (if applicable)** | Legacy vs new compared side-by-side |
| **NOT-verified routes listed** | Report explicitly names routes that have build-green but no visual check |

Without all 8, the work is "build pipeline green" — not "done".

## Incident Record

| Date | Project | Failure | Lesson |
|---|---|---|---|
| 2026-05-30 | ATLAS UI migration (Phases 1-3) | Declared 22 pages complete based on HTTP 200 + npm run build success. Legacy public/atlas-ui/*.html deleted before any page was opened in a browser. User opened the Electron window and reported regression — visual fidelity gone, features broken. | HTTP 200 + build pass is the floor of verification, not the ceiling. Visual inspection is mandatory. Never delete legacy before user-confirmed parity. |

## Related Skills

- `SKILL_FULLSTACK_REACT_ELECTRON_THREEJS_001` — Electron app patterns
- `SKILL_RELEASE_GATE_CI_001` — CI release gates (this skill is the manual companion)
- `SKILL_PARALLEL_DEPLOY_001` — multi-agent fan-out (sub-agent reports don't substitute for visual check)
- `SKILL_VERIFY_VALIDATE_001` — broader verify+validate discipline
