# Autonomous Trading Bot Status Playbook

## Purpose
Check the autonomous trading bot status — running state, active strategies, recent signals, P&L, and circuit breaker state. Use when the user asks about the trading bot, is the bot running, bot status, or trading activity.

## Imported Source
- Collection: `elson_claude_skills_2026-05-17`
- Selected raw source: `16_knowledge/external_collateral/elson_claude_skills_2026-05-17/raw/trading_bot_elson_tb2/bot-status/SKILL.md`
- Raw SHA-256: `d71cfa3bc84e3d226803ec41294bc1f76ff8fc1903918d794b1f7c4b6b08fabe`
- Source model hint: `claude-sonnet-4-6`

## Activation Rule
Use this skill only when the request is in the Elson / trading bot / portfolio automation domain and matches `bot-status`, `bot status`, or the source skill title.

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
