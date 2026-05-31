# Canonical Trigger Router

Version: 1.1  
Status: canonical  
Model: verb-first, noun-refined, single surface

## Purpose

This router standardizes natural-language trigger words so ordinary speech deterministically activates the correct skill bundle, output contract, validation standard, and miss-recovery path.

The router uses the proprietary Atlas naming rule:

- Semantic graph layer: Atlas Graph Engine.
- Human-readable linked knowledge layer: Atlas Knowledge Vault.
- Graph folder: `43_atlas_graph_engine/`.
- Knowledge folder: `44_atlas_knowledge_vault/`.
- Graph skill: `36-atlas-graph-engine`.
- Knowledge skill: `37-atlas-knowledge-vault`.

External product or tool names must not be used as subsystem names inside SUPER C Atlas.

## Supersession Order

1. `Verb_First_Trigger_Map_v3.0` controls routing architecture.
2. `Natural_Language_Trigger_Map_v2.0` supplies noun clusters and ordinary-language synonyms.
3. `Trigger_Word_Lexicon_v1.0` is retained as the legacy shorthand alias layer only.
4. `Master_Project_Instruction_Guide_v1.0` governs the skill ecosystem and universal protocols.
5. `Apex_Skill_Refinement_Protocol_v1.0` governs misses, skill updates, regression tests, and promotion.
6. `Apex_Skill_Operational_Toolkit_v1.1` governs executable deployment through skill cards, ledgers, regression tests, and CI.
7. The Atlas build profile extends the router into Bookworm, Atlas Graph Engine, Atlas Knowledge Vault, Repo Twins, Skill Refinery, Context Compiler, and Proof Matrix.

## Canonical Rule

```text
The verb opens the pathway.
The noun narrows it.
The modifier tunes it.
The target binds it.
The output trigger shapes it.
The proof trigger validates it.
The corrective trigger improves it.
```

## Precedence

The runtime parser must apply one ordering everywhere:

```text
behavioral_protocol -> root_verb -> noun -> modifier -> target -> output -> proof -> corrective
```

Behavioral protocols apply globally. Corrective triggers override the active route and force miss recovery. `/atlas:*` commands are compatibility aliases and resolve into the same Atlas noun/target branches as natural text such as `atlas graph`.

## Routing Rules

- Root verbs open a foundation stack. `build` activates creation skills before the object is interpreted.
- Nouns select one primary branch. If no root verb exists, noun-only routing uses the noun default and the domain-safe base stack.
- Modifiers tune depth, output, proof, and audience without replacing the noun branch.
- Targets bind the branch to a project, repo, matter, metric, or proprietary Atlas subsystem.
- Proof triggers add validation requirements and prevent unsupported completion claims.
- Correctives stop the current path, classify the miss, and route to ledger/regression hardening.
- Machine-code emit constants are routed through `machine_encoding`, which activates `SKILL_APEX_VERIFIED_MACHINE_ENCODING_001` and requires oracle-backed constant verification before any instruction word lands.
- When multiple nouns appear, choose the branch nearest to the selected root. If there is no root, choose the earliest highest-priority noun. Only merge secondary branches when an explicit target or compatibility rule permits it.

## Canonical Files

- Human-readable source: `13_skills/skill_refinery/trigger_router.md`
- Machine-readable source: `13_skills/skill_refinery/trigger_router.yaml`
- Runtime catalog: `37_command_protocol/trigger_router.yaml`
- Schema mirror: `26_schemas/trigger_router/trigger_router.schema.yaml`
- Prompt guidance: `24_prompt_library/reusable_prompts/trigger_router_instructions.md`
- Knowledge index: `44_atlas_knowledge_vault/07_skills/Trigger_Router.md`
- Graph artifact: `43_atlas_graph_engine/graphs/trigger_skill.graph.json`
