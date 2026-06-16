# Trigger Router Instructions

Use the canonical trigger router when a request contains ordinary trigger language, shorthand, or `/atlas:*` commands.

## Runtime Grammar

```text
behavioral_protocol -> root_verb -> noun -> modifier -> target -> output -> proof -> corrective
```

Interpret the request as one surface:

- `/atlas:graph`, `atlas graph`, and `Atlas Graph Engine` resolve to the Atlas branch plus the Atlas Graph Engine target.
- `/atlas:knowledge_vault`, `atlas knowledge vault`, and `Knowledge Vault` resolve to the Atlas branch plus the Atlas Knowledge Vault target.
- `build platform` resolves to build foundation plus the platform branch.
- `build dashboard DeepThink proof one-shot` resolves to build foundation plus dashboard branch plus depth/output/proof modifiers.
- Correctives such as `re-read`, `wrong target`, `missed it`, and `do not miss that again` override the current route and trigger miss recovery.

## Required Response Shape

When exposing router results, include:

- `selected_root`
- `selected_noun`
- `selected_target`
- `active_modifiers`
- `active_output_contract`
- `proof_requirements`
- `corrective_override`
- `matched_intents`
- `skills`
- `required_outputs`

## Naming Rule

Use proprietary Atlas names for subsystem references:

- Atlas Graph Engine
- Atlas Knowledge Vault
- Atlas Graph
- Knowledge Vault
- Linked Knowledge Layer
- Graph Intelligence Layer

Do not use external graph/vault product names as ATLAS subsystem names. Legacy command names remain compatibility aliases only.
