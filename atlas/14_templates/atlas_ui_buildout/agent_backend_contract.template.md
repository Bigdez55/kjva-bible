# ATLAS Agent Backend Contract

## Purpose
Define how coding agents access tenant repo context, skills, resources, proof gates, and repo-change ingestion.

## Endpoints
| Method | Path | Purpose | Required Scope |
| --- | --- | --- | --- |
| GET | `/api/tenant` | Read tenant and repo connector state | tenant |
| GET | `/api/skills` | Read skill/resource and proof-gate surface | tenant |
| GET | `/api/agent-context` | Bootstrap coding-agent context | tenant + repo corpus |
| POST | `/api/ingest/repo-event` | Submit commit, diff, validation, sync, or agent-report event | tenant + repo |

## Repo Event Payload
```json
{
  "tenantId": "desmond-personal-poc",
  "repoName": "ATLAS",
  "eventType": "commit",
  "commitSha": "abc123",
  "branch": "main",
  "summary": "Describe the change",
  "changedFiles": ["path/to/file.ts"],
  "evidence": ["test output or proof path"]
}
```

## Propagation Rule
Repo events are accepted into a tenant-scoped ingestion ledger first. Only then should they update Atlas Graph Engine, Atlas Knowledge Vault, Proof Matrix, and agent context packets.
