# Mobile Application Production Readiness — Playbook

**Skill:** `SKILL_MOBILE_APP_PRODUCTION_001`
**Corpus category owned:** `Mobile Application` (`PRC.MOBILE_APPLICATION`, `coverage_status: NONE` → this skill fills it)
**Source of truth:** the production-readiness corpus. The category has three sections and 58 items; item IDs are `PRC.MOBILE_APPLICATION.<SECTION>.NNN`. This playbook teaches how to satisfy each item with verifiable evidence. Corpus item text is verbatim — never paraphrase or invent items, and note the category `default_severity` is `medium` with no per-item severity defined.

---

## When to use

Use this playbook whenever a mobile app (iOS, Android, or cross-platform such as React Native / Flutter / Expo) is approaching a real release, specifically:

- Preparing a release candidate for the App Store or Google Play.
- Reviewing signing, provisioning, store metadata, privacy manifests, or Data Safety declarations.
- Hardening secret storage, network security, certificate pinning, crash/performance telemetry, accessibility, or OTA updates.
- Running a mobile go/no-go before submission.

This skill is a **category specialist** under `SKILL_PRODUCTION_READINESS_AUDIT_001` (the orchestrator). The orchestrator computes the cross-category tier and go/no-go; this skill produces the evidence-backed PASS/FAIL for the Mobile Application category. Inherit its discipline: **no item is marked pass without evidence** (a path, a command and its result, or a cited artifact), and a green build alone is not "done."

The three corpus sections:

1. `IOS_PRODUCTION_READINESS` — 19 items
2. `ANDROID_PRODUCTION_READINESS` — 20 items
3. `CROSS_PLATFORM_AND_SECURITY` — 19 items

---

## Key practices by corpus section

### 1. iOS Production Readiness (`IOS_PRODUCTION_READINESS.001`..`.019`)

- **Project identity & permissions.** Bundle ID and team configured in Xcode (`.001`); `Info.plist` carries a usage-description string for every requested permission (`.002`); declare background modes only for functionality you actually use (`.010`).
- **Privacy & store compliance.** Submit `PrivacyInfo.xcprivacy` for review (`.003`); complete the App Store privacy questionnaire accurately (`.016`); complete the listing — screenshots, description, privacy policy URL (`.015`).
- **Platform target & layout.** Define a minimum iOS version, targeting iOS 16+ for 2024+ releases (`.004`); test universal layout on iPhone and iPad (`.005`); handle notch, Dynamic Island, and Safe Area insets (`.006`); test dark and light mode (`.007`).
- **Security.** Enforce App Transport Security with no `NSAllowsArbitraryLoads` in production (`.008`); store all sensitive data — tokens, passwords, cryptographic keys — in the Keychain (`.009`).
- **Distribution & delivery.** Configure an APNs certificate or auth key for push (`.011`); sign with a distribution certificate and provisioning profile (`.012`); configure Universal Links with an AASA file at `/.well-known/apple-app-site-association` (`.013`); use TestFlight for beta before submission (`.014`).
- **Commerce & telemetry & a11y.** Validate IAP receipts server-side, never client-side only (`.017`); upload symbols to Crashlytics/Sentry for symbolication (`.018`); test Dynamic Type and VoiceOver (`.019`).

### 2. Android Production Readiness (`ANDROID_PRODUCTION_READINESS.001`..`.020`)

- **Build identity & targets.** `applicationId`, `versionCode`, `versionName` correct (`.001`); `minSdk`/`targetSdk` at current recommended values (`.002`); ProGuard/R8 minification with tuned rules (`.009`).
- **Assets & layout.** Adaptive icons for all launcher versions (`.003`); all screen densities mdpi→xxxhdpi (`.004`); edge-to-edge display with window insets handled (`.005`); dark and light theme tested (`.006`).
- **Security.** Sensitive data in the Android Keystore, not SharedPreferences plaintext (`.007`); `android:allowBackup=false` or backup rules that exclude sensitive data (`.008`); network security config disables cleartext traffic in production (`.010`); request runtime permissions with a rationale dialog before the system prompt (`.011`).
- **Distribution & delivery.** FCM push configured and tested end-to-end (`.012`); App Signing by Google Play enrolled (`.013`); ship an Android App Bundle, not an APK (`.014`); App Links via Digital Asset Links configured and tested (`.015`).
- **Commerce, telemetry, a11y, battery.** IAP verified server-side via the Google Play Developer API (`.016`); Data Safety section accurate (`.017`); symbols uploaded for symbolication (`.018`); TalkBack and font scaling tested (`.019`); background tasks use WorkManager (`.020`).

### 3. Cross-Platform & Security (`CROSS_PLATFORM_AND_SECURITY.001`..`.019`)

- **Framework & OTA.** Pin the framework version with a defined upgrade path (`.001`); define an OTA update policy — Expo Updates or CodePush with signed updates (`.002`); sign OTA updates and verify the signature before applying (`.003`).
- **Links.** Test deep links on both iOS and Android (`.004`).
- **Network security.** Certificate pinning for all API calls, **pin renewed before expiry** (`.005`); all network calls over HTTPS with certificate validation enabled and never disabled (`.012`).
- **Data hygiene.** Keep sensitive data out of logs, temp files, and screenshots (`.006`); do not capture screenshots of sensitive-data screens (`.007`); clear the clipboard of sensitive data after a defined timeout (`.008`).
- **Auth & session.** Integrate biometric authentication — Face ID / fingerprint (`.009`); session timeout after an inactivity period (`.010`).
- **Secrets & threat model.** API keys never hardcoded in the client; use a backend proxy (`.011`); review the Mobile OWASP Top 10 and mitigate all applicable risks (`.013`).
- **Performance & resilience.** Cold-start target `< 2s` (`.014`); 60fps during animations (`.015`); no memory leaks on screen transitions, profiled (`.016`); core features usable offline (`.017`); download size `< 50MB` where possible (`.018`); crash reporting analytics configured (`.019`).

---

## Concrete pre-submission workflow / checklist

Run top to bottom. Each item must have reproducible evidence; record PASS/FAIL/N-A with the cited artifact and the corpus item ID.

1. **Signing & artifact** — fresh CI checkout produces a signed `.ipa` (IOS.012, to TestFlight IOS.014) and a signed `.aab` (ANDROID.013/.014) with no manual cert wrangling; all certs/profiles valid past release date.
2. **Privacy & store** — `PrivacyInfo.xcprivacy` submitted (IOS.003); App Store questionnaire (IOS.016) and Play Data Safety (ANDROID.017) accurate; listing complete (IOS.015).
3. **Secret storage** — static scan + on-device dump: zero secrets in SharedPreferences/plaintext, zero hardcoded API keys; all secrets via Keychain/Keystore (IOS.009, ANDROID.007, CROSS.011).
4. **Network security** — proxy capture: all HTTPS with validation on, no `NSAllowsArbitraryLoads` (IOS.008), Android cleartext disabled (ANDROID.010, CROSS.012).
5. **Certificate pinning** — pin set documented with expiry + rotation date earlier than expiry, backup pin present (CROSS.005).
6. **Crash & perf telemetry** — test crash lands symbolicated (IOS.018, ANDROID.018, CROSS.019); cold start `< 2s` (CROSS.014), 60fps (CROSS.015), no transition leaks (CROSS.016).
7. **IAP integrity** — server-side receipt validation rejects a bad receipt (IOS.017, ANDROID.016).
8. **OTA** — update policy defined; OTA signed and signature verified before apply (CROSS.002, CROSS.003).
9. **Links** — Universal Links (IOS.013) and App Links (ANDROID.015) open the installed app; deep links tested both platforms (CROSS.004).
10. **Accessibility** — VoiceOver + Dynamic Type (IOS.019), TalkBack + font scaling (ANDROID.019) complete the primary flow.
11. **Data hygiene** — no sensitive data in logs/temp/screenshots (CROSS.006/.007); clipboard auto-clear (CROSS.008).
12. **Threat model** — Mobile OWASP Top 10 reviewed and mitigated (CROSS.013).
13. **Layout & theming** — iPhone/iPad + insets (IOS.005/.006), edge-to-edge (ANDROID.005), dark/light (IOS.007, ANDROID.006), densities/adaptive icons (ANDROID.003/.004).
14. **Footprint & offline** — download `< 50MB` (CROSS.018); core features offline (CROSS.017); Android background via WorkManager (ANDROID.020).

**Output:** a category report with PASS/FAIL/N-A + evidence per item ID. N-A must be justified by the active profile (e.g., an iOS-only app marks Android items N-A with a reason) — never silently skip an item.

---

## Anti-patterns

| Anti-pattern | Why it fails | Do instead |
|---|---|---|
| Filling store metadata / privacy forms at submission time | App Store / Play rejection burns a review cycle and the release date (IOS.003, IOS.016, ANDROID.017) | Submit PrivacyInfo.xcprivacy and complete questionnaires/Data Safety before code-freeze |
| Manual cert juggling on a developer laptop | Expired profile / lost key blocks release; not reproducible (IOS.012, ANDROID.013) | CI-driven signing; enroll Play App Signing; ship an AAB (ANDROID.014); track expiries |
| Storing a token in SharedPreferences / hardcoding an API key | The bundle is extractable; plaintext secrets leak (ANDROID.007, CROSS.011) | Keychain / Keystore only; route keys through a backend proxy; verify by device dump |
| Leaving `NSAllowsArbitraryLoads` on "to unblock dev" | Cleartext traffic ships to production (IOS.008, ANDROID.010, CROSS.012) | Enforce ATS / network security config; verify HTTPS-only via proxy capture |
| Pinning a single cert and forgetting it | Silent pin expiry bricks the app for all users (CROSS.005) | Pin live + backup key; rotation date earlier than expiry; document it |
| Shipping without uploading dSYMs / mapping files | Crash reports arrive unsymbolicated and are useless (IOS.018, ANDROID.018) | Automate symbol upload in the release build; verify with a test crash |
| Validating IAP receipts only on-device | Trivial entitlement bypass (IOS.017, ANDROID.016) | Validate server-side / via Google Play Developer API |
| "We added accessibility labels" without a screen-reader run | Unlabeled controls remain (IOS.019, ANDROID.019) | Walk the primary flow with VoiceOver and TalkBack, Dynamic Type / font scaling on |
| Marking a category PASS without evidence | Checkbox theater; false-green at go-live | Every PASS = a reproducible check (command output, capture, dashboard) cited to the item ID |

---

## Related

- **`SKILL_PRODUCTION_READINESS_AUDIT_001`** — the orchestrator that runs the full corpus gate and renders go/no-go; this skill feeds it the Mobile Application category result.
- **`SKILL_SECURITY_AUDIT_001`** — secret-handling, network-security, and OWASP depth (supports IOS.008/.009, ANDROID.007/.010, CROSS.005/.011/.012/.013).
- **`SKILL_OBSERVABILITY_001`** — telemetry, alerting, and SLOs (supports IOS.018, ANDROID.018, CROSS.014–.016/.019).
- **`SKILL_DESKTOP_UI_ACCESSIBILITY_001`** — accessibility patterns transferable to mobile screen readers (supports IOS.019, ANDROID.019).
- **`SKILL_RELEASE_GATE_CI_001`** / **`SKILL_CI_PIPELINE_001`** — enforce these checks in the pipeline so the gate is real, not just documented (supports IOS.012, ANDROID.013/.014, IOS.018/ANDROID.018).
