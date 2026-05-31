# Debugging Context Compiler

## Purpose
Compile an agent context packet scoped to debugging work.

## Inputs
- Target persona under [12_agents/personas/](../12_agents/personas/).
- Source ranking from [19_truth_state/source_of_truth_ranking.yaml](../19_truth_state/source_of_truth_ranking.yaml).
- Task description.

## Steps
1. Load persona yaml.
2. Load relevant truth-state files.
3. Filter skills by domain.
4. Emit packet to `42_context_compiler/output/generated/`.

## Schema
[context_packet.schema.yaml](context_packet.schema.yaml)
