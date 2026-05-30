# Next.js CSP Nonce + strict-dynamic Hydration Trap

> Promoted from ATLAS UI audit 2026-05-30. A silent killer — CI green,
> server returns 200, page looks "thin" because hydration never runs.

## The Trap

You set this on every response from your Next.js middleware/proxy:

```typescript
"script-src 'self' 'nonce-XXX' 'strict-dynamic'"
```

It LOOKS correct. CSP best-practice guides recommend exactly this pattern. It
even passes Mozilla Observatory.

**It silently breaks Next.js.** Reason:

1. `'strict-dynamic'` tells the browser: "ignore `'self'` for scripts; ONLY trust scripts that carry a nonce attribute (or are dynamically loaded by a nonced script)".
2. Next.js does NOT automatically attach the per-request nonce to its own webpack chunk `<script>` tags (verified Next 16).
3. Browser blocks every `_next/static/chunks/*.js` → React never hydrates → no `useEffect`, no `fetch`, no form handlers, no client interactivity.

Server-side it looks fine: HTML renders, HTTP 200, build green. **The bug only appears in the browser console.**

## How to Detect

If you see all of these together, it's this bug:

- Pages render the SSR shell but feel "thin" — no forms, no buttons that work
- DevTools console shows: `Loading the script '/_next/static/chunks/...' violates the following Content Security Policy directive: "script-src 'self' 'nonce-XXX' 'strict-dynamic'"`
- `npm run build`, `npm run lint`, `npm run typecheck` all PASS
- `curl /` returns HTTP 200 with full HTML
- Playwright capture shows `pageerror` events about CSP violations

## The Fix Tier List

### Tier 1 — Desktop Electron / private LAN app (simplest, recommended)

Drop nonce + strict-dynamic. `'self' 'unsafe-inline'` is acceptable because:

- The app loads only its own bundled code; no third-party scripts.
- The XSS attack surface that nonce protects against doesn't apply.

```typescript
// src/proxy.ts or src/middleware.ts
"script-src 'self' 'unsafe-inline'"
```

### Tier 2 — Hosted public app (strict CSP required)

Inject the nonce into framework script tags. Either:

- Use Next.js's experimental nonce flag (check current docs — was `experimental.csp.nonce` historically) and VERIFY at runtime that `<script>` tags actually carry the attribute. Don't trust the config name — verify the HTML.
- Or, rewrite the response body in the proxy: parse outgoing HTML, add `nonce="..."` to every `<script>` tag.

### Tier 3 — Static analysis hash-based CSP

Compute SHA-256 hashes of every inline script in the build output, list them in `script-src 'sha256-...'`. Brittle (new chunk hashes per build) but the most secure option for fully-static sites.

## Anti-Patterns

### Trusting `'strict-dynamic'` advice from CSP guides

```typescript
// WRONG for Next.js (advice from generic CSP guides)
"script-src 'self' 'nonce-X' 'strict-dynamic'"
```

The advice is correct for hand-written HTML where you control every `<script>` tag. It is wrong for Next.js where the framework emits its own scripts without nonce attribution.

### Verifying CSP changes with curl

```bash
# WRONG — proves nothing about browser behavior
curl -I /  | grep Content-Security-Policy   # header is correct
curl /     | grep -c "<script"              # chunks are present
# Conclusion: "CSP is fine!" — NO. The browser is what blocks them.
```

### Trusting build pipeline as verification

`npm run build` compiles JS. It does not execute the browser. It cannot detect CSP violations. Build green is not CSP green.

## Validation Gate

Before declaring CSP work done:

```typescript
// tests/csp-no-block.test.ts (with Playwright)
import { test, expect } from "@playwright/test";

test("no CSP violations on any route", async ({ page }) => {
  const cspErrors: string[] = [];
  page.on("console", (msg) => {
    if (msg.type() === "error" && msg.text().includes("Content Security Policy")) {
      cspErrors.push(msg.text());
    }
  });
  page.on("pageerror", (err) => {
    if (err.message.includes("Content Security Policy")) {
      cspErrors.push(`pageerror: ${err.message}`);
    }
  });
  for (const route of ["/", "/login", "/profile" /* ... */]) {
    await page.goto(`http://127.0.0.1:3100${route}`, { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(1500);  // give chunks time to attempt load
  }
  expect(cspErrors).toEqual([]);
});
```

## Incident Record

| Date | Project | Bug | Commit |
|---|---|---|---|
| 2026-05-30 | ATLAS UI migration | All 22 pages had no client interactivity. Audit showed 3 console errors per page, all `Content Security Policy ... 'strict-dynamic'`. Fix: drop nonce, use `'self' 'unsafe-inline'`. `/graph` went 549 → 5885 visible chars + 0 → 12 inputs + 0 → 75 buttons. | `2d7a502` |

## Related Skills

- `SKILL_UI_LIVE_VERIFICATION_BEFORE_DONE_001` — the verification discipline that would have caught this earlier
- `SKILL_NEXTJS_16_NATIVE_DEPS_BUNDLE_001` — Next 16 specific gotchas
- `SKILL_FULLSTACK_REACT_ELECTRON_THREEJS_001` — Electron + Next.js app pattern
