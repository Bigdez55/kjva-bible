# Go-To-Market and Growth — Playbook

**Skill:** `SKILL_GTM_GROWTH_001`
**Corpus category owned:** `Go-To-Market & Growth` (`PRC.GO_TO_MARKET_AND_GROWTH`)
**Authority:** `platform/systems/53_production_readiness/corpus/categories/PRC-GO_TO_MARKET_AND_GROWTH.yaml`

This playbook turns the hand-authored Go-To-Market & Growth production-readiness
items into a launch-blocking discipline. The category has three sections —
**Launch Strategy**, **Growth Analytics**, and **Lifecycle & Retention** — and
every practice below maps to specific corpus item ids. The governing rule:
**GTM readiness is proven by an approving owner, a live dashboard, or an artifact —
never by a verbal claim that something exists.**

---

## When to use

Use this skill whenever a system is preparing to go to market or to grow its user
base, specifically:

- Before any public launch, or when choosing a launch tier (silent, minor, major,
  flagship) and shipping a landing/product page.
- When defining positioning and getting the messaging framework approved across
  product, sales, marketing, and support.
- When defining or changing the North Star metric or the activation (first-value) metric.
- When instrumenting the AARRR funnel or its event taxonomy.
- When designing onboarding, welcome sequences, or behavior-triggered lifecycle
  and re-engagement campaigns.
- When prioritizing the growth experiment backlog or authoring a new experiment.
- When reviewing churn, win/loss, cohort retention, or segment usage after launch.
- When running a production-readiness audit on the Go-To-Market & Growth category.

Pair it with `SKILL_PRODUCTION_READINESS_AUDIT_001` for the overall audit; this
skill is the deep-dive owner for the GTM category.

---

## Key practices by corpus section

### 1. Launch Strategy (`LAUNCH_STRATEGY.001`–`.012`)

- Write a **positioning statement** with four parts: audience, problem, promise,
  proof (`.001`).
- Get the **messaging framework approved by all four functions** — product, sales,
  marketing, AND support — not just engineering (`.002`). Keep the sign-off record.
- **Segment the launch audience**: internal, beta, existing, new, enterprise (`.003`),
  and explicitly choose a **launch tier**: silent, minor, major, flagship (`.004`).
- Have the public-facing assets ready before launch: **landing/product page** (`.005`),
  **demo script + demo environment** (`.006`), **sales-enablement deck** (`.007`),
  and an **FAQ** covering objections, pricing, limitations, and support (`.008`).
- For public launches, prepare a **press / social / community plan** (`.009`).
- Build a **launch timeline** spanning content, product, support, and engineering
  milestones (`.010`), assign a **named launch owner per business function** (`.011`),
  and **schedule the launch retrospective** up front (`.012`).

### 2. Growth Analytics (`GROWTH_ANALYTICS.001`–`.012`)

- Agree a **North Star metric** with product and leadership (`.001`).
- Define a **measurable activation metric** — the first value moment, observable in
  data, not a vague "signed up" (`.002`).
- Instrument the **full AARRR funnel**: acquisition, activation, retention,
  referral, revenue (`.003`).
- Document the **event taxonomy** with a **consistent naming convention** (`.004`) —
  inconsistent names make the funnel un-analyzable.
- Select an **attribution model** for marketing channels (`.005`) and define
  **UTM governance** for all campaigns (`.006`).
- Stand up a **cohort-retention dashboard** (`.007`) and a **conversion-funnel
  dashboard** (`.008`), and **review drop-off weekly after launch** (`.009`).
- Maintain a **growth experiment backlog prioritized by impact and effort** (`.010`);
  every experiment declares **hypothesis, success metric, guardrail metric, and
  duration** (`.011`); **archive and share results** across teams (`.012`).

### 3. Lifecycle & Retention (`LIFECYCLE_AND_RETENTION.001`–`.011`)

- Build a **welcome sequence** that guides new users to the first value moment
  (`.001`) and an **in-app onboarding checklist tied to the activation metric** (`.002`).
- Trigger **lifecycle emails by user behavior, not only by time** (`.003`).
- Define a **re-engagement campaign for inactive users** (`.004`).
- Tie **upgrade prompts to real usage limits or demonstrated value moments** (`.005`).
- Connect a **customer feedback loop to roadmap planning** (`.006`).
- **Capture, categorize, and review churn reasons monthly** (`.007`).
- Perform **win/loss analysis for sales-led products** (`.008`).
- **Review product usage by customer segment** (`.009`) and **surface retention risks
  to customer success / the account owner** (`.010`).
- **Localize lifecycle content for key customer segments** (`.011`).

---

## Launch checklist / workflow

Work the three sections top to bottom. Launch-Strategy approvals gate a public launch.

**Launch Strategy**
1. [ ] Positioning statement (audience, problem, promise, proof) written (`.001`).
2. [ ] Messaging framework approved by product, sales, marketing, AND support (`.002`).
3. [ ] Launch audience segmented and launch tier chosen (`.003`–`.004`).
4. [ ] Landing page, demo script + env, sales deck, FAQ ready (`.005`–`.008`).
5. [ ] Press/social/community plan ready for public launch (`.009`).
6. [ ] Timeline covers content/product/support/eng; owner per function; retro scheduled (`.010`–`.012`).

**Growth Analytics**
7. [ ] North Star metric agreed; activation metric measurable (`.001`–`.002`).
8. [ ] AARRR funnel instrumented; event taxonomy documented with naming convention (`.003`–`.004`).
9. [ ] Attribution model + UTM governance defined (`.005`–`.006`).
10. [ ] Cohort-retention and conversion-funnel dashboards live; drop-off reviewed weekly (`.007`–`.009`).
11. [ ] Experiment backlog prioritized; each experiment has hypothesis/success/guardrail/duration; results archived (`.010`–`.012`).

**Lifecycle & Retention**
12. [ ] Welcome sequence + onboarding checklist tied to activation metric (`.001`–`.002`).
13. [ ] Behavior-triggered lifecycle emails + re-engagement campaign + usage-tied upgrade prompts (`.003`–`.005`).
14. [ ] Feedback loop to roadmap; churn reasons captured, categorized, reviewed monthly (`.006`–`.007`).
15. [ ] Win/loss analysis; usage by segment; retention risks surfaced; lifecycle content localized (`.008`–`.011`).

Any unmet item blocks the corresponding launch gate until waived by an accountable
owner (see `SKILL_PRODUCTION_READINESS_AUDIT_001` for the evidence-and-waiver discipline).

---

## Anti-patterns

| Anti-pattern | Why it fails | Corpus item | Fix |
| --- | --- | --- | --- |
| Engineering-only messaging deck | Sales/support contradict the promise at launch | LAUNCH_STRATEGY.002 | Get four-function sign-off and keep the record |
| No explicit launch tier or audience | Launch motion and comms are improvised | LAUNCH_STRATEGY.003-004 | Choose tier + segment audience before launch |
| No retro scheduled | Lessons evaporate; same mistakes next launch | LAUNCH_STRATEGY.012 | Put the retro on the calendar up front |
| North Star but no activation metric | First-value moment is invisible; funnel health unknown | GROWTH_ANALYTICS.002 | Define a measurable activation event |
| Ad-hoc event names | AARRR funnel is un-analyzable | GROWTH_ANALYTICS.004 | Documented taxonomy + naming convention |
| Dashboards nobody reviews | Drop-off regressions go unnoticed | GROWTH_ANALYTICS.009 | Weekly drop-off review with an owner |
| Experiment with no guardrail/duration | Peek-and-ship on noise; harmful variants slip through | GROWTH_ANALYTICS.011 | Require hypothesis + success + guardrail + duration |
| Only time-based lifecycle emails | Miss the behavioral activation window | LIFECYCLE_AND_RETENTION.003 | Trigger emails on user behavior |
| Churn reasons captured nowhere | Retention work has no signal | LIFECYCLE_AND_RETENTION.007 | Capture, categorize, review monthly |
| Upgrade prompts unrelated to usage | Annoying, low-converting, erodes trust | LIFECYCLE_AND_RETENTION.005 | Tie prompts to real limits or value moments |

---

## Related

- `SKILL_PRODUCTION_READINESS_AUDIT_001` — parent audit discipline; this skill owns
  the GTM category within it.
- `SKILL_PROVISIONING_ONBOARDING_LIFECYCLE_001` — provisioning/onboarding mechanics
  that the welcome sequence and activation checklist build on.
- `SKILL_DRIFT_DETECTION_001` — detect drift between the documented event taxonomy
  and the events actually emitted.
- `SKILL_CONTEXT_COMPILATION_002` — compile the evidence bundle for a GTM readiness review.
- `SKILL_TRIGGER_ROUTER_001` — routes GTM/launch/growth intents to this skill.
- Corpus authority: `platform/systems/53_production_readiness/corpus/categories/PRC-GO_TO_MARKET_AND_GROWTH.yaml`
