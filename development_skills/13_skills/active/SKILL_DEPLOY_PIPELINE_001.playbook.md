# deploy-pipeline

<!-- Source: migrated from ~/.claude/skills/deploy-pipeline/SKILL.md on 2026-05-26 -->
<!-- Runtime alias: deploy-pipeline -->

**Summary.** CI/CD deployment pipelines for KPI dashboards: GitHub Actions workflows for GitHub Pages and SPFx (gulp bundle, package-solution, M365 CLI deploy), Vercel/Netlify/AWS deployment configs, GitHub Secrets management, branch-based deploy rules (main → production, feature → preview), artifact versioning and rollback, Node.js caching, health checks, environment-specific configs, Slack/Teams deployment notifications, Docker containerization, and blue-green deployment strategies. Trigger on: 'CI/CD', 'deploy pipeline', 'GitHub Actions', 'sppkg', 'automated deploy', 'GitHub Pages', 'Vercel', 'Netlify', 'Docker', 'rollback', 'deployment notification'.

# CI/CD Deployment Pipelines

## Purpose & Scope

Sets up complete CI/CD pipelines for KPI dashboard deployment across multiple platforms. Covers GitHub Actions workflows, SPFx packaging, static site deployment (GitHub Pages, Vercel, Netlify), Docker containerization, environment management, rollback strategies, health checks, and deployment notifications.

## When to Trigger

- Setting up automated deployment for a new dashboard project
- GitHub Actions workflow failing on SPFx package or deploy step
- Configuring which branches trigger deployment to which environments
- Adding secrets to GitHub for M365 CLI authentication
- Setting up GitHub Pages, Vercel, or Netlify deployment
- Need rollback strategy after failed deployment
- Configuring deployment notifications to Slack/Teams

## When NOT to Trigger

- Test configuration → **test-harness** skill
- Performance optimization → **perf-profiler** skill
- Auth setup → **auth-guard** skill
- Full deployment architecture → **Dashboard Deployer** agent

## Deployment Environments

| Environment | Branch | URL | Purpose |
|-------------|--------|-----|---------|
| Production | `main` | `dashboard.example.com` | Live dashboard |
| Staging | `staging` | `staging.dashboard.example.com` | Pre-production validation |
| Preview | `feature/*` | Auto-generated | PR review |
| Development | `develop` | `dev.dashboard.example.com` | Integration testing |

## GitHub Pages Static Dashboard Deploy

```yaml
# .github/workflows/deploy-pages.yml
name: Deploy Dashboard to GitHub Pages
on:
  push:
    branches: [main]
    paths:
      - 'src/**'
      - 'data/**'
      - '*.html'
      - '*.json'
      - 'package.json'
  workflow_dispatch:
    inputs:
      reason:
        description: 'Reason for manual deploy'
        required: false
        default: 'Manual trigger'

permissions:
  contents: read
  pages: write
  id-token: write

concurrency:
  group: 'pages'
  cancel-in-progress: false

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Setup Node.js
        uses: actions/setup-node@v4
        with:
          node-version: '20'
          cache: 'npm'
          cache-dependency-path: package-lock.json

      - name: Install dependencies
        run: npm ci

      - name: Process Excel data
        run: npm run process-excel

      - name: Generate AI insights
        run: npm run update-dashboard
        env:
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}

      - name: Build dashboard
        run: npm run build

      - name: Upload artifact
        uses: actions/upload-pages-artifact@v3
        with:
          path: ./dist

  deploy:
    needs: build
    runs-on: ubuntu-latest
    environment:
      name: github-pages
      url: ${{ steps.deployment.outputs.page_url }}
    steps:
      - name: Deploy to GitHub Pages
        id: deployment
        uses: actions/deploy-pages@v4

      - name: Notify deployment
        if: always()
        uses: slackapi/slack-github-action@v1.25.0
        with:
          payload: |
            {
              "text": "${{ job.status == 'success' && '✅' || '❌' }} Dashboard deployed to GitHub Pages\nCommit: ${{ github.sha }}\nBy: ${{ github.actor }}\nStatus: ${{ job.status }}"
            }
        env:
          SLACK_WEBHOOK_URL: ${{ secrets.SLACK_WEBHOOK_URL }}
```

## SPFx Full Deploy Workflow

```yaml
# .github/workflows/deploy-spfx.yml
name: SPFx Build and Deploy
on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Setup Node.js
        uses: actions/setup-node@v4
        with:
          node-version: '18'
          cache: 'npm'

      - name: Install dependencies
        run: npm ci

      - name: Run tests
        run: npm test -- --ci --coverage

      - name: Build SPFx bundle
        run: gulp bundle --ship

      - name: Package SPFx solution
        run: gulp package-solution --ship

      - name: Upload sppkg artifact
        uses: actions/upload-artifact@v4
        with:
          name: sppkg-${{ github.sha }}
          path: sharepoint/solution/*.sppkg
          retention-days: 30

  deploy-to-sharepoint:
    needs: build
    if: github.ref == 'refs/heads/main' && github.event_name == 'push'
    runs-on: ubuntu-latest
    environment: production
    steps:
      - name: Download sppkg artifact
        uses: actions/download-artifact@v4
        with:
          name: sppkg-${{ github.sha }}
          path: ./sppkg

      - name: Install M365 CLI
        run: npm install -g @pnp/cli-microsoft365

      - name: Login to M365
        run: |
          m365 login --authType certificate \
            --certificateFile <(echo "${{ secrets.SP_CERT_B64 }}" | base64 -d) \
            --appId "${{ secrets.APP_ID }}" \
            --tenant "${{ secrets.TENANT_ID }}"

      - name: Upload to App Catalog
        run: |
          m365 spo app add \
            --filePath ./sppkg/*.sppkg \
            --appCatalogUrl "${{ secrets.APP_CATALOG_URL }}" \
            --overwrite

      - name: Deploy to tenant
        run: |
          m365 spo app deploy \
            --name kpi-dashboard.sppkg \
            --appCatalogUrl "${{ secrets.APP_CATALOG_URL }}" \
            --skipFeatureDeployment

      - name: Health check
        run: |
          sleep 30
          STATUS=$(curl -s -o /dev/null -w "%{http_code}" "${{ secrets.DASHBOARD_URL }}")
          if [ "$STATUS" != "200" ]; then
            echo "Health check failed with status $STATUS"
            exit 1
          fi
          echo "Dashboard is healthy (HTTP $STATUS)"
```

## Vercel Deployment

```json
// vercel.json
{
  "buildCommand": "npm run build",
  "outputDirectory": "dist",
  "framework": null,
  "rewrites": [
    { "source": "/api/(.*)", "destination": "/api/$1" }
  ],
  "headers": [
    {
      "source": "/api/(.*)",
      "headers": [
        { "key": "Cache-Control", "value": "public, max-age=300, stale-while-revalidate=60" }
      ]
    },
    {
      "source": "/(.*)",
      "headers": [
        { "key": "X-Content-Type-Options", "value": "nosniff" },
        { "key": "X-Frame-Options", "value": "DENY" },
        { "key": "Strict-Transport-Security", "value": "max-age=31536000; includeSubDomains" }
      ]
    }
  ]
}
```

```yaml
# .github/workflows/deploy-vercel.yml
name: Deploy to Vercel
on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with: { node-version: '20', cache: 'npm' }
      - run: npm ci
      - run: npm test -- --ci

      - name: Deploy to Vercel (Preview)
        if: github.event_name == 'pull_request'
        run: npx vercel --token=${{ secrets.VERCEL_TOKEN }}
        env:
          VERCEL_ORG_ID: ${{ secrets.VERCEL_ORG_ID }}
          VERCEL_PROJECT_ID: ${{ secrets.VERCEL_PROJECT_ID }}

      - name: Deploy to Vercel (Production)
        if: github.ref == 'refs/heads/main'
        run: npx vercel --prod --token=${{ secrets.VERCEL_TOKEN }}
        env:
          VERCEL_ORG_ID: ${{ secrets.VERCEL_ORG_ID }}
          VERCEL_PROJECT_ID: ${{ secrets.VERCEL_PROJECT_ID }}
```

## Netlify Deployment

```toml
# netlify.toml
[build]
  command = "npm run build"
  publish = "dist"

[build.environment]
  NODE_VERSION = "20"

[[headers]]
  for = "/api/*"
  [headers.values]
    Cache-Control = "public, max-age=300, stale-while-revalidate=60"

[[headers]]
  for = "/*"
  [headers.values]
    X-Content-Type-Options = "nosniff"
    X-Frame-Options = "DENY"

[[redirects]]
  from = "/*"
  to = "/index.html"
  status = 200
  conditions = {Role = ["admin"]}

[context.deploy-preview]
  command = "npm run build"

[context.branch-deploy]
  command = "npm run build"
```

## Docker Containerization

```dockerfile
# Dockerfile
FROM node:20-alpine AS builder
WORKDIR /app
COPY package*.json ./
RUN npm ci --production=false
COPY . .
RUN npm run build

FROM nginx:alpine AS production
COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

HEALTHCHECK --interval=30s --timeout=3s --retries=3 \
  CMD wget --no-verbose --tries=1 --spider http://localhost/ || exit 1

EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
```

```nginx
# nginx.conf
server {
    listen 80;
    root /usr/share/nginx/html;
    index index.html;

    # Security headers
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-Frame-Options "DENY" always;
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;

    # Cache static assets
    location ~* \.(js|css|png|jpg|svg|ico|woff2)$ {
        expires 1y;
        add_header Cache-Control "public, immutable";
    }

    # API JSON with short cache
    location /api/ {
        expires 5m;
        add_header Cache-Control "public, max-age=300, stale-while-revalidate=60";
    }

    # SPA fallback
    location / {
        try_files $uri $uri/ /index.html;
    }

    # Gzip compression
    gzip on;
    gzip_types text/plain text/css application/json application/javascript text/xml;
    gzip_min_length 256;
}
```

```yaml
# .github/workflows/deploy-docker.yml
name: Build and Push Docker Image
on:
  push:
    branches: [main]
    tags: ['v*']

jobs:
  build-and-push:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Set up Docker Buildx
        uses: docker/setup-buildx-action@v3

      - name: Login to Container Registry
        uses: docker/login-action@v3
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}

      - name: Extract metadata
        id: meta
        uses: docker/metadata-action@v5
        with:
          images: ghcr.io/${{ github.repository }}
          tags: |
            type=sha
            type=semver,pattern={{version}}
            type=raw,value=latest,enable={{is_default_branch}}

      - name: Build and push
        uses: docker/build-push-action@v5
        with:
          context: .
          push: true
          tags: ${{ steps.meta.outputs.tags }}
          cache-from: type=gha
          cache-to: type=gha,mode=max
```

## Required GitHub Secrets

```
SECRET NAME           PURPOSE                                      USED BY
─────────────        ───────                                      ───────
SP_CERT_B64           Base64-encoded PFX certificate               SPFx deploy
APP_ID                Azure AD App Registration Client ID          SPFx deploy
TENANT_ID             Azure AD Tenant ID                           SPFx deploy
APP_CATALOG_URL       SharePoint App Catalog URL                   SPFx deploy
ANTHROPIC_API_KEY     Claude API key for AI insights               Pages build
VERCEL_TOKEN          Vercel deployment token                      Vercel deploy
VERCEL_ORG_ID         Vercel organization ID                       Vercel deploy
VERCEL_PROJECT_ID     Vercel project ID                            Vercel deploy
SLACK_WEBHOOK_URL     Slack incoming webhook for notifications     All deploys
DASHBOARD_URL         Production dashboard URL for health checks   Health check
GITHUB_TOKEN          Auto-provided by Actions                     Pages, Docker
```

## Rollback Strategy

### Artifact-Based Rollback

```yaml
# .github/workflows/rollback.yml
name: Rollback Deployment
on:
  workflow_dispatch:
    inputs:
      artifact_sha:
        description: 'Commit SHA of the artifact to rollback to'
        required: true
      environment:
        description: 'Target environment'
        required: true
        default: 'production'
        type: choice
        options: [production, staging]

jobs:
  rollback:
    runs-on: ubuntu-latest
    environment: ${{ github.event.inputs.environment }}
    steps:
      - name: Download previous artifact
        uses: actions/download-artifact@v4
        with:
          name: sppkg-${{ github.event.inputs.artifact_sha }}
          path: ./sppkg

      - name: Deploy previous version
        run: |
          npm install -g @pnp/cli-microsoft365
          m365 login --authType certificate \
            --certificateFile <(echo "${{ secrets.SP_CERT_B64 }}" | base64 -d) \
            --appId "${{ secrets.APP_ID }}" \
            --tenant "${{ secrets.TENANT_ID }}"
          m365 spo app add --filePath ./sppkg/*.sppkg \
            --appCatalogUrl "${{ secrets.APP_CATALOG_URL }}" --overwrite
          m365 spo app deploy --name kpi-dashboard.sppkg \
            --appCatalogUrl "${{ secrets.APP_CATALOG_URL }}" --skipFeatureDeployment

      - name: Notify rollback
        uses: slackapi/slack-github-action@v1.25.0
        with:
          payload: |
            {
              "text": "⚠️ Dashboard ROLLBACK executed\nRolled back to: ${{ github.event.inputs.artifact_sha }}\nEnvironment: ${{ github.event.inputs.environment }}\nBy: ${{ github.actor }}"
            }
        env:
          SLACK_WEBHOOK_URL: ${{ secrets.SLACK_WEBHOOK_URL }}
```

## Health Check Script

```javascript
// scripts/health-check.js
const HEALTH_CHECKS = [
  { name: 'Dashboard HTML', url: process.env.DASHBOARD_URL, expect: 200 },
  { name: 'KPI API', url: `${process.env.DASHBOARD_URL}/api/kpis.json`, expect: 200 },
  { name: 'Performance API', url: `${process.env.DASHBOARD_URL}/api/performance.json`, expect: 200 },
];

async function runHealthChecks() {
  const results = [];
  for (const check of HEALTH_CHECKS) {
    try {
      const response = await fetch(check.url, { method: 'GET', signal: AbortSignal.timeout(10000) });
      const passed = response.status === check.expect;
      results.push({ ...check, status: response.status, passed });
      console.log(`${passed ? '✅' : '❌'} ${check.name}: HTTP ${response.status}`);
    } catch (err) {
      results.push({ ...check, status: 'ERROR', passed: false, error: err.message });
      console.log(`❌ ${check.name}: ${err.message}`);
    }
  }

  const allPassed = results.every(r => r.passed);
  console.log(`\n${allPassed ? '✅ All checks passed' : '❌ Some checks failed'}`);
  process.exit(allPassed ? 0 : 1);
}

runHealthChecks();
```

## Deployment Notifications

### Teams Adaptive Card

```javascript
function buildDeployNotification(status, commit, actor, environment, url) {
  return {
    type: 'message',
    attachments: [{
      contentType: 'application/vnd.microsoft.card.adaptive',
      content: {
        type: 'AdaptiveCard', version: '1.4',
        body: [
          { type: 'TextBlock', text: `${status === 'success' ? '✅' : '❌'} Dashboard Deployment`,
            size: 'Large', weight: 'Bolder',
            color: status === 'success' ? 'Good' : 'Attention' },
          { type: 'FactSet', facts: [
            { title: 'Environment', value: environment },
            { title: 'Commit', value: commit.substring(0, 7) },
            { title: 'Deployed By', value: actor },
            { title: 'Status', value: status },
            { title: 'Time', value: new Date().toLocaleString() },
          ]},
        ],
        actions: [
          { type: 'Action.OpenUrl', title: 'View Dashboard', url },
        ],
      },
    }],
  };
}
```

## Branch-Based Deploy Rules

```yaml
# Complete branch strategy
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with: { node-version: '20', cache: 'npm' }
      - run: npm ci
      - run: npm test -- --ci --coverage
      - run: npm run lint

  deploy-preview:
    needs: test
    if: github.event_name == 'pull_request'
    runs-on: ubuntu-latest
    steps:
      - run: echo "Deploy preview for PR #${{ github.event.pull_request.number }}"
      # Vercel/Netlify auto-deploy previews for PRs

  deploy-staging:
    needs: test
    if: github.ref == 'refs/heads/staging'
    runs-on: ubuntu-latest
    environment: staging
    steps:
      - run: echo "Deploying to staging..."

  deploy-production:
    needs: test
    if: github.ref == 'refs/heads/main' && github.event_name == 'push'
    runs-on: ubuntu-latest
    environment: production
    steps:
      - run: echo "Deploying to production..."
```

## NPM Cache Optimization

```yaml
# Reduces install time from ~2min to ~20sec on cache hit
- uses: actions/setup-node@v4
  with:
    node-version: '20'
    cache: 'npm'
    cache-dependency-path: package-lock.json

# For monorepos or multiple lock files
- uses: actions/cache@v4
  with:
    path: |
      ~/.npm
      node_modules
    key: ${{ runner.os }}-node-${{ hashFiles('**/package-lock.json') }}
    restore-keys: |
      ${{ runner.os }}-node-
```

## Integration

| Agent | Relationship |
|-------|-------------|
| **Dashboard Deployer** | Full deployment orchestration |
| **SENTINEL** (Testing) | Test gates before deployment |
| **alert-system** | Deployment status notifications |
| **auth-guard** | M365 certificate-based auth for SPFx |

## Standards

- Deploy to production only from the `main` branch; PRs run tests only
- Always upload `.sppkg` as a build artifact with commit SHA for rollback
- Never hardcode tenant URLs, app IDs, or certificates in workflow YAML
- Run `npm test` before deploy; fail the deploy job if tests fail
- Use `--overwrite` when uploading to App Catalog to replace existing package
- Health check after every production deployment with 30-second wait
- Artifact retention: 30 days minimum for rollback capability
- Use GitHub Environments for deployment approval gates on production
- Deployment notifications to Slack/Teams for every production deploy
- Docker images tagged with both SHA and `latest` for production builds

## Anti-Patterns

1. **No test gate** — never deploy without passing tests first
2. **Hardcoded secrets** — use GitHub Secrets or environment variables
3. **No rollback plan** — always keep artifacts for previous versions
4. **Missing health checks** — verify deployment succeeded before notifying
5. **No concurrency control** — use `concurrency` group to prevent parallel deploys
6. **Deploying from feature branches** — only `main` deploys to production
7. **No deployment notifications** — team must know when deploys happen
8. **Missing cache** — npm ci without cache wastes 2+ minutes per build
