# ATLAS Orbital Visual Identity Playbook

## Skill ID
SKILL_ATLAS_ORBITAL_IDENTITY_001

## Purpose
Apply the ATLAS visual identity across UI surfaces using the locked globe direction: blue atmospheric rim, dark night side, gold city-light intelligence network, starfield/nebula environment, and orbital command surfaces.

## Trigger Conditions
- User references the final ATLAS globe image.
- User asks for space, nebula, earth, orbital, or constellation-based UI/UX.
- User asks to preserve the logo direction.

## Hard Constraints
- The final globe image is the design anchor.
- ATLAS should feel like an orbital intelligence workspace, not a generic SaaS dashboard.
- Visual treatment must not reduce operational usability.
- The UI must remain responsive and build-safe.

## Workflow

### Observe
- Identify the target surface and current CSS/component structure.
- Confirm whether the surface is identity, navigation, hero, workspace, graph, editor, or proof UI.

### Orient
- Convert the globe image into reusable design tokens:
  - blue atmospheric rim
  - black/deep navy space
  - gold city-light network
  - starfield layer
  - nebula glow layer
  - glass command surface
- Determine where the mark appears: nav, hero, loading, empty state, workspace chrome, favicon future backlog.

### Decide
- Add reusable CSS classes or components, not one-off inline decorations.
- Preserve live workspace interactions.
- Keep contrast high enough for operational controls.

### Act
- Apply the logo mark.
- Apply star/nebula/orbital background system.
- Apply glass-panel command shell treatment.
- Validate `npm run lint`, `npm run build`, and public URL `200`.

## Required Outputs
- Logo mark treatment
- Visual language tokens
- Background atmosphere
- Operational UI application
- Responsive validation

## Validation Checklist
- Logo appears in primary shell.
- Orbital/space visual language appears without external subsystem naming drift.
- Buttons, editor, command bar, and sidebars remain legible.
- `npm run lint` passes.
- `npm run build` passes.
