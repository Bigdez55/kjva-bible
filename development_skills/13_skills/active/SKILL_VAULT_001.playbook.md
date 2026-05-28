# vault

<!-- Source: migrated from ~/.claude/skills/vault/SKILL.md on 2026-05-26 -->
<!-- Runtime alias: vault -->

**Summary.** Enterprise deployment patterns for SharePoint and Microsoft 365: SPFx tenant-wide deployment, M365 CLI commands, App Catalog management, SharePoint permissions and service principals, and GitHub Actions pipelines for automated SPFx deployment. Trigger on: "enterprise deployment", "SPFx deploy", "App Catalog", "M365 CLI", "tenant-wide", "sppkg", "SharePoint deployment".

# Enterprise SPFx Deployment Patterns

## Core Expertise
- SPFx solution packaging: gulp bundle, package-solution, .sppkg generation
- Tenant-wide App Catalog deployment via M365 CLI and PnP PowerShell
- Site-level vs tenant-level deployment decisions
- SharePoint permissions model: Site Owner, Member, Visitor + custom groups
- Service principal setup for automated deployments (app registration)
- GitHub Actions workflow for automated SPFx CI/CD

## When to Use
- Deploying SPFx web part or extension to SharePoint tenant
- Setting up App Catalog (tenant or site collection level)
- Configuring GitHub Actions to automate SPFx build and deploy
- Managing who can access or modify the dashboard in SharePoint
- Troubleshooting deployment failures or permission errors

## Key Patterns

1. **SPFx Build and Package**
```bash
# Production build and package
gulp clean
gulp bundle --ship
gulp package-solution --ship
# Output: sharepoint/solution/*.sppkg
```

2. **M365 CLI Tenant-Wide Deployment**
```bash
# Authenticate (interactive or app-only)
m365 login --authType certificate \
  --certificateFile ./certs/sp-cert.pfx \
  --password "$CERT_PASSWORD" \
  --appId "$APP_ID" \
  --tenant "$TENANT_ID"

# Add to App Catalog and deploy tenant-wide
m365 spo app add \
  --filePath sharepoint/solution/kpi-dashboard.sppkg \
  --appCatalogUrl "https://TENANT.sharepoint.com/sites/appcatalog" \
  --overwrite

m365 spo app deploy \
  --name kpi-dashboard.sppkg \
  --appCatalogUrl "https://TENANT.sharepoint.com/sites/appcatalog" \
  --skipFeatureDeployment  # tenant-wide
```

3. **GitHub Actions SPFx Deploy Workflow**
```yaml
name: Deploy SPFx to SharePoint
on:
  push:
    branches: [main]
jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with: { node-version: '18' }
      - run: npm ci
      - run: gulp bundle --ship && gulp package-solution --ship
      - name: Deploy to App Catalog
        run: |
          npm install -g @pnp/cli-microsoft365
          m365 login --authType certificate \
            --certificateFile <(echo "${{ secrets.SP_CERT }}" | base64 -d) \
            --appId ${{ secrets.APP_ID }} --tenant ${{ secrets.TENANT_ID }}
          m365 spo app add --filePath sharepoint/solution/*.sppkg \
            --appCatalogUrl ${{ secrets.APP_CATALOG_URL }} --overwrite
          m365 spo app deploy --name kpi-dashboard.sppkg \
            --appCatalogUrl ${{ secrets.APP_CATALOG_URL }} --skipFeatureDeployment
```

4. **Required GitHub Secrets**
```
SP_CERT          # Base64-encoded .pfx certificate
APP_ID           # Azure App Registration Client ID
TENANT_ID        # Azure AD Tenant ID
APP_CATALOG_URL  # https://TENANT.sharepoint.com/sites/appcatalog
```

5. **App Registration Permissions for Deployment**
```
SharePoint > Sites.FullControl.All (Application) — for App Catalog write
SharePoint > TermStore.ReadWrite.All               — if using taxonomy
Microsoft Graph > Sites.Read.All                   — for reading site data
```

6. **Site Collection App Catalog (Non-Tenant-Wide)**
```bash
# Enable site collection app catalog
m365 spo site appcatalog add --siteUrl "https://TENANT.sharepoint.com/sites/operations"

# Deploy to site-level catalog only
m365 spo app add \
  --filePath sharepoint/solution/kpi-dashboard.sppkg \
  --appCatalogScope sitecollection \
  --appCatalogUrl "https://TENANT.sharepoint.com/sites/operations"
```

## Standards
- Always build with --ship flag for production; debug builds expose source maps
- Use certificate-based auth (not username/password) for CI/CD pipelines
- Store all secrets in GitHub Secrets or Azure Key Vault; never in workflow YAML
- Test deployment in a non-production site collection before tenant-wide deploy
- --skipFeatureDeployment enables tenant-wide availability without per-site activation
- Rollback strategy: keep previous .sppkg artifact; redeploy previous version from GitHub release
