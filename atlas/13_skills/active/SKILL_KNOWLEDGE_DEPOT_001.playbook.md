# SKILL_ATLAS_KNOWLEDGE_DEPOT_001 Playbook

## Purpose

Use this skill when ATLAS must function as a coding-agent knowledge depot instead of a static dashboard. The required outcome is an operational model where every page/surface has a reason, a user action, an agent input contract, an agent output contract, and a proof gate.

## Operating Loop

1. Identify the surface being requested: command center, repo workbench, Atlas Knowledge Vault, Atlas Graph Engine, planning studio, agent handoff, or proof review.
2. State why the surface exists in the ergonomic layout.
3. Bind the surface to user actions and coding-agent inputs.
4. Produce or update an agent knowledge packet that includes repo truth, active notes, backlinks, graph neighborhood, ideation, and proof gates.
5. Mark demo-only behavior separately from production persistence, authenticated repo writes, and live agent execution.
6. Add or update a regression case if the user correction exposed a repeated miss.

## Required Output Contract

- Four-zone workbench layout.
- Page-by-page use case map.
- Layout rationale.
- Agent knowledge packet.
- Repo truth input.
- Linked knowledge input.
- Graph neighborhood input.
- Planning trace input.
- Proof gate output.
- Production backlog boundaries.

## Vertical Slice Requirement

The first functional implementation must demonstrate:

1. Repo ingest.
2. Repo twin generation.
3. Knowledge Vault note/detail view.
4. Atlas Graph Engine node/edge view.
5. Backlinks and related files.
6. Spec Planner output.
7. Agent Handoff markdown export.
8. Proof Matrix claim/evidence table.
9. Drift Review finding table.
10. Skill Refinery miss and trigger view.

## Forbidden Actions

- Do not describe ATLAS as a clone of an external product.
- Do not leave a page as a decorative panel without action/state/proof.
- Do not claim a coding agent can use the platform unless an explicit context packet or API contract exists.
- Do not call demo-local state durable persistence.

## Validation

- `/api/use-cases` must expose surfaces and layout rationale.
- `/api/agent-context` must include the surface model.
- The UI must allow an agent packet to be generated from selected surface, repo, active file, backlinks, ideation, and proof gate.
- Regression case `REG-032` must route to `atlas_knowledge_depot`.
