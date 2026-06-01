# azure rbac

<!-- Imported from /Users/desmondearly/.agents/skills/azure-rbac/SKILL.md on 2026-05-27. -->
<!-- Full source directory archived at platform/sdlc/16_knowledge/external_collateral/local_runtime_skills_2026-05-27/agents/azure-rbac. -->
<!-- Runtime alias: azure-rbac; canonical id: SKILL_AZURE_RBAC_001. -->
**Summary.** Helps users find the right Azure RBAC role for an identity with least privilege access, then generate CLI commands and Bicep code to assign it. USE FOR: "what role should I assign", "least privilege role", "RBAC role for", "role to read blobs", "role for managed identity", "custom role definition", "assign role to identity". DO NOT USE FOR: creating or configuring managed identities, or general Azure security hardening; those are out of scope for this role-selection skill.

Relative links from the source skill body were rewritten to the archived source directory when possible.

Use the 'azure__documentation' tool to find the minimal role definition that matches the desired permissions the user wants to assign to an identity. If no built-in role matches the desired permissions, use the 'azure__extension_cli_generate' tool to create a custom role definition with the desired permissions. Then use the 'azure__extension_cli_generate' tool to generate the CLI commands needed to assign that role to the identity. Finally, use the 'azure__bicepschema' and 'azure__get_azure_bestpractices' tools to provide a Bicep code snippet for adding the role assignment.
