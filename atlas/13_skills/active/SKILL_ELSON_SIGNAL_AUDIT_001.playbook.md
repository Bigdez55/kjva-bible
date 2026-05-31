# Signal Gate Audit — Elson Trading Bot Playbook

## Purpose
Audit the autonomous trading signal gate — AI vs rule-based accuracy, confidence calibration, gate rejection rates, and strategy performance. Use when the user asks about signal quality, is the AI beating rules, signal gate tuning, or trading accuracy.

## Imported Source
- Collection: `elson_claude_skills_2026-05-17`
- Selected raw source: `16_knowledge/external_collateral/elson_claude_skills_2026-05-17/raw/trading_bot_elson_tb2/signal-audit/SKILL.md`
- Raw SHA-256: `db2c026a7dd362d509720da90a4c555c4d59fa5beebad1aaa7e2793972eb12b8`
- Source model hint: `claude-opus-4-6`

## Activation Rule
Use this skill only when the request is in the Elson / trading bot / portfolio automation domain and matches `signal-audit`, `signal audit`, or the source skill title.

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
