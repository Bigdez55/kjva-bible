# Trust & Safety / Content Moderation — Playbook

`SKILL_TRUST_SAFETY_MODERATION_001` · layer: governance · tier: active

## When to use

Use this skill whenever a platform accepts or displays **user-generated content**
(posts, comments, profiles, reviews, chat) or allows users to **upload images,
video, or audio**. Also use it for any trust-and-safety / content-policy review,
when designing reporting / appeals / enforcement flows, when operating in the EU
under the **Digital Services Act (DSA)**, or when minors may be present.

This skill owns the Production-Readiness Corpus category
**"Trust & Safety / Content Moderation"** (`53_production_readiness`,
`coverage_status: NONE` before this skill). Every practice below maps to a real,
hand-authored corpus item. Item ids are abbreviated to their section + number
(full prefix is `PRC.TRUST_AND_SAFETY_CONTENT_MODERATION.<SECTION>.<NNN>`).

> **Hard legal blocker:** Any platform hosting user-uploaded media must integrate
> CSAM detection and a NCMEC reporting process before launch. This is never waived.

---

## Key practices by corpus section

### 1. Content Moderation Pipeline (CONTENT_MODERATION_PIPELINE.001–012)

- **Publish a content policy** (community guidelines / acceptable use) before any
  UGC goes live (.001).
- **Choose a moderation strategy explicitly** — pre-moderation, post-moderation,
  reactive, or hybrid (.002). Document why.
- **Automated classification** for text, image, video, and audio, via ML or a
  vendor (Hive, Sift, Rekognition) (.003), with a **human-review queue for
  borderline and appealed content** (.004).
- **Model content states**: pending, approved, rejected, quarantined, removed
  (.005). **Define severity tiers**: benign, sensitive, harmful, illegal (.006).
- **Real-time moderation path** for live content — streams, chat, comments (.007)
  — with a **moderation latency SLO** so legitimate content is not over-delayed
  (.008).
- **Re-moderate** on policy change or newly surfaced signals (.009).
- **Measure classifier accuracy**: precision, recall, false-positive rate (.010).
- **Log moderation decisions immutably** with reason and reviewer (.011), and
  **preserve context** for moderators: thread, history, prior violations (.012).

### 2. Illegal Content & CSAM (ILLEGAL_CONTENT_AND_CSAM.001–012)

- **Integrate CSAM detection** — PhotoDNA, Google CSAI Match, or Thorn Safer
  (.001). **Legal blocker.**
- **Establish the NCMEC CyberTipline reporting process** (US legal requirement)
  (.002) and **identify mandatory-reporting obligations per jurisdiction** (.003).
- **Preserve detected CSAM per legal requirement**, with tightly restricted
  access, and **notify authorities** (.004).
- **Trauma support and strict access controls** for staff who handle CSAM (.005).
- **Terrorist / violent-extremist content** detection via **GIFCT hash sharing**
  (.006); **non-consensual intimate imagery** takedown via **StopNCII** (.007);
  **illegal goods** detection — controlled substances, weapons (.008).
- **EU DSA notice-and-action** process for illegal content (.009), with a
  **legal escalation path defined and tested** (.010).
- **Evidence preservation and chain of custody** for law-enforcement requests
  (.011), and **hash-matching against known illegal-content databases** (.012).

### 3. Abuse, Harassment & Spam (ABUSE_HARASSMENT_AND_SPAM.001–012)

- **Spam detection** combining content + behavioral signals (.001).
- **Harassment / bullying detection with easy reporting** (.002); **hate-speech
  classification aligned to published policy** (.003).
- **Self-harm and suicide content detection surfaces crisis resources** — not
  silent removal (.004).
- **Coordinated inauthentic behavior** detection (.005); **doxxing / PII-exposure**
  detection (.006); **impersonation detection + verified-identity options** (.007).
- **Toxicity scoring** on UGC text — Perspective API or equivalent (.008).
- **Repeat-offender tracking** across accounts and devices (.009); **mass-report /
  brigading** abuse detection (.010); **fake-review / review-spam** detection
  (.011); **link, file, and malware scanning** within UGC (.012).

### 4. Reporting, Appeals & Enforcement (REPORTING_APPEALS_AND_ENFORCEMENT.001–012)

- **In-product reporting flow for every content type** (.001), with **report
  categories aligned to published policy** (.002), and **reporter gets
  acknowledgment + status updates** (.003).
- **Tiered enforcement**: warning, content removal, feature limit, suspension, ban
  (.004); a **documented, consistently applied strike/penalty system** (.005).
- **Appeals process for enforcement actions** (DSA requirement in EU) (.006),
  **reviewed by a different reviewer than the original decision** (.007).
- **Enforcement decisions logged immutably with rationale** (.008); **user
  notified of action and reason where legally permitted** (.009).
- **Ban-evasion / re-registration detection** (.010); **graduated response with a
  rehabilitation path where appropriate** (.011); **report-review SLA defined by
  severity tier** (.012).

### 5. T&S Operations & Transparency (T_AND_S_OPERATIONS_AND_TRANSPARENCY.001–012)

- **Moderator tooling**: efficient review UI, bulk actions, context, decision
  history (.001); **training and calibration program** (.002); **wellness program
  for exposure to harmful content** (.003).
- **Quality assurance**: decision audits and inter-rater reliability measured
  (.004); **escalation path from moderator to policy and legal teams** (.005).
- **Publish a transparency report**: volumes, actions, appeal outcomes (.006);
  **log and legally review government / legal takedown requests** (.007).
- **Support a trusted-flagger program** (DSA) (.008); **policy review cadence with
  legal and safety input** (.009); **crisis protocol** for viral harmful content
  or coordinated attacks (.010).
- **Measure prevalence of violating content, not just volume removed** (.011);
  core **metrics: report volume, time-to-action, reversal rate, prevalence**
  (.012).

---

## Concrete launch checklist / workflow

1. Inventory every surface that ingests or displays UGC or media.
2. Confirm a published content policy and an explicit moderation strategy.
3. Confirm automated classification + a human-review queue for borderline/appealed
   content, with content states and severity tiers modeled.
4. If media is hosted: confirm CSAM detection, NCMEC reporting, evidence
   preservation, restricted access, and staff wellness — **before launch**.
5. Confirm a DSA notice-and-action process and a tested legal-escalation path.
6. Confirm abuse/harassment/spam defenses, including self-harm crisis resources
   and malware scanning of uploads.
7. Confirm an in-product report flow per content type, tiered enforcement, and a
   strike system.
8. Confirm an appeals flow reviewed by a different reviewer, with immutable
   decision logs and a severity-tiered report-review SLA.
9. Confirm moderator tooling, training, wellness, QA/IRR, and an escalation path.
10. Confirm a transparency report, government-request log, trusted-flagger
    support, crisis protocol, and prevalence + accuracy metrics.

---

## Anti-patterns

| Anti-pattern | Instead | Corpus item |
|---|---|---|
| UGC live with no published policy | Publish community guidelines / AUP first | PIPELINE.001 |
| No human-review queue | Add a queue for borderline + appealed content | PIPELINE.004 |
| Media uploads with no CSAM scanning | Integrate PhotoDNA / CSAI Match / Safer | CSAM.001 |
| CSAM found but no NCMEC report | Establish CyberTipline reporting process | CSAM.002 |
| CSAM not preserved / access not restricted | Preserve per law, restrict access, notify | CSAM.004 |
| Moderators exposed with no support | Trauma/wellness support + access controls | CSAM.005 / OPS.003 |
| Self-harm content silently removed | Surface crisis resources | ABUSE.004 |
| Removal/ban with no appeal | DSA-compliant appeals | ENFORCE.006 |
| Original reviewer also decides appeal | Route to a different reviewer | ENFORCE.007 |
| Decisions not logged | Immutable log with reason + reviewer | PIPELINE.011 / ENFORCE.008 |
| Unbounded report queue, no SLA | Severity-tiered report-review SLA | ENFORCE.012 |
| "Volume removed" as success metric | Measure prevalence, time-to-action, reversal | OPS.011 / OPS.012 |
| No transparency report | Publish volumes, actions, appeal outcomes | OPS.006 |

---

## Related

- `SKILL_PRODUCTION_READINESS_AUDIT_001` — parent production-readiness audit that
  scores this category.
- `SKILL_FILE_UPLOAD_MEDIA_001` — upload-time scanning surface that feeds
  CSAM/malware detection (its corpus items explicitly defer to this category).
- `SKILL_RATE_LIMIT_TENANT_SCOPED_001` — rate limiting that backs abuse/spam and
  mass-report/brigading defenses.
- `SKILL_AUDIT_LOG_IMMUTABLE_001` — immutable moderation/enforcement decision logs
  and chain of custody for law-enforcement requests.
- `SKILL_SECURITY_COMPLIANCE_GOVERNANCE_001` — governance and legal-compliance
  surface (DSA, mandatory reporting, government-request handling).
- `SKILL_CMS_CONTENT_EDITORIAL_001` — editorial content (explicitly NOT T&S UGC
  moderation; this skill owns that).
