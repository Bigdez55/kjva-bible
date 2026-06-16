# Content, CMS and Editorial — Production-Readiness Playbook

`SKILL_CMS_CONTENT_EDITORIAL_001` · layer: content · corpus category: **Content, CMS & Editorial**

Fills the zero-coverage gap for the Production-Readiness Corpus category `PRC.CONTENT_CMS_AND_EDITORIAL`
(sections: **CMS Architecture**, 12 items; **Editorial Governance & Media**, 16 items). Every practice
below maps to a specific corpus item id.

---

## When to use

Use this skill whenever you are:

- Selecting, standing up, or auditing a CMS (Sanity, Contentful, Strapi, WordPress, or custom).
- Designing the content model — types, fields, validations, relationships.
- Building or reviewing the draft → preview → approval → publish workflow, scheduling, or rollback.
- Defining editorial roles, governance, style/voice guidelines, review cadence, or legal review.
- Handling media: a digital asset library, image optimization, captions/transcripts, EXIF stripping, malware scanning.
- Answering "is our content platform production ready?" or auditing the **Content, CMS & Editorial** corpus category.

This is a content-platform skill. It does NOT cover trust-and-safety user-generated-content moderation
(that is a separate corpus category) — it covers *first-party editorial content* and the CMS that serves it.

---

## Section 1 — CMS Architecture

Maps to `PRC.CONTENT_CMS_AND_EDITORIAL.CMS_ARCHITECTURE.001–012`.

### 1.1 Choose and justify the CMS (.001)
Pick deliberately, not by habit. Write a one-page decision record comparing candidates against:
content volume and growth, number/locale of editors, required workflow depth, headless vs. coupled
rendering, hosting/compliance constraints, and migration cost. Headless (Sanity, Contentful, Strapi)
decouples content from rendering; WordPress couples them; custom is justified only when an off-the-shelf
model genuinely cannot express the domain. The artifact is the deliverable — "we use X" with no rationale fails.

### 1.2 Document the content model BEFORE authoring (.002)
For every content type, document: fields, types, which are required, validation rules (length, format,
enum), and relationships (references, arrays, embeds). Treat the model like a schema — versioned in the
repo, reviewed on change. Authoring before the model is locked produces unmigratable content.

### 1.3 Editorial roles (.003) + workflow (.004) + scheduling (.005)
- Define `author`, `editor`, `publisher`, `admin` as distinct CMS roles with least-privilege permissions.
- Configure a real workflow: **draft → preview → approval → publish**. Approval is a *mandatory gate*.
- Support **scheduled publishing and unpublishing** (embargoes, campaign windows, time-boxed banners).

### 1.4 Versioning + rollback (.006)
Enable version history and rollback for all critical content types. Do not trust the toggle —
*exercise a rollback in a drill* and confirm content restores cleanly.

### 1.5 Preview fidelity (.007)
Preview MUST render through the **same template, data fetch, and component path** as production. A
separate "preview renderer" is an anti-pattern: editors approve something other than what ships. Diff a
preview render against the production render for a sample page and confirm they are identical.

### 1.6 SEO metadata on public types (.008)
Every public content type exposes SEO fields: title, meta description, canonical URL, Open Graph/social
tags, optional structured data. Make key fields required so they cannot publish blank.

### 1.7 Content API security (.009) + change logging (.010)
- The content API has **no anonymous/public write path**. Every create/update/delete/publish endpoint
  requires an authenticated editor role with least-privilege scope. Test it: an unauthenticated write
  must return 401/403.
- Log every mutation with **editor identity, timestamp, and before/after (or version id)** for audit/forensics.

### 1.8 Backup/export (.011) + migration path (.012)
Document and *test* a backup + export procedure (restore into a scratch environment — an untested backup
is a wish). Document a content-migration path so a future CMS change does not strand the content estate.

---

## Section 2 — Editorial Governance & Media

Maps to `PRC.CONTENT_CMS_AND_EDITORIAL.EDITORIAL_GOVERNANCE_AND_MEDIA.001–016`.

### 2.1 Governance docs (.001–.004)
- **Editorial style guide** documented (grammar, formatting, terminology).
- **Voice and tone** guidelines documented.
- **Content ownership** assigned by section or content type (a named owner per area).
- **Review cadence** defined for evergreen content (e.g. quarterly re-verification of pricing/claims pages).

### 2.2 Gating reviews (.005, .006, .008)
- **Legal review** is a required step for claims, pricing, guarantees, and regulated content before publish.
- **Accessibility review** is required for all published content (alt text, heading order, contrast, link text).
- The **approval gate prevents accidental publishing** — no one-click "publish" on unreviewed drafts.

### 2.3 Localization + analytics (.007, .009)
- **Localization workflow** defined for translated content (source-of-truth locale, translation handoff,
  per-locale publish state).
- **Content analytics** reviewed to improve high-traffic pages (close the loop, don't just collect).

### 2.4 Media governance (.010, .011)
- **Digital asset library** organized with naming conventions (predictable, searchable).
- **Image licensing and usage rights** documented per asset (avoid using assets you cannot legally serve).

### 2.5 Media performance + accessibility (.012, .013)
- **Images compressed and served in modern formats (WebP/AVIF)** with fallbacks.
- **Video captions and transcripts required** for accessibility.

### 2.6 Media safety + integrity (.014, .015, .016)
- **EXIF and sensitive metadata stripped** from every public upload (prevents GPS/author leakage).
- **Malware scanning** performed on uploaded assets before they are served (verify with an EICAR test file).
- **Broken media references monitored** in production (dangling asset links surfaced and triaged).

---

## Concrete workflow / checklist

1. **Decide & document**: write the CMS decision record (.001); commit the content-model doc (.002).
2. **Model & validate**: implement types/fields/validations/relationships; review the schema (.002).
3. **Roles & workflow**: configure author/editor/publisher/admin (.003); wire draft→preview→approval→publish (.004); enable scheduling (.005).
4. **Versioning**: enable history + rollback on critical types and run a rollback drill (.006).
5. **Preview fidelity**: route preview through the production render path; diff a sample (.007).
6. **SEO**: add SEO fields to all public types; mark key fields required (.008).
7. **Secure the API**: remove anonymous writes; require editor auth; test 401/403 (.009); enable change logging (.010).
8. **Backup & migration**: document + test backup/export (.011); document migration path (.012).
9. **Governance docs**: style guide, voice/tone, ownership, review cadence (.001–.004).
10. **Review gates**: legal review for regulated content (.005); accessibility review (.006); confirm approval blocks accidental publish (.008).
11. **Localization & analytics**: define translation workflow (.007); set up content analytics review (.009).
12. **Media library**: naming conventions (.010); licensing records (.011).
13. **Media pipeline**: WebP/AVIF compression (.012); captions + transcripts (.013); EXIF stripping (.014); malware scan (.015).
14. **Monitor**: broken-media-reference monitor in production (.016).

Each step is "done" only with **evidence** — a path, a command + result, or a cited artifact — per
`SKILL_PRODUCTION_READINESS_AUDIT_001`. A green build is not done; verify the rendered surface
(`SKILL_UI_LIVE_VERIFICATION_BEFORE_DONE_001`).

---

## Anti-patterns

| Anti-pattern | Why it fails | Corpus item |
| --- | --- | --- |
| CMS chosen "because we always use it", no rationale | Wrong tool for content volume/workflow; costly later migration | .001 |
| Authoring content before the model is documented | Unmigratable, inconsistent content; validation gaps | .002 |
| One-click / default-on publish, no approval gate | Unreviewed (and legally risky) content goes live | .004, .008 |
| Separate "preview renderer" | Editors approve something different from what ships | .007 |
| Versioning toggle on but never tested | Rollback fails when you actually need it | .006 |
| Public/anonymous content API write endpoint | Content tampering, spam injection | .009 |
| No change log on mutations | No audit trail of who changed what, when | .010 |
| Untested backup, no migration path | Content estate unrecoverable / vendor lock-in | .011, .012 |
| Publishing regulated claims/pricing with no legal review | Compliance and liability exposure | .005 |
| Serving raw uploads (EXIF intact, unscanned) | GPS/author leak; malware distribution | .014, .015 |
| Oversized PNG/JPEG, video without captions | Performance + accessibility failures | .012, .013 |
| No broken-media monitor | Dangling assets / 404 images in production | .016 |

---

## Related

- `SKILL_PRODUCTION_READINESS_AUDIT_001` — scores this category in a full production-readiness audit; this skill is its fix-skill for the **Content, CMS & Editorial** category.
- `SKILL_UI_LIVE_VERIFICATION_BEFORE_DONE_001` — verify preview/publish on the real rendered surface, not just a 200/green build.
- `SKILL_VERIFY_VALIDATE_001` — evidence-gated verification of every checklist item.
- `SKILL_AUTOMATED_REGRESSION_TESTING_001` — guard preview-equals-production and SEO/media invariants against regressions.
