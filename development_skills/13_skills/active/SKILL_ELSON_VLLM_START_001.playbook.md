# Start vLLM VM — elson-dvora-training-l4-2 Playbook

## Purpose
Start the vLLM VM (elson-dvora-training-l4-2) for AI trading. Use when the user says start the model, start vLLM, power on the AI, or before market open on Monday.

## Imported Source
- Collection: `elson_claude_skills_2026-05-17`
- Selected raw source: `16_knowledge/external_collateral/elson_claude_skills_2026-05-17/raw/trading_bot_elson_tb2/vllm-start/SKILL.md`
- Raw SHA-256: `4669ca330f9595127f2c9c7501b8cf50d384ec295bbc766863094f8bf16eac85`
- Source model hint: `claude-sonnet-4-6`

## Activation Rule
Use this skill only when the request is in the Elson / trading bot / portfolio automation domain and matches `vllm-start`, `vllm start`, or the source skill title.

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
