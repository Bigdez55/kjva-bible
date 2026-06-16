# Sustainability and Green Software — Playbook

> Skill: `SKILL_SUSTAINABILITY_GREEN_SOFTWARE_001`
> Layer: operations · Tier: active · Source: native
> Corpus category: **Sustainability & Green Software** (53_production_readiness)

## When to use

Use this skill whenever a decision affects how much **energy** a system burns or
how much **carbon** it emits — and you want that impact measured, budgeted, and
reduced rather than left implicit. Concretely:

- Reviewing an architecture, workload, or region choice for energy/carbon impact.
- Hunting idle, orphaned, or over-provisioned compute (the cheapest carbon win).
- Scheduling deferrable batch/cron work and grid carbon intensity matters.
- Setting storage retention, tiering, or data-lifecycle policy.
- A FinOps/cost review surfaces waste that overlaps directly with energy waste.
- Tuning CI/CD that runs always-on runners or redundant builds.
- Auditing the Sustainability & Green Software production-readiness category.

The guiding principle from the corpus: **you cannot manage what you do not
measure** (SGS-005). Every practice below is evidence-first — a metric, a config,
a dashboard, or command output, never intent.

---

## Key practices (grounded in the corpus)

### 1. Carbon-aware scheduling and placement (SGS-001)
- Classify every batch/cron job as **deferrable** or **time-critical**. Only
  deferrable work can be shifted.
- Integrate a carbon-intensity API (**WattTime**, **Electricity Maps**) into the
  scheduler and run deferrable jobs in low-carbon grid windows.
- When picking a region, weigh **grid carbon intensity**, not just latency/cost.

### 2. Idle resource reaping (SGS-002) — the highest-leverage win
- Apply **auto-stop** to non-prod (dev/test/staging) outside business hours.
- Run **idle detection** across VMs, databases, and Kubernetes nodes.
- Schedule an **orphaned-resource sweeper**: unattached disks, idle load
  balancers, zombie environments, dangling snapshots.

### 3. Right-sizing (SGS-003)
- Drive requests/limits from **actual usage percentiles**, not peak-padded
  defaults or "to be safe" headroom.
- Apply utilization-based right-sizing recommendations on a cadence.
- Configure autoscaling to **scale to zero** wherever the workload allows.

### 4. Efficient data lifecycle (SGS-004)
- Set **retention limits** that delete data past its useful life.
- Use **tiered storage** to move cold data to low-energy tiers (hot → cool →
  archive / cold object storage).
- **Compress** logs, backups, and archives.

### 5. Measure carbon and energy (SGS-005) — the keystone
- Track **Software Carbon Intensity (SCI)** or an equivalent per service.
- Review **cloud provider carbon dashboards** on a defined cadence; record it.
- Set **carbon/energy budgets** and **trend** them over time.

### 6. Carbon-efficient architecture (SGS-006)
- Prefer **serverless / managed / multi-tenant** platforms for bursty or
  low-utilization workloads over idle dedicated fleets.
- Use **bin-packing** to raise hardware utilization (don't claim "managed is
  greener" without utilization evidence).
- Use **edge caching** to cut redundant compute and transfer.

### 7. Software efficiency (SGS-007)
- **Profile hot paths** and optimize CPU/memory; capture before/after.
- **Cache** to eliminate redundant computation and network calls.
- Use **efficient data formats** (compression, binary protocols) on high-volume
  paths — fewer bytes and cycles per request means less energy per request.

### 8. Green CI/CD (SGS-008)
- Enable **build caching** and **incremental / affected-only** builds.
- Make CI runners **scale to zero** when idle.
- Use **test selection** so the full suite does not run on every trivial change.

### 9. Hardware lifecycle and embodied carbon (SGS-009)
- **Extend refresh cycles** where feasible — embodied (manufacturing) carbon
  dominates lifecycle impact for short-lived devices.
- Favor cloud regions/providers with **renewable commitments**.
- **Reuse or recycle** decommissioned hardware responsibly.

### 10. Embed sustainability in culture (SGS-010)
- Make sustainability an explicit checkpoint in **architecture/design reviews**.
- Maintain **green-software guidelines / training** for the team.
- Weigh **carbon impact in vendor and technology selection**.

---

## Concrete workflow / checklist

1. **Scope** — name the system, environments, and regions in scope; note what is
   out of scope. Capture a baseline (current cost + any existing energy metric).
2. **Measure first (SGS-005)** — confirm an SCI/energy metric exists per service.
   If none exists, that is finding #1: stand up measurement before optimizing.
3. **Reap idle (SGS-002)** — inventory non-prod auto-stop, idle detection, and
   the orphaned-resource sweeper; record what was reclaimed on the last run.
4. **Right-size (SGS-003)** — compare requests/limits to usage percentiles; flag
   chronic over-provisioning; confirm scale-to-zero where possible.
5. **Data lifecycle (SGS-004)** — verify retention limits, tiering, compression.
6. **Carbon-aware scheduling (SGS-001)** — confirm deferrable classification and
   a carbon-intensity signal in the scheduler; check region carbon weighting.
7. **Architecture & efficiency (SGS-006, SGS-007)** — check serverless/bin-pack
   fit, edge caching, profiled hot paths, and efficient data formats.
8. **Green CI/CD (SGS-008)** — check cache hit rate, incremental builds, runner
   scale-to-zero, test selection.
9. **Hardware & embodied carbon (SGS-009)** — check refresh cycles, renewable
   region choice, decommissioning reuse/recycle.
10. **Culture (SGS-010)** — confirm sustainability appears in a recent design
    review or vendor decision record.
11. **Report** — for each SGS item: pass / gap, the evidence, and an actionable
    remediation tied to the specific item id. Every claim cites its SGS id.

---

## Anti-patterns

| Anti-pattern | Why it fails | Corpus fix |
| --- | --- | --- |
| "Build is green, so we're green" | Ignores idle and over-provisioned compute | SGS-002, SGS-003 |
| Optimize only cost & latency, never carbon | Impact stays invisible; cannot manage what you don't measure | SGS-005 |
| Region chosen on price/latency only | Silently lands on a high-carbon grid | SGS-001, SGS-009 |
| "Keep everything" retention | Cold data accrues on hot, high-energy tiers | SGS-004 |
| Non-prod & CI runners up 24/7 | Burns energy/money for zero value off-hours | SGS-002, SGS-008 |
| Pad requests "to be safe" | Chronic over-provisioning wastes energy ∝ unused headroom | SGS-003 |
| "Serverless is greener" with no data | Claim without bin-packing/utilization evidence | SGS-006 |
| Full test suite on every trivial change | Redundant build/test compute waste | SGS-008 |
| Replace hardware on a fixed short cycle | Embodied carbon dominates short-lived device impact | SGS-009 |
| Sustainability listed as a value, never gated | Green software does not stick without review gates | SGS-010 |

---

## Related

- `SKILL_PRODUCTION_READINESS_AUDIT_001` — umbrella audit; this skill is the
  deep-dive for the Sustainability & Green Software category.
- `SKILL_AZURE_COST_OPTIMIZATION_001` — cost waste overlaps directly with energy
  waste (idle reaping, right-sizing): SGS-002, SGS-003.
- `SKILL_PERFORMANCE_FORGE_001` — hot-path profiling and efficiency that lowers
  compute energy per request (SGS-007).
- `SKILL_OBSERVABILITY_NEXUS_001` — the measurement substrate for SCI, energy,
  and carbon metrics and trends (SGS-005).
- `SKILL_SCALABILITY_RESILIENCE_DR_001` — autoscaling, scale-to-zero, and
  capacity decisions that minimize idle running capacity (SGS-003, SGS-006).
