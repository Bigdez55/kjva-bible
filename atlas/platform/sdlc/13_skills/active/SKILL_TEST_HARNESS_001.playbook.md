# test-harness

<!-- Source: migrated from ~/.claude/skills/test-harness/SKILL.md on 2026-05-26 -->
<!-- Runtime alias: test-harness -->

**Summary.** Comprehensive test harness for KPI dashboards: Jest/Vitest configuration with ts-jest and moduleNameMapper, Playwright E2E flows, React Testing Library patterns, visual regression with Chromatic/Percy, contract compliance custom matchers, KPI test fixtures (penalty/on-target/incentive scenarios), PnPjs mocking, snapshot strategies, coverage thresholds, CI test gates, cross-browser testing, and accessibility audit automation. Trigger on: 'test harness', 'jest config', 'vitest', 'test setup', 'mock data', 'test fixtures', 'E2E test', 'Playwright', 'visual regression', 'test coverage', 'contract test'.

# Comprehensive Test Harness

## Purpose & Scope

Sets up complete testing infrastructure for KPI dashboards: unit tests, integration tests, E2E flows, visual regression, accessibility audits, and CI test gates. Covers Jest/Vitest configuration, React Testing Library patterns, Playwright browser automation, contract compliance assertions, and performance regression detection.

## When to Trigger

- Setting up Jest or Vitest in a new SPFx or React dashboard project
- CSS module imports causing "cannot find module" errors in tests
- Writing tests that need realistic KPI data without calling real APIs
- Adding custom Jest matchers for contract-specific assertions
- Creating E2E tests for dashboard user flows
- Setting up visual regression baselines
- Configuring CI test gates with coverage thresholds
- Testing chart components without opaque snapshot bloat
- Deciding between unit, integration, and E2E tests for a feature

## When NOT to Trigger

- Chart configuration → **chart-builder** skill
- Data processing logic → **data-pipeline** skill
- Performance profiling → **perf-profiler** skill
- Full test architecture → **SENTINEL** agent

## Testing Strategy Pyramid

```
        ╱╲
       ╱E2E╲          5-10 critical user flows
      ╱──────╲
     ╱ Visual  ╲       Component screenshot baselines
    ╱───────────╲
   ╱ Integration ╲     Service + component integration
  ╱────────────────╲
 ╱   Unit Tests     ╲   Pure functions, utilities, hooks
╱════════════════════╲
```

| Layer | Tool | Count | Speed |
|-------|------|-------|-------|
| Unit | Jest / Vitest | 200+ | < 30s |
| Integration | RTL + MSW | 50-100 | < 60s |
| Visual | Chromatic / Percy | 20-40 | < 5min |
| E2E | Playwright | 5-10 | < 3min |
| Accessibility | axe-core | All pages | < 30s |

## Jest Configuration (SPFx)

```javascript
// jest.config.js
module.exports = {
  preset: 'ts-jest',
  testEnvironment: 'jsdom',
  setupFilesAfterSetup: ['./src/test-setup.ts'],
  moduleNameMapper: {
    '\\.(css|scss|sass)$': '<rootDir>/__mocks__/styleMock.js',
    '\\.(png|jpg|svg|gif)$': '<rootDir>/__mocks__/fileMock.js',
    '@components/(.*)': '<rootDir>/src/webparts/kpiDashboard/components/$1',
    '@services/(.*)': '<rootDir>/src/webparts/kpiDashboard/services/$1',
    '@utils/(.*)': '<rootDir>/src/webparts/kpiDashboard/utils/$1',
    '@microsoft/sp-core-library': '<rootDir>/__mocks__/sp-core-library.js',
    '@microsoft/sp-http': '<rootDir>/__mocks__/sp-http.js',
  },
  transform: {
    '^.+\\.tsx?$': ['ts-jest', { tsconfig: 'tsconfig.json' }],
  },
  collectCoverageFrom: [
    'src/**/*.{ts,tsx}',
    '!src/**/*.d.ts',
    '!src/index.ts',
    '!src/**/__mocks__/**',
    '!src/**/__fixtures__/**',
  ],
  coverageThresholds: {
    global: {
      branches: 80,
      functions: 85,
      lines: 85,
      statements: 85,
    },
    './src/utils/kpi-calculator.ts': {
      branches: 100,
      functions: 100,
      lines: 100,
      statements: 100,
    },
  },
  testPathIgnorePatterns: ['/node_modules/', '/dist/', '/lib/'],
};
```

## Vitest Configuration (Vite Projects)

```typescript
// vitest.config.ts
import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: ['./src/test-setup.ts'],
    css: { modules: { classNameStrategy: 'non-scoped' } },
    coverage: {
      provider: 'v8',
      reporter: ['text', 'html', 'lcov'],
      thresholds: { branches: 80, functions: 85, lines: 85, statements: 85 },
      exclude: ['**/__mocks__/**', '**/__fixtures__/**', '**/*.d.ts'],
    },
    include: ['src/**/*.{test,spec}.{ts,tsx}'],
  },
  resolve: {
    alias: {
      '@': '/src',
      '@components': '/src/components',
      '@utils': '/src/utils',
      '@services': '/src/services',
    },
  },
});
```

## Mock Files

```javascript
// __mocks__/styleMock.js
module.exports = {};

// __mocks__/fileMock.js
module.exports = 'test-file-stub';

// __mocks__/sp-core-library.js
module.exports = {
  Log: { info: jest.fn(), warn: jest.fn(), error: jest.fn() },
  Environment: { type: 3 },
  EnvironmentType: { Local: 1, SharePoint: 3, ClassicSharePoint: 4 },
};

// __mocks__/sp-http.js
module.exports = {
  SPHttpClient: { configurations: { v1: {} } },
  HttpClient: { configurations: { v1: {} } },
};
```

## KPI Test Fixtures

```typescript
// src/__fixtures__/kpis.ts
import type { IKpiData } from '../types';

export const KPI_FIXTURES = {
  /** All KPIs in penalty zone — worst case */
  allPenalties: {
    pph: 1.38,
    otp: 90.3,
    lateTripsPercent: 8.2,
    excessivelyLatePercent: 0.35,
    missedTripsPercent: 0.19,
    holdTimePercent: 92,
    complaintsPerThousand: 1.4,
    firstPickupOTP: 93,
    isComplete: true,
    reportMonth: '2025-07',
    lastUpdated: '2025-07-31T23:59:59Z',
  },

  /** All KPIs meeting target — no penalties, no incentives */
  allOnTarget: {
    pph: 1.55,
    otp: 91.5,
    lateTripsPercent: 3.2,
    excessivelyLatePercent: 0.15,
    missedTripsPercent: 0.10,
    holdTimePercent: 96,
    complaintsPerThousand: 0.8,
    firstPickupOTP: 96,
    isComplete: true,
    reportMonth: '2025-08',
    lastUpdated: '2025-08-31T23:59:59Z',
  },

  /** All KPIs qualifying for incentives — best case */
  allIncentives: {
    pph: 1.82,
    otp: 94.5,
    lateTripsPercent: 0,
    excessivelyLatePercent: 0.05,
    missedTripsPercent: 0.05,
    holdTimePercent: 98,
    complaintsPerThousand: 0.5,
    firstPickupOTP: 97,
    isComplete: true,
    reportMonth: '2025-09',
    lastUpdated: '2025-09-30T23:59:59Z',
  },

  /** Edge case: PPH just at penalty threshold boundary */
  pphBoundary: {
    pph: 1.30, // Exactly 0.20 below 1.5 — triggers penalty
    otp: 90.0,
    lateTripsPercent: 5.0, // Exactly at threshold — no penalty
    excessivelyLatePercent: 0.25, // Exactly at threshold — no penalty
    missedTripsPercent: 0.15,
    holdTimePercent: 95,
    complaintsPerThousand: 1.0,
    firstPickupOTP: 95,
    isComplete: true,
    reportMonth: '2025-10',
    lastUpdated: '2025-10-31T23:59:59Z',
  },

  /** Incomplete month — should not be used for penalty calculations */
  incompleteMonth: {
    pph: 1.45,
    otp: 89.0,
    lateTripsPercent: 6.0,
    excessivelyLatePercent: 0.30,
    missedTripsPercent: 0.20,
    holdTimePercent: 94,
    complaintsPerThousand: 1.2,
    firstPickupOTP: 94,
    isComplete: false,
    reportMonth: '2025-11',
    lastUpdated: '2025-11-15T12:00:00Z',
  },
} as const satisfies Record<string, IKpiData>;

/** Historical data array for trend tests (12 months) */
export const KPI_HISTORY: IKpiData[] = [
  { ...KPI_FIXTURES.allPenalties, reportMonth: '2025-01' },
  { ...KPI_FIXTURES.allPenalties, reportMonth: '2025-02', pph: 1.40, lateTripsPercent: 7.8 },
  { ...KPI_FIXTURES.allPenalties, reportMonth: '2025-03', pph: 1.42, lateTripsPercent: 7.2 },
  { ...KPI_FIXTURES.allOnTarget, reportMonth: '2025-04' },
  { ...KPI_FIXTURES.allOnTarget, reportMonth: '2025-05', pph: 1.58 },
  { ...KPI_FIXTURES.allOnTarget, reportMonth: '2025-06', pph: 1.60, otp: 92.0 },
  { ...KPI_FIXTURES.allPenalties, reportMonth: '2025-07' },
  { ...KPI_FIXTURES.allOnTarget, reportMonth: '2025-08' },
  { ...KPI_FIXTURES.allIncentives, reportMonth: '2025-09' },
  { ...KPI_FIXTURES.pphBoundary, reportMonth: '2025-10' },
  { ...KPI_FIXTURES.allOnTarget, reportMonth: '2025-11', otp: 93.5, pph: 1.65 },
  { ...KPI_FIXTURES.allIncentives, reportMonth: '2025-12' },
];
```

## Custom Jest Matchers for Contract Compliance

```typescript
// src/test-setup.ts
import '@testing-library/jest-dom';

interface KpiResult {
  penalty: number;
  incentive: number;
  status: 'CRITICAL' | 'WARNING' | 'ON_TARGET' | 'INCENTIVE';
}

declare global {
  namespace jest {
    interface Matchers<R> {
      toHavePenalty(expected: number): R;
      toHaveIncentive(expected: number): R;
      toHaveStatus(expected: string): R;
      toBeWithinContractThreshold(threshold: number, direction: 'above' | 'below'): R;
    }
  }
}

expect.extend({
  toHavePenalty(received: KpiResult, expectedPenalty: number) {
    const pass = received.penalty === expectedPenalty;
    return {
      pass,
      message: () =>
        `Expected penalty ${pass ? 'not ' : ''}to be $${expectedPenalty}, got $${received.penalty}`,
    };
  },

  toHaveIncentive(received: KpiResult, expectedIncentive: number) {
    const pass = received.incentive === expectedIncentive;
    return {
      pass,
      message: () =>
        `Expected incentive ${pass ? 'not ' : ''}to be $${expectedIncentive}, got $${received.incentive}`,
    };
  },

  toHaveStatus(received: KpiResult, expectedStatus: string) {
    const pass = received.status === expectedStatus;
    return {
      pass,
      message: () =>
        `Expected status ${pass ? 'not ' : ''}to be "${expectedStatus}", got "${received.status}"`,
    };
  },

  toBeWithinContractThreshold(received: number, threshold: number, direction: 'above' | 'below') {
    const pass = direction === 'above' ? received <= threshold : received >= threshold;
    return {
      pass,
      message: () =>
        `Expected ${received} to be ${direction === 'above' ? 'at or below' : 'at or above'} ${threshold}`,
    };
  },
});
```

## Contract Compliance Test Examples

```typescript
// src/utils/__tests__/kpi-calculator.test.ts
import { calculatePenalties, calculateIncentives } from '../kpi-calculator';
import { KPI_FIXTURES } from '../../__fixtures__/kpis';

describe('Contract Penalty Calculations', () => {
  describe('PPH Penalties', () => {
    test('no penalty when less than 0.20 below 1.5 standard', () => {
      // PPH 1.38 = only 0.12 below 1.5 → no penalty
      const result = calculatePenalties(KPI_FIXTURES.allPenalties);
      expect(result.pph).toHavePenalty(0);
    });

    test('$5,000 penalty when 0.20+ below 1.5 standard', () => {
      const result = calculatePenalties(KPI_FIXTURES.pphBoundary);
      expect(result.pph).toHavePenalty(5000);
      expect(result.pph).toHaveStatus('CRITICAL');
    });

    test('incentive requires both PPH >= 1.7 AND OTP >= 93%', () => {
      const result = calculateIncentives(KPI_FIXTURES.allIncentives);
      expect(result.pph).toHaveIncentive(2500); // 1.82 is 0.12 above 1.7 → 1 increment
    });

    test('no incentive when PPH >= 1.7 but OTP < 93%', () => {
      const data = { ...KPI_FIXTURES.allIncentives, otp: 92.0 };
      const result = calculateIncentives(data);
      expect(result.pph).toHaveIncentive(0);
    });
  });

  describe('Late Trips Penalties', () => {
    test('$10,000 penalty when above 5%', () => {
      const result = calculatePenalties(KPI_FIXTURES.allPenalties);
      expect(result.lateTrips).toHavePenalty(10000);
    });

    test('$5,000 incentive when exactly 0%', () => {
      const result = calculateIncentives(KPI_FIXTURES.allIncentives);
      expect(result.lateTrips).toHaveIncentive(5000);
    });

    test('no penalty at exactly 5% (threshold is >5%, not >=5%)', () => {
      const result = calculatePenalties(KPI_FIXTURES.pphBoundary);
      expect(result.lateTrips).toHavePenalty(0);
    });
  });

  describe('Total Penalty Aggregation', () => {
    test('sums all individual penalties correctly', () => {
      const result = calculatePenalties(KPI_FIXTURES.allPenalties);
      // Late: $10K + ExcLate: $5K + HoldTime: $1.2K + Complaints: $400 + Missed: $50
      expect(result.total).toBe(16650);
    });

    test('zero total when all KPIs on target', () => {
      const result = calculatePenalties(KPI_FIXTURES.allOnTarget);
      expect(result.total).toBe(0);
    });
  });
});
```

## Mocking PnPjs in Tests

```typescript
// __mocks__/@pnp/sp.ts
const mockItems = jest.fn().mockResolvedValue([]);
const mockChain = {
  select: jest.fn().mockReturnThis(),
  filter: jest.fn().mockReturnThis(),
  orderBy: jest.fn().mockReturnThis(),
  top: jest.fn().mockReturnThis(),
  then: (resolve: Function) => resolve(mockItems()),
  [Symbol.asyncIterator]: async function* () { yield* await mockItems(); },
};

export const spfi = jest.fn(() => ({
  web: {
    lists: {
      getByTitle: jest.fn(() => ({
        items: mockChain,
      })),
    },
    currentUser: {
      groups: jest.fn().mockResolvedValue([{ Title: 'Site Members' }]),
    },
  },
}));

export const SPFI = jest.fn();

/** Helper to set mock data for tests */
export function __setMockItems(data: any[]) {
  mockItems.mockResolvedValue(data);
}
```

## React Testing Library Patterns

```tsx
// src/components/__tests__/KpiCard.test.tsx
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { KpiCard } from '../KpiCard';

describe('KpiCard', () => {
  test('renders label, value, and target', () => {
    render(<KpiCard label="Late Trips" value={8.2} target={5} unit="%" />);
    expect(screen.getByText('Late Trips')).toBeInTheDocument();
    expect(screen.getByText('8.2%')).toBeInTheDocument();
    expect(screen.getByText('Target: 5%')).toBeInTheDocument();
  });

  test('shows CRITICAL status when in penalty zone', () => {
    render(<KpiCard label="Late Trips" value={8.2} target={5} penalty={10000} />);
    const chip = screen.getByText('CRITICAL');
    expect(chip).toHaveClass('status-critical');
  });

  test('displays penalty amount in card footer', () => {
    render(<KpiCard label="Late Trips" value={8.2} target={5} penalty={10000} />);
    expect(screen.getByText('$10,000 penalty')).toBeInTheDocument();
  });

  test('accordion expands details on click', async () => {
    const user = userEvent.setup();
    render(<KpiCard label="PPH" value={1.38} target={1.5} details="Contract threshold is 0.20 below standard" />);
    const toggle = screen.getByRole('button', { name: /details/i });
    await user.click(toggle);
    expect(screen.getByText(/Contract threshold/)).toBeVisible();
  });

  test('meets accessibility requirements', () => {
    const { container } = render(
      <KpiCard label="OTP" value={90.3} target={90} status="on-target" />
    );
    const card = container.firstChild as HTMLElement;
    expect(card).toHaveAttribute('role', 'region');
    expect(card).toHaveAttribute('aria-label', 'OTP');
  });
});
```

## Snapshot Testing Strategy

```typescript
// USE snapshots for: static layout, status chips, simple presentational components
test('KpiCard renders correctly for CRITICAL status', () => {
  const { container } = render(
    <KpiCard label="Late Trips" value={8.2} target={5} penalty={10000} />
  );
  expect(container).toMatchSnapshot();
});

// AVOID snapshots for: charts, dynamic timestamps, random IDs, large DOM trees
// For charts: assert on semantic attributes instead
test('chart has accessible label', () => {
  render(<TrendChart data={mockData} kpiKey="otp" />);
  expect(screen.getByRole('img', { name: /OTP trend/i })).toBeInTheDocument();
});

// INLINE snapshots for small, stable output
test('formatPenalty returns correct string', () => {
  expect(formatPenalty(10000)).toMatchInlineSnapshot(`"$10,000"`);
  expect(formatPenalty(0)).toMatchInlineSnapshot(`"$0"`);
});
```

## Playwright E2E Tests

```typescript
// e2e/dashboard.spec.ts
import { test, expect } from '@playwright/test';

test.describe('KPI Dashboard', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    await page.waitForSelector('[data-testid="kpi-grid"]');
  });

  test('displays all KPI cards on load', async ({ page }) => {
    const cards = page.locator('[data-testid="kpi-card"]');
    await expect(cards).toHaveCount(8); // PPH, OTP, Late, ExcLate, Missed, Hold, Complaints, FirstPickup
  });

  test('penalty banner shows total amount', async ({ page }) => {
    const banner = page.locator('[data-testid="penalty-banner"]');
    await expect(banner).toContainText('$16,650');
  });

  test('filter by month updates all cards', async ({ page }) => {
    await page.selectOption('[data-testid="month-filter"]', '2025-08');
    await expect(page.locator('[data-testid="kpi-card-pph"] .value')).toContainText('1.55');
  });

  test('export to PDF triggers download', async ({ page }) => {
    const downloadPromise = page.waitForEvent('download');
    await page.click('[data-testid="export-pdf"]');
    const download = await downloadPromise;
    expect(download.suggestedFilename()).toContain('Transdev_KPI');
    expect(download.suggestedFilename()).toContain('.pdf');
  });

  test('chart renders without console errors', async ({ page }) => {
    const errors: string[] = [];
    page.on('console', msg => { if (msg.type() === 'error') errors.push(msg.text()); });
    await page.goto('/');
    await page.waitForTimeout(2000);
    expect(errors).toHaveLength(0);
  });
});
```

## Playwright Configuration

```typescript
// playwright.config.ts
import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: './e2e',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 1 : undefined,
  reporter: process.env.CI ? 'github' : 'html',
  use: {
    baseURL: 'http://localhost:3000',
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
  },
  projects: [
    { name: 'chromium', use: { ...devices['Desktop Chrome'] } },
    { name: 'firefox', use: { ...devices['Desktop Firefox'] } },
    { name: 'webkit', use: { ...devices['Desktop Safari'] } },
    { name: 'Mobile Chrome', use: { ...devices['Pixel 5'] } },
    { name: 'Mobile Safari', use: { ...devices['iPhone 13'] } },
  ],
  webServer: {
    command: 'npm run preview',
    port: 3000,
    reuseExistingServer: !process.env.CI,
  },
});
```

## Visual Regression Testing

```typescript
// visual/kpi-card.visual.test.tsx
import { test, expect } from '@playwright/test';

test.describe('Visual Regression', () => {
  test('KPI grid matches baseline', async ({ page }) => {
    await page.goto('/');
    await page.waitForSelector('[data-testid="kpi-grid"]');
    await expect(page.locator('[data-testid="kpi-grid"]')).toHaveScreenshot('kpi-grid.png', {
      maxDiffPixelRatio: 0.01,
    });
  });

  test('penalty banner critical state', async ({ page }) => {
    await page.goto('/?scenario=all-penalties');
    await expect(page.locator('[data-testid="penalty-banner"]')).toHaveScreenshot(
      'penalty-banner-critical.png'
    );
  });

  test('dark mode renders correctly', async ({ page }) => {
    await page.emulateMedia({ colorScheme: 'dark' });
    await page.goto('/');
    await expect(page).toHaveScreenshot('dashboard-dark.png', { fullPage: true });
  });
});
```

## Accessibility Testing with axe-core

```typescript
// src/test-utils/a11y.ts
import { axe, toHaveNoViolations } from 'jest-axe';
expect.extend(toHaveNoViolations);

export async function checkA11y(container: HTMLElement) {
  const results = await axe(container, {
    rules: {
      'color-contrast': { enabled: true },
      'link-name': { enabled: true },
      region: { enabled: true },
    },
  });
  expect(results).toHaveNoViolations();
}

// Usage in component tests
test('KpiCard has no accessibility violations', async () => {
  const { container } = render(<KpiCard label="OTP" value={90.3} target={90} />);
  await checkA11y(container);
});
```

## CI Test Gate Configuration

```yaml
# .github/workflows/test.yml
name: Test Suite
on: [push, pull_request]

jobs:
  unit-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with: { node-version: '18', cache: 'npm' }
      - run: npm ci
      - run: npm test -- --coverage --ci
      - name: Check coverage thresholds
        run: npx istanbul check-coverage --branches 80 --functions 85 --lines 85

  e2e-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with: { node-version: '18', cache: 'npm' }
      - run: npm ci
      - run: npx playwright install --with-deps
      - run: npx playwright test
      - uses: actions/upload-artifact@v4
        if: failure()
        with:
          name: playwright-report
          path: playwright-report/
          retention-days: 7

  visual-regression:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with: { node-version: '18', cache: 'npm' }
      - run: npm ci
      - run: npx playwright test --config=visual.config.ts
      - uses: actions/upload-artifact@v4
        if: failure()
        with:
          name: visual-diff
          path: test-results/
```

## MSW (Mock Service Worker) for API Mocking

```typescript
// src/__mocks__/handlers.ts
import { rest } from 'msw';
import { KPI_FIXTURES } from '../__fixtures__/kpis';

export const handlers = [
  rest.get('/api/kpis', (req, res, ctx) => {
    const month = req.url.searchParams.get('month');
    const fixture = month === '2025-09' ? KPI_FIXTURES.allIncentives : KPI_FIXTURES.allPenalties;
    return res(ctx.json(fixture));
  }),

  rest.get('/api/kpis/history', (req, res, ctx) => {
    return res(ctx.json(KPI_HISTORY));
  }),

  rest.post('/api/manual-data', (req, res, ctx) => {
    return res(ctx.status(200), ctx.json({ success: true }));
  }),
];

// src/__mocks__/server.ts
import { setupServer } from 'msw/node';
import { handlers } from './handlers';
export const server = setupServer(...handlers);

// src/test-setup.ts (add to existing)
import { server } from './__mocks__/server';
beforeAll(() => server.listen({ onUnhandledRequest: 'error' }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());
```

## Test Utilities

```tsx
// src/test-utils/render.tsx
import { render, RenderOptions } from '@testing-library/react';
import { ThemeProvider } from '../contexts/ThemeContext';
import { KpiProvider } from '../contexts/KpiContext';

function AllProviders({ children }: { children: React.ReactNode }) {
  return (
    <ThemeProvider>
      <KpiProvider>
        {children}
      </KpiProvider>
    </ThemeProvider>
  );
}

export function renderWithProviders(ui: React.ReactElement, options?: RenderOptions) {
  return render(ui, { wrapper: AllProviders, ...options });
}

export { screen, within, waitFor } from '@testing-library/react';
export { default as userEvent } from '@testing-library/user-event';
```

## Integration

| Agent | Relationship |
|-------|-------------|
| **SENTINEL** (Testing) | Full test architecture and CI gate strategy |
| **BEACON** (Accessibility) | axe-core audit rules and WCAG compliance |
| **TURBO** (Performance) | Performance regression detection in CI |
| **All framework agents** | Framework-specific testing patterns |

## Standards

- `moduleNameMapper` must map all CSS/SCSS/image imports to mocks or tests will fail
- Never commit large snapshot files for chart components — they change frequently and add noise
- KPI fixtures must cover: all penalties, all on-target, all incentives, boundary cases, incomplete data
- Custom matchers make contract compliance tests read like specifications — use them
- Mock PnPjs at the module level in `__mocks__` to avoid per-test setup boilerplate
- Every utility in `utils/` and `services/` must have a test file — these contain critical business logic
- E2E tests run against `npm run preview` — never against dev server with HMR
- Visual regression tolerance: `maxDiffPixelRatio: 0.01` (1% pixel difference)
- Coverage thresholds: 80% branches, 85% functions/lines/statements globally; 100% for `kpi-calculator`

## Anti-Patterns

1. **Testing implementation details** — test behavior (what the user sees), not internal state
2. **Large snapshot files** — use inline snapshots for small output, assertion for large
3. **Mocking everything** — only mock external boundaries (APIs, SharePoint), not internal utils
4. **No test fixtures** — hardcoding values in every test leads to inconsistency
5. **E2E tests for unit logic** — penalty math should be unit-tested, not browser-tested
6. **Missing error scenarios** — test what happens when API returns 500 or empty data
7. **No CI gates** — tests that don't block deployment provide false confidence
