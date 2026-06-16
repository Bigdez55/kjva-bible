# Release Gate CI (Assert Every Gate Proven Before Merge)

> Promoted from ATLAS Phase C.2 2026-05-29 (Gate 7).

## The Pattern

Every app with a production-readiness manifest gets a CI workflow that:
1. Runs all upstream gates (lint, typecheck, test, build, e2e, security scans, gate-specific tests).
2. Runs a final `release-gate-assertion.test.ts` that imports the manifest and exits 1 if ANY gate.state !== "proven".
3. Is a required status check on the main branch.

## Workflow Template

```yaml
# .github/workflows/atlas-release-gate.yml
name: ATLAS Release Gate
on:
  pull_request:
    branches: [main]
  push:
    branches: [main, prod-ready/**]

jobs:
  python-gates:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: '3.11' }
      - name: Run validation commands
        run: |
          python3 infrastructure/scripts/validate_trigger_determinism.py
          python3 infrastructure/scripts/validate_skill_router_integration.py
          python3 infrastructure/scripts/validate_skills_stack.py
          python3 infrastructure/scripts/regression_runner.py
          python3 infrastructure/scripts/registry_sync/sync_registries.py --check
          python3 infrastructure/scripts/drift_checkers/check_truth_drift.py --check --no-write
          python3 infrastructure/scripts/drift_checkers/check_traceability_drift.py
          python3 infrastructure/scripts/skill_index/generate_master_index.py --check
          python3 infrastructure/scripts/skill_dedup/detect_duplicates.py --strict --no-write

  frontend-lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with: { node-version: '22.x', cache: npm, cache-dependency-path: apps/frontend/shell/package-lock.json }
      - run: cd apps/frontend/shell && npm ci && npm run lint

  frontend-typecheck:
    runs-on: ubuntu-latest
    steps: [...similar...]
    run: cd apps/frontend/shell && npm ci && npm run typecheck

  frontend-test:
    runs-on: ubuntu-latest
    steps: [...similar...]
    run: cd apps/frontend/shell && npm ci && npm test

  db-schema-check:
    runs-on: ubuntu-latest
    steps: [...similar...]
    run: cd apps/frontend/shell && npm ci && npx drizzle-kit check

  auth-isolation:
    runs-on: ubuntu-latest
    steps: [...similar...]
    run: cd apps/frontend/shell && npm ci && node --experimental-strip-types tests/cross-tenant-isolation.test.ts

  rate-limit-tests:
    run: cd apps/frontend/shell && npm ci && node --experimental-strip-types tests/rate-limits.test.ts

  audit-chain-check:
    run: cd apps/frontend/shell && npm ci && node --experimental-strip-types tests/audit-chain.test.ts

  security-scan:
    run: cd apps/frontend/shell && npm ci && npm audit --audit-level=high

  frontend-build:
    runs-on: ubuntu-latest
    steps: [...]
    run: cd apps/frontend/shell && npm ci && npm run build

  e2e:
    runs-on: ubuntu-latest
    needs: frontend-build
    run: cd apps/frontend/shell && npm ci && npx playwright install --with-deps && npm run e2e

  release-verdict:
    runs-on: ubuntu-latest
    needs:
      - python-gates
      - frontend-lint
      - frontend-typecheck
      - frontend-test
      - db-schema-check
      - auth-isolation
      - rate-limit-tests
      - audit-chain-check
      - security-scan
      - frontend-build
      - e2e
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with: { node-version: '22.x' }
      - run: cd apps/frontend/shell && npm ci && node --experimental-strip-types tests/release-gate-assertion.test.ts
```

## The Assertion Test

```typescript
// tests/release-gate-assertion.test.ts
import {
  atlasProductionReadiness,
  productionReleaseBlockers,
} from "../src/lib/production-readiness.ts";

function main(): number {
  const blockers = productionReleaseBlockers();
  const total = atlasProductionReadiness.releaseGates.length;
  const recommendation: string = atlasProductionReadiness.releaseRecommendation;

  if (blockers.length > 0) {
    console.error(`BLOCK — ${blockers.length}/${total} gates not proven`);
    for (const g of blockers) console.error(`  - ${g.id} state=${g.state}`);
    return 1;
  }
  if (recommendation !== "READY_FOR_PUBLIC_RELEASE" && recommendation !== "READY") {
    console.error(`BLOCK — recommendation is "${recommendation}", not READY`);
    return 1;
  }
  console.log(`PASS — ${total}/${total} production gates proven. Release verdict: READY`);
  return 0;
}

process.exit(main());
```

## The Flip Discipline

Only one designated agent (e.g., apex-coordinator) modifies the manifest. They:
1. Verify Phase D evidence files exist at `/tmp/atlas-audit/D/evidence/<gate-id>.txt`
2. Flip each `state: "blocked"` → `state: "proven"`
3. Update `currentEvidence` array with evidence file path + commit SHA
4. Update `releaseRecommendation` → `"READY_FOR_PUBLIC_RELEASE"`
5. Commit + push

Any unauthorized flip (no evidence) is caught by code review + audit-log + CI history.

## Validation Gates

| Gate | Pass |
|---|---|
| Workflow YAML valid | `python3 -c "import yaml; yaml.safe_load(open('.github/workflows/atlas-release-gate.yml'))"` |
| Release-verdict depends on all jobs | grep `needs:` |
| Pre-flip assertion fails | `node tests/release-gate-assertion.test.ts` exit 1 |
| Post-flip assertion passes | same command exit 0 |
| GitHub branch protection: required status check enabled for `release-verdict` | manual config |

## Incident Record

| Date | Project | Bug | Commit |
|---|---|---|---|
| 2026-05-29 | ATLAS | No CI release gate; Gate 7 blocked | 4b9561c |
