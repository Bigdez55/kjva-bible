# Sprint Retrospective Playbook

## Purpose
Run a sprint retrospective — compare completed vs planned work, measure quality gate outcomes, identify blockers, and propose next sprint priorities. Use when the user says sprint review, retrospective, end of sprint, or what did we accomplish.

## Imported Source
- Collection: `elson_claude_skills_2026-05-17`
- Selected raw source: `16_knowledge/external_collateral/elson_claude_skills_2026-05-17/raw/trading_bot_elson_tb2/sprint-review/SKILL.md`
- Raw SHA-256: `a00bf3ec2d87ca1089bb5f142cdb06d03ec8649608b178cbd4898a0afc1a15c4`
- Source model hint: `claude-opus-4-6`

## Activation Rule
Use this skill only when the request is in the Elson / trading bot / portfolio automation domain and matches `sprint-review`, `sprint review`, or the source skill title.

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
