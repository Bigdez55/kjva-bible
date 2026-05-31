# Trading Performance Report Playbook

## Purpose
Generate a trading performance report — P&L, win rate, Sharpe ratio, strategy breakdown, and progress toward $500/day goal. Use when the user asks about performance, how is the bot doing, P&L report, or trading results.

## Imported Source
- Collection: `elson_claude_skills_2026-05-17`
- Selected raw source: `16_knowledge/external_collateral/elson_claude_skills_2026-05-17/raw/trading_bot_elson_tb2/perf-report/SKILL.md`
- Raw SHA-256: `f51a7842f23ddb80bcd056e7cf9696bedfa1123471f5f132e40835279e875d67`
- Source model hint: `claude-opus-4-6`

## Activation Rule
Use this skill only when the request is in the Elson / trading bot / portfolio automation domain and matches `perf-report`, `perf report`, or the source skill title.

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
