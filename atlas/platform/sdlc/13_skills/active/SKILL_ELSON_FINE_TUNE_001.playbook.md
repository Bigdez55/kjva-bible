# Fine-Tuning Pipeline — elson-finance-14b (DoRA) Playbook

## Purpose
Assess fine-tuning readiness, prepare training data, and trigger the DoRA fine-tuning pipeline for elson-finance-14b. Use when the user asks about fine-tuning, model retraining, improving AI accuracy, or updating the model.

## Imported Source
- Collection: `elson_claude_skills_2026-05-17`
- Selected raw source: `16_knowledge/external_collateral/elson_claude_skills_2026-05-17/raw/trading_bot_elson_tb2/fine-tune/SKILL.md`
- Raw SHA-256: `6be0a662cd7292caccf2c48790ec6f9a314a4c5efb8a9397ca7c36d4eadeccc9`
- Source model hint: `claude-opus-4-6`

## Activation Rule
Use this skill only when the request is in the Elson / trading bot / portfolio automation domain and matches `fine-tune`, `fine tune`, or the source skill title.

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
