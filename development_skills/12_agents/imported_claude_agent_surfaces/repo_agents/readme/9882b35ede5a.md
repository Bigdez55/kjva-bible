# Agent Deployment Guide

**Agents in this directory:** 35  
**Updated:** April 2026

---

## What These Are

Each `.md` file in this directory is a Claude Code subagent definition. When Claude Code encounters a task matching an agent's description, it spawns that agent as a subprocess with its own context, tools, and persona.

Agents are automatically discovered by Claude Code when this directory is present at `.claude/agents/`. No additional registration is needed.

---

## Agent File Format

Every agent file uses this frontmatter:

```yaml
---
name: agent-name
description: "Trigger description — when to activate this agent"
model: opus | sonnet | haiku
memory: project | user | none
tools: Read, Write, Edit, Glob, Grep, Bash, Agent, WebSearch, WebFetch
color: "#HEXCODE"
---

# Agent identity and detailed prompt
```

The `description` field is the most critical — Claude Code reads it to decide when to spawn the agent.

---

## Adding a New Agent

1. Create a new `.md` file in `.claude/agents/` with the naming convention `<domain>-<role>-agent.md` or `<codename>.md`
2. Add the YAML frontmatter with a clear, specific `description` trigger
3. Write the agent's identity, capabilities, activation conditions, and output format
4. Update `docs/AGENTS.md` with the new agent in the appropriate category
5. Commit: `git add .claude/agents/<new-agent>.md docs/AGENTS.md`

---

## Agent Memory

Some agents persist cross-session memory in `.claude/agents/memory/<agent-name>/`. These directories store facts the agent has learned about the project that it should recall in future sessions.

Shared memory for all agents lives in `.claude/agent-memory/_shared/`:

| File | Content |
|------|---------|
| `agent-usage-policy.md` | Governing directive: consult all agents before executing |
| `ops-dash-lineage.md` | ops-dash.json data lineage and parser chain |
| `testing-policy.md` | Test coverage and validation requirements |

---

## Agent Index

For the full registry with descriptions, triggers, and selection guide, see [docs/AGENTS.md](../../docs/AGENTS.md).

Quick reference:

| Slug | Role |
|------|------|
| `master-orchestrator` | Top-level cross-stream coordination |
| `the-architect` | System design and architecture |
| `apex-coordinator` | Parallel workstream collision prevention |
| `apex-react-agent` | React 18 CRA engineering (PRISM) |
| `apex-design-agent` | Design systems (PRESTIGE) |
| `apex-svelte-agent` | Tailwind CSS (VELOCITY) |
| `apex-accessibility-agent` | WCAG 2.1 AA (BEACON) |
| `apex-performance-agent` | CRA performance (TURBO) |
| `apex-realtime-agent` | Static JSON polling (PULSE) |
| `apex-d3-agent` | D3.js visualizations (CANVAS) |
| `apex-vue-agent` | ApexCharts/Vue (MOSAIC) |
| `apex-angular-agent` | SPFx TypeScript (FORTRESS) |
| `apex-enterprise-agent` | SPFx enterprise deployment (VAULT) |
| `apex-python-agent` | ETL pipeline engineering (JUPYTER) |
| `data-infra-engineer` | ETL implementation and debug |
| `data-infrastructure-lead` | Pipeline architecture |
| `apex-dataops-agent` | Data operations (PIPELINE) |
| `excel-processor-agent` | Excel/CSV ingestion |
| `intelligence-lead` | Analytics, KPI, forecasting |
| `intelligence-lead-v2` | AI/ML/LLM solutions |
| `kpi-analyst-agent` | KPI contract compliance analysis |
| `alpha-pulse-engine` | Anomaly detection, early warnings |
| `apex-ai-agent` | Claude API, ML integration |
| `apex-quant-architect` | Quantitative optimization |
| `guardian-sniper` | Contract compliance validation |
| `event-horizon-agent` | Incident cascade → LD analysis |
| `operations-integrity-auditor` | Data integrity audit |
| `reliability-security-sentinel` | Security and reliability |
| `dashboard-deployer-agent` | GitHub Pages + SPFx deployment |
| `product-experience-engineer` | UX and interaction design |
| `apex-testing-agent` | Testing (SENTINEL) |
| `vanguard-disruptive-alchemist` | Workflow automation |
| `vanguard-disruptor` | Challenge assumptions |
| `vanguard-innovation-scout` | Innovation scouting |

---

## Governing Policy

From `.claude/agent-memory/_shared/agent-usage-policy.md`:

> **For every task, consult all agents and synthesize their guidance before executing work or responding.**

This means that before implementing any significant change, Claude Code (or the operator) should identify which agents are relevant to the task and incorporate their domain knowledge.

---

## Model Assignment

| Model | Agents Assigned |
|-------|----------------|
| `opus` | apex-react-agent, the-architect, master-orchestrator, guardian-sniper, kpi-analyst-agent, intelligence-lead, event-horizon-agent |
| `sonnet` | Most other agents (default for speed + quality balance) |
| `haiku` | Lightweight utility agents (realtime polling, simple lookups) |

Adjust model assignments in each agent's frontmatter as needed. Opus is used for agents that handle complex multi-step reasoning or financial/compliance work.
