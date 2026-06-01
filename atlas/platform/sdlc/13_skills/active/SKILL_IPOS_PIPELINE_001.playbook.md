# IPOS Pipeline Playbook

## Purpose
Data pipeline design for paratransit dashboards: ETL patterns, SharePoint List schemas, Power Automate flows, Excel parsing with xlsx/exceljs, data validation, and MTD running totals. Covers Trapeze report ingestion, contract-aligned KPI calculations, IsComplete flags, and error handling in automated data flows. Trigger on: "data pipeline", "Power Automate", "Excel processing", "SharePoint list schema", "ETD calculations", "MTD", "Trapeze".

## Imported Source
- Raw source: `16_knowledge/external_collateral/ipos_claude_skills_2026-05-17/raw/pipeline/SKILL.md`
- Source repo: `/Users/desmondearly/Library/CloudStorage/OneDrive-Personal/IPOS/IPOS`
- Raw SHA-256: `db1e518cc0b1f29034a825c543fa4cdf444b12a80af802451b6d7738afde5742`

## Activation Rule
Use this skill when the request matches the imported trigger language, the IPOS/paratransit dashboard domain, or the user asks for the named capability: `pipeline`.

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
