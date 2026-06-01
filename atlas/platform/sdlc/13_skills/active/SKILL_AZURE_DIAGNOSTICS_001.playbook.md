# azure diagnostics

<!-- Imported from /Users/desmondearly/.agents/skills/azure-diagnostics/SKILL.md on 2026-05-27. -->
<!-- Full source directory archived at platform/sdlc/16_knowledge/external_collateral/local_runtime_skills_2026-05-27/agents/azure-diagnostics. -->
<!-- Runtime alias: azure-diagnostics; canonical id: SKILL_AZURE_DIAGNOSTICS_001. -->
**Summary.** Debug and troubleshoot production issues on Azure. Covers Container Apps diagnostics, log analysis with KQL, health checks, and common issue resolution for image pulls, cold starts, and health probes. USE FOR: debug production issues, troubleshoot container apps, analyze logs with KQL, fix image pull failures, resolve cold start issues, investigate health probe failures, check resource health, view application logs, find root cause of errors DO NOT USE FOR: deploying applications (use azure-deploy), creating new resources (use azure-prepare), setting up monitoring (use azure-observability), cost optimization (use azure-cost-optimization)

Relative links from the source skill body were rewritten to the archived source directory when possible.

# Azure Diagnostics

> **AUTHORITATIVE GUIDANCE - MANDATORY COMPLIANCE**
>
> This document is the **official source** for debugging and troubleshooting Azure production issues. Follow these instructions to diagnose and resolve common Azure service problems systematically.

## Triggers

Activate this skill when user wants to:
- Debug or troubleshoot production issues
- Diagnose errors in Azure services
- Analyze application logs or metrics
- Fix image pull, cold start, or health probe issues
- Investigate why Azure resources are failing
- Find root cause of application errors

## Rules

1. Start with systematic diagnosis flow
2. Use AppLens (MCP) for AI-powered diagnostics when available
3. Check resource health before deep-diving into logs
4. Select appropriate troubleshooting guide based on service type
5. Document findings and attempted remediation steps

---

## Quick Diagnosis Flow

1. **Identify symptoms** - What's failing?
2. **Check resource health** - Is Azure healthy?
3. **Review logs** - What do logs show?
4. **Analyze metrics** - Performance patterns?
5. **Investigate recent changes** - What changed?

---

## Troubleshooting Guides by Service

| Service | Common Issues | Reference |
|---------|---------------|-----------|
| **Container Apps** | Image pull failures, cold starts, health probes, port mismatches | [container-apps/](../../16_knowledge/external_collateral/local_runtime_skills_2026-05-27/agents/azure-diagnostics/references/container-apps/README.md) |

---

## Quick Reference

### Common Diagnostic Commands

```bash
# Check resource health
az resource show --ids RESOURCE_ID

# View activity log
az monitor activity-log list -g RG --max-events 20

# Container Apps logs
az containerapp logs show --name APP -g RG --follow
```

### AppLens (MCP Tools)

For AI-powered diagnostics, use:
```
mcp_azure_mcp_applens
  intent: "diagnose issues with <resource-name>"
  command: "diagnose"
  parameters:
    resourceId: "<resource-id>"

Provides:
- Automated issue detection
- Root cause analysis
- Remediation recommendations
```

### Azure Monitor (MCP Tools)

For querying logs and metrics:
```
mcp_azure_mcp_monitor
  intent: "query logs for <resource-name>"
  command: "logs_query"
  parameters:
    workspaceId: "<workspace-id>"
    query: "<KQL-query>"
```

See [kql-queries.md](../../16_knowledge/external_collateral/local_runtime_skills_2026-05-27/agents/azure-diagnostics/references/kql-queries.md) for common diagnostic queries.

---

## Check Azure Resource Health

### Using MCP

```
mcp_azure_mcp_resourcehealth
  intent: "check health status of <resource-name>"
  command: "get"
  parameters:
    resourceId: "<resource-id>"
```

### Using CLI

```bash
# Check specific resource health
az resource show --ids RESOURCE_ID

# Check recent activity
az monitor activity-log list -g RG --max-events 20
```

---

## References

- [KQL Query Library](../../16_knowledge/external_collateral/local_runtime_skills_2026-05-27/agents/azure-diagnostics/references/kql-queries.md)
- [Azure Resource Graph Queries](../../16_knowledge/external_collateral/local_runtime_skills_2026-05-27/agents/azure-diagnostics/references/azure-resource-graph.md)
