# Production Logs — Cloud Run Playbook

## Purpose
View production Cloud Run logs for the Elson backend. Use when the user asks to see logs, check errors, what happened, recent crashes, or view production output.

## Imported Source
- Collection: `elson_claude_skills_2026-05-17`
- Selected raw source: `16_knowledge/external_collateral/elson_claude_skills_2026-05-17/raw/trading_bot_elson_tb2/logs/SKILL.md`
- Raw SHA-256: `9462d82855ac95fc2ba396c30bc0fd442e84142495a9de1142cc314391edc5a3`
- Source model hint: `claude-sonnet-4-6`

## Activation Rule
Use this skill only when the request is in the Elson / trading bot / portfolio automation domain and matches `logs`, `logs`, or the source skill title.

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
