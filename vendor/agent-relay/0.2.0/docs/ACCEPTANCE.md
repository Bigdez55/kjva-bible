# Candidate-bound acceptance, not a gate-count scoreboard

Three independent statements must not be conflated:

- An individual executable assertion passed against a particular installed build.
- A declared local deployment profile has all required evidence and reviewed gaps.
- Every original requirement has unqualified production certification everywhere.

The release report supports the first; `relayctl certify` evaluates the second.
Neither automatically establishes the third.

## Immutable policy and exact inputs

`contracts/LOCAL_GATE_POLICY.json` is byte-identical to the policy installed inside
the wheel. It contains the original G01–G46 identifiers and requirement text,
explicit required test IDs, pinned test-tree/runner hashes and remaining boundaries.
The original contract file is preserved unchanged. The evaluator rejects a
weakened policy, omitted IDs, duplicate/fake-count records, missing/failed/skipped
required tests, source-mode results and changed runtime/source/test/runner bytes.
Before/after identity is mandatory. Cleanup errors also hold acceptance.

Run:

```sh
"$P/bin/relayctl" certify --evidence /tmp/relay-020-acceptance/verification.json \
  --policy contracts/LOCAL_GATE_POLICY.json --output /tmp/relay-020-evaluation.json
```

Status per gate is PASS_IN_DECLARED_PROFILE, NEEDS_REVIEW,
TESTS_MISSING_OR_FAILED, or EXCEPTED_REMAINING_BOUNDARY. Missing/failed tests remain
blocking even when another boundary is approved. There is no command to set PASS.
A new run's evidence digest invalidates prior reviews even on identical code.

## Reviewed exceptions

A separate reviewer controls a private key not shared with worker/provider
processes. The package contains no real review key and no preapproved decisions.
Create the key with an operator-controlled secrets process, e.g. generate at least
32 random bytes with Python `secrets.token_bytes`, store mode 0600, and retain it
outside repositories and provider context. Do not use the disposable test key.

```sh
"$P/bin/relayctl" review-template --evaluation /tmp/relay-020-evaluation.json \
  --reviewer "Actual responsible reviewer" --out /private/reviews/unsigned.json
```

The template is UNSIGNED and has TODO reasons. Review the original requirement,
actual tests, deployment and consequences. Replace each applicable TODO with a
specific rationale and expiry; do not approve a boundary that the deployment
cannot tolerate. If a required boundary is not approved, keep the deployment held.

```sh
"$P/bin/relayctl" review-sign --input /private/reviews/unsigned.json \
  --review-key /private/reviews/review.key --out /private/reviews/decisions.json \
  --confirm-reviewed
"$P/bin/relayctl" certify --evidence /tmp/relay-020-acceptance/verification.json \
  --policy contracts/LOCAL_GATE_POLICY.json --decisions /private/reviews/decisions.json \
  --review-key /private/reviews/review.key
```

A decision binds gate, candidate, exact policy bytes, exact evidence bytes, reviewer,
reason and expiry with HMAC. Tampering, cross-candidate reuse, expired decisions,
duplicate decisions and placeholder reasons are rejected. EXCEPTED stays EXCEPTED.
The CLI's explicit confirmation is not an electronic signature asserting a human
identity; possession of a same-UID key does not prove authorship. Stronger assurance
requires an external reviewer/CI identity boundary and independent attestation.

`full_original_certification` remains false for this scoped local profile. That
field is deliberately not a configurable marketing switch. Migration activation
uses the evaluated `ready` state with explicit reviewed exceptions and separately
checks the migration/recovery state. It never uses a rewritten historical PASS.

## Rerun after changes

Any code, test, protocol, environment-relevant registration or source changes need
new evidence. Runtime policy/test edits require a newly built and verified wheel;
`tools/build_gate_policy.py` is a maintainer build step, never an operator method
for bypassing held readiness. Do not patch installed data to approve yourself.
