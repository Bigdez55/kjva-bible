# Browser Extension Production Readiness — Playbook

`SKILL_BROWSER_EXTENSION_001` · layer: frontend · corpus category: **Browser Extension**

Fills the `coverage_status: NONE` gap for the **Browser Extension** category of the
Production-Readiness Corpus (`platform/systems/53_production_readiness`). Every practice
below maps to a hand-authored corpus item id (`PRC.BROWSER_EXTENSION.*`). Use this skill to
move a working extension prototype to store-shippable, hardened production software.

---

## When to use

Invoke this skill when you are:

- Building, reviewing, or shipping a Chrome-family (Chrome, Edge, Brave, Opera) or Firefox extension.
- Authoring or changing `manifest.json`, a content script, a background service worker, a popup, or an options page.
- Deciding which `permissions` / `host_permissions` to request, or tightening Content Security Policy.
- Preparing a Chrome Web Store, Edge Add-ons, or Firefox AMO submission — or recovering from a rejection.
- Debugging cross-browser, multi-tab, restart, or post-session-expiry breakage.

This is the **fixing skill** the Production-Readiness Audit links when the Browser Extension
category fails. Pair it with `SKILL_PRODUCTION_READINESS_AUDIT_001` to score the category and
with `SKILL_UI_LIVE_VERIFICATION_BEFORE_DONE_001` to prove the rendered UI actually works.

---

## Key practices

### 1. Manifest, Store & Permissions  (`PRC.BROWSER_EXTENSION.MANIFEST_STORE_AND_PERMISSIONS.*`)

- **Manifest V3 only** for Chrome-family extensions (`.001`). `manifest_version: 3`, `action`
  (not `browser_action`), `background.service_worker` (not `background.page`). MV2 will not be
  accepted by the Chrome Web Store.
- **Firefox compatibility is explicit, not assumed** (`.002`). Firefox supports MV3 but with
  differences: `background.scripts` (event pages) vs `service_worker`, the `browser.*` promise
  API vs callback `chrome.*`, `browser_specific_settings.gecko.id`, and AMO review. Either
  ship a Firefox-specific manifest or use `webextension-polyfill` and test on AMO.
- **Store metadata meets guidelines** (`.003`): name, description, 128px icon set,
  and screenshots match the target store's size/content rules. State a single purpose.
- **Least-privilege permissions** (`.004`): every entry in `permissions` has a one-line written
  justification tied to a feature. Delete anything you cannot defend in a review.
- **host_permissions restricted to required domains** (`.005`): list exact origins. No
  `<all_urls>` / `*://*/*` unless a documented core feature genuinely needs it.
- **Optional permissions for non-core features** (`.006`): use `optional_permissions` and
  `optional_host_permissions`, requested at runtime via `chrome.permissions.request()` behind a
  user gesture. This is the single biggest lever on review approval and install conversion.
- **Privacy policy linked in the listing** (`.007`) — required whenever you handle user data.
- **Store review requirements checked pre-submission** (`.008`): single-purpose policy,
  data-use disclosures, remote-code ban, permission justifications.
- **Versioning + changelog maintained** (`.009`): bump `version` every release, keep a changelog.
- **Beta / unlisted test channel** (`.010`): publish unlisted or to a trusted-tester group for
  pre-release validation before public rollout.

### 2. Extension Security  (`PRC.BROWSER_EXTENSION.EXTENSION_SECURITY.*`)

- **Content scripts isolated from page scripts** (`.001`): content scripts run in an isolated
  world. Never read page globals as trusted, never expose extension APIs onto `window`, and
  bridge to page context only through validated `postMessage` if unavoidable.
- **Validate sender, origin, and payload schema on every message** (`.002`): in
  `runtime.onMessage` / `onConnect` check `sender.id === chrome.runtime.id` (and `sender.origin`/
  `sender.url` for content scripts); for `window.postMessage` check `event.origin` and
  `event.source`. Validate the payload against a typed schema. Reject anything unexpected.
- **No secrets in the bundle** (`.003`): no API keys, tokens, or private keys in JS, JSON, or
  assets. Anything shipped is public. Move secrets to a backend; the extension calls an
  authenticated endpoint.
- **No remote code execution** (`.004`): no `eval`, no `new Function`, no remotely-hosted
  `<script>`, no `import()` of remote URLs. All executable code ships in the package (an MV3 rule).
- **Tight Content Security Policy** (`.005`): keep or harden the MV3 default
  `extension_pages` CSP (`script-src 'self'; object-src 'self'`). Never add `unsafe-eval` or
  `unsafe-inline`; never widen `script-src`.
- **Least-sensitivity, encrypted-where-possible storage** (`.006`): store only what you need;
  do not write sensitive data to `storage.local` in plaintext. Encrypt with the Web Crypto API
  when the platform allows.
- **Service worker fails and restarts cleanly** (`.007`): treat the worker as ephemeral.
  Persist state to `chrome.storage` / `chrome.alarms`, never assume in-memory state survives.
- **Authenticate extension API calls securely** (`.008`): use OAuth / `chrome.identity`,
  short-lived tokens, HTTPS only; never inline long-lived credentials.
- **No cross-site data exfiltration** (`.009`): the extension must not be usable as a channel to
  read data from one origin and send it to another. Constrain network destinations and host scope.
- **Security review covers malicious-page scenarios** (`.010`): explicitly test a hostile page
  trying to call your content script, spoof messages, or trigger your handlers.

### 3. UX & Compatibility  (`PRC.BROWSER_EXTENSION.UX_AND_COMPATIBILITY.*`)

- **Small-viewport UI** (`.001`): popup typically ~300–800px wide; options and injected UI must
  fit and scroll gracefully. Design for the popup, not a full page.
- **Works across supported browser versions** (`.002`): define and test a min-version matrix
  (Chrome/Edge, and Firefox if claimed).
- **Handles logged-out / expired-session / revoked-access** (`.003`): show clear recovery UI,
  never a silent failure or blank popup.
- **Clear active/inactive status** (`.004`): badge text/color and popup state must show whether
  the extension is doing anything on this tab.
- **Injected UI does not break the host page** (`.005`): scope CSS (Shadow DOM or prefixed
  classes), avoid clobbering host layout, z-index, or focus.
- **Keyboard accessibility** (`.006`): popup and injected UI fully operable by keyboard; visible
  focus; ARIA where needed.
- **Multiple tabs and browser restarts** (`.007`): per-tab state is correct; state rehydrates
  after restart from persisted storage.
- **Performance impact measured** (`.008`): measure content-script CPU/memory and host-page
  impact; defer or lazy-load heavy work.
- **Clean disable / disconnect** (`.009`): the user can disable, log out, or disconnect and the
  extension stops cleanly with no residue.
- **Support docs** (`.010`): install, permissions explanation, troubleshooting, and uninstall.

---

## Concrete checklist / workflow

1. **Manifest pass** — `manifest_version: 3`; `action` + `background.service_worker`; min-version
   set; (Firefox manifest or polyfill if cross-browser). [`.MANIFEST...001,002`]
2. **Permission diet** — list every permission with a one-line justification; downgrade broad
   ones to optional + runtime request; pin `host_permissions` to exact origins. [`.004–006`]
3. **Secret sweep** — run a secret scanner over the *packaged* artifact; confirm zero keys. [`SECURITY.003`]
4. **RCE / CSP gate** — static-scan for `eval`, `new Function`, remote scripts; confirm tight
   CSP with no `unsafe-*`. [`SECURITY.004,005`]
5. **Isolation + message validation** — audit every message handler for sender/origin/schema
   validation; confirm content script does not trust page globals. [`SECURITY.001,002,009,010`]
6. **Service-worker resilience** — kill the worker; reopen; confirm state rehydrates and no
   logic assumed a persistent background. [`SECURITY.007`]
7. **Storage review** — confirm least-sensitivity, no plaintext sensitive data, encryption where
   possible; authenticated API calls. [`SECURITY.006,008`]
8. **UX matrix** — popup/options/injected UI at popup size; keyboard-only pass; host-page layout
   unchanged; active/inactive status visible. [`UX.001,004,005,006`]
9. **State matrix** — logged-out / expired / revoked handled; multi-tab + restart correct; clean
   disable/disconnect. [`UX.003,007,009`]
10. **Perf measurement** — record content-script impact on host pages. [`UX.008`]
11. **Store-readiness** — privacy policy URL, single-purpose statement, icons/screenshots, version
   bump + changelog, unlisted beta validated. [`MANIFEST...003,007,008,009,010`]
12. **Verify rendered surface** — load the unpacked build, walk the golden path. Do not declare
   done on build success alone (`SKILL_UI_LIVE_VERIFICATION_BEFORE_DONE_001`).

---

## Anti-patterns

| Anti-pattern | Why it fails | Corpus item | Do instead |
|---|---|---|---|
| `host_permissions: ["<all_urls>"]` for convenience | Store rejection, user-trust warning, broad attack surface | `MANIFEST...005` | Pin exact origins; optional + runtime request for the rest |
| Requesting `tabs` / `webRequest` "just in case" | Unjustified broad permission, review flag | `MANIFEST...004,006` | Justify each; downgrade to optional |
| Hardcoded API key/token in JS | Trivially extracted from public package | `SECURITY.003` | Backend holds the secret; extension calls an authed endpoint |
| `eval()` / remote `<script src>` / loosened CSP | Violates MV3, load failure or rejection | `SECURITY.004,005` | Ship all code in the package; keep tight default CSP |
| `chrome.runtime.onMessage` acts without checks | Any page/extension can drive your logic | `SECURITY.002,010` | Validate `sender.id`, origin, and payload schema; reject otherwise |
| Trusting `window.*` page globals in a content script | Malicious page escalates into the extension | `SECURITY.001,009` | Treat the page as hostile; isolate; bridge only via validated postMessage |
| In-memory cache / timer in the service worker | Lost on MV3 worker termination | `SECURITY.007` | Persist to `chrome.storage` / `chrome.alarms`; rehydrate |
| High z-index / global CSS for injected UI | Breaks host page layout and a11y | `UX.005,006` | Shadow DOM or scoped CSS; keyboard accessible |
| Blank popup after token expiry | Silent failure, user confusion | `UX.003,004` | Detect expired/revoked; show recovery UI and status |
| "Chrome works, ship to Firefox" untested | `browser.*` vs `chrome.*` and AMO differences break it | `MANIFEST...002`, `UX.002` | Polyfill + test the version matrix on each store |

---

## Related

- `SKILL_PRODUCTION_READINESS_AUDIT_001` — scores the Browser Extension category against the corpus.
- `SKILL_UI_LIVE_VERIFICATION_BEFORE_DONE_001` — load the unpacked extension and walk the golden path; build-green is not done.
- `SKILL_VERIFY_VALIDATE_001` — pre-commit / pre-ship verification gate.
- `SKILL_DESKTOP_UI_ACCESSIBILITY_001` — keyboard and a11y patterns reused for popup/injected UI.
- `SKILL_API_CONTRACT_001` — typed payload schemas for message passing and backend calls.
- `SKILL_SECURITY_AUDIT_001` — secret scanning and malicious-page threat modeling.
