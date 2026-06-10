# DO_NOT_MODIFY.md - Contract Change Guardrails

This file is a guardrail list, not an external authority record. These files
can be changed, but only with a focused reason and a matching verification pass.

## Contract Surfaces

- `heptagon/harness.py`
- `heptagon/layers.py`
- `heptagon/unified_model_spec.json`
- `governance/covenant_enforcer.py`
- `governance/decision_envelope.py`
- `soul_manager/soul_manager.py`
- `soul_manager/aes_gcm_bridge.py`
- `ai/xmind/include/*.h`
- `adr/ADR-S49-01-COGNITIVE-ARCHITECTURE-DOCTRINE.md`

## Required Before Editing

1. Identify the consuming runtime path affected by the change.
2. Run the smallest relevant smoke test before and after.
3. Update docs or audit notes if the contract shape changes.
4. Keep project-specific names out of the contract surface.

## Current Exception

Name cleanup that removes old project-origin language is allowed when it does
not change runtime behavior.
