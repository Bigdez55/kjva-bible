# ATLAS Ideation Playbook

## Skill ID
SKILL_ATLAS_PLANNING_TRACE_001

## Purpose
Create an ATLAS-native planning workflow where brainstorming cards become architecture graph nodes and edges, then produce a coding-agent handoff packet for repo buildout.

## Trigger Conditions
- User asks for a Traycer-style brainstorming or planning feature.
- User wants notes/backlinks to support architecture and design.
- User wants plans mapped into graph relationships and pushed to coding agents.

## Hard Constraints
- The feature must remain ATLAS-native.
- Use `Atlas Graph Engine` and `Atlas Knowledge Vault`.
- Do not use external product names as ATLAS subsystem names.
- Every ideation must include brainstorm cards, graph projection, coding-agent handoff, proof gates, and stop rules.
- Demo ideations can be API-generated; production ideations require tenant-scoped persistence.

## Workflow

### Observe
- Identify the planning prompt, target repo, target surface, current files, and related knowledge notes.
- Determine whether the ideation is for brainstorming, architecture, implementation, or proof closure.

### Orient
- Convert the prompt into lanes:
  - intent
  - surface
  - data
  - risk
  - build
- Convert cards into graph nodes and relationships.
- Convert graph relationships into coding-agent scope.

### Decide
- Define target repo and files to touch.
- Define build steps in execution order.
- Define proof gates and stop rules.
- Label demo-local behavior vs production persistence.

### Act
- Generate the ideation.
- Render cards, graph projection, and handoff packet.
- Push the handoff through repo-event ingestion or agent context when requested.
- Validate API and UI behavior.

## Required Outputs
- Brainstorm cards
- Architecture graph nodes
- Architecture graph edges
- Coding-agent handoff packet
- Target repo
- Files to touch
- Build steps
- Proof gates
- Stop rules

## Validation Checklist
- `/api/planning-trace` returns `200`.
- POST `/api/planning-trace` returns an ideation with cards, graph nodes, graph edges, and agent handoff.
- UI exposes ideation creation.
- UI exposes graph projection.
- UI exposes coding-agent handoff action.
- `npm run lint` passes.
- `npm run build` passes.
