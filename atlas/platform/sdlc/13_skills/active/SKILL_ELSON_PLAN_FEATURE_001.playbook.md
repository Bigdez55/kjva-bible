# Feature Planning Protocol Playbook

## Purpose
Plan a new feature — decompose requirements, identify impacted files, define API contracts, assign agents, and produce a phased implementation plan. Use when the user wants to plan a feature, design a new capability, or asks how should we build X.

## Imported Source
- Collection: `elson_claude_skills_2026-05-17`
- Selected raw source: `16_knowledge/external_collateral/elson_claude_skills_2026-05-17/raw/trading_bot_elson_tb2/plan-feature/SKILL.md`
- Raw SHA-256: `17f21a43ce5454a7024691627f5c90056e0ae9945d46b513b5e1d528dfc119d7`
- Source model hint: `claude-opus-4-6`

## Activation Rule
Use this skill only when the request is in the Elson / trading bot / portfolio automation domain and matches `plan-feature`, `plan feature`, or the source skill title.

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
