---
name: Pass 2 Governance OODA Deep Dive 2026-04-24
description: Verification and expansion of Pass 1 governance vulnerabilities; Citadel/governance and Citadel/council/runtime full audit. Governance layer is orphaned and non-functional.
type: project
---

# Pass 2 OODA — Governance + Refusal Gate Audit (2026-04-24)

Commit: `75bc2f0` main. Audit Token: `GS-P2-GOV-20260424-75bc2f0`.

## TL;DR
The governance layer is **architecturally dead**. Gate chain, covenant enforcer, heptagon invariant engine, and attestation engine all work in isolation and have unit tests, but **ZERO production callers** wire them into any running daemon. Every Pass 1 vulnerability is confirmed; multiple new ones found.

## Pass 1 Vulnerability Verification

### VULN-GOV-01 CONFIRMED (P0) — GateChainExecutor ALLOW/ALLOW branch
- File: `Citadel/governance/decision_envelope.py:217-227`
- Exact bug: `verdict = GateVerdict.ALLOW if not blocking else GateVerdict.ALLOW`
- Impact: If ANY of the 7 authorities is unregistered, that gate falls through to ALLOW regardless of whether blocking. An EMPTY executor (the default in `GenesysIntegrator()` and `GovernanceInterceptors()`) passes every DecisionEnvelope.
- Fix (1 line): `verdict = GateVerdict.ALLOW if not blocking else GateVerdict.DENY`
- Additional note: docstring says `"escalate for blocking"` but code doesn't escalate.

### VULN-GOV-02 CONFIRMED (P0) — Magen substring-match trust spoofing
- File: `Citadel/governance/gate_evaluators.py:304-305`
- Bug: `is_known_source = any(t in source for t in self.TRUSTED_SOURCES)`
- With TRUSTED_SOURCES including `"gen"`, an attacker can spoof `created_by="generic-user"` or `"genuine-attacker"` — both contain "gen" → trust bonus +0.2 applied.
- Also affects: `"forge"` substrings, `"ruth"`, etc. Any impersonator name that *contains* a trusted name.
- Fix: Change `any(t in source for t in TRUSTED_SOURCES)` → `source in TRUSTED_SOURCES` OR use structured signed identity.

### VULN-GOV-03 CONFIRMED (P1) — SOUL_ISOLATION dead code / prefix mismatch
- File: `Citadel/council/runtime/invariants/invariant_engine.py:127-140, 251`
- Default prefix: `f"{agent_id}/"` (e.g., `"Sarah/"`)
- But SoulManager keys (`Citadel/council/runtime/memory/soul_manager.py:619`): `f"soul:{agent}:{bucket}:{sub_path}"`
- Any `check_soul_isolation()` call with a real storage key `"soul:Sarah:persistent:x"` will NOT match `"Sarah/"` prefix — `is_owner` returns False for the legitimate owner → perpetual CRITICAL violation or (more likely) no caller uses it.
- grep confirmed: ZERO external callers of `check_soul_isolation`. Dead code.

### VULN-GOV-04 CONFIRMED (P0) — governance_approved self-attestation bypass
- File 1: `Citadel/council/runtime/invariants/enforcement.py:266-269` — `governance_approved = bool(context.get("governance_approved", False) or decision.get("governance_approved", False))`
- File 2: `Citadel/council/runtime/invariants/invariant_engine.py:391-394` — `governance_approved = decision.get("governance_approved", False)`
- File 3: `Citadel/council/ruth/ruth/authority.py:110-132` — `escalate(gate_results, governance_approved: bool = False)` — boolean arg, no signature
- The flag is just a boolean in a dict the agent itself builds. There is no HMAC, no signature, no proof of origin, no chain of custody, no witness quorum required to set it.
- Anyone can bypass with `decision["governance_approved"] = True`.
- Comment at authority.py:116 says "The governance_approved flag is set by Esther daemon via IPC" but NO code verifies that.

### VULN-GOV-05 CONFIRMED (P1) — SoulManager uses SHA-256 concat not HKDF
- File: `Citadel/council/runtime/memory/soul_manager.py:138-144`
- Code: `return hashlib.sha256(master_secret + agent.encode("utf-8")).digest()`
- Docstring claims "Uses HKDF-SHA256 pattern (simplified)" — it is NOT HKDF. It's raw concatenation → SHA-256, vulnerable to length-extension in some contexts and crucially lacks the PRK/salt separation that makes HKDF a KDF rather than a hash.
- Per-agent keys are derivable if the master_secret ever leaks; no salt, no info string, no stretch.
- Fix: use `cryptography.hazmat.primitives.kdf.hkdf.HKDF(algorithm=SHA256, length=32, salt=..., info=agent.encode())`.

## NEW P0 FINDINGS (Pass 2)

### VULN-GOV-06 NEW (P0) — Governance layer is orphaned (no production callers)
- Searched entire repo for external callers of:
  - `create_default_gate_chain()` → **ZERO callers** outside its own module and tests
  - `build_heptagon_engine()` → **ZERO callers** outside its own module and tests
  - `build_default_engine()` (5 core invariants) → **ZERO callers** outside own module and tests
  - `GovernanceInterceptors` → only referenced in `__init__.py` exports
  - `CovenantEnforcer` → only referenced in `__init__.py` exports
  - `citadel_before_execute()` → called ONLY from the `__main__` demo block in `genesys_integrator.py`
  - `AttestationEngine.attest()` → no daemon invokes it at startup
- Heptagon L7 enforcement claims 12 invariants; **invariants are never checked on any real decision path**.
- The entire Sarah → Esther → Magen → Abigail → Ruth → Ezri → Ahki gate chain is a unit-tested library with no kernel, daemon, or service hook.
- `GenesysIntegrator.__init__` defaults to an **empty** `GateChainExecutor()` — and combined with VULN-GOV-01, every gate returns ALLOW.

### VULN-GOV-07 NEW (P0) — genos-validate Gate 5 is manifest-self-attestation
- File: `devices/cloud/platform/refusal/cmd/genos_validate.py:228-253`
- Gate 5 `gate_conformance_suite` ONLY checks:
  - `manifest["conformance_suite"]["suite_id"]` is non-empty string
  - `manifest["conformance_suite"]["result"] == "pass"`
  - `manifest["conformance_suite"]["timestamp"]` is non-empty
- There is NO execution of any conformance suite. NO signed suite-run result. NO registry of valid suite IDs (no cross-check against `approved_toolchains` etc.). NO timestamp freshness check.
- A workload can submit `{"conformance_suite": {"suite_id": "any_string", "result": "pass", "timestamp": "2020-01-01"}}` and pass Gate 5.
- The 13-gate refusal pipeline has additional weakness: Gate 5 is in position 5 (not last), short-circuits further gates on failure — meaning if Gate 5 is bypassed trivially, Gates 6-13 still run, but Gate 5 itself is the confidence root.

### VULN-GOV-08 NEW (P1) — Attestation is nominal, not cryptographic
- File: `Citadel/heptagon/attestation.py:150-225`
- `attest()` checks:
  - Registry existence: string lookup in MEMBER_REGISTRY
  - Schema hash: SHA-256 of member descriptor fields — computed by the SAME module, so the "verified" and "expected" are always identical UNLESS a separate hash is pre-registered (which no daemon does)
  - Memory lineage: line 113-123 — "If no prior lineage, accept with WARNING and initialise chain" — cold start = trust on first use forever
  - Witness quorum: line 201-206 — just checks "at least 2 of 3 names not in vacant_members list" — witnesses don't sign anything, just need to be named
- NO TPM PCR binding, NO Ed25519 signature from witnesses, NO challenge-response, NO nonce, NO attestation ticket.
- The "Identity Attestation Doctrine" comment talks about secure boot, but the code implements a name-list check.

### VULN-GOV-09 NEW (P1) — Covenant enforcer pattern matching is bypassable
- File: `Citadel/governance/covenant_enforcer.py`
- Pattern detection is pure substring match on lowercase text: `[p for p in HARM_PATTERNS if p in text]`
- Trivial bypasses:
  - `"c4use harm"` → doesn't match `"cause harm"`
  - `"cause  harm"` (two spaces) → doesn't match
  - Non-English phrasings, Unicode homoglyphs, encoded text
  - Base64-encoded intent text
- No caller wiring anyway (VULN-GOV-06) — but if wired, rule enforcement is porous.

### VULN-GOV-10 NEW (P2) — Empty executor double-fault
- File: `Citadel/council/substrate/genesys_integrator.py:178` AND `Citadel/governance/interceptors.py:46`
- Both default to `GateChainExecutor()` (no evaluators) when not passed
- Combined with VULN-GOV-01, this is a **double-fault**: the DI default is an empty executor, and empty-evaluator fallback is ALLOW.
- Fix: raise `RuntimeError("gate_chain required — use create_default_gate_chain()")` instead of defaulting.

## Integration Status

| Component | Implemented | Called From Production | Blocking Any Real Action |
|---|---|---|---|
| GateChainExecutor | yes | no | no |
| Gate Evaluators (Sarah-Ahki) | yes | no | no |
| CovenantEnforcer | yes | no | no |
| HeptagonInvariantEngine | yes | no | no |
| InvariantEngine (core 5) | yes | no | no |
| AttestationEngine | yes | no | no |
| GovernanceInterceptors | yes | no | no |
| SoulManager (AES-GCM) | yes | yes (via tests) | n/a |
| genos-validate 13 gates | yes | CI (manifest check) | advisory only |
| XPKG refusal_gate (9 gates) | yes in C | yes — xpkg install path | YES — genuine block |

Only XPKG's `refusal_gate.c` is genuinely wired and blocking.

## Attestation Chain Break

Claimed: TPM PCR → boot manifest → kernel → governance decision.

Actual:
1. TPM measurement exists in `aetherboot/src/tpm.c` — produces PCR values
2. CitadelBootManifest (`Citadel/governance/boot_manifest.py`) has fields for PCR, but `generate_boot_manifest` in `genesys_integrator.py:190` receives PCR state as PARAMETERS from Python caller — no kernel IPC binding, no TPM quote verification
3. DecisionEnvelope has `provenance_hash` field — never populated by any caller
4. Gate chain never checks provenance_hash exists
5. Governance decisions have no link back to boot manifest

**Chain is broken at every join.** TPM PCR quote is generated but never consumed by governance.

## Action Items (P0 first)

1. **VULN-GOV-01**: Change `decision_envelope.py:219` to return DENY for blocking. 1-line fix.
2. **VULN-GOV-06**: Wire `create_default_gate_chain()` into at least one daemon startup. Pick gensd or council orchestrator. Otherwise, delete the code.
3. **VULN-GOV-04**: Require HMAC signature on `governance_approved` flag. Introduce `governance_approval_token: bytes` signed by a dedicated governance key (Esther daemon holds signing key). Verify before trusting. Store in audit log.
4. **VULN-GOV-07**: Gate 5 must run an actual signed suite executor OR check a signed registry entry proving the suite ran. Also add timestamp freshness window.
5. **VULN-GOV-02**: Replace substring-match with exact-match + structured identity.
6. **VULN-GOV-05**: Replace SHA-256 concat with HKDF-SHA256 in `_derive_key`. Add 16-byte salt stored alongside master secret.
7. **VULN-GOV-08**: Bind attestation to TPM PCR quote. Require Ed25519 signature chain from witnesses. Enforce nonce on every attest() call.
8. **VULN-GOV-10**: Remove empty-executor default; require explicit gate chain or raise.
9. **VULN-GOV-03**: Either integrate SOUL_ISOLATION with the actual `soul:{agent}:{bucket}:` key format or delete it.
10. **VULN-GOV-09**: Replace substring covenant patterns with a structured policy language, or intent classifier with signed labels.

## Audit Chain

- Pass 1 → Pass 2 audit chain token: `GS-P2-GOV-20260424-75bc2f0-v1`
- 5 Pass 1 VULNs: all CONFIRMED
- 5 Pass 2 new VULNs: filed
- Next pass: wire one evaluator end-to-end and verify enforcement actually blocks
