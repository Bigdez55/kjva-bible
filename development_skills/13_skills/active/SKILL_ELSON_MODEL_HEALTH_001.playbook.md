# AI Model Health Check — elson-finance-14b Playbook

## Purpose
Check vLLM and elson-finance-14b model health — VM status, model loaded, inference latency, EFT agent configs, and fine-tuning readiness. Use when the user asks about the AI model, is vLLM running, model status, or EFT health.

## Imported Source
- Collection: `elson_claude_skills_2026-05-17`
- Selected raw source: `16_knowledge/external_collateral/elson_claude_skills_2026-05-17/raw/trading_bot_elson_tb2/model-health/SKILL.md`
- Raw SHA-256: `88e5595382918fda6d64c2fced29cf060c5bef9e539856245791feb7de85dd77`
- Source model hint: `claude-sonnet-4-6`

## Activation Rule
Use this skill only when the request is in the Elson / trading bot / portfolio automation domain and matches `model-health`, `model health`, or the source skill title.

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
