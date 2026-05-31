# Viewport Responsive Chrome and Layout Integrity Playbook

## Skill ID
SKILL_VIEWPORT_RESPONSIVE_CHROME_001

## Purpose
Prevent application chrome, page panels, and conditional controls from overlapping, crowding, or implying unavailable state across real desktop-app window sizes.

## Trigger Conditions
- User reports overlapping text, search bars, controls, windows, margins, scaling, or convoluted layout.
- UI work touches topbars, command/search bars, sidebars, inspectors, drawers, profile/settings shells, or desktop app packaging.
- A control should appear only when backed by real state, especially update buttons and notification badges.

## Hard Rules
- Do not absolute-center search/command bars unless viewport collision behavior is explicitly tested.
- Use flow layout, `min-width: 0`, truncation, clamp/minmax sizing, and breakpoint hiding before fixed widths.
- No visible direct topbar controls may overlap at 512px desktop-app width.
- Conditional controls render only when their backing state exists.
- Update topbar buttons and settings badges appear only for real pending release/feed entries.
- Pane toggles, focus mode, and walkthrough/help controls are shared shell invariants; do not strand them on one special-case page.
- If a page implements panes inside its content grid, the shared pane controls must still collapse those page panes.
- Every fix must add or update regression coverage.

## Workflow

### Observe
- Reproduce at the reported viewport size and capture the exact overlapping controls.
- Identify whether the issue is fixed positioning, missing `min-width: 0`, unbounded text, non-wrapping tables, or unconditional state chrome.

### Orient
- Map the affected surfaces: topbar, sidebar, center workbench, inspector, drawer, modal, settings/profile panel, or page-specific shell.
- Determine whether the control is always valid or conditional.
- Check whether the affected control is a global shell invariant or a page-specific tool.

### Decide
- Prefer responsive flow and collapse/hide rules over visual cramming.
- Define breakpoints before editing.
- Decide what must disappear first at narrow widths: optional subtitle, secondary buttons, nav arrows, chat affordance, then search.

### Act
- Patch layout CSS/components.
- Remove or gate unconditional controls.
- Preserve shared shell controls across all primary pages before changing page-specific chrome.
- Add viewport regression tests for the failure width.
- Add shared-control regression tests when a pane/focus/help affordance is added, removed, or moved.
- Run lint, typecheck, tests, and browser/E2E checks when available.

## Required Evidence
- Affected viewport size.
- Before/after behavior.
- Regression test name.
- Validation commands and results.
