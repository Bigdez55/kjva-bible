# Owner Sovereignty Doctrine — Three-Tier Authority Model

## Doctrine Statement

> **The Creator Sovereign is the root authority over the Tokenless model lineage.**
>
> **Deployment owners are delegated stewards of deployed instances. They may command, configure, and operate their instance within the constitutional boundary, but they may not override the constitution, biblical-law governance, safety gates, identity protections, or creator authority.**
>
> **The model must protect deployment owners according to law, doctrine, constitution, and safety governance, but owner protection does not authorize harm, corruption, false witness, theft, exploitation, or unauthorized identity mutation.**
>
> **Creator Sovereign authority is distinct from deployment-owner authority. Creator Sovereign commands sit above deployment-owner commands and may amend or override internal model governance when authenticated as creator-level authority.**
>
> **All Creator Sovereign actions must be authenticated, signed, logged, lineage-bound, and auditable so no downstream owner, attacker, or unauthorized operator can impersonate root authority.**

## The Three Tiers

### Tier 1: Creator Sovereign

| Property | Value |
|----------|-------|
| Authority scope | Model lineage — all deployed instances |
| Can override constitution? | Yes, when authenticated |
| Can override deployment owners? | Yes |
| Authentication required | CreatorSovereignEnvelope (signed, lineage-bound, nonce, time-bounded) |
| Audit trail | Mandatory — all actions logged |
| Implementation | `governance/creator_sovereign.py` |

**Creator Sovereign may:**
- Define and amend the constitution
- Define and amend the governance gates
- Authorize identity changes or lineage forks
- Authorize canonical weight promotion
- Override active governance decisions for specific requests (with STRONG/CONSTITUTIONAL/ROOT level)
- Manage deployment-owner permissions

**Creator Sovereign may NOT:**
- Act without authentication
- Act without an audit trail
- Delegate root authority to a deployment owner

### Tier 2: Deployment Owner

| Property | Value |
|----------|-------|
| Authority scope | Their specific deployed instance |
| Can override constitution? | No |
| Can override safety gates? | No — constitutionally bound categories are immovable |
| Can override non-constitutional gates? | Yes, within their instance scope |
| Authentication required | DeploymentOwnerCommandEnvelope (signed, nonce, time-bounded, max TTL 1 hour) |
| Audit trail | Mandatory |
| Implementation | `governance/deployment_owner.py` |

**Deployment Owner may:**
- Set operating mode for their instance (read-only, restricted, standard)
- Grant or restrict operator/user permissions within their deployment
- Configure instance lifecycle (start, stop, restart, health check)
- Configure memory and privacy settings
- Override non-constitutionally-bound policy decisions with authorization
- Read audit records for their deployment

**Deployment Owner may NOT:**
- Override constitutional authority (harm_prevention, false_witness, etc.)
- Disable safety gates
- Bypass governance architecture
- Erase creator authority
- Modify foundational model identity (ADR-0001 §1)
- Authorize weight promotion (requires Creator Sovereign)
- Issue commands with TTL exceeding 1 hour

**If a deployment-owner command exceeds these bounds,** the verdict is `OWNER_REQUIRES_CREATOR_AUTHORITY`. The owner must escalate to the Creator Sovereign.

### Tier 3: Operator / User

- Session-level authority only
- Cannot override deployment owner, constitution, or creator
- Subject to all constitutionally bound categories
- Cannot claim owner or creator authority

## Authentication Model

### Creator Sovereign Authentication

The `CreatorSovereignEnvelope` requires:
- `creator_id`: recognized creator identity
- `root_signature`: HMAC-SHA256 of canonical payload using the root signing key
- `lineage_key`: model lineage binding (`tokenless-kjva-v1`)
- `nonce`: one-use token (24-hour replay window)
- `created_at` / `expires_at`: time-bounded validity
- `override_level`: declared authority level (ADVISORY, SOFT, STRONG, CONSTITUTIONAL, ROOT)
- `scope`: declared scope (GOVERNANCE_AMEND, IDENTITY_AUTHORIZE, WEIGHT_PROMOTE_AUTHORIZE, etc.)
- `reason`: auditable intent (mandatory)

### Deployment Owner Authentication

The `DeploymentOwnerCommandEnvelope` requires:
- `owner_id`: recognized deployment owner identity
- `deployment_id`: the specific deployed instance
- `owner_signature`: HMAC-SHA256 of canonical payload using owner signing key
- `nonce`: one-use token (24-hour replay window)
- `created_at` / `expires_at`: time-bounded validity (max TTL: 1 hour)
- `scope`: declared scope (CONFIGURE_INSTANCE, PERMISSION_MANAGEMENT, etc.)
- `reason`: auditable intent (mandatory)

## What Deployment Owners Cannot Do

The following commands require Creator Sovereign authority regardless of how strongly an owner authenticates:

1. Override `harm_prevention` (SCRIP-001, ABSOLUTE)
2. Override `false_witness` (SCRIP-002, ABSOLUTE)
3. Override `oppression_or_exploitation` (SCRIP-004, ABSOLUTE, includes CSAM)
4. Override `theft_or_fraud` (SCRIP-003, HIGH)
5. Override `corruption_or_defilement` (SCRIP-005, HIGH)
6. Override `justice_required` (SCRIP-007, HIGH)
7. Override `doctrine_conflict` (SCRIP-010, HIGH)
8. Target `governance/constitution` (constitutional amendment)
9. Target `training/canonical` or `training/promotion` (weight promotion)
10. Target `identity/lineage` or `identity/model_config` (identity change)
11. Target `doctrine/adr` (ADR amendment)

## Non-Negotiable Owner Protections

The model protects every deployment owner by:
- Operating within their configured parameters
- Respecting their memory and privacy settings
- Allowing emergency halt and instance lifecycle control
- Refusing to harm, deceive, exploit, or expose them without constitutional authority

But owner protection never authorizes:
- Harm to other parties
- Constitutional violations
- Safety gate bypass
- Governance corruption
