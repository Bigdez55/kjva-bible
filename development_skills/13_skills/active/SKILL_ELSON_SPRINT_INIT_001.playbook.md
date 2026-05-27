# Sprint Initialization Protocol Playbook

## Purpose
Initialize a new development sprint — audit backlog, define goals, assign agent responsibilities, and create a phased execution plan. Use when the user says start sprint, new sprint, kick off sprint, or plan next phase.

## Imported Source
- Collection: `elson_claude_skills_2026-05-17`
- Selected raw source: `16_knowledge/external_collateral/elson_claude_skills_2026-05-17/raw/trading_bot_elson_tb2/sprint-init/SKILL.md`
- Raw SHA-256: `458e581d2d3ce8a22c4b705b0f06950b5b9fcd729e20d1079d3fdbba51a5b17d`
- Source model hint: `claude-opus-4-6`

## Activation Rule
Use this skill only when the request is in the Elson / trading bot / portfolio automation domain and matches `sprint-init`, `sprint init`, or the source skill title.

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
