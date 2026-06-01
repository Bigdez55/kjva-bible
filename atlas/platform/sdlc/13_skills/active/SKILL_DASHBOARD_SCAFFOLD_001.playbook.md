# dashboard-scaffold

<!-- Source: migrated from ~/.claude/skills/dashboard-scaffold/SKILL.md on 2026-05-26 -->
<!-- Runtime alias: dashboard-scaffold -->

**Summary.** Universal dashboard scaffolding skill: generates complete project structures for React/Next.js, Vue/Nuxt, Angular, Svelte/SvelteKit, Python (Dash/Streamlit), and Vanilla JS dashboards. Includes build configs, linting, testing, CI/CD, environment management, and folder conventions. Trigger on: 'scaffold', 'new dashboard', 'project setup', 'folder structure', 'project structure', 'initialize project', 'create dashboard'.

# Dashboard Scaffolding Patterns — Universal Project Generator

## Purpose & Scope

This skill generates production-ready dashboard project structures for any supported framework. It handles everything from directory layout and build configuration to linting, testing, CI/CD, and deployment setup. The output is a complete, immediately-buildable project skeleton that follows the conventions of whichever framework is selected — not a generic template with framework-specific gaps.

Every scaffold includes: TypeScript configuration, linting/formatting, test infrastructure, CI pipeline, environment variable management, and the KPI data interface that is the core data contract for all paratransit dashboards.

## When to Trigger

- User says "scaffold", "new dashboard", "project setup", "folder structure", "initialize project", "create dashboard", "start a new project"
- User wants to start a KPI dashboard from scratch in any framework
- User is migrating an existing dashboard to a new framework
- User needs to add a new web part to an existing SPFx solution
- User asks for recommended project structure or folder conventions

## When NOT to Trigger

- User is working within an already-scaffolded project (delegate to framework-specific APEX agent)
- User needs data processing logic only (delegate to **data-pipeline** skill)
- User needs deployment only (delegate to **deploy-pipeline** skill)
- User is asking about chart configuration (delegate to **chart-builder** skill)

## Supported Frameworks

| Framework | Build Tool | Test Runner | CSS | Primary APEX Agent |
|-----------|-----------|-------------|-----|-------------------|
| React 18+ / Next.js 14+ | Vite / Next.js | Vitest | Tailwind + shadcn/ui | PRISM |
| Vue 3 / Nuxt 3 | Vite / Nuxt | Vitest | Tailwind / Vuetify | MOSAIC |
| Angular 17+ | Angular CLI | Jest / Karma | Angular Material / Tailwind | FORTRESS |
| SvelteKit / Svelte 5 | Vite / SvelteKit | Vitest / Playwright | Tailwind | VELOCITY |
| Python (Dash / Streamlit) | pip / poetry | pytest | Dash Bootstrap | JUPYTER |
| Vanilla JS (Static HTML) | esbuild / Vite | Jest | CSS custom properties | — |
| SPFx (SharePoint) | Gulp + Webpack | Jest | SCSS Modules | PRISM |

## Framework A: React / Next.js 14+

### Directory Structure

```
kpi-dashboard/
├── public/
│   ├── favicon.ico
│   └── assets/
│       └── logo.svg
├── src/
│   ├── app/                          # Next.js App Router
│   │   ├── layout.tsx                # Root layout with providers
│   │   ├── page.tsx                  # Dashboard home
│   │   ├── loading.tsx               # Suspense fallback
│   │   ├── error.tsx                 # Error boundary
│   │   ├── api/
│   │   │   └── kpis/
│   │   │       └── route.ts          # API route for KPI data
│   │   └── reports/
│   │       └── page.tsx              # Historical reports page
│   ├── components/
│   │   ├── ui/                       # shadcn/ui primitives
│   │   │   ├── card.tsx
│   │   │   ├── badge.tsx
│   │   │   └── button.tsx
│   │   ├── dashboard/
│   │   │   ├── KpiCard.tsx
│   │   │   ├── KpiGrid.tsx
│   │   │   ├── PenaltySummary.tsx
│   │   │   └── HealthScore.tsx
│   │   ├── charts/
│   │   │   ├── TrendChart.tsx
│   │   │   ├── GaugeChart.tsx
│   │   │   └── SparklineChart.tsx
│   │   └── layout/
│   │       ├── Header.tsx
│   │       ├── Sidebar.tsx
│   │       └── Footer.tsx
│   ├── hooks/
│   │   ├── useKpiData.ts
│   │   ├── useAlerts.ts
│   │   └── useTheme.ts
│   ├── lib/
│   │   ├── kpi-calculator.ts         # Contract penalty/incentive engine
│   │   ├── formatters.ts             # Number, currency, percentage formatters
│   │   └── api-client.ts             # Fetch wrapper with error handling
│   ├── types/
│   │   ├── kpi.ts                    # IKpiData, IKpiStatus interfaces
│   │   └── contract.ts              # Contract threshold types
│   ├── stores/
│   │   └── dashboard-store.ts        # Zustand store
│   └── styles/
│       ├── globals.css               # Tailwind imports + custom properties
│       └── tokens.css                # Design tokens
├── tests/
│   ├── unit/
│   │   ├── kpi-calculator.test.ts
│   │   └── formatters.test.ts
│   ├── integration/
│   │   ├── KpiCard.test.tsx
│   │   └── KpiGrid.test.tsx
│   ├── e2e/
│   │   └── dashboard.spec.ts
│   ├── fixtures/
│   │   ├── kpis.json
│   │   └── history.json
│   └── mocks/
│       ├── handlers.ts               # MSW handlers
│       └── server.ts                 # MSW server setup
├── .github/
│   └── workflows/
│       ├── ci.yml                    # Test + lint on push/PR
│       └── deploy.yml                # Deploy on merge to main
├── .env.example
├── .eslintrc.json
├── .prettierrc
├── next.config.js
├── tailwind.config.ts
├── tsconfig.json
├── vitest.config.ts
├── playwright.config.ts
└── package.json
```

### package.json (React/Next.js)

```json
{
  "name": "kpi-dashboard",
  "version": "1.0.0",
  "private": true,
  "scripts": {
    "dev": "next dev",
    "build": "next build",
    "start": "next start",
    "lint": "eslint . --ext .ts,.tsx",
    "format": "prettier --write 'src/**/*.{ts,tsx,css}'",
    "test": "vitest run",
    "test:watch": "vitest",
    "test:coverage": "vitest run --coverage",
    "test:e2e": "playwright test",
    "type-check": "tsc --noEmit"
  },
  "dependencies": {
    "next": "^14.2.0",
    "react": "^18.3.0",
    "react-dom": "^18.3.0",
    "recharts": "^2.12.0",
    "zustand": "^4.5.0",
    "@radix-ui/react-slot": "^1.0.0",
    "class-variance-authority": "^0.7.0",
    "clsx": "^2.1.0",
    "tailwind-merge": "^2.2.0"
  },
  "devDependencies": {
    "@testing-library/react": "^14.2.0",
    "@testing-library/user-event": "^14.5.0",
    "@types/node": "^20.11.0",
    "@types/react": "^18.2.0",
    "eslint": "^8.56.0",
    "eslint-config-next": "^14.2.0",
    "msw": "^2.1.0",
    "playwright": "^1.42.0",
    "prettier": "^3.2.0",
    "tailwindcss": "^3.4.0",
    "typescript": "^5.3.0",
    "vitest": "^1.3.0",
    "@vitest/coverage-v8": "^1.3.0"
  }
}
```

## Framework B: Vue 3 / Nuxt 3

### Directory Structure

```
kpi-dashboard/
├── assets/
│   └── css/
│       ├── main.css
│       └── tokens.css
├── components/
│   ├── dashboard/
│   │   ├── KpiCard.vue
│   │   ├── KpiGrid.vue
│   │   ├── PenaltySummary.vue
│   │   └── HealthScore.vue
│   ├── charts/
│   │   ├── TrendChart.vue
│   │   └── GaugeChart.vue
│   └── layout/
│       ├── AppHeader.vue
│       ├── AppSidebar.vue
│       └── AppFooter.vue
├── composables/
│   ├── useKpiData.ts
│   ├── useAlerts.ts
│   └── useTheme.ts
├── layouts/
│   └── default.vue
├── pages/
│   ├── index.vue                     # Dashboard home
│   └── reports/
│       └── index.vue                 # Historical reports
├── server/
│   └── api/
│       └── kpis.get.ts               # Server API route
├── stores/
│   └── dashboard.ts                  # Pinia store
├── types/
│   └── kpi.ts
├── utils/
│   ├── kpi-calculator.ts
│   └── formatters.ts
├── tests/
│   ├── unit/
│   ├── integration/
│   ├── e2e/
│   └── fixtures/
├── nuxt.config.ts
├── tailwind.config.ts
├── vitest.config.ts
└── package.json
```

## Framework C: SPFx (SharePoint Framework)

### Directory Structure

```
kpi-dashboard-spfx/
├── src/
│   ├── webparts/
│   │   └── kpiDashboard/
│   │       ├── KpiDashboardWebPart.ts       # Entry point with PnPjs init
│   │       ├── KpiDashboardWebPart.manifest.json
│   │       ├── components/
│   │       │   ├── KpiDashboard.tsx         # Root component
│   │       │   ├── KpiDashboard.module.scss
│   │       │   ├── KpiCard/
│   │       │   │   ├── KpiCard.tsx
│   │       │   │   ├── KpiCard.module.scss
│   │       │   │   └── KpiCard.test.tsx
│   │       │   ├── charts/
│   │       │   │   ├── TrendChart.tsx
│   │       │   │   └── GaugeChart.tsx
│   │       │   └── alerts/
│   │       │       └── AlertBanner.tsx
│   │       ├── services/
│   │       │   ├── pnpjs-config.ts          # PnPjs initialization
│   │       │   ├── KpiService.ts            # SharePoint List reads
│   │       │   └── ExcelService.ts          # Excel processing
│   │       ├── hooks/
│   │       │   ├── useKpiData.ts
│   │       │   └── useAlerts.ts
│   │       ├── utils/
│   │       │   ├── kpi-calculator.ts
│   │       │   └── formatters.ts
│   │       └── types/
│   │           └── IKpiData.ts
│   └── mocks/
│       ├── handlers.ts
│       └── fixtures/
│           └── kpis.json
├── config/
│   ├── config.json
│   ├── deploy-azure-storage.json
│   ├── package-solution.json
│   └── serve.json
├── teams/
│   └── manifest.json
├── gulpfile.js
├── tsconfig.json
└── package.json
```

### PnPjs Initialization Pattern

```typescript
// services/pnpjs-config.ts
import { spfi, SPFx } from '@pnp/sp';
import { graphfi, GraphFI, SPFx as GraphSPFx } from '@pnp/graph';
import '@pnp/sp/webs';
import '@pnp/sp/lists';
import '@pnp/sp/items';

let _sp: SPFI | null = null;
let _graph: GraphFI | null = null;

export const getSP = (context?: WebPartContext): SPFI => {
  if (context) _sp = spfi().using(SPFx(context));
  if (!_sp) throw new Error('PnPjs SP not initialized — call getSP(context) in onInit()');
  return _sp;
};

export const getGraph = (context?: WebPartContext): GraphFI => {
  if (context) _graph = graphfi().using(GraphSPFx(context));
  if (!_graph) throw new Error('PnPjs Graph not initialized');
  return _graph;
};
```

## Framework D: Vanilla JS (Static HTML)

### Directory Structure

```
kpi-dashboard/
├── index.html                        # Dashboard HTML
├── src/
│   ├── excel-processor.js            # Excel → JSON
│   ├── kpi-calculator.js             # Contract penalty engine
│   ├── ai-recommendations.js         # AI insights engine
│   └── dashboard-updater.js          # JSON → HTML generator
├── data/
│   ├── td-reports/                   # Source Excel/CSV files
│   ├── processed/
│   │   ├── current-kpis.json
│   │   └── history/
│   └── manual-data.json
├── docs/
│   └── assets/
│       ├── styles.css
│       └── charts.js
├── tests/
│   ├── kpi-calculator.test.js
│   └── excel-processor.test.js
├── .github/
│   └── workflows/
│       ├── ci.yml
│       └── deploy.yml
├── package.json
└── jest.config.js
```

## Core Data Interface (All Frameworks)

```typescript
// types/kpi.ts — Single source of truth for KPI data shape
export interface IKpiData {
  reportMonth: string;                // "2025-07" ISO format
  pph: number;                        // Passengers Per Hour (1.38)
  otp: number;                        // On-Time Performance % (90.3)
  lateTripsPercent: number;           // Late Trips % (8.2)
  excessivelyLatePercent: number;     // Excessively Late % (0.35)
  missedTripsPercent: number;         // Missed Trips % (0.19)
  firstPickupOTP: number | null;      // Manual entry — Operations Team
  holdTimePercent: number | null;     // Manual entry — Call Center Manager
  complaintsPerThousand: number | null; // Manual entry — Customer Service
  isComplete: boolean;                // All 8 KPIs populated
  lastUpdated: string;                // ISO 8601 timestamp
}

export interface IKpiStatus {
  kpi: string;
  value: number;
  target: number;
  status: 'CRITICAL' | 'WARNING' | 'ON_TARGET' | 'INCENTIVE';
  penalty: number;
  incentive: number;
  contractClause: string;
}

export interface IDashboardState {
  currentMonth: IKpiData | null;
  history: IKpiData[];
  healthScore: number;
  totalPenalties: number;
  totalIncentives: number;
  loading: boolean;
  error: string | null;
}
```

## Build Configuration

### Vite Config (React/Vue/Svelte)

```typescript
// vite.config.ts
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'path';

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
      '@components': path.resolve(__dirname, './src/components'),
      '@hooks': path.resolve(__dirname, './src/hooks'),
      '@lib': path.resolve(__dirname, './src/lib'),
      '@types': path.resolve(__dirname, './src/types'),
    },
  },
  build: {
    target: 'es2020',
    sourcemap: true,
    rollupOptions: {
      output: {
        manualChunks: {
          vendor: ['react', 'react-dom'],
          charts: ['recharts'],
        },
      },
    },
  },
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: ['./tests/setup.ts'],
    coverage: {
      provider: 'v8',
      reporter: ['text', 'json', 'html'],
      thresholds: {
        global: { branches: 80, functions: 80, lines: 80 },
        'src/lib/kpi-calculator.*': { branches: 95, functions: 95, lines: 95 },
      },
    },
  },
});
```

### tsconfig.json (Universal)

```json
{
  "compilerOptions": {
    "strict": true,
    "target": "ES2020",
    "module": "ESNext",
    "moduleResolution": "bundler",
    "jsx": "react-jsx",
    "esModuleInterop": true,
    "forceConsistentCasingInImports": true,
    "skipLibCheck": true,
    "baseUrl": ".",
    "paths": {
      "@/*": ["src/*"],
      "@components/*": ["src/components/*"],
      "@hooks/*": ["src/hooks/*"],
      "@lib/*": ["src/lib/*"],
      "@types/*": ["src/types/*"]
    }
  },
  "include": ["src/**/*", "tests/**/*"],
  "exclude": ["node_modules", "dist"]
}
```

## Linting & Formatting

### ESLint Configuration

```json
{
  "root": true,
  "extends": [
    "eslint:recommended",
    "plugin:@typescript-eslint/recommended",
    "plugin:react-hooks/recommended",
    "prettier"
  ],
  "parser": "@typescript-eslint/parser",
  "plugins": ["@typescript-eslint"],
  "rules": {
    "@typescript-eslint/no-unused-vars": ["error", { "argsIgnorePattern": "^_" }],
    "@typescript-eslint/no-explicit-any": "warn",
    "no-console": ["warn", { "allow": ["warn", "error"] }]
  },
  "ignorePatterns": ["dist/", "node_modules/", "*.config.*"]
}
```

### Prettier Configuration

```json
{
  "semi": true,
  "singleQuote": true,
  "tabWidth": 2,
  "trailingComma": "all",
  "printWidth": 100,
  "arrowParens": "always",
  "bracketSpacing": true
}
```

## CI/CD Starter Template

```yaml
# .github/workflows/ci.yml
name: CI
on: [push, pull_request]

jobs:
  quality:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: '20'
          cache: 'npm'
      - run: npm ci
      - run: npm run type-check
      - run: npm run lint
      - run: npm test -- --coverage
      - uses: codecov/codecov-action@v4
        if: always()
```

## Environment Variable Pattern

```bash
# .env.example — committed to repo (no secrets)
NEXT_PUBLIC_API_URL=http://localhost:3000/api
NEXT_PUBLIC_SITE_NAME=Transdev KPI Dashboard
SHAREPOINT_SITE_URL=
TENANT_ID=
CLIENT_ID=

# .env.local — NOT committed (contains secrets)
# Copy .env.example to .env.local and fill in values
```

## Scaffolding Process

1. **Select framework** → determines directory structure, build tool, test runner
2. **Create directory tree** → all folders and placeholder files
3. **Write package.json** → framework-specific dependencies
4. **Write build config** → Vite/Next/Angular CLI/SvelteKit config
5. **Write TypeScript config** → strict mode, path aliases, framework-specific settings
6. **Write linting config** → ESLint + Prettier + framework plugins
7. **Write test infrastructure** → test runner config, MSW setup, fixture files
8. **Write CI pipeline** → GitHub Actions workflow for test + lint + build
9. **Write KPI data interface** → IKpiData.ts as the core data contract
10. **Write environment template** → .env.example with all required variables

## Integration with APEX Agents

| Agent | Relationship |
|-------|-------------|
| **PRISM** (React) | Scaffolds React/Next.js projects, then hands off to PRISM for feature development |
| **MOSAIC** (Vue) | Scaffolds Vue/Nuxt projects, then hands off to MOSAIC |
| **FORTRESS** (Angular) | Scaffolds Angular projects with Material/PrimeNG, then hands off |
| **VELOCITY** (Svelte) | Scaffolds SvelteKit projects, then hands off |
| **SENTINEL** (Testing) | Scaffold creates test infrastructure that SENTINEL extends with comprehensive tests |
| **PRESTIGE** (Design) | Scaffold creates token files that PRESTIGE populates with design system |

## Anti-Patterns

1. **No TypeScript** — always use TypeScript, even for small projects
2. **No test infrastructure** — scaffolds must include test setup from day one
3. **Hardcoded KPI thresholds** — use the contract calculator module, never inline numbers
4. **Missing .env.example** — every environment variable must be documented
5. **No path aliases** — imports like `../../../components/KpiCard` are fragile
6. **Framework mismatch** — don't use React patterns in a Vue scaffold or vice versa
7. **Missing CI pipeline** — every scaffold includes a GitHub Actions workflow
8. **No type definitions** — IKpiData.ts must exist before any feature code is written
