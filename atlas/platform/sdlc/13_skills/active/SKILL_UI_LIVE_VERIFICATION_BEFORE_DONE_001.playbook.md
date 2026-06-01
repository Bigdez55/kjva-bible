# Live UI Verification Before "Done"

> Promoted from ATLAS UI migration failure 2026-05-30. Refined the same day with
> the Playwright capture pattern that recovered the migration. Canonical rule for
> ALL user-facing surfaces — web, Electron, mobile, CLI TUI.

## The Rule

**Build pipeline green ≠ UI works.** Curl 200, build success, lint clean, typecheck clean — these are NECESSARY signals that prove the server boots and the syntax compiles. They are NEVER SUFFICIENT to claim a UI is "done", "ready", "working", or "verified". The actual rendered surface must be observed in the target runtime, AND browser console errors must be captured.

## The Canonical Verification Recipe

### Step 1 — Playwright screenshot + console capture

For any web/Electron UI, this is the canonical pattern:

```javascript
// /tmp/verify-ui.mjs (zero-deps if Playwright is in node_modules)
import pkg from "<absolute-path>/node_modules/playwright/index.js";
const { chromium } = pkg;

const browser = await chromium.launch({ headless: true });
const ctx = await browser.newContext({
  viewport: { width: 1440, height: 900 },
  deviceScaleFactor: 2,
});

const results = [];
for (const route of ROUTES) {
  const page = await ctx.newPage();
  const errors = [];
  page.on("console", (m) => { if (m.type() === "error") errors.push("console: " + m.text()); });
  page.on("pageerror", (e) => errors.push("pageerror: " + e.message));

  await page.goto(`http://127.0.0.1:3100${route}`, { waitUntil: "domcontentloaded", timeout: 20000 });
  await page.waitForTimeout(2000);  // give client-side rendering time to settle

  await page.screenshot({ path: `/tmp/ui-verify-${route.replace(/\//g, "_")}.png`, fullPage: true });
  const text = (await page.locator("body").innerText()).replace(/\s+/g, " ").trim();
  const buttons = await page.locator("button:visible").count();
  const inputs = await page.locator("input:visible, textarea:visible, select:visible").count();
  results.push({ route, textLen: text.length, buttons, inputs, errors });
  await page.close();
}

await browser.close();
console.log(JSON.stringify(results, null, 2));
```

**Why this is canonical:**
- Screenshot = visual evidence (matches "open it and look")
- `page.on('console')` + `page.on('pageerror')` = catches CSP violations, hydration mismatches, missing chunks, ALL runtime errors invisible to server-side checks
- Button + input counts = quick proxy for "is interactivity present"
- Text length = quick proxy for "did the content render"

### Step 2 — Compare against expected

| Signal | Healthy | Suspicious |
|---|---|---|
| Console errors | 0 | ≥1 (especially "Content Security Policy", "Hydration mismatch", "Cannot read properties of undefined") |
| Visible text length | within 80% of legacy or expected baseline | < 60% of expected — likely hydration broken or content fetch failing |
| Visible buttons | matches expected count | 0 or 1 button = likely client component not hydrated |
| Visible inputs | matches expected count | 0 inputs on pages with forms = forms not hydrated |

### Step 3 — Walk the golden path

For each modified route, perform at least:
- Click the primary CTA
- Submit one form (if present) — verify success state
- Reload the page — verify no hydration error or state loss
- For Electron: also confirm the dock icon shows the brand (not generic Electron)

### Step 4 — For migrations: side-by-side parity

Before deleting legacy assets:
- Capture screenshots of BOTH legacy and new
- Compare visual layout, colors, spacing, typography
- Compare button + input counts
- **NEVER delete legacy first, then verify** — regression is irreversible without git revert + safety branch

### Step 5 — Honest reporting

Report sections:
- **Verified visually:** routes you actually loaded with screenshots
- **Verified by user:** routes the user confirmed
- **NOT visually verified:** routes that only have build-pipeline green — list them by name
- **Console errors found:** any errors captured by Playwright, by route

A truthful "build passed but I haven't opened the page" is always better than a false "verified".

## Anti-Patterns

### Trusting curl + build as proof of correctness

```bash
# WRONG — none of these touch the rendered page
curl /api/health → 200          # server boots
npm run build → success          # syntax + reachability
npm run lint → 0 errors          # style
npm run typecheck → 0 errors     # type contracts
# Therefore: "UI is done!" — NO.
```

Real example (ATLAS 2026-05-30 morning): all four green, but CSP nonce trap blocked every Next.js chunk → all 22 pages had no interactivity. Only Playwright's `page.on('console')` caught the 3 CSP violation errors per page that explained everything.

### Trusting sub-agent reports

```
Sub-agent: "✓ Build PASS, ✓ Lint PASS, ✓ All routes 200"
Parent (wrong):   "Migration complete!"
Parent (right):   "Build green per agent. Visual verification still pending —
                   running Playwright capture now."
```

The sub-agent ran the same checks the parent could run. It did NOT open the rendered surface either.

### Deleting legacy before verifying new

```bash
# WRONG — irreversible if new is broken
git rm public/old-ui/*.html
git commit -m "delete legacy, new TSX renders"
```

```bash
# RIGHT — keep legacy alongside new, verify, then delete
# 1. Add path-scoped redirects (legacy + new both reachable)
# 2. Playwright capture both surfaces, compare
# 3. User confirms parity
# 4. Delete legacy in a separate commit, with backup branch
```

### Hiding behind isolation

"The 4 parallel sub-agents each reported their builds passed." → says nothing about whether the UI works. The visual check is owed by SOMEONE — usually the parent who declares the phase done.

## Validation Gates

Before any "done" claim on UI work, ALL of these must be true:

| Gate | Pass condition |
|---|---|
| Server boot | curl /api/health → 200 |
| Build | `npm run build` exits 0 |
| Lint | `npm run lint` exits 0 (or within agreed warning budget) |
| Typecheck | `npm run typecheck` exits 0 |
| **Rendered output observed** | Playwright screenshot saved + visual inspection OR user confirmation |
| **Console clean** | Playwright captured 0 console errors + 0 pageerror events per route |
| **Golden path walked** | At least 1 interactive flow per modified route (or user-confirmed) |
| **Migration parity (if applicable)** | Legacy vs new screenshots compared; user signed off before legacy delete |
| **NOT-verified routes listed** | Report explicitly names any routes with build-green but no visual check |

Without all 9, the work is "build pipeline green" — not "done".

## Incident Record

| Date | Project | Failure | Lesson |
|---|---|---|---|
| 2026-05-30 (morning) | ATLAS UI migration Phase 1-3 | Declared 22 pages complete based on HTTP 200 + build success. Legacy /atlas-ui/*.html deleted before any page opened in a browser. User reported regression. | Build green is the floor, not the ceiling. Visual inspection mandatory. Never delete legacy before user-confirmed parity. |
| 2026-05-30 (afternoon) | ATLAS UI recovery audit | Playwright capture caught CSP-nonce-blocks-Next.js-chunks (`SKILL_NEXTJS_CSP_HYDRATION_TRAP_001`). All 22 pages had 3 identical console errors invisible to server-side checks. Once fixed, /graph went 549 → 5885 chars, 0 → 12 inputs, 0 → 75 buttons. | Playwright screenshot + console + pageerror capture is the canonical verification tool. Many bugs are invisible without browser execution. |

## Related Skills

- `SKILL_NEXTJS_CSP_HYDRATION_TRAP_001` — the bug whose discovery elevated Playwright from "suggested" to "canonical"
- `SKILL_ELECTRON_MACOS_DOCK_ICON_DISCIPLINE_001` — dock icon as a separate visible-witness signal
- `SKILL_FULLSTACK_REACT_ELECTRON_THREEJS_001` — Electron app overall
- `SKILL_RELEASE_GATE_CI_001` — CI gate (this skill is the manual companion)
- `SKILL_PARALLEL_DEPLOY_001` — multi-agent fan-out (sub-agent reports don't substitute for visual check)
