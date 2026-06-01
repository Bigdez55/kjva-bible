# Cloud Run Emergency Rollback Playbook

## Purpose
Roll back Cloud Run to the previous stable revision. Use when the user says rollback, revert production, undo deploy, or the health check is failing after a deploy.

## Imported Source
- Collection: `elson_claude_skills_2026-05-17`
- Selected raw source: `16_knowledge/external_collateral/elson_claude_skills_2026-05-17/raw/trading_bot_elson_tb2/rollback/SKILL.md`
- Raw SHA-256: `1bd67cb00bb96c6081a34895474d8ccf2548f9c496c58642f36160b448c0f22c`
- Source model hint: `claude-sonnet-4-6`

## Activation Rule
Use this skill only when the request is in the Elson / trading bot / portfolio automation domain and matches `rollback`, `rollback`, or the source skill title.

## Operating Contract
- Read the preserved raw `SKILL.md` before issuing Elson-specific commands, deployment steps, production diagnostics, model actions, or trading-bot recommendations.
- Treat raw commands as source guidance, not automatic authorization to run production operations.
- Do not repeat preserved secrets or credentials in responses.
- Require current evidence before claiming bot status, Cloud Run health, vLLM state, migration state, or deployment outcome.

## Required Output Shape
- Objective and active Elson context.
- Applicable source skill rules or command family.
- Action sequence or analysis steps.
- Validation gates and evidence requirements.
- Risk, blocker, or escalation condition.
