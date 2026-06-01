# IPOS Data Pipeline Playbook

## Purpose
KPI data ingestion pipelines: Bronze/Silver/Gold medallion architecture, Trapeze CSV/Excel parsing, fuzzy column mapping, SUM-based MTD aggregation (never AVERAGE for PPH), SharePoint List writes via PnPjs, DuckDB-WASM in-browser SQL, data quality scoring, and audit trail logging. Trigger on: 'data pipeline', 'ETL', 'Trapeze', 'CSV parsing', 'MTD calculation', 'running total', 'data ingestion', 'medallion architecture'.

## Imported Source
- Raw source: `16_knowledge/external_collateral/ipos_claude_skills_2026-05-17/raw/data-pipeline/SKILL.md`
- Source repo: `/Users/desmondearly/Library/CloudStorage/OneDrive-Personal/IPOS/IPOS`
- Raw SHA-256: `624168f2a9b82ffaf9e2e0529297f50737379f70fe8e57b35bab25afd1de4888`

## Activation Rule
Use this skill when the request matches the imported trigger language, the IPOS/paratransit dashboard domain, or the user asks for the named capability: `data-pipeline`.

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
