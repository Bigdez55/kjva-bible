# Fraud & Abuse Prevention — Playbook

> Owns the **Fraud & Abuse Prevention** category of the ATLAS Production-Readiness
> Corpus (`platform/systems/53_production_readiness`), 5 sections / 60 items.
> Turns that hand-authored standard into an executable, evidence-backed launch gate
> so "no fraud yet" is never mistaken for "fraud-resistant."

## When to use

Invoke this skill whenever a platform, service, or feature exposes a surface that
fraudsters or abusers can exploit for value or disruption:

- Signup, login, account-recovery, and email/phone-change flows.
- Checkout, payout, and any promo / referral / free-trial / credit redemption.
- Data-rich or enumerable endpoints (search, listings, profile, export APIs).
- Any public or monetized API.

Use it proactively (designing a value-bearing or data-rich flow) and reactively
(after a spike in fake accounts, card testing, trial abuse, scraping, or fraud
rings). It is a launch-blocker for fintech and any monetized product.

## Key practices by corpus section

### 1. Account Takeover & Credential Attacks
- Defend the login path: breached-password checks, anomaly detection, progressive
  delays, lockout, and a CAPTCHA challenge against brute force and credential stuffing.
- Score risky logins: impossible-travel / geo-velocity, new device, new location,
  and proxy/VPN/known-malicious IP ranges; require **step-up auth** on the risky ones.
- Harden recovery: account-recovery and email/phone-change require step-up
  verification and resist social-engineering takeover.
- Notify the user on password change, new device, and security events; terminate
  suspicious sessions and force re-auth; mitigate session fixation, token theft,
  MFA bypass, and push-bombing (MFA fatigue). Monitor the dark web for leaked creds.

### 2. Bot & Automation Defense
- Deploy bot detection (reCAPTCHA Enterprise, hCaptcha, Turnstile, or DataDome),
  preferring **invisible challenges** that balance friction and security; always
  keep an accessible fallback so the control does not lock out disabled users.
- Use behavioral signals, headless-browser/automation-framework detection, and
  **privacy-compliant** device fingerprinting for risk scoring.
- Add honeypot fields for naive bots and proof-of-work/attestation on high-abuse
  endpoints where appropriate. Treat **API abuse detection as distinct** from web
  bot detection. Escalate rate limits/challenges for suspicious clients.
- Maintain a good-bot allowlist (search crawlers, monitoring), segment bot traffic
  out of analytics, and measure bot-defense effectiveness against known campaigns.

### 3. Velocity, Anomaly & Risk Scoring
- Compute a **per-action risk score** from multiple signals.
- Enforce **velocity checks** on signups, logins, purchases, and messages per
  identity / IP / device — **server-side**, not just at the CDN/UI.
- Detect anomalies (sudden spikes, unusual sequences). Drive a documented
  **allow / challenge / review / deny** decision engine: low risk frictionless,
  high risk challenged or blocked, medium risk to a manual review queue.
- Keep thresholds **tunable without code deploy** and support a **shadow mode**
  before enforcement. Log every decision for audit and dispute resolution.
- Monitor the **false-positive rate** so legitimate users are not over-blocked,
  and feed confirmed fraud + chargeback data back to retune rules and models.

### 4. Multi-Account & Sybil Defense
- Detect multi-accounting via shared device, payment, IP, and fingerprint; link
  related accounts in an **identity graph**; enforcement on one applies to the ring.
- Detect promo/referral abuse (self-referral, fake accounts), free-tier/trial
  abuse (serial trial creation), collusion, and fraud rings.
- Block or flag disposable/temporary email domains; require phone verification for
  high-abuse signup flows; detect synthetic identity for regulated signups.
- Factor account age and reputation into trust decisions, and apply limits **per
  verified identity, not just per account**. Provide Sybil resistance for voting,
  ratings, and reputation systems.

### 5. Scraping & Data Exfiltration Defense
- Detect scraping on data-rich and enumerable endpoints; enforce per-account and
  per-IP **data-access volume limits**.
- Block sequential-ID enumeration with **non-guessable IDs + authorization checks**;
  throttle pagination and bulk-export abuse; tarpit or progressively slow detected
  scrapers and escalate challenges for aggressive crawlers.
- **Minimize API responses** to what each client needs; require elevated
  authorization to access sensitive fields in bulk; watermark or seed canary
  records to detect and trace theft.
- Monitor exports/downloads with anomaly alerts, watch for insider exfiltration
  (unusual internal access), and keep legal terms that prohibit scraping.

## Concrete checklist / workflow

1. **Inventory surfaces.** List every signup/login/recovery, value-bearing
   (checkout/payout/promo/referral/trial), and data-rich/enumerable endpoint.
2. **Harden the login path** (Section 1): breached-password + brute-force defenses,
   anomalous-login scoring, step-up auth, recovery hardening, security notifications.
3. **Deploy bot defense** (Section 2): invisible challenge + accessible fallback,
   headless detection, privacy-compliant fingerprinting, good-bot allowlist.
4. **Stand up velocity + risk scoring** (Section 3): server-side velocity per
   identity/IP/device; multi-signal score; allow/challenge/review/deny engine.
5. **Make thresholds config-driven** with shadow mode; log every rule change.
6. **Log every decision** and route medium-risk to a **manual review queue**.
7. **Monitor false-positive rate**; wire the confirmed-fraud/chargeback feedback loop.
8. **Cap and abuse-check redemptions** (Section 4): self-referral, serial trials,
   disposable email, phone verification, per-identity limits.
9. **Link accounts** in an identity graph; enforce ring-wide.
10. **Block scraping/enumeration** (Section 5): non-guessable IDs + authz, volume
    limits, throttled export, minimized responses, export anomaly alerts.
11. **Run the validation tests** below and capture evidence (path/command/result)
    for each PASS — HTTP 200 and a green build are not evidence.

## Anti-patterns

| Anti-pattern | Why it fails | Do instead |
| --- | --- | --- |
| Velocity limit only at CDN/UI | Direct API caller bypasses every check | Enforce velocity server-side per identity/IP/device |
| Visual-only CAPTCHA | Blocks accessibility users | Invisible challenge + accessible fallback |
| Single-signal account linkage (email) | Trivially varied to multi-account | Identity graph: device + payment + IP + fingerprint |
| Sequential / guessable IDs | Enables enumeration and scraping | Non-guessable IDs + per-request authorization |
| Hard-coded thresholds | Live fraud spike needs emergency deploy | Config-driven, shadow mode, logged changes |
| Decisions made but not logged | Disputes unresolvable; FPs invisible | Log every allow/challenge/review/deny |
| Auto-block with no FP monitoring/appeal | False positive = permanent account loss | Monitor FP rate; manual review queue; appeal |
| Over-broad API responses | Mass data exfiltration in one call | Minimize fields; elevated authz for bulk sensitive |
| New rule enforced with no shadow mode | Blocks real users before validation | Shadow-mode new rules before enforcement |
| Bot traffic left in analytics | Polluted metrics, blind to attacks | Segment bots; allowlist good bots; measure defense |

## Related

- **SKILL_PRODUCTION_READINESS_AUDIT_001** — parent launch gate; this skill owns
  its Fraud & Abuse Prevention category (`coverage_status: NONE` gap-filler).
- **SKILL_RUNTIME_REGRESSION_VERIFY_001** — exercise the live abuse-control surface
  (call the API directly, simulate the burst), not just builds/tests.
- **SKILL_DRIFT_DETECTION_001** — catch silent erosion of fraud rules and thresholds
  over time.
- Corpus source: `platform/systems/53_production_readiness/corpus/categories/PRC-FRAUD_AND_ABUSE_PREVENTION.yaml`
  (sections: Account Takeover & Credential Attacks, Bot & Automation Defense,
  Velocity/Anomaly & Risk Scoring, Multi-Account & Sybil Defense, Scraping & Data
  Exfiltration Defense). Adjacent: Payments (Fraud, Refunds & Reporting),
  Identity Verification & KYC/AML, Rate Limiting/Quotas, Trust & Safety.
