# IPOS Alert System Playbook

## Purpose
Threshold-based alert system: penalty warnings, KPI degradation alerts, anomaly detection (Z-score), multi-channel delivery (email, Slack, Teams, SMS, webhook), alert lifecycle management, deduplication, escalation policies, snooze/mute, and dashboard alert feed widget. Trigger on: 'alerts', 'notifications', 'threshold breach', 'warning system', 'penalty alert', 'escalation'.

## Imported Source
- Raw source: `16_knowledge/external_collateral/ipos_claude_skills_2026-05-17/raw/alert-system/SKILL.md`
- Source repo: `/Users/desmondearly/Library/CloudStorage/OneDrive-Personal/IPOS/IPOS`
- Raw SHA-256: `2ccd27c67df213bcefd2a0ef31b760155951b729109d33342d45bd6018371322`

## Activation Rule
Use this skill when the request matches the imported trigger language, the IPOS/paratransit dashboard domain, or the user asks for the named capability: `alert-system`.

## Operating Contract
- Apply the imported patterns from the raw `SKILL.md` before inventing new dashboard, KPI, SharePoint, export, testing, deployment, or UI patterns.
- Keep outputs implementation-ready: include files, schemas, components, formulas, tests, commands, or validation gates when relevant.
- Preserve auditability for KPI, contract, paratransit, SharePoint, and data pipeline outputs.
- If the request is outside the dashboard/IPOS domain, route through the trigger router first and use this skill only as a supporting branch.

## Required Output Shape
- Situation or objective.
- Applicable imported patterns.
- Implementation steps or artifact structure.
- Validation checks.
- Risks or assumptions.

## Source Detail
Read the raw source file above for the full imported body and examples when this skill fires.
