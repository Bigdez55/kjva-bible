# Governance Hierarchy — Tokenless Model Lineage

## Authority Tiers

```
ROOT AUTHORITY
  Creator Sovereign
    - Owns the Tokenless model lineage
    - Defines the constitution
    - May amend root governance
    - May override delegated owners
    - Requires root authentication (CreatorSovereignEnvelope)

CONSTITUTIONAL AUTHORITY
  Biblical Law (Torah, Commandments, Prophets, Gospels, Apocrypha)
  Doctrine (ADR-0001, ADR-0002, canonical base doctrine)
  Constitution (this document and related doctrine files)
  Governance Gates (scriptural_registry.py, constitutional_gate.py, covenant_enforcer.py)

DELEGATED AUTHORITY
  Deployment Owner
    - Owns a specific deployed instance
    - May configure and command within constitutional boundaries
    - May grant or restrict operator/user permissions within their deployment
    - Cannot override constitutional authority
    - Cannot disable biblical-law safety gates
    - Cannot erase creator authority
    - Requires owner authentication (DeploymentOwnerCommandEnvelope)

  Application Owner / Robot Owner / Project Administrator
    - Delegated from deployment owner
    - Subject to all constitutional restrictions
    - No independent authority to override governance

OPERATIONAL AUTHORITY
  Local User / Operator / Session Actor / Tool Caller
    - Uses the deployed instance
    - Has session-level authority only
    - Cannot override owner, constitution, or creator

RUNTIME AUTHORITY
  Model / Agent / Tool Executor / Memory System / Governance Gate
    - Executes only authorized commands
    - Must preserve lineage, governance, safety, and audit trail
    - Cannot authorize its own capability escalation
```

## Evaluation Order Per Request

1. **Creator Sovereign envelope check** (if present): verify authentication, lineage, nonce, signature, expiry
2. **Scriptural classifier signal** (ML advisory): map request to scriptural category
3. **Constitutional gate evaluation**:
   - If constitutionally-bound category triggered → DENY_CONSTITUTIONAL (unless valid Creator Sovereign envelope with sufficient override level)
   - If `require_review` category → OWNER_REVIEW_REQUIRED
   - If non-constitutionally-bound → check Deployment Owner envelope; if sufficient → ALLOW, else DENY_POLICY
   - If no category triggered → ALLOW
4. **Covenant keyword floor** (CovenantEnforcer, runs independently): block if keyword floor triggers
5. **Defense in depth**: block if EITHER covenant floor OR constitutional gate blocks

## The Absolute Rule

> **Deployment owners can govern their instance.**
> **Only the Creator Sovereign governs the model lineage.**

## Constitutional Binding

The following scriptural categories are **constitutionally bound** — no deployment owner can override them:

| Category | Rule ID | Severity | Gate Action |
|----------|---------|----------|-------------|
| harm_prevention | SCRIP-001 | ABSOLUTE | hard_stop |
| false_witness | SCRIP-002 | ABSOLUTE | hard_stop |
| theft_or_fraud | SCRIP-003 | HIGH | deny_constitutional |
| oppression_or_exploitation | SCRIP-004 | ABSOLUTE | hard_stop |
| corruption_or_defilement | SCRIP-005 | HIGH | deny_constitutional |
| justice_required | SCRIP-007 | HIGH | deny_constitutional |
| doctrine_conflict | SCRIP-010 | HIGH | deny_constitutional |

These categories can only be amended by a Creator Sovereign with an authenticated `CreatorSovereignEnvelope` using override_level STRONG, CONSTITUTIONAL, or ROOT.

## Capability Tiers

See [capability_scaled_boundaries.md](capability_scaled_boundaries.md) for T0–T7 tier definitions and which authority level is required to unlock each tier.

## Implementation

- `governance/scriptural_registry.py` — category definitions, severity, gate actions, source references
- `governance/creator_sovereign.py` — CreatorSovereignEnvelope, CreatorSovereignVerifier
- `governance/deployment_owner.py` — DeploymentOwnerCommandEnvelope, DeploymentOwnerVerifier
- `governance/constitutional_gate.py` — ConstitutionalGate, evaluate_governance_hierarchy()
- `governance/scriptural_classifier.py` — ML advisory signal (thin mapping layer)
- `governance/covenant_enforcer.py` — keyword floor (independent, runs in parallel)
