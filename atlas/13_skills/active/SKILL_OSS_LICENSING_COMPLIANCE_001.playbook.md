# Open Source and Licensing Compliance — Playbook

**Skill:** `SKILL_OSS_LICENSING_COMPLIANCE_001`
**Layer:** governance
**Corpus category owned:** "Open Source & Licensing" (`PRC.OPEN_SOURCE_AND_LICENSING`)

This playbook operationalizes the Production-Readiness Corpus category that previously
had **zero skill coverage** (`coverage_status: NONE`). Every practice below maps to a
hand-authored corpus item id so an auditor can trace guidance back to the standard.

---

## When to use

Invoke this skill when you:

- Add, upgrade, fork, or vendor a third-party dependency and need to know if its license is allowed.
- Are about to **open-source** a repository or make it community-facing.
- Are about to **publish a package** to a registry (npm, PyPI, crates.io, Maven Central, NuGet, Go module proxy, container registry).
- Need to produce or review a **NOTICE / attribution** file, an **SBOM**, or a **license scan**.
- Detect a **copyleft** (GPL / AGPL / LGPL / MPL) or commercially-restricted dependency in a *distributed* product.
- Have a **maintainer leaving** the org and must review package ownership and namespace access.
- See a production-readiness audit flag "Open Source & Licensing" as failing or NONE.

The category default severity is **medium**, but copyleft contamination of a distributed
product and an orphaned package namespace are effectively launch-blockers — treat them as high.

---

## Section 1 — Dependency License Controls

Maps to `PRC.OPEN_SOURCE_AND_LICENSING.DEPENDENCY_LICENSE_CONTROLS.001–011`.

Key practices:

1. **Define the allowlist first (.001).** Legal or leadership ratifies an explicit
   allowed/prohibited license list. A typical SaaS allowlist permits MIT, Apache-2.0,
   BSD-2/3-Clause, ISC; flags weak-copyleft (MPL-2.0, LGPL) for review; and prohibits
   strong copyleft in distributed code (GPL-3.0, AGPL-3.0) and "no-commercial"/SSPL/BSL
   terms. Encode it as machine-readable config the scanner consumes.
2. **Scan on every PR (.002).** Wire a license scanner (e.g. `license-checker`,
   `pip-licenses`, `cargo-deny`, `licensee`, FOSSA, ScanCode, Syft+Grype) into CI so a
   prohibited or **unknown** license **fails the build**. Green tests are not license
   clearance — the gate must exist and block.
3. **Walk the transitive tree (.003).** Scan the full resolved dependency graph from the
   lockfile, not just `package.json`/`pyproject` direct deps. Most license surprises live
   transitively.
4. **Review copyleft before distribution (.004).** Any GPL/AGPL/LGPL/MPL in a product you
   *ship* (binary, container, SDK, on-prem) gets an explicit, recorded approval. SaaS-only
   use changes the analysis (AGPL still triggers) — document the distribution model.
5. **Generate NOTICE / attribution (.005).** Permissive licenses (MIT, Apache-2.0, BSD)
   *require* attribution. Emit a `THIRD_PARTY_NOTICES` / `NOTICE` file and ship it inside
   the artifact. Automate it from the SBOM so it never drifts.
6. **Check commercial-use restrictions (.006)** and **document approved exceptions (.007)**
   — every exception is time-bounded and owner-assigned, never an open-ended waiver.
7. **Verify provenance for high-risk packages (.008).** For sensitive or low-reputation
   deps, verify the publisher, signature, and that the source repo matches the artifact.
8. **Replace abandoned packages (.009)** and **track forks with an owner + update policy (.010).**
9. **SBOM carries license metadata (.011).** Produce SPDX or CycloneDX for every release;
   each component entry must have a non-empty license field.

---

## Section 2 — Open Source Project Readiness

Maps to `PRC.OPEN_SOURCE_AND_LICENSING.OPEN_SOURCE_PROJECT_READINESS.001–012`.

Before a repo goes public, the governance files must be in place:

- **README** with purpose, install, usage, and support expectations (.001).
- **LICENSE** file present and *correct* — absence means "all rights reserved", and it must
  not contradict the obligations of your dependencies (.002).
- **CONTRIBUTING.md** describing the contribution workflow (.003).
- **CODE_OF_CONDUCT.md** published (.004).
- **SECURITY.md** with the vulnerability reporting process (.005).
- **Issue and PR templates** configured (.006).
- **Maintainer roles and approval rules** documented (.007).
- **Release process** documented and repeatable (.008).
- **Public roadmap / project status** if community-facing (.009).
- **Support boundaries** — free vs paid — stated (.010).
- **CLA or DCO** configured *before* accepting external contributions when needed (.011).
- **Examples / sample projects** for common use cases (.012).

---

## Section 3 — Package Publishing & Provenance

Maps to `PRC.OPEN_SOURCE_AND_LICENSING.PACKAGE_PUBLISHING_AND_PROVENANCE.001–011`.

- **Org-owned namespace (.001).** The registry namespace/scope belongs to an organization
  account, never a personal employee account. Personal ownership orphans the package when
  the person leaves.
- **MFA on registry accounts (.002).**
- **Publish from CI, not laptops — SLSA (.003).** Releases run in a pipeline with no human
  pushing from a local machine.
- **Build provenance attached (.004).** Generate and attach attestation (e.g. SLSA
  provenance, npm `--provenance`, GitHub artifact attestations).
- **Sign packages where supported (.005)** (Sigstore/cosign, GPG, npm provenance).
- **Immutable version tags (.006).** Never mutate or re-push a released tag.
- **Deprecations carry migration guidance (.007)**; **breaking changes require a major
  bump (.008)** under semver.
- **Pre-release channels (.009):** alpha / beta / rc.
- **Checksums on artifacts (.010).**
- **Review ownership when maintainers leave (.011).**

---

## Concrete workflow / checklist

**A. Adding or upgrading a dependency**

- [ ] Resolve the full transitive tree from the lockfile.
- [ ] Run the license scanner; confirm every license is on the allowlist (no unknown/prohibited).
- [ ] If copyleft and the product is distributed → open a recorded review/approval.
- [ ] Confirm provenance for any high-risk package; verify the namespace is not typosquatted.
- [ ] Regenerate the SBOM and the NOTICE/attribution file; commit them.

**B. Open-sourcing a repository**

- [ ] LICENSE present, correct, and compatible with all dependency obligations.
- [ ] README, CONTRIBUTING.md, CODE_OF_CONDUCT.md, SECURITY.md present.
- [ ] Issue/PR templates, maintainer roles, support boundaries documented.
- [ ] CLA/DCO wired if external contributions are accepted.
- [ ] Examples included.

**C. Publishing a release**

- [ ] Namespace is org-owned; publishing account has MFA.
- [ ] Release runs in CI (not local); provenance/attestation attached.
- [ ] Artifacts signed (where supported) and checksummed.
- [ ] Tag is immutable; semver respected (major bump on breaking change).
- [ ] SBOM (SPDX/CycloneDX) with license metadata published alongside the release.

**D. Maintainer offboarding**

- [ ] Audit every package namespace the departing maintainer owned/co-owned.
- [ ] Transfer ownership to the org; rotate publish tokens; confirm MFA on remaining owners.

---

## Anti-patterns

| Anti-pattern | Why it fails | Corpus item | Do instead |
|---|---|---|---|
| Scanning only direct deps | Copyleft/proprietary hides transitively | DEPENDENCY_LICENSE_CONTROLS.003 | Scan the full resolved lockfile graph |
| "Build is green = licenses OK" | No license gate actually ran | DEPENDENCY_LICENSE_CONTROLS.002 | Add a CI gate that fails on prohibited/unknown |
| Shipping without NOTICE file | Permissive licenses legally require attribution | DEPENDENCY_LICENSE_CONTROLS.005 | Auto-generate NOTICE from the SBOM, ship in artifact |
| Open-sourcing with no LICENSE | Default = all rights reserved; unusable | OPEN_SOURCE_PROJECT_READINESS.002 | Add a correct, dependency-compatible LICENSE |
| Accepting PRs with no CLA/DCO | Cannot relicense or prove provenance later | OPEN_SOURCE_PROJECT_READINESS.011 | Configure CLA/DCO before first external PR |
| Publishing from a laptop | No provenance; unauditable supply chain | PACKAGE_PUBLISHING_AND_PROVENANCE.003 | Publish from CI with SLSA attestation |
| Personal-account namespace | Package orphaned when person leaves | PACKAGE_PUBLISHING_AND_PROVENANCE.001 | Org-owned namespace + ownership review on exit |
| Re-pushing a released tag | Breaks reproducibility and downstream lockfiles | PACKAGE_PUBLISHING_AND_PROVENANCE.006 | Immutable tags; cut a new version |
| SBOM without license fields | Audit cannot verify obligations | DEPENDENCY_LICENSE_CONTROLS.011 | Emit SPDX/CycloneDX with license per component |

---

## Related

- `SKILL_PRODUCTION_READINESS_AUDIT_001` — scores this category; this skill fixes its gaps.
- `SKILL_DEPENDENCY_SOVEREIGNTY_001` — dependency control and vendoring discipline.
- `SKILL_REPRODUCIBLE_BUILD_DISCIPLINE_001` — deterministic builds underpinning provenance.
- `SKILL_CI_PIPELINE_001` / `SKILL_RELEASE_GATE_CI_001` — where the license + provenance gates run.
- `SKILL_PROOF_MATRIX_001` — evidence matrix for proving each item passes.
- `SKILL_VERIFY_VALIDATE_001` — evidence discipline for marking items pass.
